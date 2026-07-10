from __future__ import annotations

from typing import Any

from app.v2.domain.schemas import ApiHarnessArtifact, ApiHarnessJob


def public_job(job: Any, artifacts: tuple[ApiHarnessArtifact, ...]) -> ApiHarnessJob:
    return ApiHarnessJob(
        job_id=job.job_id, job_type=job.job_type, created_at=job.created_at, started_at=job.started_at,
        updated_at=job.updated_at, completed_at=job.completed_at, cancelled_at=job.cancelled_at, failed_at=job.failed_at,
        actor_id=job.actor_id, actor_role=job.actor_role, status=job.status, progress_percent=job.progress_percent,
        current_endpoint=job.current_endpoint, current_page=job.current_page, current_cursor=job.current_cursor,
        records_seen=job.records_seen, records_written=job.records_written, records_failed=job.records_failed,
        warnings_count=job.warnings_count, errors_count=job.errors_count, output_dir=job.output_dir,
        redaction_mode=job.redaction_mode, raw_sensitive_mode_used=job.raw_sensitive_mode_used,
        cancel_requested=job.cancel_requested, last_heartbeat_at=job.last_heartbeat_at, artifacts=artifacts,
    )
