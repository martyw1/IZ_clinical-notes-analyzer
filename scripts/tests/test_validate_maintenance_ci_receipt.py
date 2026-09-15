#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=8"]
# ///

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


MODULE_PATH = Path(__file__).parents[1] / "validate-maintenance-ci-receipt.py"
GATE_NAMES = (
    "backend_tests",
    "frontend_tests",
    "frontend_build",
    "repository_safety",
    "directory_safety",
    "zip_safety",
    "frozen_bundle_inspection",
)


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("maintenance_ci_receipt", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(
    tmp_path: Path,
    *,
    gate_status: str = "passed",
    evidence: str = "receipts/gate.json",
) -> tuple[Path, Path]:
    receipt_root = tmp_path / "build"
    package_root = receipt_root / "IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4"
    evidence_path = receipt_root / evidence if not evidence.startswith("../") else receipt_root / "receipts" / "gate.json"
    package_root.mkdir(parents=True)
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text('{"status":"passed"}\n', encoding="utf-8")
    (package_root / "release-manifest.json").write_text('{"schema":"synthetic"}\n', encoding="utf-8")
    zip_path = receipt_root / "candidate.zip"
    zip_path.write_bytes(b"synthetic-safe-candidate")
    gates = [
        {
            "name": name,
            "status": gate_status,
            "command": "synthetic gate",
            "exit_code": 0 if gate_status == "passed" else 1,
            "evidence": evidence,
        }
        for name in GATE_NAMES
    ]
    receipt = {
        "schema": "iz-cna-build-receipt-v1",
        "product_id": "r3.iz-clinical-notes-analyzer.desktop",
        "version": "2.0.0-beta.4",
        "build": "2026.09.14.1",
        "installer_revision": 1,
        "source_revision": "a" * 40,
        "package_directory": str(package_root.resolve()),
        "zip_path": str(zip_path.resolve()),
        "zip_length": zip_path.stat().st_size,
        "zip_sha256": _sha256(zip_path),
        "manifest_sha256": _sha256(package_root / "release-manifest.json"),
        "payload_identity": "b" * 64,
        "gates": gates,
        "created_utc": "2026-09-14T12:00:00Z",
    }
    receipt_path = zip_path.with_suffix(".build-receipt.json")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, zip_path


def test_valid_receipt_writes_sanitized_summary(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, zip_path = _write_receipt(tmp_path)
    output_path = tmp_path / "summary" / "maintenance-ci-receipt.json"
    output_path.parent.mkdir()

    result = validator.validate_build_receipt(receipt_path, candidate_zip=zip_path)
    validator.write_ci_summary(output_path, result)

    summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.status == "passed"
    assert summary["status"] == "passed"
    assert summary["zip_sha256"] == _sha256(zip_path)
    assert "zip_path" not in summary
    assert "command" not in summary["gates"][0]


def test_success_output_names_summary_and_candidate_identity(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    validator = _load_validator()
    receipt_path, zip_path = _write_receipt(tmp_path)
    output_path = tmp_path / "summary" / "maintenance-ci-receipt.json"
    output_path.parent.mkdir()

    assert validator.main([
        "--receipt", str(receipt_path),
        "--candidate-zip", str(zip_path),
        "--expected-source-revision", "a" * 40,
        "--output", str(output_path),
    ]) == 0

    captured = capsys.readouterr()
    assert f"summary={output_path}" in captured.out
    assert f"candidate_zip_sha256={_sha256(zip_path)}" in captured.out


def test_missing_required_gate_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["gates"] = receipt["gates"][:-1]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path)

    assert error.value.reason == "REQUIRED_GATE_SET_MISMATCH"


def test_duplicate_required_gate_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["gates"][-1]["name"] = receipt["gates"][0]["name"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path)

    assert error.value.reason == "REQUIRED_GATE_SET_MISMATCH"


def test_expected_source_revision_mismatch_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path)

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path, expected_source_revision="f" * 40)

    assert error.value.reason == "SOURCE_REVISION_MISMATCH"


def test_stale_zip_hash_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, zip_path = _write_receipt(tmp_path)
    zip_path.write_bytes(b"mutated-safe-candidate!!")

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path, candidate_zip=zip_path)

    assert error.value.reason == "ZIP_HASH_MISMATCH"


def test_stale_manifest_hash_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    package_root = Path(receipt["package_directory"])
    (package_root / "release-manifest.json").write_text('{"schema":"changed"}\n', encoding="utf-8")

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path)

    assert error.value.reason == "MANIFEST_HASH_MISMATCH"


def test_non_sibling_receipt_is_rejected_when_candidate_is_supplied(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, zip_path = _write_receipt(tmp_path)
    copied_receipt = receipt_path.with_name("supplied.build-receipt.json")
    copied_receipt.write_bytes(receipt_path.read_bytes())

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(copied_receipt, candidate_zip=zip_path)

    assert error.value.reason == "BUILD_RECEIPT_SIBLING_MISMATCH"


def test_blocked_required_gate_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path, gate_status="blocked")

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path)

    assert error.value.reason == "REQUIRED_GATE_NOT_PASSED"


def test_unsafe_relative_evidence_path_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path, evidence="../../.env")

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.validate_build_receipt(receipt_path)

    assert error.value.reason == "UNSAFE_EVIDENCE_PATH"


def test_unsafe_summary_output_path_is_rejected(tmp_path: Path) -> None:
    validator = _load_validator()
    receipt_path, _ = _write_receipt(tmp_path)
    result = validator.validate_build_receipt(receipt_path)
    output_path = tmp_path / ".env-summary.json"

    with pytest.raises(validator.ReceiptValidationError) as error:
        validator.write_ci_summary(output_path, result)

    assert error.value.reason == "UNSAFE_OUTPUT_PATH"
