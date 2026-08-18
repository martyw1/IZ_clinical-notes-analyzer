#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# noqa: SIZE_OK — Task 6 requires one shared, auditable release-safety CLI boundary.

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Run: uv run scripts/release_safety.py --help
# 3. Or: python scripts/release_safety.py --help
# ─────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Sequence


ENTRY_KEYS: Final = frozenset({"platform", "profile", "source", "destination", "kind", "cardinality", "introduced_by_task", "generator", "invocation_target", "sha_policy"})
KINDS: Final = frozenset({"static", "generated", "pyinstaller-toc", "symlink"})
SCHEMES: Final = {"pyi": "pyi://", "windows": "windows://", "dmg": "dmg://"}
SAFE_STATIC: Final = {
    "VERSION": "pyi://VERSION",
    "VERSION.json": "pyi://VERSION.json",
    "frontend/dist/index.html": "pyi://frontend/dist/index.html",
    "config/rules/alleva_treatment_plan_completeness_rules.yaml": "pyi://config/rules/alleva_treatment_plan_completeness_rules.yaml",
    "config/checklists/treatment-plan-v1.json": "pyi://config/checklists/treatment-plan-v1.json",
    "README.md": "pyi://docs/README.md",
    "docs/Windows-User-Guide-Version-1.md": "pyi://docs/Windows-User-Guide-Version-1.md",
    "docs/Windows-Deployment-and-Test-Guide-Version-1.md": "pyi://docs/Windows-Deployment-and-Test-Guide-Version-1.md",
    "docs/beta-client-test-run-guide.md": "pyi://docs/beta-client-test-run-guide.md",
    "docs/patient-treatment-plan-handling.md": "pyi://docs/patient-treatment-plan-handling.md",
    "packaging/macos/IZ Clinical Notes Analyzer - Read Me.txt": "dmg://IZ Clinical Notes Analyzer - Read Me.txt",
}
COMMON_REQUIRED: Final = frozenset(value for value in SAFE_STATIC.values() if value != "dmg://IZ Clinical Notes Analyzer - Read Me.txt") | {"pyi://frontend/dist/assets/"}
WINDOWS_REQUIRED: Final = frozenset(
    f"windows://IZ Clinical Notes Analyzer/{relative}"
    for relative in (
        "release-manifest.json", "release-manifest.sha256", "Install-IZ-Clinical-Notes-Analyzer.cmd",
        "Launch-IZ-Clinical-Notes-Analyzer.cmd", "Stop-IZ-Clinical-Notes-Analyzer.cmd",
        "Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd", "Backup-IZ-Clinical-Notes-Analyzer.cmd",
        "Restore-IZ-Clinical-Notes-Analyzer.cmd", "Uninstall-IZ-Clinical-Notes-Analyzer.cmd",
        "Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd", "installer/install-windows-release.ps1",
        "installer/uninstall-windows-release.ps1", "app/runtime/IZClinicalNotesAnalyzer.exe",
        "app/tools/launch-packaged-runtime.cmd", "app/tools/stop-windows-local.ps1",
        "app/tools/backup-local-data.ps1", "app/tools/restore-local-data.ps1",
        "app/tools/collect-diagnostics.ps1", "app/tools/complete-uninstall-local-data.ps1",
    )
)
FORBIDDEN_PARTS: Final = {
    ".git": "repository_metadata", ".codegraph": "repository_metadata", ".codex": "repository_metadata",
    ".github": "repository_metadata", ".agents": "repository_metadata", ".omo": "local_evidence",
    "node_modules": "dependencies", "venv": "environment", ".pytest_cache": "cache", ".mypy_cache": "cache",
    ".ruff_cache": "cache", "__pycache__": "cache", ".tmp": "cache", ".cache": "cache", "reports": "report",
    "test-results": "report", "playwright-report": "report", "htmlcov": "report", "coverage": "report",
    "api-connectivity-reports": "report", "uploads": "upload", "exports": "clinical_export",
    "example-treatment-plans": "clinical_export", "logs": "log", "alleva-api-test-logs": "log",
}
DEVICE_RE: Final = re.compile(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")
HTML_REFERENCE_RE: Final = re.compile(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
JS_REFERENCE_RE: Final = re.compile(r"\bimport\s*(?:\(\s*)?(?:[^'\"\n]*?\sfrom\s*)?['\"]([^'\"]+)['\"]")
CSS_REFERENCE_RE: Final = re.compile(r"url\(\s*['\"]?([^'\")]+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ReleaseSafetyError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class Entry:
    platform: str
    profile: str
    source: str
    destination: str
    kind: str
    cardinality: str
    introduced_by_task: int
    generator: str
    invocation_target: str
    sha_policy: str


@dataclass(frozen=True, slots=True)
class Manifest:
    generators: frozenset[str]
    entries: tuple[Entry, ...]


def _fail(reason: str) -> None:
    raise ReleaseSafetyError(reason)


def _canonical_json(payload: dict[str, str | int | list[dict[str, str | int]]]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _safe_relative(raw: str) -> str:
    value = raw.replace("\\", "/")
    if value.startswith(("\\?", "\\.", "//?", "//.")):
        _fail("device_path")
    if value.startswith("//"):
        _fail("unc_path")
    if re.match(r"^[A-Za-z]:", value):
        _fail("drive_path")
    path = PurePosixPath(value)
    if path.is_absolute():
        _fail("absolute_path")
    if any(part in {"", ".", ".."} for part in path.parts):
        _fail("traversal")
    for part in path.parts:
        if part.endswith((".", " ")):
            _fail("trailing_alias")
        if ":" in part:
            _fail("ads_path")
        if DEVICE_RE.fullmatch(part):
            _fail("device_name")
    return path.as_posix()


def _forbidden_category(relative: str) -> str | None:
    parts = tuple(part.casefold() for part in PurePosixPath(relative).parts)
    for part in parts:
        if part in FORBIDDEN_PARTS:
            return FORBIDDEN_PARTS[part]
        if part.startswith(".venv"):
            return "environment"
    filename = parts[-1] if parts else ""
    if filename == ".env.example":
        return None
    if filename == ".debug-journal.md":
        return "local_evidence"
    if filename == ".env" or filename.startswith(".env.") or filename == ".alleva.local.ps1" or ".local." in filename or ".local-" in filename:
        return "local_config"
    if filename in {"app credentials info.md", "test-allevaapi.ps1"} or any(word in filename for word in ("credential", "secret", "token")):
        return "secret"
    if filename.endswith((".sqlite", ".sqlite3", ".db")):
        return "database"
    if filename.endswith(".izcnabackup"):
        return "backup"
    if filename.endswith(".log"):
        return "log"
    if filename.endswith((".tmp", ".bak", ".pyc")):
        return "cache"
    return None


def _destination_relative(destination: str) -> str:
    for prefix in SCHEMES.values():
        if destination.startswith(prefix):
            value = destination.removeprefix(prefix).rstrip("/")
            return _safe_relative(value)
    _fail("free_form_entry")


def _load_manifest(path: Path) -> Manifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseSafetyError("manifest_unreadable") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "generators", "entries"} or payload.get("schema") != "iz-desktop-package-manifest-v1":
        _fail("manifest_schema")
    raw_generators, raw_entries = payload["generators"], payload["entries"]
    if not isinstance(raw_generators, list) or not all(isinstance(item, str) and item for item in raw_generators) or len(raw_generators) != len(set(raw_generators)) or not isinstance(raw_entries, list):
        _fail("manifest_schema")
    generators = frozenset(raw_generators)
    entries: list[Entry] = []
    destinations: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != ENTRY_KEYS:
            _fail("manifest_schema")
        if not all(isinstance(raw[key], str) for key in ENTRY_KEYS - {"introduced_by_task"}) or not isinstance(raw["introduced_by_task"], int):
            _fail("manifest_schema")
        entry = Entry(**raw)
        if entry.kind not in KINDS or entry.cardinality not in {"one", "one-or-more", "tree"} or entry.sha_policy not in {"sha256", "tree-sha256", "link-only", "link-target-sha256"}:
            _fail("manifest_schema")
        if any(mark in entry.source + entry.destination for mark in "*?[]"):
            _fail("ambiguous_glob")
        relative = _destination_relative(entry.destination)
        alias = unicodedata.normalize("NFC", relative).casefold()
        if alias in destinations:
            _fail("duplicate_destination")
        destinations.add(alias)
        if entry.kind in {"generated", "pyinstaller-toc", "symlink"} and entry.generator not in generators:
            _fail("unknown_generator")
        if entry.kind == "static" and SAFE_STATIC.get(entry.source) != entry.destination:
            _fail("free_form_entry")
        if entry.kind == "generated" and entry.generator == "vite-asset-graph" and (entry.source != "frontend/dist/index.html" or entry.destination != "pyi://frontend/dist/assets/"):
            _fail("free_form_entry")
        entries.append(entry)
    return Manifest(generators=generators, entries=tuple(entries))


def _selected(manifest: Manifest, platform: str, profile: str) -> tuple[Entry, ...]:
    rows = tuple(entry for entry in manifest.entries if entry.platform == platform and entry.profile == profile)
    if not rows:
        _fail("manifest_selection_empty")
    destinations = frozenset(entry.destination for entry in rows)
    if platform == "common" and profile == "pyinstaller" and destinations != COMMON_REQUIRED:
        _fail("common_inventory")
    if platform == "windows" and profile == "release" and destinations != WINDOWS_REQUIRED:
        _fail("windows_inventory")
    if platform == "windows" and profile == "release":
        for entry in rows:
            relative = entry.destination.removeprefix("windows://IZ Clinical Notes Analyzer/")
            if relative == "release-manifest.json":
                expected = ("generated://metadata/release-manifest.json", "generated", "release-manifest", "scripts/release_safety.py:release-manifest")
            elif relative == "release-manifest.sha256":
                expected = ("generated://metadata/release-manifest.sha256", "generated", "release-manifest-digest", "scripts/release_safety.py:release-manifest-digest")
            elif relative == "app/runtime/IZClinicalNotesAnalyzer.exe":
                expected = (f"pyinstaller://{relative}", "pyinstaller-toc", "windows-pyinstaller", f"windows-pyinstaller:{relative}")
            else:
                expected = (f"generated://{relative}", "generated", "windows-release-builder", f"windows-release-builder:{relative}")
            actual = (entry.source, entry.kind, entry.generator, entry.invocation_target)
            if actual != expected or entry.cardinality != "one" or entry.introduced_by_task != 6 or entry.sha_policy != "sha256":
                _fail("free_form_entry")
    return rows


def _regular_source(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    root_resolved = root.resolve(strict=True)
    source = root_resolved.joinpath(*PurePosixPath(safe).parts)
    try:
        status = source.lstat()
    except OSError as exc:
        raise ReleaseSafetyError("missing_source") from exc
    if stat.S_ISLNK(status.st_mode) or getattr(status, "st_reparse_tag", 0) & 0x20000000 or not stat.S_ISREG(status.st_mode) or root_resolved not in source.resolve(strict=True).parents:
        _fail("unsafe_source_type")
    return source


def _regular_tree_source(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    root_resolved = root.resolve(strict=True)
    source = root_resolved.joinpath(*PurePosixPath(safe).parts)
    try:
        status = source.lstat()
    except OSError as exc:
        raise ReleaseSafetyError("missing_source") from exc
    if stat.S_ISLNK(status.st_mode) or getattr(status, "st_reparse_tag", 0) & 0x20000000 or not stat.S_ISDIR(status.st_mode) or root_resolved not in source.resolve(strict=True).parents:
        _fail("unsafe_source_type")
    _inventory_tree(source, allow_symlinks=True)
    return source


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vite_graph(source_root: Path) -> tuple[Path, ...]:
    asset_root = (source_root / "frontend/dist/assets").resolve(strict=True)
    pending = [(source_root / "frontend/dist/index.html").resolve(strict=True)]
    reached: set[Path] = set()
    while pending:
        current = pending.pop()
        try:
            text = current.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ReleaseSafetyError("unresolved_asset") from exc
        reference_pattern = HTML_REFERENCE_RE if current.suffix.lower() == ".html" else JS_REFERENCE_RE if current.suffix.lower() in {".js", ".mjs"} else CSS_REFERENCE_RE
        for match in reference_pattern.finditer(text):
            reference = match.group(1)
            if reference.startswith(("data:", "http:", "https:", "#")):
                continue
            candidate = source_root / "frontend/dist" / reference.lstrip("/") if reference.startswith("/") else current.parent / reference
            candidate = candidate.resolve(strict=False)
            if asset_root != candidate and asset_root not in candidate.parents:
                _fail("asset_escape")
            if not candidate.is_file():
                _fail("unresolved_asset")
            if candidate not in reached:
                reached.add(candidate)
                if candidate.suffix.lower() in {".js", ".mjs", ".css", ".html"}:
                    pending.append(candidate)
    actual = {path.resolve() for path in asset_root.rglob("*") if path.is_file()}
    if actual != reached:
        _fail("unreferenced_asset")
    return tuple(sorted(reached))


def _scan_content(data: bytes) -> None:
    if b"SYNTHETIC_SECRET_CANARY" in data or b"-----BEGIN PRIVATE KEY-----" in data:
        _fail("secret_canary")
    if b"SYNTHETIC_PHI_CANARY" in data:
        _fail("phi_canary")


def _check_aliases(names: Sequence[str]) -> None:
    raw: set[str] = set()
    nfc: set[str] = set()
    folded: set[str] = set()
    for name in names:
        safe = _safe_relative(name.rstrip("/") if name.endswith("/") else name)
        if name in raw:
            _fail("raw_duplicate")
        raw.add(name)
        normalized = unicodedata.normalize("NFC", safe)
        if normalized in nfc:
            _fail("nfc_collision")
        nfc.add(normalized)
        alias = normalized.casefold()
        if alias in folded:
            _fail("case_collision")
        folded.add(alias)


def _inventory_tree(root: Path, *, allow_symlinks: bool = False) -> list[dict[str, str | int]]:
    resolved = root.resolve(strict=True)
    entries: list[dict[str, str | int]] = []
    names: list[str] = []
    stack = [resolved]
    while stack:
        directory = stack.pop()
        for item in os.scandir(directory):
            path = Path(item.path)
            relative = path.relative_to(resolved).as_posix()
            category = _forbidden_category(relative)
            if category is not None:
                _fail(category)
            names.append(relative)
            if item.is_symlink():
                if not allow_symlinks:
                    _fail("unlisted_symlink")
                entries.append({"path": relative, "type": "symlink", "link_target": os.readlink(path)})
            elif item.is_dir(follow_symlinks=False):
                stack.append(path)
            elif item.is_file(follow_symlinks=False):
                data = path.read_bytes()
                _scan_content(data)
                entries.append({"path": relative, "type": "file", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            else:
                _fail("unsafe_file_type")
    _check_aliases(names)
    return sorted(entries, key=lambda row: str(row["path"]))


def _write_report(path: Path | None, payload: dict[str, str | int | list[dict[str, str | int]]]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canonical_json(payload))


def _success(operation: str, entries: list[dict[str, str | int]], report: Path | None = None) -> dict[str, str | int | list[dict[str, str | int]]]:
    payload: dict[str, str | int | list[dict[str, str | int]]] = {"schema": "iz-release-safety-result-v1", "result": "PASS", "operation": operation, "entries": entries}
    _write_report(report, payload)
    return payload


def _stage(args: argparse.Namespace) -> dict[str, str | int | list[dict[str, str | int]]]:
    manifest = _load_manifest(args.manifest)
    rows = _selected(manifest, args.platform, args.profile)
    output = args.output.resolve(strict=False)
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if temp_root != output.parent and temp_root not in output.parents:
        _fail("unsafe_staging_root")
    if output.exists():
        if output.is_symlink() or temp_root not in output.resolve().parents:
            _fail("unsafe_staging_root")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    try:
        for entry in rows:
            destination = output / _destination_relative(entry.destination)
            if entry.kind == "symlink":
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(entry.source, destination)
                continue
            if entry.generator == "vite-asset-graph":
                asset_root = (args.source_root / "frontend/dist/assets").resolve(strict=True)
                for source in _vite_graph(args.source_root):
                    target = output / "frontend/dist/assets" / source.relative_to(asset_root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                continue
            if entry.generator in {"release-manifest", "release-manifest-digest"}:
                continue
            source_root = args.source_root if entry.kind == "static" else args.generated_root
            source_relative = entry.source if entry.kind == "static" else entry.source.split("://", 1)[-1]
            if entry.cardinality == "tree":
                source = _regular_tree_source(source_root, source_relative)
                source_inventory = _inventory_tree(source, allow_symlinks=True)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination, symlinks=True)
                if source_inventory != _inventory_tree(destination, allow_symlinks=True):
                    _fail("copy_hash_mismatch")
                continue
            source = _regular_source(source_root, source_relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if _hash(source) != _hash(destination):
                _fail("copy_hash_mismatch")
        release_manifest = next((entry for entry in rows if entry.generator == "release-manifest"), None)
        release_digest = next((entry for entry in rows if entry.generator == "release-manifest-digest"), None)
        if (release_manifest is None) != (release_digest is None):
            _fail("release_manifest_pair")
        if release_manifest is not None and release_digest is not None:
            payload_entries = _inventory_tree(output)
            manifest_rel, digest_rel = _destination_relative(release_manifest.destination), _destination_relative(release_digest.destination)
            payload_entries = [entry for entry in payload_entries if entry["path"] not in {manifest_rel, digest_rel}]
            archive_root = PurePosixPath(manifest_rel).parent.as_posix() + "/"
            payload_entries = [{**entry, "path": str(entry["path"]).removeprefix(archive_root)} for entry in payload_entries]
            manifest_bytes = _canonical_json({"schema": "iz-release-manifest-v1", "entries": payload_entries})
            manifest_path, digest_path = output / manifest_rel, output / digest_rel
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_bytes(manifest_bytes)
            digest_path.write_bytes(f"{hashlib.sha256(manifest_bytes).hexdigest()}  release-manifest.json\n".encode())
        inventory = _inventory_tree(output, allow_symlinks=args.platform == "macos")
        tree_roots = {_destination_relative(entry.destination) for entry in rows if entry.cardinality == "tree"}
        expected = {_destination_relative(entry.destination) for entry in rows if entry.generator != "vite-asset-graph" and entry.cardinality != "tree"}
        actual = {str(entry["path"]) for entry in inventory}
        graph = (
            {
                f"frontend/dist/assets/{path.relative_to((args.source_root / 'frontend/dist/assets').resolve(strict=True)).as_posix()}"
                for path in _vite_graph(args.source_root)
            }
            if any(entry.generator == "vite-asset-graph" for entry in rows)
            else set()
        )
        missing = (expected | graph) - actual
        unexpected = {path for path in actual - expected - graph if not any(path.startswith(f"{tree}/") for tree in tree_roots)}
        if missing or unexpected or any(not (output / tree).is_dir() for tree in tree_roots):
            _fail("inventory_mismatch")
        if args.zip is not None:
            archive = args.zip.resolve(strict=False)
            if temp_root != archive.parent and temp_root not in archive.parents:
                _fail("unsafe_staging_root")
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(output.rglob("*")):
                    if path.is_file():
                        bundle.write(path, path.relative_to(output).as_posix())
        return _success("stage", inventory, args.report)
    except (OSError, ReleaseSafetyError):
        if output.exists() and temp_root in output.resolve().parents:
            shutil.rmtree(output)
        raise


def _scan_tree(args: argparse.Namespace) -> dict[str, str | int | list[dict[str, str | int]]]:
    entries = _inventory_tree(args.path)
    if args.manifest is not None:
        expected = {_destination_relative(entry.destination) for entry in _selected(_load_manifest(args.manifest), args.platform, args.profile)}
        actual = {str(entry["path"]) for entry in entries}
        if actual != expected:
            _fail("inventory_mismatch")
    return _success("scan-tree", entries, args.report)


def _scan_zip(args: argparse.Namespace) -> dict[str, str | int | list[dict[str, str | int]]]:
    try:
        with zipfile.ZipFile(args.path) as bundle:
            infos = bundle.infolist()
            _check_aliases([info.filename for info in infos])
            entries: list[dict[str, str | int]] = []
            for info in infos:
                if info.is_dir():
                    continue
                category = _forbidden_category(_safe_relative(info.filename))
                if category is not None:
                    _fail(category)
                if stat.S_ISLNK(info.external_attr >> 16):
                    _fail("unlisted_symlink")
                data = bundle.read(info)
                _scan_content(data)
                entries.append({"path": info.filename, "type": "file", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseSafetyError("zip_unreadable") from exc
    if args.manifest is not None:
        rows = _selected(_load_manifest(args.manifest), args.platform, args.profile)
        expected = {_destination_relative(entry.destination) for entry in rows}
        if {str(entry["path"]) for entry in entries} != expected:
            _fail("inventory_mismatch")
    with tempfile.TemporaryDirectory(prefix="iz-release-extract-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(args.path) as bundle:
            for info in bundle.infolist():
                if not info.is_dir():
                    target = root / _safe_relative(info.filename)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(bundle.read(info))
        extracted = _inventory_tree(root)
    if {str(entry["path"]): entry for entry in entries} != {str(entry["path"]): entry for entry in extracted}:
        _fail("zip_extraction_mismatch")
    return _success("scan-zip", entries, args.report)


def _verify_git(args: argparse.Namespace) -> dict[str, str | int | list[dict[str, str | int]]]:
    root = args.repository_root.resolve(strict=True)
    def run(*command: str) -> str:
        completed = subprocess.run(("git", "-C", str(root), *command), check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            _fail("git_metadata_command_failed")
        return completed.stdout
    if Path(run("rev-parse", "--show-toplevel").strip()).resolve() != root:
        _fail("repository_root_mismatch")
    head = run("rev-parse", "HEAD").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_head) or head != args.expected_head:
        _fail("stale_repository_state")
    if run("status", "--porcelain=v1", "--untracked-files=no").strip() and not args.allow_dirty:
        _fail("dirty_worktree")
    repository_inputs = (
        run("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"),
        run("ls-files", "--others", "--exclude-standard", "-z"),
    )
    for raw_paths in repository_inputs:
        for relative in (path for path in raw_paths.split("\0") if path):
            category = _forbidden_category(_safe_relative(relative))
            if category is not None:
                _fail(category)
    return _success("verify-git-source", [], args.report)


def _scan_pyi(args: argparse.Namespace) -> dict[str, str | int | list[dict[str, str | int]]]:
    rows = _selected(_load_manifest(args.manifest), args.platform, args.profile)
    expected = {entry.source.removeprefix("pyinstaller://") for entry in rows if entry.kind == "pyinstaller-toc"}
    if not expected:
        _fail("pyinstaller_inventory")
    viewer = args.viewer
    command = (sys.executable, str(viewer), "-l", "-b", str(args.archive)) if viewer.suffix.lower() == ".py" else (str(viewer), "-l", "-b", str(args.archive))
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        _fail("pyinstaller_viewer_failed")
    names = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]
    _check_aliases(names)
    for name in names:
        category = _forbidden_category(_safe_relative(name))
        if category is not None:
            _fail(category)
    if set(names) != expected:
        _fail("inventory_mismatch")
    entries = [{"path": name, "type": "pyinstaller-toc"} for name in names]
    if args.collect is not None:
        collect_entries = _inventory_tree(args.collect)
        expected_collect = {_destination_relative(entry.destination) for entry in rows if entry.kind not in {"pyinstaller-toc", "symlink"}}
        if {str(entry["path"]) for entry in collect_entries} != expected_collect:
            _fail("inventory_mismatch")
        entries.extend(collect_entries)
    return _success("scan-pyinstaller-toc", entries, args.report)


def _resolve_dmg_link(link: Path, *, listed: bool) -> Path:
    try:
        resolved = link.resolve(strict=True)
    except RuntimeError as exc:
        raise ReleaseSafetyError("symlink_cycle") from exc
    except OSError as exc:
        if not listed:
            raise ReleaseSafetyError("unlisted_symlink") from exc
        raise ReleaseSafetyError("symlink_escape") from exc
    if not listed:
        _fail("unlisted_symlink")
    return resolved


def _scan_dmg(args: argparse.Namespace) -> dict[str, str | int | list[dict[str, str | int]]]:
    root = args.path.resolve(strict=True)
    rows: tuple[Entry, ...] = ()
    allowed: dict[str, Entry] = {}
    if args.manifest is not None:
        rows = _selected(_load_manifest(args.manifest), args.platform, args.profile)
        allowed = {_destination_relative(entry.destination): entry for entry in rows if entry.kind == "symlink"}
    entries = _inventory_tree(root, allow_symlinks=True)
    for row in entries:
        if row["type"] != "symlink":
            continue
        relative, target = str(row["path"]), str(row["link_target"])
        if target == "/Applications":
            if relative != "Applications":
                _fail("applications_symlink_wrong_parent")
            if relative not in allowed and args.manifest is not None:
                _fail("unlisted_symlink")
            continue
        if os.path.isabs(target):
            _fail("absolute_symlink")
        link = root / relative
        resolved = _resolve_dmg_link(link, listed=relative in allowed)
        app = next((root / PurePosixPath(*PurePosixPath(relative).parts[: index + 1]) for index, part in enumerate(PurePosixPath(relative).parts) if part.endswith(".app")), None)
        if app is None or (resolved != app and app not in resolved.parents):
            _fail("symlink_escape")
        row["target_sha256"] = _hash(resolved) if resolved.is_file() else hashlib.sha256("\n".join(sorted(path.relative_to(resolved).as_posix() for path in resolved.rglob("*"))).encode()).hexdigest()
    if rows:
        expected_roots = {PurePosixPath(_destination_relative(entry.destination)).parts[0] for entry in rows}
        if {item.name for item in root.iterdir()} != expected_roots:
            _fail("inventory_mismatch")
        for entry in rows:
            destination = root / _destination_relative(entry.destination)
            tree_is_valid = entry.cardinality == "tree" and destination.is_dir() and not destination.is_symlink()
            link_is_valid = entry.kind == "symlink" and destination.is_symlink()
            file_is_valid = entry.cardinality != "tree" and entry.kind != "symlink" and destination.is_file() and not destination.is_symlink()
            if not (tree_is_valid or link_is_valid or file_is_valid):
                _fail("inventory_mismatch")
    return _success("scan-dmg-manifest", entries, args.report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    def report(command: argparse.ArgumentParser) -> None:
        command.add_argument("--report", type=Path)
    stage = commands.add_parser("stage")
    for name in ("manifest", "source-root", "generated-root", "output"):
        stage.add_argument(f"--{name}", type=Path, required=True)
    stage.add_argument("--platform", required=True)
    stage.add_argument("--profile", required=True)
    stage.add_argument("--zip", type=Path)
    report(stage)
    for name in ("scan-tree", "scan-zip", "scan-dmg-manifest"):
        command = commands.add_parser(name)
        command.add_argument("--path", type=Path, required=True)
        command.add_argument("--manifest", type=Path)
        command.add_argument("--platform", default="common" if name == "scan-tree" else "macos" if name == "scan-dmg-manifest" else "windows")
        command.add_argument("--profile", default="pyinstaller" if name == "scan-tree" else "dmg" if name == "scan-dmg-manifest" else "release")
        report(command)
    pyi = commands.add_parser("scan-pyinstaller-toc")
    pyi.add_argument("--archive", type=Path, required=True)
    pyi.add_argument("--viewer", type=Path, required=True)
    pyi.add_argument("--manifest", type=Path, required=True)
    pyi.add_argument("--platform", required=True)
    pyi.add_argument("--profile", required=True)
    pyi.add_argument("--collect", type=Path)
    report(pyi)
    verify = commands.add_parser("verify-git-source")
    verify.add_argument("--repository-root", type=Path, required=True)
    verify.add_argument("--expected-head", required=True)
    verify.add_argument("--allow-dirty", action="store_true")
    report(verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    operations = {"stage": _stage, "scan-tree": _scan_tree, "scan-zip": _scan_zip, "scan-pyinstaller-toc": _scan_pyi, "scan-dmg-manifest": _scan_dmg, "verify-git-source": _verify_git}
    try:
        payload = operations[args.command](args)
    except ReleaseSafetyError as exc:
        payload = {"schema": "iz-release-safety-result-v1", "result": "FAIL", "operation": args.command, "reason": exc.reason, "entries": []}
        _write_report(getattr(args, "report", None), payload)
        sys.stdout.write(_canonical_json(payload).decode())
        return 2
    sys.stdout.write(_canonical_json(payload).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
