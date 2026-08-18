from __future__ import annotations

# noqa: SIZE_OK — Task 6 requires its cross-platform release contract in this exact test module.

import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Final

import pytest

from scripts import release_safety


ROOT: Final = Path(__file__).resolve().parents[2]
SCRIPT: Final = ROOT / "scripts" / "release_safety.py"
ENTRY_KEYS: Final = {
    "platform",
    "profile",
    "source",
    "destination",
    "kind",
    "cardinality",
    "introduced_by_task",
    "generator",
    "invocation_target",
    "sha_policy",
}
GENERATORS: Final = [
    "vite-asset-graph",
    "release-manifest",
    "release-manifest-digest",
    "windows-release-builder",
    "windows-pyinstaller",
    "macos-release-builder",
    "macos-pyinstaller",
]
WINDOWS_PAYLOADS: Final = (
    "Install-IZ-Clinical-Notes-Analyzer.cmd",
    "Launch-IZ-Clinical-Notes-Analyzer.cmd",
    "Stop-IZ-Clinical-Notes-Analyzer.cmd",
    "Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd",
    "Backup-IZ-Clinical-Notes-Analyzer.cmd",
    "Restore-IZ-Clinical-Notes-Analyzer.cmd",
    "Uninstall-IZ-Clinical-Notes-Analyzer.cmd",
    "Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd",
    "installer/install-windows-release.ps1",
    "installer/uninstall-windows-release.ps1",
    "app/runtime/IZClinicalNotesAnalyzer.exe",
    "app/tools/launch-packaged-runtime.cmd",
    "app/tools/stop-windows-local.ps1",
    "app/tools/backup-local-data.ps1",
    "app/tools/restore-local-data.ps1",
    "app/tools/collect-diagnostics.ps1",
    "app/tools/complete-uninstall-local-data.ps1",
)


def _row(
    source: str,
    destination: str,
    *,
    platform: str = "common",
    profile: str = "pyinstaller",
    kind: str = "static",
    cardinality: str = "one",
    generator: str = "",
    invocation_target: str = "scripts/release_safety.py",
    sha_policy: str = "sha256",
) -> dict[str, str | int]:
    return {
        "platform": platform,
        "profile": profile,
        "source": source,
        "destination": destination,
        "kind": kind,
        "cardinality": cardinality,
        "introduced_by_task": 6,
        "generator": generator,
        "invocation_target": invocation_target,
        "sha_policy": sha_policy,
    }


def _common_rows() -> list[dict[str, str | int]]:
    exact = (
        ("VERSION", "pyi://VERSION"),
        ("VERSION.json", "pyi://VERSION.json"),
        ("frontend/dist/index.html", "pyi://frontend/dist/index.html"),
        ("config/rules/alleva_treatment_plan_completeness_rules.yaml", "pyi://config/rules/alleva_treatment_plan_completeness_rules.yaml"),
        ("config/checklists/treatment-plan-v1.json", "pyi://config/checklists/treatment-plan-v1.json"),
        ("README.md", "pyi://docs/README.md"),
        ("docs/Windows-User-Guide-Version-1.md", "pyi://docs/Windows-User-Guide-Version-1.md"),
        ("docs/Windows-Deployment-and-Test-Guide-Version-1.md", "pyi://docs/Windows-Deployment-and-Test-Guide-Version-1.md"),
        ("docs/beta-client-test-run-guide.md", "pyi://docs/beta-client-test-run-guide.md"),
        ("docs/patient-treatment-plan-handling.md", "pyi://docs/patient-treatment-plan-handling.md"),
    )
    rows = [_row(source, destination) for source, destination in exact]
    rows.append(
        _row(
            "frontend/dist/index.html",
            "pyi://frontend/dist/assets/",
            kind="generated",
            cardinality="one-or-more",
            generator="vite-asset-graph",
            invocation_target="scripts/release_safety.py:vite-asset-graph",
        )
    )
    return rows


def _windows_rows() -> list[dict[str, str | int]]:
    root = "IZ Clinical Notes Analyzer/"
    rows = [
        _row("generated://metadata/release-manifest.json", f"windows://{root}release-manifest.json", platform="windows", profile="release", kind="generated", generator="release-manifest", invocation_target="scripts/release_safety.py:release-manifest"),
        _row("generated://metadata/release-manifest.sha256", f"windows://{root}release-manifest.sha256", platform="windows", profile="release", kind="generated", generator="release-manifest-digest", invocation_target="scripts/release_safety.py:release-manifest-digest"),
    ]
    for relative in WINDOWS_PAYLOADS:
        kind = "pyinstaller-toc" if relative.endswith(".exe") else "generated"
        generator = "windows-pyinstaller" if kind == "pyinstaller-toc" else "windows-release-builder"
        scheme = "pyinstaller" if kind == "pyinstaller-toc" else "generated"
        rows.append(_row(f"{scheme}://{relative}", f"windows://{root}{relative}", platform="windows", profile="release", kind=kind, generator=generator, invocation_target=f"{generator}:{relative}"))
    return rows


def _write_manifest(path: Path, rows: list[dict[str, str | int]]) -> Path:
    path.write_text(json.dumps({"schema": "iz-desktop-package-manifest-v1", "generators": GENERATORS, "entries": rows}), encoding="utf-8")
    return path


def _write_common_sources(root: Path, *, extra_asset: bool = False, unresolved: bool = False) -> None:
    values = {
        "VERSION": "2.0.0-test\n",
        "VERSION.json": '{"version":"2.0.0-test"}\n',
        "config/rules/alleva_treatment_plan_completeness_rules.yaml": "rules: []\n",
        "config/checklists/treatment-plan-v1.json": '{"steps":[]}\n',
        "README.md": "synthetic readme\n",
        "docs/Windows-User-Guide-Version-1.md": "synthetic guide\n",
        "docs/Windows-Deployment-and-Test-Guide-Version-1.md": "synthetic deployment\n",
        "docs/beta-client-test-run-guide.md": "synthetic beta\n",
        "docs/patient-treatment-plan-handling.md": "synthetic handling\n",
        "frontend/dist/index.html": '<script type="module" src="/assets/main.js"></script><link href="/assets/main.css" rel="stylesheet">',
        "frontend/dist/assets/main.js": 'import "./nested/chunk.js"; import("./dynamic.js");',
        "frontend/dist/assets/nested/chunk.js": "export const value = 1;",
        "frontend/dist/assets/dynamic.js": "export const value = 2;",
        "frontend/dist/assets/main.css": "body{background:url('./pixel.svg')}",
        "frontend/dist/assets/pixel.svg": "<svg/>",
    }
    if unresolved:
        values["frontend/dist/assets/main.js"] = 'import "./missing.js";'
    if extra_asset:
        values["frontend/dist/assets/unlisted.js"] = "export const extra = true;"
    for relative, content in values.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run((sys.executable, str(SCRIPT), *args), cwd=cwd, check=False, capture_output=True, text=True)


def _reason(result: subprocess.CompletedProcess[str]) -> str:
    return str(json.loads(result.stdout)["reason"])


def _safe_stage_args(source: Path, manifest: Path, output: Path, report: Path, profile: str = "pyinstaller", platform: str = "common") -> tuple[str, ...]:
    return ("stage", "--manifest", str(manifest), "--source-root", str(source), "--generated-root", str(source), "--output", str(output), "--platform", platform, "--profile", profile, "--report", str(report))


def test_stage_stages_transitive_vite_graph_and_excludes_unlisted_file(tmp_path: Path) -> None:
    # Given an exact common manifest and a benign file beside its inputs.
    source, output = tmp_path / "source", tmp_path / "output"
    _write_common_sources(source)
    (source / "frontend/dist/benign-unlisted.txt").write_text("not selected", encoding="utf-8")
    manifest = _write_manifest(tmp_path / "manifest.json", _common_rows())

    # When the real staging command runs.
    result = _run(*_safe_stage_args(Path("source"), manifest.relative_to(tmp_path), output, Path("stage.json")), cwd=tmp_path)

    # Then only the exact mappings and recursively referenced assets exist.
    assert result.returncode == 0, result.stdout + result.stderr
    files = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
    assert "frontend/dist/benign-unlisted.txt" not in files
    assert files == {str(row["destination"]).removeprefix("pyi://").rstrip("/") for row in _common_rows() if row["kind"] == "static"} | {
        "frontend/dist/assets/main.js", "frontend/dist/assets/nested/chunk.js", "frontend/dist/assets/dynamic.js", "frontend/dist/assets/main.css", "frontend/dist/assets/pixel.svg"
    }


@pytest.mark.parametrize("mutation,expected", [("unknown", "manifest_schema"), ("glob", "ambiguous_glob"), ("generator", "unknown_generator"), ("duplicate", "duplicate_destination"), ("freeform", "free_form_entry")])
def test_manifest_rejects_non_allowlist_rows(tmp_path: Path, mutation: str, expected: str) -> None:
    # Given a manifest mutated outside the strict schema/allowlist.
    source = tmp_path / "source"
    _write_common_sources(source)
    rows = _common_rows()
    if mutation == "unknown":
        rows[0]["unexpected"] = "value"
    elif mutation == "glob":
        rows[0]["source"] = "docs/*.md"
    elif mutation == "generator":
        rows[-1]["generator"] = "missing-generator"
    elif mutation == "duplicate":
        rows[1]["destination"] = rows[0]["destination"]
    else:
        rows.append(_row("docs/free-form.md", "pyi://docs/free-form.md"))
    manifest = _write_manifest(tmp_path / "manifest.json", rows)

    # When staging parses the untrusted manifest.
    result = _run(*_safe_stage_args(source, manifest, tmp_path / "output", tmp_path / "report.json"))

    # Then it fails with a redacted stable category.
    assert result.returncode == 2
    assert _reason(result) == expected


@pytest.mark.parametrize("extra_asset,unresolved,expected", [(True, False, "unreferenced_asset"), (False, True, "unresolved_asset")])
def test_vite_graph_rejects_missing_or_extra_assets(tmp_path: Path, extra_asset: bool, unresolved: bool, expected: str) -> None:
    # Given an invalid Vite graph.
    source = tmp_path / "source"
    _write_common_sources(source, extra_asset=extra_asset, unresolved=unresolved)
    manifest = _write_manifest(tmp_path / "manifest.json", _common_rows())

    # When staging follows the graph.
    result = _run(*_safe_stage_args(source, manifest, tmp_path / "output", tmp_path / "report.json"))

    # Then unresolved and unreachable files are rejected before publication.
    assert result.returncode == 2
    assert _reason(result) == expected


def test_windows_stage_emits_exact_tree_zip_manifest_and_digest(tmp_path: Path) -> None:
    # Given every exact Windows generated input plus an unlisted neighbour.
    generated = tmp_path / "generated"
    for relative in WINDOWS_PAYLOADS:
        target = generated / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"synthetic:{relative}".encode())
    (generated / "unlisted-benign.txt").write_text("excluded", encoding="utf-8")
    manifest = _write_manifest(tmp_path / "manifest.json", _windows_rows())
    output, archive = tmp_path / "windows-output", tmp_path / "windows.zip"

    # When the real staging path emits the folder and ZIP.
    result = _run(*_safe_stage_args(generated, manifest, output, tmp_path / "report.json", "release", "windows"), "--zip", str(archive))

    # Then inventory and detached digest are exact and the benign file is absent.
    assert result.returncode == 0, result.stdout + result.stderr
    root = output / "IZ Clinical Notes Analyzer"
    expected = set(WINDOWS_PAYLOADS) | {"release-manifest.json", "release-manifest.sha256"}
    assert {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()} == expected
    manifest_bytes = (root / "release-manifest.json").read_bytes()
    assert (root / "release-manifest.sha256").read_bytes() == f"{hashlib.sha256(manifest_bytes).hexdigest()}  release-manifest.json\n".encode()
    payload = json.loads(manifest_bytes)
    assert {entry["path"] for entry in payload["entries"]} == set(WINDOWS_PAYLOADS)
    assert _run("scan-zip", "--path", str(archive), "--manifest", str(manifest), "--platform", "windows", "--profile", "release").returncode == 0


def test_windows_manifest_without_installer_helper_is_rejected(tmp_path: Path) -> None:
    # Given a Windows manifest missing its required installer entry.
    generated = tmp_path / "generated"
    generated.mkdir()
    rows = [row for row in _windows_rows() if not str(row["destination"]).endswith("Install-IZ-Clinical-Notes-Analyzer.cmd")]
    manifest = _write_manifest(tmp_path / "manifest.json", rows)

    # When the stage boundary validates the selected profile.
    result = _run(*_safe_stage_args(generated, manifest, tmp_path / "output", tmp_path / "report.json", "release", "windows"))

    # Then it fails before an incomplete release can be emitted.
    assert result.returncode == 2
    assert _reason(result) == "windows_inventory"


def test_windows_manifest_rejects_substituted_generated_source_mapping(tmp_path: Path) -> None:
    # Given every destination is present but one generated source mapping is substituted.
    generated = tmp_path / "generated"
    for relative in WINDOWS_PAYLOADS:
        target = generated / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"synthetic:{relative}".encode())
    (generated / "free-form-source.bin").write_bytes(b"FREEFORM")
    rows = _windows_rows()
    installer = next(row for row in rows if str(row["destination"]).endswith("Install-IZ-Clinical-Notes-Analyzer.cmd"))
    installer["source"] = "generated://free-form-source.bin"
    installer["invocation_target"] = "arbitrary:free-form"
    manifest = _write_manifest(tmp_path / "manifest.json", rows)
    output = tmp_path / "output"

    # When the exact Windows profile is staged.
    result = _run(*_safe_stage_args(generated, manifest, output, tmp_path / "report.json", "release", "windows"))

    # Then source substitution fails closed before retaining an output package.
    assert result.returncode == 2
    assert _reason(result) == "free_form_entry"
    assert not output.exists()


@pytest.mark.parametrize(
    "case,name,reason",
    [
        ("traversal", "../escape.txt", "traversal"),
        ("drive_name", "C:/escape.txt", "drive_path"),
        ("unc_name", "//server/share.txt", "unc_path"),
        ("device_name", "CON.txt", "device_name"),
        ("ads_name", "safe.txt:stream", "ads_path"),
        ("trailing_alias", "alias. ", "trailing_alias"),
    ],
)
def test_zip_rejects_unsafe_raw_names(tmp_path: Path, case: str, name: str, reason: str) -> None:
    # Given a ZIP with one adversarial raw central-directory name.
    archive = tmp_path / f"{case}.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(name, b"safe")

    # When the ZIP boundary scans names before extraction.
    result = _run("scan-zip", "--path", str(archive))

    # Then it rejects the exact safe category.
    assert result.returncode == 2
    assert _reason(result) == reason


def test_raw_duplicate_zip_name_is_rejected(tmp_path: Path) -> None:
    # Given duplicate raw names in the central directory.
    archive = tmp_path / "raw-duplicate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("safe.txt", b"one")
        with pytest.warns(UserWarning, match="Duplicate name"):
            bundle.writestr("safe.txt", b"two")

    # When scanned.
    result = _run("scan-zip", "--path", str(archive))

    # Then duplicate entries cannot merge.
    assert result.returncode == 2
    assert _reason(result) == "raw_duplicate"


@pytest.mark.parametrize("case,names,reason", [("nfc_collision", ("caf\u00e9.txt", "cafe\u0301.txt"), "nfc_collision"), ("case_collision", ("Readme.txt", "README.TXT"), "case_collision")])
def test_zip_rejects_unicode_and_case_collisions(tmp_path: Path, case: str, names: tuple[str, str], reason: str) -> None:
    # Given two distinct raw names that alias after canonicalization.
    archive = tmp_path / f"{case}.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in names:
            bundle.writestr(name, b"safe")

    # When scanned.
    result = _run("scan-zip", "--path", str(archive))

    # Then the alias class is rejected.
    assert result.returncode == 2
    assert _reason(result) == reason


@pytest.mark.parametrize("case,marker,reason", [("secret_canary", "SYNTHETIC_SECRET_CANARY_73A19", "secret_canary"), ("phi_canary", "SYNTHETIC_PHI_CANARY_46B27", "phi_canary")])
def test_tree_rejects_privacy_canary_without_disclosure(tmp_path: Path, case: str, marker: str, reason: str) -> None:
    # Given a real tree containing a synthetic privacy canary.
    root = tmp_path / case
    root.mkdir()
    (root / "payload.bin").write_text(marker, encoding="utf-8")

    # When the tree scanner reads content.
    result = _run("scan-tree", "--path", str(root))

    # Then the value is redacted and no artifact is approved.
    assert result.returncode == 2
    assert _reason(result) == reason
    assert marker not in result.stdout + result.stderr


def test_forbidden_release_canary_path_is_rejected_without_disclosure(tmp_path: Path) -> None:
    # Given a real tree containing a forbidden upload category and a private marker.
    marker = "SYNTHETIC_PRIVATE_PATH_CANARY_8D41"
    root = tmp_path / "tree"
    target = root / "uploads" / f"{marker}.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"safe")

    # When the tree scanner inventories it.
    result = _run("scan-tree", "--path", str(root))

    # Then only the safe category is exposed.
    assert result.returncode == 2
    assert _reason(result) == "upload"
    assert marker not in result.stdout + result.stderr


def test_dirty_source_is_rejected_even_with_misleading_success_output(tmp_path: Path) -> None:
    # Given a real Git repository with a modified tracked file.
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.email", "synthetic@example.invalid"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.name", "Synthetic"), cwd=repository, check=True)
    (repository / "tracked.txt").write_text("clean", encoding="utf-8")
    subprocess.run(("git", "add", "tracked.txt"), cwd=repository, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repository, check=True)
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    (repository / "tracked.txt").write_text("result=PASS", encoding="utf-8")

    # When exact source verification runs.
    result = _run("verify-git-source", "--repository-root", str(repository), "--expected-head", head)

    # Then process state wins over misleading file text.
    assert result.returncode == 2
    assert _reason(result) == "dirty_worktree"


def test_dirty_source_rejects_forbidden_untracked_staging_input_without_disclosure(tmp_path: Path) -> None:
    # Given a clean repository plus an untracked forbidden staging input.
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.email", "synthetic@example.invalid"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.name", "Synthetic"), cwd=repository, check=True)
    (repository / "tracked.txt").write_text("clean", encoding="utf-8")
    subprocess.run(("git", "add", "tracked.txt"), cwd=repository, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repository, check=True)
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    marker = "SYNTHETIC_PRIVATE_PATH_CANARY_231D"
    target = repository / "uploads" / f"{marker}.bin"
    target.parent.mkdir()
    target.write_bytes(b"safe")

    # When the diagnostic dirty override scans the repository boundary.
    result = _run("verify-git-source", "--repository-root", str(repository), "--expected-head", head, "--allow-dirty")

    # Then the forbidden untracked input still fails with only a safe category.
    assert result.returncode == 2
    assert _reason(result) == "upload"
    assert marker not in result.stdout + result.stderr


def test_misleading_exit23_from_pyinstaller_viewer_is_rejected(tmp_path: Path) -> None:
    # Given a viewer that prints PASS and exits 23.
    archive, viewer = tmp_path / "runtime.exe", tmp_path / "viewer.py"
    archive.write_bytes(b"synthetic")
    viewer.write_text("import sys\nprint('result=PASS')\nraise SystemExit(23)\n", encoding="utf-8")
    manifest = _write_manifest(tmp_path / "manifest.json", _windows_rows())

    # When the actual command adapter invokes it.
    result = _run("scan-pyinstaller-toc", "--archive", str(archive), "--viewer", str(viewer), "--manifest", str(manifest), "--platform", "windows", "--profile", "release")

    # Then the nonzero exit is authoritative.
    assert result.returncode == 2
    assert _reason(result) == "pyinstaller_viewer_failed"


def test_pyinstaller_inventory_rejects_unexpected_only_viewer_output(tmp_path: Path) -> None:
    # Given an exact manifest and an exit-zero viewer that reports only an undeclared entry.
    archive, viewer = tmp_path / "runtime.exe", tmp_path / "viewer.py"
    archive.write_bytes(b"synthetic")
    viewer.write_text("print('unexpected-only.bin')\n", encoding="utf-8")
    manifest = _write_manifest(tmp_path / "manifest.json", _windows_rows())

    # When the actual PyInstaller inventory boundary runs.
    result = _run("scan-pyinstaller-toc", "--archive", str(archive), "--viewer", str(viewer), "--manifest", str(manifest), "--platform", "windows", "--profile", "release")

    # Then the viewer cannot approve a missing and extra inventory.
    assert result.returncode == 2
    assert _reason(result) == "inventory_mismatch"


def test_pyinstaller_inventory_accepts_the_exact_declared_toc(tmp_path: Path) -> None:
    # Given an exact manifest and a viewer reporting its sole declared PyInstaller source.
    archive, viewer = tmp_path / "runtime.exe", tmp_path / "viewer.py"
    archive.write_bytes(b"synthetic")
    viewer.write_text("print('app/runtime/IZClinicalNotesAnalyzer.exe')\n", encoding="utf-8")
    manifest = _write_manifest(tmp_path / "manifest.json", _windows_rows())

    # When the actual PyInstaller inventory boundary runs.
    result = _run("scan-pyinstaller-toc", "--archive", str(archive), "--viewer", str(viewer), "--manifest", str(manifest), "--platform", "windows", "--profile", "release")

    # Then the exact declared inventory is approved and reported.
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["entries"] == [{"path": "app/runtime/IZClinicalNotesAnalyzer.exe", "type": "pyinstaller-toc"}]


def test_cleanup_escape_output_is_rejected_without_removing_sentinel(tmp_path: Path) -> None:
    # Given a stage output outside the system temporary root.
    source, sentinel = tmp_path / "source", ROOT / f"task6-sentinel-{tmp_path.name}.txt"
    _write_common_sources(source)
    manifest = _write_manifest(tmp_path / "manifest.json", _common_rows())
    sentinel.write_text("preserve", encoding="utf-8")
    try:
        # When staging is pointed beside the repository.
        result = _run(*_safe_stage_args(source, manifest, ROOT / f"task6-output-{tmp_path.name}", tmp_path / "report.json"))

        # Then it fails before cleanup can cross its temp boundary.
        assert result.returncode == 2
        assert _reason(result) == "unsafe_staging_root"
        assert sentinel.read_text(encoding="utf-8") == "preserve"
    finally:
        sentinel.unlink(missing_ok=True)


def test_macos_app_tree_stages_as_a_bounded_tree(tmp_path: Path) -> None:
    # Given a manifest-declared PyInstaller app tree with one regular payload file.
    generated = tmp_path / "generated"
    payload = generated / "IZ Clinical Notes Analyzer.app/Contents/MacOS/IZClinicalNotesAnalyzer"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"synthetic-app")
    rows = [
        _row(
            "pyinstaller://IZ Clinical Notes Analyzer.app",
            "dmg://IZ Clinical Notes Analyzer.app",
            platform="macos",
            profile="dmg",
            kind="pyinstaller-toc",
            cardinality="tree",
            generator="macos-pyinstaller",
            invocation_target="macos-pyinstaller:main-app",
            sha_policy="tree-sha256",
        )
    ]
    manifest = _write_manifest(tmp_path / "manifest.json", rows)
    output = tmp_path / "output"

    # When the staging boundary copies the declared tree.
    result = _run(*_safe_stage_args(generated, manifest, output, tmp_path / "report.json", "dmg", "macos"))

    # Then the bounded tree and its byte-identical payload are emitted.
    assert result.returncode == 0, result.stdout + result.stderr
    assert (output / payload.relative_to(generated)).read_bytes() == b"synthetic-app"


def test_dmg_manifest_rejects_missing_roots_and_benign_extra(tmp_path: Path) -> None:
    # Given a DMG root containing only an undeclared benign file.
    root = tmp_path / "dmg"
    root.mkdir()
    (root / "benign-extra.txt").write_text("safe", encoding="utf-8")

    # When it is scanned against the production DMG manifest.
    result = _run("scan-dmg-manifest", "--path", str(root), "--manifest", str(ROOT / "config/release/desktop-package-manifest.json"), "--platform", "macos", "--profile", "dmg")

    # Then missing required roots and the extra entry fail closed.
    assert result.returncode == 2
    assert _reason(result) == "inventory_mismatch"


def test_dmg_cycle_detection_precedes_unlisted_link_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given resolution reports a cycle for a link that is not allowlisted.
    link = tmp_path / "link"

    def raise_cycle(_path: Path, *, strict: bool = False) -> Path:
        raise RuntimeError

    monkeypatch.setattr(Path, "resolve", raise_cycle)

    # When the shared DMG link policy resolves it.
    with pytest.raises(release_safety.ReleaseSafetyError) as captured:
        release_safety._resolve_dmg_link(link, listed=False)

    # Then the intrinsic cycle class wins over the unlisted policy class.
    assert captured.value.reason == "symlink_cycle"


def test_dmg_link_policy_still_rejects_ordinary_unlisted_link(tmp_path: Path) -> None:
    # Given a resolvable path that is not allowlisted.
    link = tmp_path / "link"

    # When the shared DMG link policy evaluates it.
    with pytest.raises(release_safety.ReleaseSafetyError) as captured:
        release_safety._resolve_dmg_link(link, listed=False)

    # Then arbitrary unlisted links remain rejected.
    assert captured.value.reason == "unlisted_symlink"


@pytest.mark.skipif(os.name == "nt", reason="Windows runner lacks unprivileged POSIX symlinks; macOS native lane executes this policy")
@pytest.mark.parametrize("case,target,reason", [("absolute_symlink", "/tmp/outside", "absolute_symlink"), ("unlisted_symlink", "target", "unlisted_symlink"), ("symlink_cycle", "cycle-b", "symlink_cycle"), ("applications_symlink_wrong_parent", "/Applications", "applications_symlink_wrong_parent")])
def test_dmg_rejects_unsafe_links(tmp_path: Path, case: str, target: str, reason: str) -> None:
    # Given a real DMG-shaped tree containing one unsafe link class.
    root = tmp_path / "dmg"
    root.mkdir()
    link = root / ("Nested/Applications" if case == "applications_symlink_wrong_parent" else "link")
    link.parent.mkdir(parents=True, exist_ok=True)
    if case == "symlink_cycle":
        os.symlink("cycle-b", root / "link")
        os.symlink("link", root / "cycle-b")
    else:
        if target == "target":
            (root / target).write_text("safe", encoding="utf-8")
        os.symlink(target, link)

    # When the DMG manifest scanner evaluates it without following escapes.
    result = _run("scan-dmg-manifest", "--path", str(root))

    # Then the stable link category is rejected.
    assert result.returncode == 2
    assert _reason(result) == reason


@pytest.mark.skipif(os.name == "nt", reason="Windows runner lacks unprivileged POSIX symlinks; macOS native lane executes this policy")
def test_manifest_valid_framework_and_applications_symlinks_pass(tmp_path: Path) -> None:
    # Given enumerated in-bundle framework and exact DMG-root Applications links.
    root = tmp_path / "dmg"
    framework = root / "IZ Clinical Notes Analyzer.app/Contents/Frameworks/Synthetic.framework"
    (framework / "Versions/A").mkdir(parents=True)
    (framework / "Versions/A/Synthetic").write_text("binary", encoding="utf-8")
    os.symlink("A", framework / "Versions/Current")
    os.symlink("Versions/Current/Synthetic", framework / "Synthetic")
    os.symlink("/Applications", root / "Applications")
    rows = [
        _row("pyinstaller://IZ Clinical Notes Analyzer.app", "dmg://IZ Clinical Notes Analyzer.app", platform="macos", profile="dmg", kind="pyinstaller-toc", cardinality="tree", generator="macos-pyinstaller", invocation_target="macos-pyinstaller:main-app", sha_policy="tree-sha256"),
        _row("/Applications", "dmg://Applications", platform="macos", profile="dmg", kind="symlink", generator="macos-release-builder", sha_policy="link-only"),
        _row("A", "dmg://IZ Clinical Notes Analyzer.app/Contents/Frameworks/Synthetic.framework/Versions/Current", platform="macos", profile="dmg", kind="symlink", generator="macos-pyinstaller", sha_policy="link-target-sha256"),
        _row("Versions/Current/Synthetic", "dmg://IZ Clinical Notes Analyzer.app/Contents/Frameworks/Synthetic.framework/Synthetic", platform="macos", profile="dmg", kind="symlink", generator="macos-pyinstaller", sha_policy="link-target-sha256"),
    ]
    manifest = _write_manifest(tmp_path / "manifest.json", rows)

    # When the DMG scanner uses the exact symlink allowlist.
    result = _run("scan-dmg-manifest", "--path", str(root), "--manifest", str(manifest), "--platform", "macos", "--profile", "dmg")

    # Then both links pass and link text/target hashes are recorded.
    assert result.returncode == 0, result.stdout + result.stderr
    entries = json.loads(result.stdout)["entries"]
    assert {entry["path"] for entry in entries if entry["type"] == "symlink"} == {str(row["destination"]).removeprefix("dmg://") for row in rows}
    assert all("link_target" in entry for entry in entries if entry["type"] == "symlink")


def test_production_manifest_has_exact_row_keys_and_payload_contract() -> None:
    # Given the checked-in staging source of truth.
    payload = json.loads((ROOT / "config/release/desktop-package-manifest.json").read_text(encoding="utf-8"))

    # When its machine contract is inspected.
    rows = payload["entries"]

    # Then every row is exact and Windows has the fixed archive inventory.
    assert all(set(row) == ENTRY_KEYS for row in rows)
    windows = {row["destination"].removeprefix("windows://IZ Clinical Notes Analyzer/") for row in rows if row["platform"] == "windows" and row["profile"] == "release"}
    assert windows == set(WINDOWS_PAYLOADS) | {"release-manifest.json", "release-manifest.sha256"}
