from __future__ import annotations

import sqlite3
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from types import ModuleType

import pytest

from test_v2_manual_patient_correction import _fresh_client


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _jobs_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    client = _fresh_client(tmp_path, monkeypatch)
    client.close()
    import app.v2.services.jobs as jobs

    return jobs


def _store_job(jobs: ModuleType, service, job_id: str, job_type: str) -> None:
    timestamp = jobs._now()
    job = jobs.MutableJob(
        job_id=job_id, job_type=job_type, created_at=timestamp, started_at=timestamp,
        updated_at=timestamp, completed_at=None, cancelled_at=None, failed_at=None,
        actor_id="admin", actor_role="admin", status="running", progress_percent=5,
        current_endpoint="synthetic", current_page=0, current_cursor="", records_seen=0,
        records_written=0, records_failed=0, warnings_count=0, errors_count=0,
        output_dir="", redaction_mode="redacted", raw_sensitive_mode_used=False,
        cancel_requested=False, last_heartbeat_at=timestamp,
    )
    with service._lock:
        service._jobs[job_id] = job
    jobs.save_job(job)


def test_drain_uses_one_fifteen_second_deadline_across_outer_and_nested_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one outer worker and one nested future that ignore cancellation.
    jobs = _jobs_module(tmp_path, monkeypatch)
    clock = _Clock()
    observed: list[float] = []
    release = Event()
    outer_started = Event()
    nested_started = Event()

    def wait_for_futures(
        futures: set[Future[dict[str, object]]], timeout: float,
    ) -> tuple[set[Future[dict[str, object]]], set[Future[dict[str, object]]]]:
        observed.append(timeout)
        clock.value += 7.0
        return set(), futures

    def join_thread(_thread: Thread, timeout: float) -> None:
        observed.append(timeout)
        clock.value += timeout

    registry = jobs.WorkerRegistry(clock=clock, future_wait=wait_for_futures, thread_join=join_thread)
    registry.start_worker("sync-one-budget", lambda: (outer_started.set(), release.wait()))
    executor_context = registry.detail_executor("sync-one-budget", 1, "synthetic-detail")
    executor = executor_context.__enter__()

    def nested_fetch(_candidate: str) -> dict[str, object]:
        nested_started.set()
        release.wait()
        return {}

    executor.fetch(nested_fetch, "synthetic")
    assert outer_started.wait(1)
    assert nested_started.wait(1)

    try:
        # When: shutdown drains against its production default budget.
        result = registry.drain()

        # Then: the nested and outer waits share exactly one 15-second deadline.
        assert observed == [15.0, 8.0]
        assert clock.value == 15.0
        assert result.cooperative is False
        assert result.survivors == ("sync-one-budget",)
        assert registry.tracked_work_count > 0
    finally:
        release.set()
        executor_context.__exit__(None, None, None)
        registry.join_tracked_for_test()
        registry.drain(timeout_seconds=0)


def test_nested_submission_and_new_outer_worker_are_rejected_after_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a registered detail executor whose registry has begun shutdown.
    jobs = _jobs_module(tmp_path, monkeypatch)
    registry = jobs.WorkerRegistry()
    executor_context = registry.detail_executor("sync-admission", 1, "synthetic-detail")
    executor = executor_context.__enter__()
    admitted_target_called = Event()
    registry.admit_job("admitted-before-shutdown")
    try:
        registry.request_shutdown()

        # When/Then: neither nested nor outer work can cross the shutdown fence.
        with pytest.raises(jobs.AllevaSyncCancelled, match="desktop_shutdown_in_progress"):
            executor.fetch(lambda _candidate: {}, "synthetic")
        registry.start_worker("admitted-before-shutdown", admitted_target_called.set)
        registry.join_tracked_for_test()
        assert not admitted_target_called.is_set()
        with pytest.raises(jobs.DesktopShutdownInProgressError) as rejected:
            registry.start_worker("diagnostic-admission", lambda: None)
        assert rejected.value.detail == "desktop_shutdown_in_progress"
    finally:
        executor_context.__exit__(None, None, None)
        registry.drain(timeout_seconds=0)


def test_all_job_admissions_and_sync_resume_are_rejected_during_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the service has atomically stopped admitting desktop jobs.
    jobs = _jobs_module(tmp_path, monkeypatch)
    from test_v2_sync_contract_runtime import _contract

    service = jobs.ApiHarnessJobService()
    try:
        service.request_shutdown()
        connection = jobs.HarnessConnection(
            "https://synthetic.invalid", "https://synthetic.invalid/token", "id", "secret", "",
            "basic", 5, 10, "1.0", "2000-01-01T16:03",
        )
        calls = (
            lambda: service.create_all_fields_job(connection),
            lambda: service.create_treatment_plan_sync_job(1, "admin", _contract()),
            lambda: service.create_roster_pull_job(1, "admin", _contract()),
            lambda: service.resume_treatment_plan_sync_job("missing", 1, "admin", _contract()),
        )

        # When/Then: every create/resume surface returns the exact shutdown code.
        for call in calls:
            with pytest.raises(jobs.DesktopShutdownInProgressError) as rejected:
                call()
            assert rejected.value.detail == "desktop_shutdown_in_progress"
    finally:
        service.drain(timeout_seconds=0)


def test_active_diagnostic_roster_and_sync_workers_drain_cooperatively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one real outer thread for each supported background job kind.
    jobs = _jobs_module(tmp_path, monkeypatch)
    registry = jobs.WorkerRegistry()
    service = jobs.ApiHarnessJobService(registry)
    job_types = {
        "diagnostic-cooperative": "pull_all_treatment_plans_all_fields",
        "roster-cooperative": "active_patient_roster_pull",
        "sync-cooperative": "approved_treatment_plan_sync",
    }
    started = {job_id: Event() for job_id in job_types}

    def run_job(job_id: str) -> None:
        started[job_id].set()
        registry._cancel_events[job_id].wait()
        service._set(job_id, status="cancelled", cancelled_at=jobs._now(), progress_percent=100)

    try:
        monkeypatch.setattr(service, "_run_job", run_job)
        for job_id, job_type in job_types.items():
            _store_job(jobs, service, job_id, job_type)
            registry.admit_job(job_id)
            service._start_worker(job_id)
        assert all(event.wait(1) for event in started.values())

        # When: the service requests shutdown and drains all registered work.
        result = service.drain()

        # Then: all three rows are cancelled and no tracked work survives.
        assert result == jobs.DrainResult(cooperative=True, survivors=())
        assert service.tracked_work_count == 0
        assert {service.get_job(job_id).status for job_id in job_types} == {"cancelled"}
    finally:
        service.drain(timeout_seconds=0)
        registry.join_tracked_for_test()


def test_noncooperative_nested_fetch_is_reported_as_survivor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a nested detail fetch that ignores cancellation until explicitly released.
    jobs = _jobs_module(tmp_path, monkeypatch)
    clock = _Clock()
    release = Event()
    nested_started = Event()
    late_write_attempted = Event()

    def wait_for_futures(
        futures: set[Future[dict[str, object]]], timeout: float,
    ) -> tuple[set[Future[dict[str, object]]], set[Future[dict[str, object]]]]:
        clock.value += timeout
        return set(), futures

    registry = jobs.WorkerRegistry(
        clock=clock,
        future_wait=wait_for_futures,
        thread_join=lambda _thread, _timeout: None,
    )
    service = jobs.ApiHarnessJobService(registry)
    job_id = "sync-noncooperative"
    _store_job(jobs, service, job_id, "approved_treatment_plan_sync")
    registry.admit_job(job_id)

    def run_job(_job_id: str) -> None:
        with registry.detail_executor(job_id, 1, "synthetic-detail") as executor:
            def nested_fetch(_candidate) -> dict[str, object]:
                nested_started.set()
                release.wait()
                return {}

            executor.fetch(nested_fetch, "synthetic").result()
        late_write_attempted.set()
        service._set(job_id, status="completed", completed_at=jobs._now(), progress_percent=100)

    try:
        monkeypatch.setattr(service, "_run_job", run_job)
        service._start_worker(job_id)
        assert nested_started.wait(1)

        # When: drain spends its entire simulated shared budget on the noncooperative future.
        result = service.drain()

        # Then: the exact survivor is durable and never appears cooperatively drained.
        assert clock.value == 15.0
        assert result == jobs.DrainResult(False, (job_id,))
        assert service.tracked_work_count > 0
        assert service.get_job(job_id).status == "stale_or_interrupted"
    finally:
        release.set()
        registry.join_tracked_for_test()
        service.drain(timeout_seconds=0)
    assert late_write_attempted.wait(1)
    assert service.get_job(job_id).status == "stale_or_interrupted"


def test_interrupted_worker_is_terminal_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: active API and sync-ledger rows left behind by a terminated desktop process.
    jobs = _jobs_module(tmp_path, monkeypatch)
    service = jobs.ApiHarnessJobService()
    job_id = "sync-restart"
    try:
        _store_job(jobs, service, job_id, "approved_treatment_plan_sync")
        database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
        started_at = jobs._now()
        with sqlite3.connect(database_path) as database:
            approval = database.execute(
                "INSERT INTO alleva_contract_approvals("
                "contract_version,encrypted_contract_json,contract_sha256,approver_user_id,"
                "approved_at,effective_at) VALUES(?,?,?,?,?,?)",
                ("synthetic-restart-v1", b"synthetic", "a" * 64, 1, started_at, started_at),
            )
            database.execute(
                "INSERT INTO sync_jobs("
                "external_job_id,requested_by_user_id,approval_record_id,status,idempotency_key,"
                "cancel_requested,started_at,counters_json) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, 1, approval.lastrowid, "running", job_id, 0, started_at, "{}"),
            )

        # When: two fresh application instances run startup recovery.
        _fresh_client(tmp_path, monkeypatch).close()
        with sqlite3.connect(database_path) as database:
            first = database.execute(
                "SELECT api.status,api.cancel_requested,api.failed_at,api.current_endpoint,"
                "sync.status,sync.cancel_requested,sync.completed_at "
                "FROM api_harness_jobs AS api JOIN sync_jobs AS sync "
                "ON sync.external_job_id=api.job_id WHERE api.job_id=?",
                (job_id,),
            ).fetchone()
        _fresh_client(tmp_path, monkeypatch).close()
        with sqlite3.connect(database_path) as database:
            second = database.execute(
                "SELECT api.status,api.cancel_requested,api.failed_at,api.current_endpoint,"
                "sync.status,sync.cancel_requested,sync.completed_at "
                "FROM api_harness_jobs AS api JOIN sync_jobs AS sync "
                "ON sync.external_job_id=api.job_id WHERE api.job_id=?",
                (job_id,),
            ).fetchone()

        # Then: both rows are terminal and idempotent, including the original timestamp.
        assert first == second
        assert first is not None
        assert first[0:2] == ("stale_or_interrupted", 1)
        assert first[2] is not None
        assert first[3] == "startup_recovery"
        assert first[4:6] == ("stale_or_interrupted", 1)
        assert datetime.fromisoformat(first[6]).replace(tzinfo=None) == datetime.fromisoformat(first[2])
    finally:
        service.drain(timeout_seconds=0)
