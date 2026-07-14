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
        cancel_requested=job.cancel_requested, last_heartbeat_at=job.last_heartbeat_at,
        phase=_phase(job.status, job.current_endpoint),
        message=_message(job.job_type, job.status),
        artifacts=artifacts,
    )


def _phase(status: str, current_endpoint: str) -> str:
    if status in {"completed", "completed_with_warnings", "failed", "cancelled", "stale_or_interrupted"}:
        return status
    endpoint = current_endpoint.lower()
    if "clients" in endpoint:
        return "roster"
    if "treatment-plan" in endpoint or "treatment_plan" in endpoint:
        return "treatment_plans"
    return status


def _message(job_type: str, status: str) -> str:
    label = {
        "active_patient_roster_pull": "Patient roster pull",
        "approved_treatment_plan_sync": "Treatment-plan sync",
        "pull_all_treatment_plans_all_fields": "Treatment-plan diagnostic preview",
    }.get(job_type, "Job")
    if status == "completed":
        return f"{label} completed."
    if status == "completed_with_warnings":
        return f"{label} completed with partial results; existing local records were preserved."
    if status == "failed":
        return f"{label} failed. Review the saved API configuration and sanitized forensic log."
    if status == "cancelled":
        return f"{label} was cancelled."
    if status == "stale_or_interrupted":
        return f"{label} was interrupted and can be queried from local history."
    return f"{label} is {status}."
