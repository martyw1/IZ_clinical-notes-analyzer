from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from test_v2_distinct_alleva_jobs import _configure, _wait
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_reloaded_job_events_keep_their_utc_instant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str,
) -> None:
    # Given: SQLite has persisted a synthetic UTC job, stripping its timezone.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    from app.v2.db import SessionLocal
    from app.v2.models import ApiHarnessJobRecord

    instant = datetime(2026, 9, 10, 18, 25, 30, tzinfo=timezone.utc)
    terminal_field = {"completed": "completed_at", "failed": "failed_at", "cancelled": "cancelled_at"}[status]
    with SessionLocal() as db:
        row = ApiHarnessJobRecord(
            job_id="sync-synthetic-time", job_type="approved_treatment_plan_sync",
            status=status, created_at=instant, started_at=instant, updated_at=instant,
            last_heartbeat_at=instant,
        )
        setattr(row, terminal_field, instant)
        db.add(row)
        db.commit()

    # When: a persisted job is returned through the actual last-run API.
    response = client.get("/api/v2/alleva-sync-last-run", headers=headers)

    # Then: every populated event has an explicit UTC offset and the same instant.
    assert response.status_code == 200
    payload = response.json()
    for field in ("created_at", "started_at", "updated_at", "last_heartbeat_at", terminal_field):
        parsed = datetime.fromisoformat(payload[field])
        assert parsed.utcoffset() == timedelta(0), field
        assert parsed == instant, field
    for field in {"completed_at", "failed_at", "cancelled_at"} - {terminal_field}:
        assert payload[field] is None


def test_sync_timeout_cause_survives_restart_without_sensitive_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a configured synthetic sync whose network operation times out.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    _configure(client, headers, "https://mock.invalid")
    from app.v2.services import jobs
    from app.v2.services.alleva_sync import AllevaSyncError, AllevaSyncResult

    def fail_sync(*_args: None, **_kwargs: None) -> AllevaSyncResult:
        try:
            raise httpx.ReadTimeout("synthetic-private-token patient-synthetic-detail")
        except httpx.ReadTimeout as exc:
            raise AllevaSyncError("synthetic-private-wrapper") from exc

    monkeypatch.setattr(jobs, "run_treatment_plan_sync", fail_sync)
    started = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    current = _wait(client, headers, f"/api/v2/alleva-sync/jobs/{job_id}")
    assert current["status"] == "failed"

    # When: the app reloads its durable job history after a restart.
    restarted = _fresh_client(tmp_path, monkeypatch)
    response = restarted.get(
        f"/api/v2/alleva-sync/jobs/{job_id}", headers=_auth_headers(restarted),
    )

    # Then: both live and persisted job feedback explain the timeout safely.
    assert response.status_code == 200
    assert "timed out" in response.json()["message"].lower()
    assert response.json()["message"] == current["message"]
    assert "synthetic-private" not in response.text
    assert "patient-synthetic-detail" not in response.text
