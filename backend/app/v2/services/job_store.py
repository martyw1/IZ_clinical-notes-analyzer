from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.v2.db import SessionLocal
from app.v2.models import ApiHarnessJobRecord


def save_job(job: Any) -> None:
    values = _record_values(job)
    with SessionLocal() as db:
        row = db.execute(select(ApiHarnessJobRecord).where(ApiHarnessJobRecord.job_id == job.job_id)).scalar_one_or_none()
        if row is None:
            db.add(ApiHarnessJobRecord(job_id=job.job_id, **values))
        else:
            for field, value in values.items():
                setattr(row, field, value)
        db.commit()


def record_values(job: Any) -> dict[str, object]:
    return _record_values(job)


def record_as_job_values(row: ApiHarnessJobRecord) -> dict[str, object]:
    return {
        "job_id": row.job_id, "job_type": row.job_type, "created_at": row.created_at.isoformat(),
        "started_at": _as_iso(row.started_at), "updated_at": row.updated_at.isoformat(), "completed_at": _as_iso(row.completed_at),
        "cancelled_at": _as_iso(row.cancelled_at), "failed_at": _as_iso(row.failed_at), "actor_id": row.actor_id,
        "actor_role": row.actor_role, "status": row.status, "progress_percent": row.progress_percent,
        "current_endpoint": row.current_endpoint, "current_page": row.current_page, "current_cursor": row.current_cursor,
        "records_seen": row.records_seen, "records_written": row.records_written, "records_failed": row.records_failed,
        "warnings_count": row.warnings_count, "errors_count": row.errors_count, "output_dir": row.output_dir,
        "redaction_mode": row.redaction_mode, "raw_sensitive_mode_used": row.raw_sensitive_mode_used,
        "cancel_requested": row.cancel_requested, "last_heartbeat_at": row.last_heartbeat_at.isoformat(),
    }


def _record_values(job: Any) -> dict[str, object]:
    return {
        "job_type": job.job_type, "actor_id": job.actor_id, "actor_role": job.actor_role, "status": job.status,
        "progress_percent": job.progress_percent, "current_endpoint": job.current_endpoint, "current_page": job.current_page,
        "current_cursor": job.current_cursor, "records_seen": job.records_seen, "records_written": job.records_written,
        "records_failed": job.records_failed, "warnings_count": job.warnings_count, "errors_count": job.errors_count,
        "output_dir": job.output_dir, "redaction_mode": job.redaction_mode, "raw_sensitive_mode_used": job.raw_sensitive_mode_used,
        "cancel_requested": job.cancel_requested, "created_at": _as_datetime(job.created_at), "started_at": _as_datetime(job.started_at),
        "updated_at": _as_datetime(job.updated_at), "completed_at": _as_datetime(job.completed_at),
        "cancelled_at": _as_datetime(job.cancelled_at), "failed_at": _as_datetime(job.failed_at), "last_heartbeat_at": _as_datetime(job.last_heartbeat_at),
    }


def _as_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
