#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run validate-maintenance-ci-receipt.py --receipt <path> --output <path>
# 3. Or make executable and run:
#      chmod +x validate-maintenance-ci-receipt.py && ./validate-maintenance-ci-receipt.py --receipt <path> --output <path>
# ──────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Mapping, NoReturn, TypeAlias


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
BUILD_KEYS: Final = frozenset({
    "schema", "product_id", "version", "build", "installer_revision", "source_revision",
    "package_directory", "zip_path", "zip_length", "zip_sha256", "manifest_sha256",
    "payload_identity", "gates", "created_utc",
})
GATE_KEYS: Final = frozenset({"name", "status", "command", "exit_code", "evidence"})
GATE_NAMES: Final = (
    "backend_tests", "frontend_tests", "frontend_build", "repository_safety",
    "directory_safety", "zip_safety", "frozen_bundle_inspection",
)
GATE_STATUSES: Final = frozenset({"passed", "failed", "blocked", "skipped"})
PRODUCT_ID: Final = "r3.iz-clinical-notes-analyzer.desktop"
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
SOURCE_RE: Final = re.compile(r"^[0-9a-f]{7,64}$")
VERSION_RE: Final = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
BUILD_RE: Final = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d+$")
ALLOWED_SUFFIXES: Final = frozenset({".json", ".txt"})
FORBIDDEN_NAMES: Final = frozenset({
    ".env", "sqlite", ".db", ".bak", ".zip", ".7z", ".exe", ".dll", ".pem", ".key", ".pfx", "trace",
})
REDACTION_MARKERS: Final = (
    "password=", "client_secret", "access_token", "bearer ", "begin private key",
    "playwright", ".sqlite", ".env", "trace.zip",
)


@dataclass(frozen=True, slots=True)
class ReceiptValidationError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class GateSummary:
    name: str
    status: str
    exit_code: int
    evidence: str


@dataclass(frozen=True, slots=True)
class BuildReceiptSummary:
    status: str
    source_revision: str
    version: str
    build: str
    installer_revision: int
    zip_length: int
    zip_sha256: str
    manifest_sha256: str
    gates: tuple[GateSummary, ...]


def _fail(reason: str) -> NoReturn:
    raise ReceiptValidationError(reason)


def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("RECEIPT_JSON_INVALID")
    if not isinstance(value, dict):
        _fail("RECEIPT_OBJECT_REQUIRED")
    return value


def _keys(value: Mapping[str, JsonValue], expected: frozenset[str], reason: str) -> None:
    if frozenset(value) != expected:
        _fail(reason)


def _text(value: Mapping[str, JsonValue], name: str, reason: str = "RECEIPT_FIELD_INVALID") -> str:
    field = value.get(name)
    if not isinstance(field, str) or not field:
        _fail(reason)
    return field


def _integer(value: Mapping[str, JsonValue], name: str, reason: str = "RECEIPT_FIELD_INVALID") -> int:
    field = value.get(name)
    if not isinstance(field, int) or isinstance(field, bool):
        _fail(reason)
    return field


def _absolute(raw: str, reason: str) -> Path:
    windows_path = re.match(r"^[A-Za-z]:[\\/]", raw) is not None
    if not os.path.isabs(raw) or (os.name == "nt" and (raw.startswith("\\\\") or not windows_path)):
        _fail(reason)
    return Path(raw)


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        return bool(path.stat().st_file_attributes & 0x400)
    except (AttributeError, OSError):
        return False


def _file(path: Path, reason: str) -> None:
    if _is_reparse(path) or not path.is_file() or path.stat().st_size == 0:
        _fail(reason)


def _directory(path: Path, reason: str) -> None:
    if _is_reparse(path) or not path.is_dir():
        _fail(reason)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(raw: str) -> None:
    parts = raw.split("/")
    lowered = raw.lower()
    if (not raw or raw.startswith("/") or "\\" in raw or ":" in raw or
            any(part in {"", ".", ".."} for part in parts) or
            any(token in lowered for token in FORBIDDEN_NAMES) or
            Path(raw).suffix.lower() not in ALLOWED_SUFFIXES):
        _fail("UNSAFE_EVIDENCE_PATH")


def _evidence(root: Path, relative: str) -> None:
    _safe_relative(relative)
    candidate = root.joinpath(*relative.split("/"))
    cursor = root
    for part in relative.split("/"):
        cursor /= part
        if _is_reparse(cursor):
            _fail("UNSAFE_EVIDENCE_PATH")
    if not candidate.resolve().is_relative_to(root.resolve()):
        _fail("UNSAFE_EVIDENCE_PATH")
    _file(candidate, "EVIDENCE_ARTIFACT_INVALID")
    if candidate.stat().st_size > 1024 * 1024:
        _fail("EVIDENCE_ARTIFACT_TOO_LARGE")
    try:
        content = candidate.read_text(encoding="utf-8").lower()
    except (OSError, UnicodeError):
        _fail("EVIDENCE_ARTIFACT_INVALID")
    if any(marker in content for marker in REDACTION_MARKERS):
        _fail("UNSAFE_EVIDENCE_CONTENT")


def _gate(raw: JsonValue, root: Path, seen: set[str]) -> GateSummary:
    if not isinstance(raw, dict):
        _fail("GATE_OBJECT_REQUIRED")
    _keys(raw, GATE_KEYS, "GATE_KEYS_MISMATCH")
    name = _text(raw, "name", "GATE_NAME_INVALID")
    if name not in GATE_NAMES or name in seen:
        _fail("REQUIRED_GATE_SET_MISMATCH")
    seen.add(name)
    status = _text(raw, "status", "GATE_STATUS_INVALID")
    if status not in GATE_STATUSES:
        _fail("GATE_STATUS_INVALID")
    exit_code = _integer(raw, "exit_code", "GATE_EXIT_CODE_INVALID")
    _text(raw, "command", "GATE_COMMAND_INVALID")
    evidence = _text(raw, "evidence", "GATE_EVIDENCE_INVALID")
    _evidence(root, evidence)
    if status != "passed" or exit_code != 0:
        _fail("REQUIRED_GATE_NOT_PASSED")
    return GateSummary(name, status, exit_code, evidence)


def validate_build_receipt(
    receipt_path: Path,
    candidate_zip: Path | None = None,
    expected_source_revision: str | None = None,
) -> BuildReceiptSummary:
    _file(receipt_path, "BUILD_RECEIPT_INVALID")
    receipt = _read_json(receipt_path)
    _keys(receipt, BUILD_KEYS, "BUILD_RECEIPT_KEYS_MISMATCH")
    if _text(receipt, "schema") != "iz-cna-build-receipt-v1" or _text(receipt, "product_id") != PRODUCT_ID:
        _fail("BUILD_RECEIPT_IDENTITY_INVALID")
    version, build, source = (_text(receipt, key) for key in ("version", "build", "source_revision"))
    if not VERSION_RE.fullmatch(version) or not BUILD_RE.fullmatch(build) or not SOURCE_RE.fullmatch(source):
        _fail("BUILD_RECEIPT_IDENTITY_INVALID")
    if expected_source_revision is not None:
        if not SOURCE_RE.fullmatch(expected_source_revision) or source != expected_source_revision:
            _fail("SOURCE_REVISION_MISMATCH")
    revision = _integer(receipt, "installer_revision")
    if revision < 0:
        _fail("BUILD_RECEIPT_IDENTITY_INVALID")
    try:
        datetime.fromisoformat(_text(receipt, "created_utc").replace("Z", "+00:00"))
    except ValueError:
        _fail("BUILD_RECEIPT_TIME_INVALID")
    package = _absolute(_text(receipt, "package_directory"), "PACKAGE_DIRECTORY_NOT_ABSOLUTE")
    zip_path = _absolute(_text(receipt, "zip_path"), "ZIP_PATH_NOT_ABSOLUTE")
    _directory(package, "PACKAGE_DIRECTORY_INVALID")
    _file(zip_path, "ZIP_ARTIFACT_INVALID")
    if candidate_zip is not None:
        _file(candidate_zip, "CANDIDATE_ZIP_INVALID")
        candidate_resolved = candidate_zip.resolve()
        if os.path.normcase(str(candidate_resolved)) != os.path.normcase(str(zip_path.resolve())):
            _fail("CANDIDATE_PATH_MISMATCH")
        sibling_receipt = candidate_resolved.with_suffix(".build-receipt.json")
        if os.path.normcase(str(receipt_path.resolve())) != os.path.normcase(str(sibling_receipt)):
            _fail("BUILD_RECEIPT_SIBLING_MISMATCH")
    length = _integer(receipt, "zip_length")
    if length != zip_path.stat().st_size:
        _fail("ZIP_LENGTH_MISMATCH")
    zip_sha = _text(receipt, "zip_sha256")
    if not SHA256_RE.fullmatch(zip_sha) or _sha256(zip_path) != zip_sha:
        _fail("ZIP_HASH_MISMATCH")
    manifest = package / "release-manifest.json"
    _file(manifest, "MANIFEST_ARTIFACT_INVALID")
    manifest_sha = _text(receipt, "manifest_sha256")
    if not SHA256_RE.fullmatch(manifest_sha) or _sha256(manifest) != manifest_sha:
        _fail("MANIFEST_HASH_MISMATCH")
    if not SHA256_RE.fullmatch(_text(receipt, "payload_identity")):
        _fail("PAYLOAD_IDENTITY_INVALID")
    gates = receipt.get("gates")
    if not isinstance(gates, list) or len(gates) != len(GATE_NAMES):
        _fail("REQUIRED_GATE_SET_MISMATCH")
    seen: set[str] = set()
    summaries = tuple(_gate(item, receipt_path.parent, seen) for item in gates)
    if seen != set(GATE_NAMES):
        _fail("REQUIRED_GATE_SET_MISMATCH")
    return BuildReceiptSummary("passed", source, version, build, revision, length, zip_sha, manifest_sha, summaries)


def _safe_output(path: Path) -> None:
    if path.suffix.lower() != ".json" or any(token in path.name.lower() for token in FORBIDDEN_NAMES):
        _fail("UNSAFE_OUTPUT_PATH")
    if not path.parent.is_dir() or _is_reparse(path.parent):
        _fail("UNSAFE_OUTPUT_PATH")


def write_ci_summary(output: Path, build: BuildReceiptSummary) -> None:
    _safe_output(output)
    summary: JsonObject = {
        "schema": "iz-cna-ci-receipt-summary-v1", "status": build.status,
        "source_revision": build.source_revision, "version": build.version,
        "build": build.build, "installer_revision": build.installer_revision,
        "zip_length": build.zip_length, "zip_sha256": build.zip_sha256,
        "manifest_sha256": build.manifest_sha256,
        "gates": [{"name": gate.name, "status": gate.status, "exit_code": gate.exit_code, "evidence": gate.evidence} for gate in build.gates],
    }
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_failure(output: Path, reason: str) -> None:
    try:
        _safe_output(output)
        output.write_text(json.dumps({"schema": "iz-cna-ci-receipt-summary-v1", "status": "failed", "reason": reason}) + "\n", encoding="utf-8")
    except ReceiptValidationError:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a maintenance build receipt.")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-zip", type=Path)
    parser.add_argument("--expected-source-revision")
    args = parser.parse_args(argv)
    try:
        build = validate_build_receipt(
            args.receipt,
            args.candidate_zip,
            args.expected_source_revision,
        )
        write_ci_summary(args.output, build)
        print(
            "PASS maintenance CI receipt validation; "
            f"summary={args.output}; candidate_zip_sha256={build.zip_sha256}"
        )
        return 0
    except ReceiptValidationError as error:
        _write_failure(args.output, error.reason)
        print(f"FAIL maintenance CI receipt validation: {error.reason}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        _write_failure(args.output, "VALIDATION_FAILED")
        print("FAIL maintenance CI receipt validation: VALIDATION_FAILED", file=sys.stderr)
        return 1
    except Exception:  # noqa: BROAD_EXCEPT_OK
        _write_failure(args.output, "VALIDATION_FAILED")
        print("FAIL maintenance CI receipt validation: VALIDATION_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
