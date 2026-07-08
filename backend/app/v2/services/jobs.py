from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.services.audit import log_event
from app.v2.domain.schemas import ApiHarnessArtifact, ApiHarnessJob, JobPreview
from app.v2.services.job_artifacts import media_type, now_iso, record, write_progress, write_summaries, write_tables

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]


def _now() -> str:
    return now_iso()


@dataclass(frozen=True, slots=True)
class MutableJob:
    job_id: str
    job_type: str
    created_at: str
    started_at: str | None
    updated_at: str
    completed_at: str | None
    cancelled_at: str | None
    failed_at: str | None
    actor_id: str
    actor_role: str
    status: str
    progress_percent: int
    current_endpoint: str
    current_page: int
    current_cursor: str
    records_seen: int
    records_written: int
    records_failed: int
    warnings_count: int
    errors_count: int
    output_dir: str
    redaction_mode: str
    raw_sensitive_mode_used: bool
    cancel_requested: bool
    last_heartbeat_at: str


class ApiHarnessJobService:
    def __init__(self) -> None:
        self._jobs: dict[str, MutableJob] = {}
        self._lock = threading.Lock()

    def create_all_fields_job(self, actor_id: str = "admin", actor_role: str = "admin") -> ApiHarnessJob:
        job_id = f"job-{uuid4().hex[:12]}"
        output_dir = settings.api_harness_runs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        created = _now()
        job = MutableJob(
            job_id=job_id,
            job_type="pull_all_treatment_plans_all_fields",
            created_at=created,
            started_at=None,
            updated_at=created,
            completed_at=None,
            cancelled_at=None,
            failed_at=None,
            actor_id=actor_id,
            actor_role=actor_role,
            status="queued",
            progress_percent=0,
            current_endpoint="GET /treatment-plans",
            current_page=0,
            current_cursor="",
            records_seen=0,
            records_written=0,
            records_failed=0,
            warnings_count=0,
            errors_count=0,
            output_dir=str(output_dir),
            redaction_mode="redacted",
            raw_sensitive_mode_used=False,
            cancel_requested=False,
            last_heartbeat_at=created,
        )
        with self._lock:
            self._jobs[job_id] = job
        log_event(
            action="api_harness.job.created",
            entity_type="api_harness_job",
            entity_reference=job_id,
            actor_id=actor_id,
            actor_role=actor_role,
            details={"job_id": job_id, "job_type": job.job_type, "redaction_mode": "redacted"},
        )
        threading.Thread(target=self._run_job, args=(job_id,), daemon=True).start()
        return self.get_job(job_id)

    def list_jobs(self) -> tuple[ApiHarnessJob, ...]:
        with self._lock:
            ids = tuple(self._jobs)
        return tuple(self.get_job(job_id) for job_id in ids)

    def get_job(self, job_id: str) -> ApiHarnessJob:
        with self._lock:
            job = self._jobs[job_id]
        return self._public_job(job)

    def cancel_job(self, job_id: str) -> ApiHarnessJob:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = replace(job, cancel_requested=True, updated_at=_now())
        log_event(action="api_harness.job.cancel_requested", entity_type="api_harness_job", entity_reference=job_id)
        return self.get_job(job_id)

    def artifacts(self, job_id: str) -> tuple[ApiHarnessArtifact, ...]:
        output_dir = self._output_dir(job_id)
        names = (
            "run-summary.json",
            "progress.json",
            "all-treatment-plans.all-fields.redacted.jsonl",
            "all-treatment-plans.flattened-fields.tsv",
            "all-treatment-plans.flattened-fields.csv",
            "all-treatment-plans.observed-schema.json",
            "all-treatment-plans.field-frequency.tsv",
            "all-treatment-plans.warning-log.jsonl",
            "all-treatment-plans.error-log.jsonl",
            "audit-summary.json",
        )
        artifacts: list[ApiHarnessArtifact] = []
        for name in names:
            path = output_dir / name
            if path.exists():
                artifacts.append(
                    ApiHarnessArtifact(
                        artifact_id=name,
                        name=name,
                        media_type=media_type(name),
                        size_bytes=path.stat().st_size,
                        redaction_mode="redacted",
                    )
                )
        return tuple(artifacts)

    def artifact_path(self, job_id: str, artifact_id: str) -> Path:
        path = Path(self.get_job(job_id).output_dir) / artifact_id
        if not path.exists():
            raise FileNotFoundError(artifact_id)
        return path

    def preview(self, job_id: str) -> JobPreview:
        path = Path(self.get_job(job_id).output_dir) / "all-treatment-plans.all-fields.redacted.jsonl"
        records: list[dict[str, JsonValue]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines()[:25]:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    records.append(
                        {
                            "job_id": str(payload.get("job_id", "")),
                            "record_index": int(payload.get("record_index", 0)),
                            "record_id": str(payload.get("record_id", "")),
                            "source_endpoint": str(payload.get("source_endpoint", "")),
                            "redaction_status": str(payload.get("redaction_status", "")),
                        }
                    )
        return JobPreview(
            job_id=job_id,
            max_records=25,
            max_fields=50,
            records=tuple(records),
            message="Preview is bounded to 25 records and 50 fields; full output is local artifact files.",
        )

    def _run_job(self, job_id: str) -> None:
        output_dir = self._output_dir(job_id)
        self._set(job_id, status="running", started_at=_now(), progress_percent=5)
        jsonl = output_dir / "all-treatment-plans.all-fields.redacted.jsonl"
        rows: list[dict[str, JsonValue]] = []
        with jsonl.open("w", encoding="utf-8") as handle:
            for index in range(1, 7):
                if self.get_job(job_id).cancel_requested:
                    self._set(job_id, status="cancelled", cancelled_at=_now(), progress_percent=100)
                    log_event(action="api_harness.job.cancelled", entity_type="api_harness_job", entity_reference=job_id)
                    return
                row = record(job_id, index)
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
                write_progress(output_dir, job_id, index, index * 15)
                self._set(
                    job_id,
                    status="writing",
                    current_page=index,
                    current_cursor=f"cursor-{index}",
                    records_seen=index,
                    records_written=index,
                    progress_percent=min(95, index * 15),
                    last_heartbeat_at=_now(),
                )
                time.sleep(0.05)
        write_tables(output_dir, rows)
        write_summaries(output_dir, job_id, rows)
        self._set(job_id, status="completed", completed_at=_now(), progress_percent=100)
        log_event(
            action="api_harness.job.completed",
            entity_type="api_harness_job",
            entity_reference=job_id,
            details={"job_id": job_id, "records_seen": len(rows), "records_written": len(rows), "artifact_names": [a.name for a in self.artifacts(job_id)]},
        )

    def _set(self, job_id: str, **changes: JsonValue) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = replace(job, updated_at=_now(), **changes)

    def _output_dir(self, job_id: str) -> Path:
        with self._lock:
            return Path(self._jobs[job_id].output_dir)

    def _public_job(self, job: MutableJob) -> ApiHarnessJob:
        return ApiHarnessJob(
            job_id=job.job_id,
            job_type=job.job_type,
            created_at=job.created_at,
            started_at=job.started_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            cancelled_at=job.cancelled_at,
            failed_at=job.failed_at,
            actor_id=job.actor_id,
            actor_role=job.actor_role,
            status=job.status,
            progress_percent=job.progress_percent,
            current_endpoint=job.current_endpoint,
            current_page=job.current_page,
            current_cursor=job.current_cursor,
            records_seen=job.records_seen,
            records_written=job.records_written,
            records_failed=job.records_failed,
            warnings_count=job.warnings_count,
            errors_count=job.errors_count,
            output_dir=job.output_dir,
            redaction_mode=job.redaction_mode,
            raw_sensitive_mode_used=job.raw_sensitive_mode_used,
            cancel_requested=job.cancel_requested,
            last_heartbeat_at=job.last_heartbeat_at,
            artifacts=self.artifacts(job.job_id),
        )


job_service = ApiHarnessJobService()
