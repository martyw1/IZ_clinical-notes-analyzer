from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import sleep
from typing import ClassVar, Iterator
from urllib.parse import urlparse

import httpx
import pytest

from test_v2_manual_patient_correction import _auth_headers, _fresh_client

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class _MockAllevaState:
    paths: list[str] = field(default_factory=list)
    block_clients: bool = False
    clients_started: Event = field(default_factory=Event)
    release_clients: Event = field(default_factory=Event)
    client_items: list[dict[str, JsonValue]] = field(
        default_factory=lambda: [
            {"clientId": "912", "isActive": True, "levelOfCare": "PHP", "admissionDate": "2026-06-01"}
        ]
    )
    detail_problem: list[str] = field(default_factory=lambda: ["Synthetic clinical problem."])


class _MockAllevaHandler(BaseHTTPRequestHandler):
    state: ClassVar[_MockAllevaState]

    def do_POST(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        if content_length:
            self.rfile.read(content_length)
        type(self).state.paths.append(self.path)
        self._respond({"access_token": "mock-sync-token", "token_type": "Bearer"})

    def do_GET(self) -> None:
        type(self).state.paths.append(self.path)
        path = urlparse(self.path).path
        if path == "/clients":
            type(self).state.clients_started.set()
            if type(self).state.block_clients:
                type(self).state.release_clients.wait(timeout=3)
            self._respond({"items": type(self).state.client_items})
            return
        if path == "/treatment-plans":
            self._respond({"items": [{"id": "plan-912", "clientId": "912", "nextReviewDue": "2026-07-01"}]})
            return
        if path == "/treatment-plans/plan-912/diagnoses":
            self._respond({"items": [{"diagnosisDescription": "Synthetic diagnosis.", "icd10Code": "F10.20"}]})
            return
        if path == "/treatment-plans/plan-912/reviews":
            self._respond({"items": [{"id": "review-912"}]})
            return
        if path == "/treatment-plans/plan-912/reviews/review-912":
            self._respond({"id": "review-912", "reviewDate": "2026-06-15"})
            return
        self._respond({"id": "plan-912", "reasonForAdmission": "Synthetic recovery support.", "problems": [{"problemDescription": type(self).state.detail_problem[0]}], "diagnoses": [{"diagnosisDescription": "Synthetic diagnosis.", "icd10Code": "F10.20"}], "goals": [{"goalDescription": "Synthetic goal."}], "objectives": [{"objectiveDescription": "Synthetic objective."}], "interventions": [{"interventionDescription": "Synthetic intervention."}], "staffSignatureDate": "2026-06-02"})

    def log_message(self, _format: str, *_args: str | int | float | None) -> None:
        return None

    def _respond(self, payload: dict[str, JsonValue]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def _mock_alleva_server(*, block_clients: bool = False, client_items: list[dict[str, JsonValue]] | None = None) -> Iterator[tuple[str, _MockAllevaState]]:
    state = _MockAllevaState(block_clients=block_clients, client_items=client_items or _MockAllevaState().client_items)

    class IsolatedMockAllevaHandler(_MockAllevaHandler):
        pass

    IsolatedMockAllevaHandler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), IsolatedMockAllevaHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        state.release_clients.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _approve_synthetic_contract(client, headers, api_base_url: str = "https://api.allevasoft.com", token_url: str = "https://api.allevasoft.com/connect/token") -> None:
    approved = client.post(
        "/api/v2/alleva-sync/contracts",
        headers=headers,
        json={
            "contract_version": "synthetic-wire-contract-v1",
            "api_base_url": api_base_url,
            "effective_at": "2026-07-10T00:00:00+00:00",
            "vendor_documentation_url": "https://vendor.invalid/docs/synthetic",
            "test_population_reference": "synthetic-wire-population",
            "oauth": {"token_url": token_url, "token_auth_style": "body", "scope": "plans.read"},
            "pagination": {"limit_parameter": "limit", "offset_parameter": "offset", "maximum_page_size": 100, "maximum_records": 100, "maximum_response_bytes": 1048576},
            "rate_limit": {"maximum_requests_per_minute": 10_000, "retry_after_seconds": 1},
            "attachments": {"mode": "metadata_only", "download_allowed": False},
            "endpoints": {
                "clients": {"path": "/clients", "parameters": {}, "field_mappings": {"client_id": "clientId"}},
                "treatment_plans": {"path": "/treatment-plans", "parameters": {}, "field_mappings": {"client_id": "clientId", "plan_id": "id"}},
                "treatment_plan_detail": {"path": "/treatment-plans/{plan_id}", "parameters": {}, "field_mappings": {"signature_date": "staffSignatureDate"}},
                "diagnoses": {"path": "/treatment-plans/{plan_id}/diagnoses", "parameters": {}, "field_mappings": {"description": "diagnosisDescription"}},
                "reviews": {"path": "/treatment-plans/{plan_id}/reviews", "parameters": {}, "field_mappings": {"review_id": "id"}},
                "review_detail": {"path": "/treatment-plans/{plan_id}/reviews/{review_id}", "parameters": {}, "field_mappings": {"review_date": "reviewDate"}},
            },
        },
    )
    assert approved.status_code == 201, approved.text


def test_alleva_sync_is_blocked_until_explicit_approval_and_mapping_are_saved(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    response = client.post("/api/v2/alleva-sync/run", headers=headers)

    assert response.status_code == 409
    assert "sync" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    ("column", "value"),
    (("expires_at", "2000-01-01T00:00:00+00:00"), ("revoked_at", "2026-07-10T00:00:00+00:00")),
)
def test_expired_or_revoked_contract_blocks_sync_before_worker_starts(
    tmp_path,
    monkeypatch,
    column: str,
    value: str,
) -> None:
    # Given: a locally approved synthetic contract whose approval is no longer active.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers)
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute(f"UPDATE alleva_contract_approvals SET {column}=?", (value,))
        database.commit()

    import app.v2.api.alleva_sync_routes as alleva_sync_routes

    def worker_must_not_start(*_args, **_kwargs):
        raise AssertionError("contract gate must reject before the sync worker can reach OAuth or an API endpoint")

    monkeypatch.setattr(alleva_sync_routes.job_service, "create_treatment_plan_sync_job", worker_must_not_start)

    # When: an administrator invokes the real sync route.
    response = client.post("/api/v2/alleva-sync/run", headers=headers)

    # Then: the route safe-denies before it can create a worker or make a network request.
    assert response.status_code == 409
    assert "approved versioned contract" in response.json()["detail"]


def test_approved_alleva_sync_reads_mocked_http_and_persists_normalized_aggregate(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    with _mock_alleva_server() as (base_url, state):
        configured = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={
                "api_base_url": base_url,
                "token_url": f"{base_url}/token",
                "client_id": "mock-client",
                "client_secret": "mock-secret",
                "scopes": "plans.read",
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
                "treatment_plan_endpoint_mapping_validated": True,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")
        started = client.post("/api/v2/alleva-sync/run", headers=headers)
        assert started.status_code == 202
        job_id = started.json()["job_id"]
        database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
        with sqlite3.connect(database_path) as database:
            ledger = database.execute(
                "SELECT contract_version,contract_sha256 FROM sync_jobs JOIN alleva_contract_approvals ON approval_record_id=alleva_contract_approvals.id WHERE external_job_id=?",
                (job_id,),
            ).fetchone()
        assert ledger is not None
        assert ledger[0] == "synthetic-wire-contract-v1"
        assert len(ledger[1]) == 64
        synced = started
        for _ in range(40):
            synced = client.get(f"/api/v2/alleva-sync/jobs/{job_id}", headers=headers)
            if synced.json()["status"] in {"completed", "failed", "cancelled"}:
                break
            sleep(0.05)

        assert synced.json()["status"] == "completed"
        with sqlite3.connect(database_path) as database:
            checkpoints = database.execute(
                "SELECT endpoint_key,page_number,encrypted_records_json FROM sync_checkpoints JOIN sync_jobs ON sync_checkpoints.job_id=sync_jobs.id WHERE external_job_id=? ORDER BY endpoint_key",
                (job_id,),
            ).fetchall()
            provenance = {
                table: database.execute(
                    f"SELECT sync_job_id,approval_record_id,contract_version,contract_sha256 FROM {table} WHERE sync_job_id IS NOT NULL"
                ).fetchall()
                for table in ("treatment_plan_versions", "treatment_review_versions", "diagnosis_snapshots", "evaluation_runs")
            }
        assert [(endpoint_key, page_number) for endpoint_key, page_number, _ in checkpoints] == [("clients", 0), ("treatment_plans", 0)]
        assert all(isinstance(payload, bytes) and b"Synthetic" not in payload for _, _, payload in checkpoints)
        assert all(rows and all(row[0] is not None and row[1] is not None and row[2] == "synthetic-wire-contract-v1" and len(row[3]) == 64 for row in rows) for rows in provenance.values())
        assert synced.json()["records_written"] == 1
        detail = client.get("/api/v2/treatment-plans/912", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["source_mode"] == "alleva_rest_api"
        assert detail.json()["content_snapshot"]["problems"][0]["problem_description"] == "Synthetic clinical problem."
        assert {criterion["source_endpoint"] for criterion in detail.json()["criteria_results"]} == {"Alleva REST"}
        assert {field["source_endpoint"] for field in detail.json()["content_snapshot"]["observed_fields"]} == {"Alleva REST"}
        assert state.paths == ["/token", "/clients?limit=100&offset=0", "/treatment-plans?limit=100&offset=0", "/treatment-plans/plan-912", "/treatment-plans/plan-912/diagnoses", "/treatment-plans/plan-912/reviews", "/treatment-plans/plan-912/reviews/review-912"]

    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    completed = next(item for item in audit if item["action"] == "alleva.treatment_plan_sync.completed")
    assert completed["details"] == {
        "created_treatment_plan_count": 1,
        "imported_patient_count": 1,
        "skipped_plan_count": 0,
        "unchanged_treatment_plan_count": 0,
        "updated_treatment_plan_count": 0,
        "updated_treatment_plan_ids": [],
    }
    assert "mock-secret" not in str(audit)


def test_repeated_sync_updates_same_plan_id_and_leaves_identical_replay_unchanged(tmp_path, monkeypatch) -> None:
    # Given: an approved synthetic source with one stable treatment-plan ID.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"

    with _mock_alleva_server() as (base_url, state):
        configured = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={
                "api_base_url": base_url,
                "token_url": f"{base_url}/token",
                "client_id": "mock-client",
                "client_secret": "mock-secret",
                "scopes": "plans.read",
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
                "treatment_plan_endpoint_mapping_validated": True,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")

        # When: the plan is created, changed under the same ID, then replayed unchanged.
        first = _completed_sync(client, headers)
        assert first["status"] == "completed"
        state.detail_problem[0] = "Synthetic revised clinical problem."
        second = _completed_sync(client, headers)
        assert second["status"] == "completed"
        third = _completed_sync(client, headers)
        assert third["status"] == "completed"

    # Then: two immutable versions exist, the changed version is current, and the replay adds no duplicate.
    detail = client.get("/api/v2/treatment-plans/912", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["content_snapshot"]["problems"][0]["problem_description"] == "Synthetic revised clinical problem."
    queue = client.get("/api/v2/treatment-plans", headers=headers).json()["items"]
    assert queue[0]["treatment_plan_id"] == "plan-912"
    with sqlite3.connect(database_path) as database:
        versions = database.execute(
            "SELECT id,source_record_id,supersedes_version_id FROM treatment_plan_versions ORDER BY id"
        ).fetchall()
    assert len(versions) == 2
    assert [row[1] for row in versions] == ["plan-912", "plan-912"]
    assert versions[1][2] == versions[0][0]

    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    completions = [item for item in audit if item["action"] == "alleva.treatment_plan_sync.completed"]
    assert completions[0]["details"] == {
        "created_treatment_plan_count": 0,
        "imported_patient_count": 1,
        "skipped_plan_count": 0,
        "unchanged_treatment_plan_count": 1,
        "updated_treatment_plan_count": 0,
        "updated_treatment_plan_ids": [],
    }
    assert completions[1]["details"] == {
        "created_treatment_plan_count": 0,
        "imported_patient_count": 1,
        "skipped_plan_count": 0,
        "unchanged_treatment_plan_count": 0,
        "updated_treatment_plan_count": 1,
        "updated_treatment_plan_ids": ["plan-912"],
    }


def _completed_sync(client, headers: dict[str, str]) -> dict[str, JsonValue]:
    started = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert started.status_code == 202, started.text
    payload = started.json()
    for _ in range(80):
        payload = client.get(f"/api/v2/alleva-sync/jobs/{payload['job_id']}", headers=headers).json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        sleep(0.05)
    raise AssertionError("synthetic sync did not reach a terminal state")


def test_approved_alleva_sync_job_can_be_cancelled_while_an_api_page_is_in_flight(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    with _mock_alleva_server(block_clients=True) as (base_url, state):
        configured = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={
                "api_base_url": base_url,
                "token_url": f"{base_url}/token",
                "client_id": "mock-client",
                "client_secret": "mock-secret",
                "scopes": "plans.read",
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
                "treatment_plan_endpoint_mapping_validated": True,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")
        started = client.post("/api/v2/alleva-sync/run", headers=headers)
        assert started.status_code == 202
        job_id = started.json()["job_id"]
        assert state.clients_started.wait(timeout=10), state.paths

        cancelled = client.post(f"/api/v2/api-harness/jobs/{job_id}/cancel", headers=headers)
        assert cancelled.status_code == 200
        state.release_clients.set()
        synced = cancelled
        for _ in range(40):
            synced = client.get(f"/api/v2/alleva-sync/jobs/{job_id}", headers=headers)
            if synced.json()["status"] in {"completed", "failed", "cancelled"}:
                break
            sleep(0.05)

        assert synced.json()["status"] == "cancelled"
        assert state.paths == ["/token", "/clients?limit=100&offset=0"]

    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert any(item["action"] == "alleva.treatment_plan_sync.cancelled" for item in audit)


def test_unexpected_sync_worker_failure_reaches_a_terminal_audited_state(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    import app.v2.services.jobs as jobs

    class SyntheticWorkerFailure(RuntimeError):
        pass

    def fail_sync(*_args, **_kwargs):
        raise SyntheticWorkerFailure("synthetic worker failure")

    monkeypatch.setattr(jobs, "run_treatment_plan_sync", fail_sync)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers, "https://api.allevasoft.com", "https://authorization.allevasoft.com/connect/token")
    started = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    synced = started
    for _ in range(40):
        synced = client.get(f"/api/v2/alleva-sync/jobs/{job_id}", headers=headers)
        if synced.json()["status"] in {"completed", "failed", "cancelled"}:
            break
        sleep(0.05)

    assert synced.json()["status"] == "failed"
    audit = client.get("/api/audit/logs", headers=headers).json()["items"]
    assert any(item["action"] == "alleva.treatment_plan_sync.failed" for item in audit)


def test_failed_sync_keeps_its_approved_contract_binding_and_safe_failure_record(tmp_path, monkeypatch) -> None:
    # Given: an approved synthetic contract and a worker that fails after the job is durable.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    import app.v2.services.jobs as jobs

    class SyntheticWorkerFailure(RuntimeError):
        pass

    def fail_sync(*_args, **_kwargs):
        raise SyntheticWorkerFailure("synthetic worker failure")

    monkeypatch.setattr(jobs, "run_treatment_plan_sync", fail_sync)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers, "https://api.allevasoft.com", "https://authorization.allevasoft.com/connect/token")

    # When: the persisted sync worker reaches its unexpected-failure boundary.
    started = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    synced = started
    for _ in range(40):
        synced = client.get(f"/api/v2/alleva-sync/jobs/{job_id}", headers=headers)
        if synced.json()["status"] in {"completed", "failed", "cancelled"}:
            break
        sleep(0.05)

    # Then: the immutable contract binding survives progress persistence and the DB stores a redacted failure.
    assert synced.json()["status"] == "failed"
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        counters_row = database.execute(
            "SELECT counters_json FROM sync_jobs WHERE external_job_id=?",
            (job_id,),
        ).fetchone()
        failure_row = database.execute(
            "SELECT error_class,safe_message,retryable,attempt FROM sync_failures "
            "JOIN sync_jobs ON sync_failures.job_id=sync_jobs.id WHERE external_job_id=?",
            (job_id,),
        ).fetchone()
    assert counters_row is not None
    counters = json.loads(counters_row[0])
    assert counters["contract_version"] == "synthetic-wire-contract-v1"
    assert len(counters["contract_sha256"]) == 64
    assert failure_row == ("SyntheticWorkerFailure", "Sync worker failed before completion.", 0, 1)


def test_interrupted_sync_can_resume_as_an_idempotent_safe_replay_bound_to_original_contract(tmp_path, monkeypatch) -> None:
    # Given: an approved synthetic contract and an interrupted sync job.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    import app.v2.services.jobs as jobs

    def fail_sync(*_args, **_kwargs):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(jobs, "run_treatment_plan_sync", fail_sync)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers, "https://api.allevasoft.com", "https://authorization.allevasoft.com/connect/token")
    original = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert original.status_code == 202
    original_job_id = original.json()["job_id"]
    for _ in range(40):
        if client.get(f"/api/v2/alleva-sync/jobs/{original_job_id}", headers=headers).json()["status"] == "failed":
            break
        sleep(0.05)

    # When: an administrator requests a resume after the process-safe terminal failure.
    resumed = client.post(f"/api/v2/alleva-sync/jobs/{original_job_id}/resume", headers=headers)

    # Then: the retry has its own durable job record, exact original contract, and safe replay provenance.
    assert resumed.status_code == 202
    resumed_job_id = resumed.json()["job_id"]
    assert resumed_job_id != original_job_id
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        original_approval, resumed_approval, counters_json = database.execute(
            "SELECT original_job.approval_record_id,resumed_job.approval_record_id,resumed_job.counters_json "
            "FROM sync_jobs AS original_job JOIN sync_jobs AS resumed_job "
            "WHERE original_job.external_job_id=? AND resumed_job.external_job_id=?",
            (original_job_id, resumed_job_id),
        ).fetchone()
    assert original_approval == resumed_approval
    assert json.loads(counters_json)["resumed_from_job_id"] == original_job_id


@pytest.mark.parametrize("invalid_state", ("revoked_contract", "mismatched_configuration"))
def test_resume_revalidates_active_contract_and_configuration_before_worker_starts(tmp_path, monkeypatch, invalid_state: str) -> None:
    # Given: a terminal synthetic sync job that was created with a valid approved contract.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    import app.v2.services.jobs as jobs

    def fail_sync(*_args, **_kwargs):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(jobs, "run_treatment_plan_sync", fail_sync)
    configured = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "api_base_url": "https://api.allevasoft.com",
            "token_url": "https://authorization.allevasoft.com/connect/token",
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers, configured.json()["api_base_url"], configured.json()["token_url"])
    original = client.post("/api/v2/alleva-sync/run", headers=headers)
    assert original.status_code == 202
    original_job_id = original.json()["job_id"]
    for _ in range(40):
        if client.get(f"/api/v2/alleva-sync/jobs/{original_job_id}", headers=headers).json()["status"] == "failed":
            break
        sleep(0.05)
    assert client.get(f"/api/v2/alleva-sync/jobs/{original_job_id}", headers=headers).json()["status"] == "failed"

    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    if invalid_state == "revoked_contract":
        with sqlite3.connect(database_path) as database:
            database.execute("UPDATE alleva_contract_approvals SET revoked_at=?", ("2026-07-11T00:00:00+00:00",))
            database.commit()
    else:
        changed = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={"api_base_url": "https://changed.invalid"},
        )
        assert changed.status_code == 200

    import app.v2.api.alleva_sync_routes as alleva_sync_routes

    calls: list[str] = []

    def worker_must_not_start(job_id: str, _actor_id: int, _actor_role: str):
        calls.append(job_id)
        return alleva_sync_routes.job_service.get_job(job_id)

    monkeypatch.setattr(alleva_sync_routes.job_service, "resume_treatment_plan_sync_job", worker_must_not_start)

    # When: an administrator resumes the historical job after its live authorization state changes.
    resumed = client.post(f"/api/v2/alleva-sync/jobs/{original_job_id}/resume", headers=headers)

    # Then: the active gate denies before another worker or network call can start.
    assert resumed.status_code == 409
    assert calls == []


def test_sync_reconciles_active_inactive_discharged_deleted_and_missing_clients(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items = [
        {"clientId": "912", "isActive": True, "levelOfCare": "PHP", "admissionDate": "2026-06-01"},
        {"clientId": "913", "isActive": False},
        {"clientId": "914", "status": "discharged"},
        {"clientId": "915", "status": "deleted"},
    ]

    with _mock_alleva_server(client_items=client_items) as (base_url, _state):
        configured = client.patch(
            "/api/api-configuration",
            headers=headers,
            json={
                "api_base_url": base_url,
                "token_url": f"{base_url}/token",
                "client_id": "mock-client",
                "client_secret": "mock-secret",
                "scopes": "plans.read",
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
                "treatment_plan_endpoint_mapping_validated": True,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")
        database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
        with sqlite3.connect(database_path) as database:
            facility_id = database.execute("SELECT id FROM facilities WHERE facility_key='r3-default'").fetchone()[0]
            database.execute(
                "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
                "VALUES(?, '916', 'alleva_rest_api', 'active', '2026-07-10T00:00:00+00:00', '2026-07-10T00:00:00+00:00')",
                (facility_id,),
            )
            database.commit()
        started = client.post("/api/v2/alleva-sync/run", headers=headers)
        assert started.status_code == 202
        job_id = started.json()["job_id"]
        synced = started
        for _ in range(40):
            synced = client.get(f"/api/v2/alleva-sync/jobs/{job_id}", headers=headers)
            if synced.json()["status"] in {"completed", "failed", "cancelled"}:
                break
            sleep(0.05)

    assert synced.json()["status"] == "completed"
    with sqlite3.connect(database_path) as database:
        lifecycle_states = dict(
            database.execute(
                "SELECT canonical_client_id,lifecycle_state FROM patients WHERE source_system='alleva_rest_api'"
            ).fetchall()
        )
        outcomes = set(
            database.execute(
                "SELECT source_record_id,outcome FROM reconciliation_outcomes "
                "JOIN sync_jobs ON reconciliation_outcomes.job_id=sync_jobs.id WHERE external_job_id=?",
                (job_id,),
            ).fetchall()
        )
    assert {client_id: lifecycle_states[client_id] for client_id in ("912", "913", "914", "915", "916")} == {
        "912": "active",
        "913": "inactive",
        "914": "discharged",
        "915": "deleted",
        "916": "missing",
    }
    assert outcomes == {("912", "active"), ("913", "inactive"), ("914", "discharged"), ("915", "deleted"), ("916", "missing")}


def test_sync_retries_rate_limited_request_before_accepting_a_page() -> None:
    from app.v2.services.alleva_sync import _get_with_retry

    request_count = 0

    def response_for_request(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(429 if request_count == 1 else 200, json={"items": []})

    with httpx.Client(transport=httpx.MockTransport(response_for_request)) as http_client:
        response = _get_with_retry(
            http_client,
            "https://synthetic.invalid/clients",
            None,
            {},
            lambda: False,
            0,
        )

    assert response.status_code == 200
    assert request_count == 2


def test_sync_cancellation_interrupts_retry_backoff_without_extra_request() -> None:
    from app.v2.services.alleva_sync import AllevaSyncCancelled, _get_with_retry

    cancelled = Event()
    request_count = 0

    def response_for_request(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(429, json={"items": []})

    def cancel_after_first_backoff() -> None:
        time.sleep(0.05)
        cancelled.set()

    thread = Thread(target=cancel_after_first_backoff)
    thread.start()
    with httpx.Client(transport=httpx.MockTransport(response_for_request)) as http_client:
        with pytest.raises(AllevaSyncCancelled):
            _get_with_retry(
                http_client,
                "https://synthetic.invalid/clients",
                None,
                {},
                cancelled.is_set,
                1,
            )
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert request_count == 1
