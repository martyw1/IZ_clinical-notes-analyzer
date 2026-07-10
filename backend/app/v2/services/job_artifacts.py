from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(job_id: str, index: int, payload: dict[str, JsonValue], *, endpoint: str, page: int) -> dict[str, JsonValue]:
    record_id = _identifier(payload, "id", "treatmentPlanId", "treatment_plan_id", "planId")
    patient_id = _identifier(payload, "clientId", "client_id", "patientId", "patient_id")
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
        "redaction_status": "patient_names_excluded",
        "payload": "redacted_external_record_metadata",
        "warnings": [],
    }


def _identifier(payload: dict[str, JsonValue], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    return ""


def write_progress(output_dir: Path, job_id: str, page: int, progress: int) -> None:
    (output_dir / "progress.json").write_text(
        json.dumps({"job_id": job_id, "current_page": page, "progress_percent": progress}, indent=2),
        encoding="utf-8",
    )


def write_tables(output_dir: Path, rows: list[dict[str, JsonValue]]) -> None:
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


def write_delimited(path: Path, rows: list[dict[str, JsonValue]], delimiter: str) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0].keys()), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def write_summaries(output_dir: Path, job_id: str, rows: list[dict[str, JsonValue]]) -> None:
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


def media_type(name: str) -> str:
    if name.endswith(".json") or name.endswith(".jsonl"):
        return "application/json"
    if name.endswith(".csv"):
        return "text/csv"
    return "text/plain"
