from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final
from uuid import uuid4

from app.core.config import settings
from app.services.audit import log_event
from app.v2.db import SessionLocal
from app.v2.domain.schemas import ApiHarnessArtifact, ApiHarnessJob, JobPreview
from app.v2.models import ApiHarnessJobRecord, AppSetting, User
from app.v2.services.job_runner import fetch_paged_records
from app.v2.services.alleva_sync import AllevaSyncCancelled, AllevaSyncError, run_treatment_plan_sync
from app.v2.services.alleva_contracts import (
    ApprovedAllevaContract,
    contract_bound_to_sync_job,
    copy_sync_checkpoints,
    create_sync_ledger,
    record_sync_checkpoint,
    record_sync_failure,
    set_sync_cancellation_requested,
    update_sync_ledger,
)
from app.v2.services.audit_store import record_audit_event
from app.v2.services.job_store import record_as_job_values, save_job
from app.v2.services.job_view import public_job
from sqlalchemy import select
from app.v2.services.job_artifacts import media_type, now_iso, write_summaries, write_tables

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[JsonPrimitive] | dict[str, JsonPrimitive]
ARTIFACT_NAMES: Final = (
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


@dataclass(frozen=True, slots=True)
class HarnessConnection:
    api_base_url: str
    token_url: str
    client_id: str
    client_secret: str
    scope: str
    token_auth_style: str
    timeout_seconds: int
    page_size: int


class ApiHarnessJobService:
    def __init__(self) -> None:
        self._jobs: dict[str, MutableJob] = {}
        self._connections: dict[str, HarnessConnection] = {}
        self._sync_actor_ids: dict[str, int] = {}
        self._sync_contracts: dict[str, ApprovedAllevaContract] = {}
        self._sync_resume_sources: dict[str, str] = {}
        self._lock = threading.Lock()

    def create_all_fields_job(self, connection: HarnessConnection, actor_id: str = "admin", actor_role: str = "admin") -> ApiHarnessJob:
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
            self._connections[job_id] = connection
        save_job(job)
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

    def create_treatment_plan_sync_job(
        self,
        actor_id: int,
        actor_role: str,
        contract: ApprovedAllevaContract,
        resumed_from_job_id: str | None = None,
    ) -> ApiHarnessJob:
        job_id = f"sync-{uuid4().hex[:12]}"
        output_dir = settings.api_harness_runs_dir / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        created = _now()
        job = MutableJob(
            job_id=job_id, job_type="approved_treatment_plan_sync", created_at=created, started_at=None, updated_at=created,
            completed_at=None, cancelled_at=None, failed_at=None, actor_id=str(actor_id), actor_role=actor_role,
            status="queued", progress_percent=0, current_endpoint="GET /clients", current_page=0, current_cursor="",
            records_seen=0, records_written=0, records_failed=0, warnings_count=0, errors_count=0,
            output_dir=str(output_dir), redaction_mode="redacted", raw_sensitive_mode_used=False,
            cancel_requested=False, last_heartbeat_at=created,
        )
        with self._lock:
            self._jobs[job_id] = job
            self._sync_actor_ids[job_id] = actor_id
            self._sync_contracts[job_id] = contract
            if resumed_from_job_id:
                self._sync_resume_sources[job_id] = resumed_from_job_id
        save_job(job)
        with SessionLocal() as db:
            create_sync_ledger(db, job_id, actor_id, contract, created, resumed_from_job_id)
            if resumed_from_job_id:
                copy_sync_checkpoints(db, resumed_from_job_id, job_id)
        log_event(action="alleva.treatment_plan_sync.job.created", entity_type="api_harness_job", entity_reference=job_id, actor_id=str(actor_id), actor_role=actor_role)
        threading.Thread(target=self._run_job, args=(job_id,), daemon=True).start()
        return self.get_job(job_id)

    def resume_treatment_plan_sync_job(self, job_id: str, actor_id: int, actor_role: str) -> ApiHarnessJob:
        with SessionLocal() as db:
            original = db.execute(
                select(ApiHarnessJobRecord).where(ApiHarnessJobRecord.job_id == job_id)
            ).scalar_one_or_none()
            contract = contract_bound_to_sync_job(db, job_id)
        if original is None or original.job_type != "approved_treatment_plan_sync":
            raise KeyError(job_id)
        if original.status not in {"cancelled", "failed", "stale_or_interrupted"}:
            raise ValueError("Only a terminal sync job can be resumed.")
        if contract is None:
            raise ValueError("The sync job's approved contract is unavailable.")
        return self.create_treatment_plan_sync_job(actor_id, actor_role, contract, resumed_from_job_id=job_id)

    def list_jobs(self) -> tuple[ApiHarnessJob, ...]:
        with SessionLocal() as db:
            rows = db.execute(select(ApiHarnessJobRecord).order_by(ApiHarnessJobRecord.created_at.desc())).scalars().all()
        return tuple(self._public_job(MutableJob(**record_as_job_values(row))) for row in rows)

    def get_job(self, job_id: str) -> ApiHarnessJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            with SessionLocal() as db:
                row = db.execute(select(ApiHarnessJobRecord).where(ApiHarnessJobRecord.job_id == job_id)).scalar_one_or_none()
            if row is None:
                raise KeyError(job_id)
            job = MutableJob(**record_as_job_values(row))
        return self._public_job(job)

    def cancel_job(self, job_id: str) -> ApiHarnessJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                self._jobs[job_id] = replace(job, cancel_requested=True, updated_at=_now())
                job = self._jobs[job_id]
        if job is None:
            with SessionLocal() as db:
                row = db.execute(select(ApiHarnessJobRecord).where(ApiHarnessJobRecord.job_id == job_id)).scalar_one_or_none()
            if row is None:
                raise KeyError(job_id)
            job = replace(MutableJob(**record_as_job_values(row)), cancel_requested=True, updated_at=_now())
        save_job(job)
        if job.job_type == "approved_treatment_plan_sync":
            with SessionLocal() as db:
                set_sync_cancellation_requested(db, job_id)
        log_event(action="api_harness.job.cancel_requested", entity_type="api_harness_job", entity_reference=job_id)
        return self.get_job(job_id)

    def artifacts(self, job_id: str) -> tuple[ApiHarnessArtifact, ...]:
        output_dir = self._output_dir(job_id)
        artifacts: list[ApiHarnessArtifact] = []
        for name in ARTIFACT_NAMES:
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
        if artifact_id not in ARTIFACT_NAMES:
            raise FileNotFoundError(artifact_id)
        output_dir = Path(self.get_job(job_id).output_dir)
        path = output_dir / artifact_id
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
        with self._lock:
            sync_actor_id = self._sync_actor_ids.pop(job_id, None)
            sync_contract = self._sync_contracts.pop(job_id, None)
            resume_source_job_id = self._sync_resume_sources.pop(job_id, None)
        if sync_actor_id is not None:
            if sync_contract is None:
                self._set(job_id, status="failed", failed_at=_now(), errors_count=1, progress_percent=100)
                return
            self._run_treatment_plan_sync_job(job_id, sync_actor_id, sync_contract, resume_source_job_id)
            return
        output_dir = self._output_dir(job_id)
        self._set(job_id, status="running", started_at=_now(), progress_percent=5)
        connection = self._connection(job_id)
        rows, status = fetch_paged_records(job_id=job_id, connection=connection, output_dir=output_dir, is_cancelled=lambda: self.get_job(job_id).cancel_requested, update=lambda **changes: self._set(job_id, status="writing", last_heartbeat_at=_now(), **changes))
        if status == "cancelled":
            self._set(job_id, status="cancelled", cancelled_at=_now(), progress_percent=100)
            log_event(action="api_harness.job.cancelled", entity_type="api_harness_job", entity_reference=job_id)
            return
        if status == "failed":
            self._set(job_id, status="failed", failed_at=_now(), errors_count=1, progress_percent=100)
            return
        write_tables(output_dir, rows)
        write_summaries(output_dir, job_id, rows)
        self._set(job_id, status="completed", completed_at=_now(), progress_percent=100)
        log_event(
            action="api_harness.job.completed",
            entity_type="api_harness_job",
            entity_reference=job_id,
            details={"job_id": job_id, "records_seen": len(rows), "records_written": len(rows), "artifact_names": [a.name for a in self.artifacts(job_id)]},
        )

    def _run_treatment_plan_sync_job(self, job_id: str, actor_id: int, contract: ApprovedAllevaContract, resume_source_job_id: str | None) -> None:
        self._set(job_id, status="running", started_at=_now(), progress_percent=5, current_endpoint="GET /clients")
        with SessionLocal() as db:
            profile = db.execute(select(AppSetting)).scalar_one()
            actor = db.get(User, actor_id)
            if actor is None:
                self._set(job_id, status="failed", failed_at=_now(), errors_count=1, progress_percent=100)
                return
            try:
                result = run_treatment_plan_sync(
                    db,
                    profile,
                    actor,
                    contract,
                    is_cancelled=lambda: self.get_job(job_id).cancel_requested,
                    on_page=lambda endpoint_key, page_number, cursor_hash, response_hash, records: self._record_checkpoint(job_id, endpoint_key, page_number, cursor_hash, response_hash, records),
                    sync_job_id=job_id,
                    resumed_from_job_id=resume_source_job_id,
                )
            except AllevaSyncCancelled:
                record_audit_event(db, action="alleva.treatment_plan_sync.cancelled", actor=actor, target_entity_type="integration_sync", target_entity_id="alleva_treatment_plan_sync", outcome_status="cancelled")
                self._set(job_id, status="cancelled", cancelled_at=_now(), progress_percent=100)
                return
            except AllevaSyncError as exc:
                record_sync_failure(
                    db,
                    job_id,
                    type(exc).__name__,
                    "Sync request failed before completion.",
                    False,
                    1,
                    _now(),
                )
                record_audit_event(db, action="alleva.treatment_plan_sync.failed", actor=actor, target_entity_type="integration_sync", target_entity_id="alleva_treatment_plan_sync", outcome_status="failure", details={"error_class": type(exc).__name__})
                self._set(job_id, status="failed", failed_at=_now(), errors_count=1, progress_percent=100)
                return
            except Exception as exc:
                trace = exc.__traceback__
                while trace and trace.tb_next:
                    trace = trace.tb_next
                error_origin = trace.tb_frame.f_code.co_name if trace else "unknown"
                record_sync_failure(
                    db,
                    job_id,
                    type(exc).__name__,
                    "Sync worker failed before completion.",
                    False,
                    1,
                    _now(),
                )
                record_audit_event(db, action="alleva.treatment_plan_sync.failed", actor=actor, target_entity_type="integration_sync", target_entity_id="alleva_treatment_plan_sync", outcome_status="failure", details={"error_class": type(exc).__name__, "error_origin": error_origin})
                self._set(job_id, status="failed", failed_at=_now(), errors_count=1, progress_percent=100)
                return
            record_audit_event(
                db,
                action="alleva.treatment_plan_sync.completed",
                actor=actor,
                target_entity_type="integration_sync",
                target_entity_id="alleva_treatment_plan_sync",
                details={"imported_patient_count": result.imported_patient_count, "skipped_plan_count": result.skipped_plan_count},
            )
        self._set(
            job_id,
            status="completed",
            completed_at=_now(),
            progress_percent=100,
            records_seen=result.imported_patient_count + result.skipped_plan_count,
            records_written=result.imported_patient_count,
            records_failed=result.skipped_plan_count,
            current_endpoint="completed",
        )

    def _set(self, job_id: str, **changes: JsonValue) -> None:
        with self._lock:
            job = self._jobs[job_id]
            updated = replace(job, updated_at=_now(), **changes)
            self._jobs[job_id] = updated
        save_job(updated)
        if updated.job_type == "approved_treatment_plan_sync":
            counters = json.dumps({"records_seen": updated.records_seen, "records_written": updated.records_written, "records_failed": updated.records_failed, "warnings_count": updated.warnings_count, "errors_count": updated.errors_count}, sort_keys=True)
            terminal = updated.completed_at or updated.cancelled_at or updated.failed_at
            with SessionLocal() as db:
                update_sync_ledger(db, updated.job_id, updated.status, terminal, counters)

    def _record_checkpoint(self, job_id: str, endpoint_key: str, page_number: int, cursor_hash: str, response_hash: str, records: tuple[dict[str, object], ...]) -> None:
        with SessionLocal() as db:
            record_sync_checkpoint(db, job_id, endpoint_key, page_number, cursor_hash, response_hash, records, _now())
        current = self.get_job(job_id)
        self._set(
            job_id,
            current_endpoint=f"GET /{endpoint_key}",
            current_page=page_number,
            records_seen=current.records_seen + len(records),
            progress_percent=min(90, max(current.progress_percent, 10 + current.records_seen + len(records))),
        )

    def _output_dir(self, job_id: str) -> Path:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return Path(job.output_dir)
        with SessionLocal() as db:
            output_dir = db.execute(select(ApiHarnessJobRecord.output_dir).where(ApiHarnessJobRecord.job_id == job_id)).scalar_one_or_none()
        if output_dir is None:
            raise KeyError(job_id)
        return Path(output_dir)

    def _public_job(self, job: MutableJob) -> ApiHarnessJob:
        return public_job(job, self.artifacts(job.job_id))

    def _connection(self, job_id: str) -> HarnessConnection:
        with self._lock:
            connection = self._connections.pop(job_id, None)
        if connection is None:
            raise RuntimeError("Job connection configuration is unavailable")
        return connection


job_service = ApiHarnessJobService()


def _records_from_response(payload: object) -> list[dict[str, JsonValue]]:
    values = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError("Treatment-plan response did not contain a list")
    return [item for item in values if isinstance(item, dict)]
