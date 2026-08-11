from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread
from time import sleep
from typing import ClassVar, Iterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from test_v2_manual_patient_correction import _auth_headers, _fresh_client

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class _MockAllevaState:
    paths: list[str] = field(default_factory=list)
    request_metadata: list[dict[str, str]] = field(default_factory=list)
    block_clients: bool = False
    clients_started: Event = field(default_factory=Event)
    release_clients: Event = field(default_factory=Event)
    client_items: list[dict[str, JsonValue]] = field(
        default_factory=lambda: [
            {"id": "912", "mrn": "912", "status": "Active", "levelOfCare": "PHP", "admissionDateTime": "2026-06-01T00:00:00Z"}
        ]
    )
    plan_items: list[dict[str, JsonValue]] = field(
        default_factory=lambda: [
            {"id": "plan-912", "client": {"id": "912", "route": "/clients/912"}, "nextReviewDue": "2026-07-01"}
        ]
    )
    detail_problem: list[str] = field(default_factory=lambda: ["Synthetic clinical problem."])
    published_shape: bool = True
    plan_delay_seconds: float = 0.0
    active_plan_requests: list[int] = field(default_factory=lambda: [0])
    peak_plan_requests: list[int] = field(default_factory=lambda: [0])
    plan_request_lock: Lock = field(default_factory=Lock)
    global_plan_collection: bool = True


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
        authorization = self.headers.get("authorization", "")
        type(self).state.request_metadata.append({
            "accept": self.headers.get("accept", ""),
            "authorization_scheme": authorization.partition(" ")[0],
            "x_version": self.headers.get("x-version", ""),
        })
        path = urlparse(self.path).path
        if path == "/clients":
            type(self).state.clients_started.set()
            if type(self).state.block_clients:
                type(self).state.release_clients.wait(timeout=3)
            self._respond({"items": type(self).state.client_items})
            return
        if path == "/treatment-plans":
            query = parse_qs(urlparse(self.path).query)
            patient_ids = query.get("ClientId", [])
            if "clientId" in query or (not type(self).state.global_plan_collection and len(patient_ids) != 1):
                self.send_error(400, "Exact ClientId query parameter is required")
                return
            with type(self).state.plan_request_lock:
                type(self).state.active_plan_requests[0] += 1
                type(self).state.peak_plan_requests[0] = max(
                    type(self).state.peak_plan_requests[0],
                    type(self).state.active_plan_requests[0],
                )
            try:
                if type(self).state.plan_delay_seconds:
                    sleep(type(self).state.plan_delay_seconds)
                plans = type(self).state.plan_items
                if patient_ids:
                    patient_id = patient_ids[0]
                    plans = [plan for plan in plans if _plan_client_id(plan) == patient_id]
                if not patient_ids:
                    offset = int(query.get("Cursor", ["0"])[0])
                    limit = int(query.get("Limit", [str(len(plans) or 1)])[0])
                    plans = plans[offset : offset + limit]
                self._respond({"items": plans})
            finally:
                with type(self).state.plan_request_lock:
                    type(self).state.active_plan_requests[0] -= 1
            return
        if path == "/treatment-reviews":
            self._respond({"items": []})
            return
        path_parts = path.strip("/").split("/")
        plan_id = path_parts[1] if len(path_parts) >= 2 and path_parts[0] == "treatment-plans" else "plan-912"
        if len(path_parts) == 3 and path_parts[2] in {"diagnosis", "diagnoses"}:
            diagnosis = {"description": "Synthetic diagnosis.", "code": "F10.20"} if type(self).state.published_shape else {"diagnosisDescription": "Synthetic diagnosis.", "icd10Code": "F10.20"}
            self._respond({"items": [diagnosis]})
            return
        if len(path_parts) == 3 and path_parts[2] == "reviews":
            review_id = f"review-{plan_id.removeprefix('plan-')}"
            self._respond({"items": [{"id": review_id}]})
            return
        if len(path_parts) == 4 and path_parts[2] == "reviews":
            self._respond({"id": path_parts[3], "reviewDate": "2026-06-15"})
            return
        problem = type(self).state.detail_problem[0] if plan_id == "plan-912" else f"Synthetic problem for {plan_id}."
        if type(self).state.published_shape:
            detail_id: str | int = int(plan_id) if plan_id.isdigit() else plan_id
            self._respond({"id": detail_id, "reasonForAdmission": "Synthetic recovery support.", "lastModified": "2026-07-12T12:00:00Z", "problems": [{"description": problem, "behavioralDefinitions": [{"description": "Synthetic behavior."}], "goals": [{"description": "Synthetic goal.", "objectives": [{"description": "Synthetic objective.", "interventions": [{"description": "Synthetic intervention."}]}]}]}]})
            return
        self._respond({"id": plan_id, "reasonForAdmission": "Synthetic recovery support.", "problems": [{"problemDescription": problem}], "diagnoses": [{"diagnosisDescription": "Synthetic diagnosis.", "icd10Code": "F10.20"}], "goals": [{"goalDescription": "Synthetic goal."}], "objectives": [{"objectiveDescription": "Synthetic objective."}], "interventions": [{"interventionDescription": "Synthetic intervention."}], "staffSignatureDate": "2026-06-02"})

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
def _mock_alleva_server(
    *,
    block_clients: bool = False,
    client_items: list[dict[str, JsonValue]] | None = None,
    plan_items: list[dict[str, JsonValue]] | None = None,
    published_shape: bool = True,
    plan_delay_seconds: float = 0.0,
    global_plan_collection: bool = True,
) -> Iterator[tuple[str, _MockAllevaState]]:
    defaults = _MockAllevaState()
    resolved_clients = client_items or defaults.client_items
    state = _MockAllevaState(
        block_clients=block_clients,
        client_items=[_with_synthetic_mrn(item) for item in resolved_clients],
        plan_items=plan_items or defaults.plan_items,
        published_shape=published_shape,
        plan_delay_seconds=plan_delay_seconds,
        global_plan_collection=global_plan_collection,
    )

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


def _plan_client_id(plan: dict[str, JsonValue]) -> str:
    direct = plan.get("clientId")
    if isinstance(direct, str | int) and not isinstance(direct, bool):
        return str(direct)
    client = plan.get("client")
    if isinstance(client, str):
        return client.rstrip("/").rsplit("/", 1)[-1]
    if isinstance(client, dict):
        nested = client.get("id")
        if isinstance(nested, str | int) and not isinstance(nested, bool):
            return str(nested)
        route = client.get("route") or client.get("href")
        if isinstance(route, str):
            return route.rstrip("/").rsplit("/", 1)[-1]
    return ""


def _with_synthetic_mrn(item: dict[str, JsonValue]) -> dict[str, JsonValue]:
    mrn = item.get("mrn") or item.get("id") or item.get("clientId")
    return {**item, "mrn": mrn} if isinstance(mrn, str | int) and not isinstance(mrn, bool) else item


def _approve_synthetic_contract(_client, _headers, api_base_url: str = "https://api.allevasoft.com", token_url: str = "https://api.allevasoft.com/connect/token") -> None:
    _store_contract({
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
                "clients": {"path": "/clients", "parameters": {}, "field_mappings": {"client_id": "clientId", "mrn": "mrn"}},
                "treatment_plans": {"path": "/treatment-plans", "parameters": {"client_id": "ClientId"}, "field_mappings": {"client_id": "clientId", "plan_id": "id"}},
                "treatment_plan_detail": {"path": "/treatment-plans/{plan_id}", "parameters": {}, "field_mappings": {"signature_date": "staffSignatureDate"}},
                "diagnoses": {"path": "/treatment-plans/{plan_id}/diagnoses", "parameters": {}, "field_mappings": {"description": "diagnosisDescription"}},
                "reviews": {"path": "/treatment-plans/{plan_id}/reviews", "parameters": {}, "field_mappings": {"review_id": "id"}},
                "review_detail": {"path": "/treatment-plans/{plan_id}/reviews/{review_id}", "parameters": {}, "field_mappings": {"review_date": "reviewDate"}},
            },
        }
    )


def _approve_published_v1_contract(_client, _headers, api_base_url: str, token_url: str) -> None:
    _store_contract({
            "contract_version": "published-alleva-v1-test",
            "api_base_url": api_base_url,
            "effective_at": "2026-07-10T00:00:00+00:00",
            "vendor_documentation_url": "https://api.allevasoft.com/swagger/v1/swagger.json",
            "test_population_reference": "synthetic-published-shape-population",
            "oauth": {"token_url": token_url, "token_auth_style": "body", "scope": "plans.read"},
            "pagination": {"limit_parameter": "Limit", "offset_parameter": "Cursor", "maximum_page_size": 100, "maximum_records": 100, "maximum_response_bytes": 1048576},
            "rate_limit": {"maximum_requests_per_minute": 10_000, "retry_after_seconds": 1},
            "attachments": {"mode": "disabled", "download_allowed": False},
            "endpoints": {
                "clients": {"path": "/clients", "parameters": {"limit": "Limit", "offset": "Cursor"}, "field_mappings": {"client_id": "id", "mrn": "mrn", "lifecycle_status": "status", "level_of_care": "levelOfCare", "admission_date": "admissionDateTime"}},
                "treatment_plans": {"path": "/treatment-plans", "parameters": {"limit": "Limit", "offset": "Cursor", "client_id": "ClientId"}, "field_mappings": {"client_id": "client.id", "client_reference": "client.route", "plan_id": "id"}},
                "treatment_plan_detail": {"path": "/treatment-plans/{plan_id}", "parameters": {}, "field_mappings": {"reason_for_admission": "reasonForAdmission", "last_modified": "lastModified", "problem_description": "problems.description", "behavioral_definition": "problems.behavioralDefinitions.description", "goal_description": "problems.goals.description", "objective_description": "problems.goals.objectives.description", "intervention_description": "problems.goals.objectives.interventions.description"}},
                "diagnoses": {"path": "/treatment-plans/{plan_id}/diagnosis", "parameters": {}, "field_mappings": {"description": "description", "icd10_code": "code"}},
                "reviews": {"path": "/treatment-reviews", "parameters": {"limit": "Limit", "offset": "Cursor"}, "field_mappings": {"review_id": "id", "treatment_plan_review_id": "treatmentPlanReviewId"}},
                "review_detail": {"path": "/treatment-reviews/{review_id}", "parameters": {}, "field_mappings": {"review_date": "createdDated"}},
            },
        }
    )


def _store_contract(payload: dict[str, object]) -> None:
    from app.v2.api.models import AllevaContractApprovalIn
    from app.v2.db import SessionLocal
    from app.v2.services.alleva_contracts import approve_contract

    with SessionLocal() as database:
        approve_contract(database, AllevaContractApprovalIn.model_validate(payload), 1)


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
def test_expired_or_revoked_manual_contract_is_replaced_before_worker_starts(
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
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
        },
    )
    assert configured.status_code == 200
    _approve_synthetic_contract(client, headers)
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute(f"UPDATE alleva_contract_approvals SET {column}=?", (value,))
        database.commit()

    import app.v2.api.alleva_sync_routes as alleva_sync_routes

    captured_contracts = []

    def capture_without_starting(_actor_id, _actor_role, contract):
        captured_contracts.append(contract)
        raise ValueError("synthetic active job")

    monkeypatch.setattr(alleva_sync_routes.job_service, "create_treatment_plan_sync_job", capture_without_starting)

    # When: an administrator invokes the real sync route.
    response = client.post("/api/v2/alleva-sync/run", headers=headers)

    # Then: the unusable manual record is replaced without making a network request.
    assert response.status_code == 409
    assert captured_contracts[0].contract_version.startswith("alleva-rest-v1-built-in-")


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
        assert ledger[0].startswith("alleva-rest-v1-built-in-")
        assert len(ledger[1]) == 64
        synced = started
        for _ in range(40):
            synced = client.get(f"/api/v2/alleva-sync/jobs/{job_id}", headers=headers)
            if synced.json()["status"] in {"completed", "failed", "cancelled"}:
                break
            sleep(0.05)

        assert synced.json()["status"] == "completed", state.paths
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
        assert [(endpoint_key.split(":", 1)[0], page_number) for endpoint_key, page_number, _ in checkpoints] == [("clients", 0), ("treatment_plans", 0)]
        assert all(isinstance(payload, bytes) and b"Synthetic" not in payload for _, _, payload in checkpoints)
        assert provenance["treatment_review_versions"] == []
        assert all(
            rows and all(
                row[0] is not None
                and row[1] is not None
                and row[2].startswith("alleva-rest-v1-built-in-")
                and len(row[3]) == 64
                for row in rows
            )
            for table, rows in provenance.items()
            if table != "treatment_review_versions"
        )
        assert synced.json()["records_written"] == 1
        detail = client.get("/api/v2/treatment-plans/912", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["source_mode"] == "alleva_rest_api"
        assert detail.json()["content_snapshot"]["problems"][0]["problem_description"] == "Synthetic clinical problem."
        assert {criterion["source_endpoint"] for criterion in detail.json()["criteria_results"]} == {"Alleva REST"}
        assert {field["source_endpoint"] for field in detail.json()["content_snapshot"]["observed_fields"]} == {"Alleva REST"}
        assert state.paths == [
            "/token",
            "/clients?Limit=100&Cursor=0&api-version=1.0",
            "/treatment-plans?Limit=100&Cursor=0&api-version=1.0&StartDate=2000-01-01T16%3A03",
            "/treatment-plans/plan-912?api-version=1.0",
            "/treatment-plans/plan-912/diagnosis?api-version=1.0",
        ]
        assert state.request_metadata == [
            {"accept": "application/json", "authorization_scheme": "Bearer", "x_version": "1.0"}
        ] * 4

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


def test_approved_sync_populates_every_treatment_plan_for_the_same_patient(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    plan_items: list[dict[str, JsonValue]] = [
        {"id": "plan-912", "client": {"id": "912", "route": "/clients/912"}, "nextReviewDue": "2026-07-01"},
        {"id": "plan-913", "client": {"id": "912", "route": "/clients/912"}, "nextReviewDue": "2026-08-01"},
    ]

    with _mock_alleva_server(plan_items=plan_items) as (base_url, _state):
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
                "requests_per_minute": 10_000,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")

        synced = _completed_sync(client, headers)

    assert synced["status"] == "completed"
    assert synced["records_written"] == 2
    queue = client.get("/api/v2/treatment-plans", headers=headers)
    assert queue.status_code == 200
    assert {item["treatment_plan_id"] for item in queue.json()["items"]} == {"plan-912", "plan-913"}
    exported = client.get("/api/v2/exports/treatment-plans.csv", headers=headers)
    assert exported.status_code == 200
    assert {row["treatment_plan_id"] for row in csv.DictReader(io.StringIO(exported.text))} == {"plan-912", "plan-913"}
    second_detail = client.get("/api/v2/treatment-plans/912/plan-913", headers=headers)
    assert second_detail.status_code == 200
    assert second_detail.json()["content_snapshot"]["plan_id"] == "plan-913"


def test_patient_plan_list_accepts_vendor_page_larger_than_fair_request_within_global_budget(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items: list[dict[str, JsonValue]] = [
        {"id": str(patient_id), "status": "Active"}
        for patient_id in range(912, 922)
    ]
    plan_items: list[dict[str, JsonValue]] = [
        {"id": "plan-912", "client": {"id": "912", "route": "/clients/912"}},
        {"id": "plan-913", "client": {"id": "912", "route": "/clients/912"}},
    ]

    with _mock_alleva_server(client_items=client_items, plan_items=plan_items) as (base_url, _state):
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
                "sync_limit": 10,
                "requests_per_minute": 10_000,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")

        synced = _completed_sync(client, headers)

    assert synced["status"] == "completed"
    assert synced["records_written"] == 2
    queue = client.get("/api/v2/treatment-plans", headers=headers)
    assert {item["treatment_plan_id"] for item in queue.json()["items"]} == {"plan-912", "plan-913"}


def test_patient_scoped_single_plan_pages_do_not_repeat_ignored_vendor_cursor(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items: list[dict[str, JsonValue]] = [
        {"id": str(patient_id), "status": "Active"}
        for patient_id in range(912, 922)
    ]
    plan_items: list[dict[str, JsonValue]] = [
        {"id": f"plan-{patient_id}", "client": {"id": str(patient_id), "route": f"/clients/{patient_id}"}}
        for patient_id in range(912, 922)
    ]

    with _mock_alleva_server(client_items=client_items, plan_items=plan_items) as (base_url, _state):
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
                "sync_limit": 10,
                "requests_per_minute": 10_000,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")

        synced = _completed_sync(client, headers)

    assert synced["status"] == "completed"
    assert synced["records_written"] == 10


def test_global_plan_collection_is_requested_once_without_patient_filter(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items: list[dict[str, JsonValue]] = [
        {"id": str(patient_id), "status": "Active"}
        for patient_id in range(912, 916)
    ]
    plan_items: list[dict[str, JsonValue]] = [
        {"id": f"plan-{patient_id}", "client": {"id": str(patient_id), "route": f"/clients/{patient_id}"}}
        for patient_id in range(912, 916)
    ]

    with _mock_alleva_server(
        client_items=client_items,
        plan_items=plan_items,
        plan_delay_seconds=0.08,
    ) as (base_url, state):
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
                "requests_per_minute": 10_000,
            },
        )
        assert configured.status_code == 200
        _approve_synthetic_contract(client, headers, base_url, f"{base_url}/token")

        synced = _completed_sync(client, headers)

    assert synced["status"] == "completed"
    assert synced["records_written"] == 4
    assert state.peak_plan_requests[0] == 1
    plan_queries = [path for path in state.paths if path.startswith("/treatment-plans?")]
    assert len(plan_queries) == 1
    assert "ClientId" not in parse_qs(urlparse(plan_queries[0]).query)


def test_published_alleva_v1_numeric_nested_ids_populate_queue_and_roster(tmp_path, monkeypatch) -> None:
    # Given: payloads shaped like Alleva's published v1 Client and TreatmentPlan schemas.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    client_items: list[dict[str, JsonValue]] = [{"id": 912, "status": "Active", "levelOfCare": "PHP", "admissionDateTime": "2026-06-01T12:00:00Z"}]
    plan_items: list[dict[str, JsonValue]] = [{"id": 4815, "client": {"id": 912, "route": "/clients/912"}, "lastModified": "2026-07-12T12:00:00Z"}]

    with _mock_alleva_server(client_items=client_items, plan_items=plan_items, published_shape=True) as (base_url, state):
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
            },
        )
        assert configured.status_code == 200
        _approve_published_v1_contract(client, headers, base_url, f"{base_url}/token")

        # When: the approved operational import runs.
        synced = _completed_sync(client, headers)

    # Then: the real numeric/nested identifiers populate both operational lists.
    assert synced["status"] == "completed"
    assert synced["records_written"] == 1
    queue = client.get("/api/v2/treatment-plans", headers=headers).json()["items"]
    assert [(item["patient_id"], item["treatment_plan_id"]) for item in queue] == [("912", "4815")]
    roster = client.get("/api/v2/patient-roster", headers=headers).json()["items"]
    assert [
        (item["mrn"], item["treatment_plans"][0]["treatment_plan_id"])
        for item in roster
    ] == [("912", "4815")]
    assert "/treatment-plans/4815/diagnosis?api-version=1.0" in state.paths
    assert any(path.startswith("/treatment-plans?") for path in state.paths)
    assert not any("ClientId=" in path for path in state.paths)
    assert not any("clientId=" in path for path in state.paths)
    assert not any(path.startswith("/treatment-reviews") for path in state.paths)


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
        assert state.paths == ["/token", "/clients?Limit=100&Cursor=0&api-version=1.0"]

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
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
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
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
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
    assert counters["contract_version"].startswith("alleva-rest-v1-built-in-")
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
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
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
            "client_id": "mock-client",
            "client_secret": "mock-secret",
            "scopes": "plans.read",
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
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
        {"id": "912", "status": "Active", "levelOfCare": "PHP", "admissionDateTime": "2026-06-01T00:00:00Z"},
        {"id": "913", "status": "inactive"},
        {"id": "914", "status": "discharged"},
        {"id": "915", "status": "deleted"},
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
