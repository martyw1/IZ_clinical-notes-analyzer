from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import sleep
from typing import ClassVar, Iterator
from urllib.parse import parse_qs, urlparse

from test_v2_alleva_sync import (
    JsonValue,
    _MockAllevaHandler,
    _MockAllevaState,
    _approve_published_v1_contract,
    _mock_alleva_server,
)
from test_v2_auth_rbac import _create_user
from test_v2_manual_patient_correction import _auth_headers, _fresh_client

TERMINAL = {"completed", "completed_with_warnings", "failed", "cancelled"}


def _configure(client, headers: dict[str, str], base_url: str, *, pagination_limit: int = 100) -> None:
    response = client.patch(
        "/api/api-configuration",
        headers=headers,
        json={
            "api_base_url": base_url,
            "token_url": f"{base_url}/token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "scopes": "plans.read",
            "pagination_limit": pagination_limit,
            "sync_limit": 100,
            "requests_per_minute": 10_000,
            "api_enabled": True,
            "treatment_plan_sync_enabled": True,
            "treatment_plan_sync_approved": True,
        },
    )
    assert response.status_code == 200
    _approve_published_v1_contract(client, headers, base_url, f"{base_url}/token")


def _wait(client, headers: dict[str, str], route: str) -> dict[str, JsonValue]:
    current = client.get(route, headers=headers)
    for _ in range(80):
        assert current.status_code == 200
        if current.json()["status"] in TERMINAL:
            return current.json()
        sleep(0.05)
        current = client.get(route, headers=headers)
    if current.status_code == 200 and current.json()["status"] in TERMINAL:
        return current.json()
    raise AssertionError(f"Job did not reach a terminal state: {current.json()}")


def test_active_roster_pull_is_distinct_plan_independent_and_restart_queryable(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    clients = [{"id": "roster-101", "status": "Active", "firstName": "Never Persist"}]
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        facility_id = database.execute("SELECT id FROM facilities WHERE facility_key='r3-default'").fetchone()[0]
        database.execute(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(?, 'roster-missing-199', 'alleva_rest_api', 'active', '2026-07-01', '2026-07-01')",
            (facility_id,),
        )
        database.commit()

    with _mock_alleva_server(client_items=clients, plan_items=[]) as (base_url, state):
        _configure(client, headers, base_url)
        started = client.post("/api/v2/patient-roster/pull", headers=headers)
        assert started.status_code == 202
        job_id = started.json()["job_id"]
        completed = _wait(client, headers, f"/api/v2/patient-roster/jobs/{job_id}")

    assert completed["job_type"] == "active_patient_roster_pull"
    assert completed["status"] == "completed"
    assert completed["records_written"] == 1
    assert completed["phase"] == "completed"
    assert "roster" in completed["message"].lower()
    assert state.paths == ["/token", "/clients?Limit=100&Cursor=0&api-version=1.0"]
    roster = client.get("/api/v2/patient-roster", headers=headers)
    assert roster.status_code == 200
    roster_items = {item["mrn"]: item for item in roster.json()["items"]}
    assert roster_items["roster-101"]["lifecycle_state"] == "active"
    assert roster_items["roster-missing-199"]["lifecycle_state"] == "missing"
    assert all(item["treatment_plans"] == [] for item in roster_items.values())
    assert "Never Persist" not in roster.text

    restarted = _fresh_client(tmp_path, monkeypatch)
    restarted_headers = _auth_headers(restarted)
    recovered = restarted.get(f"/api/v2/patient-roster/jobs/{job_id}", headers=restarted_headers)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "completed"
    assert recovered.json()["records_written"] == 1
    latest = restarted.get("/api/v2/patient-roster/jobs/latest", headers=restarted_headers)
    assert latest.status_code == 200
    assert latest.json()["job_id"] == job_id


class _PartialRosterHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[str]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        if length:
            self.rfile.read(length)
        type(self).requests.append(self.path)
        self._respond(200, {"access_token": "synthetic-token", "token_type": "Bearer"})

    def do_GET(self) -> None:
        type(self).requests.append(self.path)
        cursor = parse_qs(urlparse(self.path).query).get("Cursor", ["0"])[0]
        if cursor == "0":
            self._respond(200, {"items": [{"id": "seen-201", "status": "Active"}, {"id": "seen-202", "status": "Active"}]})
            return
        self._respond(503, {"error": "sensitive vendor detail must not surface"})

    def _respond(self, status: int, payload: dict[str, JsonValue]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: str | int | float | None) -> None:
        return None


@contextmanager
def _partial_roster_server() -> Iterator[str]:
    _PartialRosterHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PartialRosterHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_partial_roster_pagination_upserts_seen_without_deactivating_unseen(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        facility_id = database.execute("SELECT id FROM facilities WHERE facility_key='r3-default'").fetchone()[0]
        database.execute(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(?, 'unseen-299', 'alleva_rest_api', 'active', '2026-07-01', '2026-07-01')",
            (facility_id,),
        )
        database.commit()

    with _partial_roster_server() as base_url:
        _configure(client, headers, base_url, pagination_limit=2)
        started = client.post("/api/v2/patient-roster/pull", headers=headers)
        assert started.status_code == 202
        completed = _wait(client, headers, f"/api/v2/patient-roster/jobs/{started.json()['job_id']}")

    assert completed["status"] == "completed_with_warnings"
    assert completed["records_written"] == 2
    assert completed["warnings_count"] == 1
    assert "partial" in completed["message"].lower()
    assert "sensitive vendor detail" not in completed["message"]
    with sqlite3.connect(database_path) as database:
        lifecycles = dict(database.execute(
            "SELECT canonical_client_id,lifecycle_state FROM patients WHERE source_system='alleva_rest_api'"
        ).fetchall())
    assert lifecycles == {"seen-201": "active", "seen-202": "active", "unseen-299": "active"}


@contextmanager
def _partial_detail_server() -> Iterator[tuple[str, _MockAllevaState]]:
    state = _MockAllevaState(plan_items=[
        {"id": "plan-912", "client": {"id": "912", "route": "/clients/912"}},
        {"id": "plan-bad", "client": {"id": "912", "route": "/clients/912"}},
    ])

    class Handler(_MockAllevaHandler):
        def do_GET(self) -> None:
            if urlparse(self.path).path == "/treatment-plans/plan-bad":
                type(self).state.paths.append(self.path)
                self.send_error(503, "synthetic detail failure")
                return
            super().do_GET()

    Handler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approved_sync_warning_completes_good_details_and_deduplicates_on_rerun(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)

    with _partial_detail_server() as (base_url, _state):
        _configure(client, headers, base_url)
        first = client.post("/api/v2/alleva-sync/run", headers=headers)
        assert first.status_code == 202
        first_result = _wait(client, headers, f"/api/v2/alleva-sync/jobs/{first.json()['job_id']}")
        second = client.post("/api/v2/alleva-sync/run", headers=headers)
        assert second.status_code == 202
        second_result = _wait(client, headers, f"/api/v2/alleva-sync/jobs/{second.json()['job_id']}")

    assert first_result["status"] == "completed_with_warnings"
    assert first_result["records_written"] == 1
    assert first_result["records_failed"] == 1
    assert second_result["status"] == "completed_with_warnings"
    assert second_result["records_written"] == 0
    assert second_result["records_failed"] == 1
    queue = client.get("/api/v2/treatment-plans", headers=headers).json()["items"]
    assert [(item["patient_id"], item["treatment_plan_id"]) for item in queue] == [("912", "plan-912")]
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        assert database.execute("SELECT COUNT(*) FROM treatment_plan_versions").fetchone()[0] == 1
        encrypted = database.execute("SELECT normalized_snapshot_encrypted FROM treatment_plan_versions").fetchone()[0]
    assert isinstance(encrypted, bytes)
    assert b"Synthetic clinical problem" not in encrypted


def test_roster_job_controls_are_admin_only_while_roster_list_is_facility_scoped(tmp_path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    admin_headers = _auth_headers(client)
    _, manager_headers = _create_user(client, admin_headers, "roster-job-manager", "office_manager")
    _, counselor_headers = _create_user(client, admin_headers, "roster-job-counselor", "counselor")
    database_path = tmp_path / "app-data" / "clinical-notes-analyzer-v2.sqlite3"
    with sqlite3.connect(database_path) as database:
        default_facility_id = database.execute(
            "SELECT id FROM facilities WHERE facility_key='r3-default'"
        ).fetchone()[0]
        database.execute(
            "INSERT INTO facilities(facility_key,display_name,timezone,is_active,created_at,updated_at) "
            "VALUES('synthetic-secondary','Synthetic Secondary','America/New_York',1,'2026-07-14','2026-07-14')"
        )
        secondary_facility_id = database.execute(
            "SELECT id FROM facilities WHERE facility_key='synthetic-secondary'"
        ).fetchone()[0]
        admin_id = database.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        database.execute(
            "INSERT INTO user_facilities(user_id,facility_id,assigned_by_user_id,assigned_at) VALUES(?,?,?,'2026-07-14')",
            (admin_id, secondary_facility_id, admin_id),
        )
        database.executemany(
            "INSERT INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) "
            "VALUES(?,?,'alleva_rest_api','active','2026-07-14','2026-07-14')",
            (
                (default_facility_id, "facility-visible-301"),
                (secondary_facility_id, "facility-hidden-302"),
            ),
        )
        database.execute(
            "INSERT INTO api_harness_jobs(job_id,job_type,actor_id,actor_role,status,progress_percent,current_endpoint,"
            "current_page,current_cursor,records_seen,records_written,records_failed,warnings_count,errors_count,"
            "output_dir,redaction_mode,raw_sensitive_mode_used,cancel_requested,created_at,updated_at,last_heartbeat_at) "
            "VALUES('roster-rbac-job','active_patient_roster_pull',?,'admin','completed',100,'completed',1,'offset-0',1,1,0,0,0,'','redacted',0,0,'2026-07-14','2026-07-14','2026-07-14')",
            (str(admin_id),),
        )
        database.commit()

    assert client.post("/api/v2/patient-roster/pull", headers=admin_headers).status_code == 409
    assert client.get("/api/v2/patient-roster/jobs/roster-rbac-job", headers=admin_headers).status_code == 200
    assert client.get("/api/v2/patient-roster/jobs/latest", headers=admin_headers).status_code == 200
    for denied_headers in (manager_headers, counselor_headers):
        assert client.post("/api/v2/patient-roster/pull", headers=denied_headers).status_code == 403
        assert client.get("/api/v2/patient-roster/jobs/roster-rbac-job", headers=denied_headers).status_code == 403
        assert client.get("/api/v2/patient-roster/jobs/latest", headers=denied_headers).status_code == 403

    admin_ids = {
        item["mrn"] for item in client.get("/api/v2/patient-roster", headers=admin_headers).json()["items"]
    }
    manager_ids = {
        item["mrn"] for item in client.get("/api/v2/patient-roster", headers=manager_headers).json()["items"]
    }
    counselor_ids = {
        item["mrn"] for item in client.get("/api/v2/patient-roster", headers=counselor_headers).json()["items"]
    }
    assert admin_ids == {"facility-visible-301", "facility-hidden-302"}
    assert manager_ids == {"facility-visible-301"}
    assert counselor_ids == set()
