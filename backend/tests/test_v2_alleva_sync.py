from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import sleep
from typing import ClassVar, Iterator
from urllib.parse import urlparse

from test_v2_manual_patient_correction import _auth_headers, _fresh_client

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class _MockAllevaState:
    paths: list[str] = field(default_factory=list)
    block_clients: bool = False
    clients_started: Event = field(default_factory=Event)
    release_clients: Event = field(default_factory=Event)


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
            self._respond({"items": [{"clientId": "912", "isActive": True, "levelOfCare": "PHP", "admissionDate": "2026-06-01"}]})
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
        self._respond({"id": "plan-912", "reasonForAdmission": "Synthetic recovery support.", "problems": [{"problemDescription": "Synthetic clinical problem."}], "diagnoses": [{"diagnosisDescription": "Synthetic diagnosis.", "icd10Code": "F10.20"}], "goals": [{"goalDescription": "Synthetic goal."}], "objectives": [{"objectiveDescription": "Synthetic objective."}], "interventions": [{"interventionDescription": "Synthetic intervention."}], "staffSignatureDate": "2026-06-02"})

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
def _mock_alleva_server(*, block_clients: bool = False) -> Iterator[tuple[str, _MockAllevaState]]:
    state = _MockAllevaState(block_clients=block_clients)

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


def _approve_synthetic_contract(client, headers) -> None:
    approved = client.post(
        "/api/v2/alleva-sync/contracts",
        headers=headers,
        json={
            "contract_version": "synthetic-wire-contract-v1",
            "effective_at": "2026-07-10T00:00:00+00:00",
            "vendor_documentation_url": "https://vendor.invalid/docs/synthetic",
            "test_population_reference": "synthetic-wire-population",
            "oauth": {"token_auth_style": "body", "scope": "plans.read"},
            "pagination": {"limit_parameter": "limit", "offset_parameter": "offset", "maximum_page_size": 100},
            "rate_limit": {"maximum_requests_per_minute": 60, "retry_after_seconds": 1},
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
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
                "treatment_plan_endpoint_mapping_validated": True,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers)
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
    assert completed["details"] == {"imported_patient_count": 1, "skipped_plan_count": 0}
    assert "mock-secret" not in str(audit)


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
                "api_enabled": True,
                "treatment_plan_sync_enabled": True,
                "treatment_plan_sync_approved": True,
                "treatment_plan_endpoint_mapping_validated": True,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers)
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
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
            "treatment_plan_endpoint_mapping_validated": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers)
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
