from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(job_id: str, index: int) -> dict[str, JsonValue]:
    return {
        "job_id": job_id,
        "source_endpoint": "GET /treatment-plans",
        "page_number": index,
        "cursor": f"cursor-{index}",
        "record_index": index,
        "fetched_at": now_iso(),
        "http_status": 200,
        "elapsed_ms": 40 + index,
        "record_id": f"TP-900{index}",
        "canonical_patient_id_if_known": "307",
        "raw_client_ref_if_known": "/clients/307",
        "extracted_patient_id_if_known": "307",
        "join_validated_if_known": True,
        "redaction_status": "patient_names_excluded",
        "payload": "redacted_safe_preview",
        "warnings": [],
    }


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
            "field_path": "payload.goals[0].description",
            "field_type": "string",
            "field_value_preview": "redacted_safe_preview",
            "is_blank": False,
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
        [{"field_path": "payload.goals[0].description", "count_present": len(rows), "redaction_status": "redacted"}],
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
        "field_path": "payload.goals[0].description",
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
