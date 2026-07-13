from __future__ import annotations

import csv
import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class DiagnosticFailure:
    failure_stage: str
    error_class: str
    safe_message: str
    http_status: int | None

    def audit_details(self) -> dict[str, JsonPrimitive]:
        details: dict[str, JsonPrimitive] = {
            "failure_stage": self.failure_stage,
            "error_class": self.error_class,
        }
        if self.http_status is not None:
            details["http_status"] = self.http_status
        return details


def record(job_id: str, index: int, payload: Mapping[str, object], *, endpoint: str, page: int) -> dict[str, JsonValue]:
    record_id = _safe_identifier(job_id, _identifier(payload, "id", "treatmentPlanId", "treatment_plan_id", "planId"))
    patient_id = _safe_identifier(job_id, _identifier(payload, "clientId", "client_id", "patientId", "patient_id"))
    return {
        "job_id": job_id,
        "source_endpoint": endpoint,
        "page_number": page,
        "cursor": f"offset-{index}",
        "record_index": index,
        "fetched_at": now_iso(),
        "http_status": 200,
        "elapsed_ms": 0,
        "record_id": record_id,
        "canonical_patient_id_if_known": patient_id,
        "raw_client_ref_if_known": "",
        "extracted_patient_id_if_known": patient_id,
        "join_validated_if_known": bool(patient_id),
        "redaction_status": "direct_identifiers_hashed",
        "payload": "redacted_external_record_metadata",
        "warnings": [],
    }


def _identifier(payload: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    return ""


def _safe_identifier(job_id: str, value: str) -> str:
    if not value:
        return ""
    digest = hmac.new(
        settings.effective_data_encryption_secret.encode("utf-8"),
        f"{job_id}:{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "hmac-sha256:" + digest


def write_progress(output_dir: Path, job_id: str, page: int, progress: int) -> None:
    (output_dir / "progress.json").write_text(
        json.dumps({"job_id": job_id, "current_page": page, "progress_percent": progress}, indent=2),
        encoding="utf-8",
    )


def write_tables(output_dir: Path, rows: Sequence[dict[str, JsonValue]]) -> None:
    table_rows = [
        {
            "job_id": row["job_id"],
            "record_index": row["record_index"],
            "source_endpoint": row["source_endpoint"],
            "treatment_plan_id": row["record_id"],
            "canonical_patient_id_if_known": row["canonical_patient_id_if_known"],
            "field_path": "redacted_external_record_metadata.record_id",
            "field_type": "string",
            "field_value_preview": row["record_id"],
            "is_blank": not bool(row["record_id"]),
            "is_array": False,
            "is_object": False,
            "redaction_status": "redacted",
            "example_count": 1,
            "warning_codes": "",
        }
        for row in rows
    ]
    write_delimited(output_dir / "all-treatment-plans.flattened-fields.tsv", table_rows, "\t")
    write_delimited(output_dir / "all-treatment-plans.flattened-fields.csv", table_rows, ",")
    write_delimited(
        output_dir / "all-treatment-plans.field-frequency.tsv",
        [{"field_path": "redacted_external_record_metadata.record_id", "count_present": sum(bool(row["record_id"]) for row in rows), "redaction_status": "redacted"}],
        "\t",
    )


def write_delimited(path: Path, rows: Sequence[dict[str, JsonValue]], delimiter: str) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0].keys()), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def write_summaries(output_dir: Path, job_id: str, rows: Sequence[dict[str, JsonValue]]) -> None:
    schema = {
        "field_path": "redacted_external_record_metadata.record_id",
        "observed_types": ["string"],
        "count_present": len(rows),
        "count_blank": 0,
        "count_null": 0,
        "source_endpoints": ["GET /treatment-plans"],
    }
    (output_dir / "all-treatment-plans.observed-schema.json").write_text(json.dumps([schema], indent=2), encoding="utf-8")
    (output_dir / "run-summary.json").write_text(json.dumps({"job_id": job_id, "records_written": len(rows)}, indent=2), encoding="utf-8")
    (output_dir / "audit-summary.json").write_text(json.dumps({"safe_summary_only": True, "job_id": job_id}, indent=2), encoding="utf-8")
    (output_dir / "all-treatment-plans.warning-log.jsonl").write_text("", encoding="utf-8")
    (output_dir / "all-treatment-plans.error-log.jsonl").write_text("", encoding="utf-8")


def write_failure(output_dir: Path, job_id: str, failure: DiagnosticFailure) -> None:
    payload: dict[str, JsonPrimitive] = {
        "job_id": job_id,
        "event": "diagnostic_pull_failed",
        "failure_stage": failure.failure_stage,
        "error_class": failure.error_class,
        "safe_message": failure.safe_message,
        "http_status": failure.http_status,
    }
    (output_dir / "all-treatment-plans.error-log.jsonl").write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def media_type(name: str) -> str:
    if name.endswith(".json") or name.endswith(".jsonl"):
        return "application/json"
    if name.endswith(".csv"):
        return "text/csv"
    return "text/plain"
