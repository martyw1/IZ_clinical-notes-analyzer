from __future__ import annotations

import socket
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Iterator, Mapping

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "desktop_contract"


def _fixture(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _resource_sha256(path: Path) -> str:
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _route_contract(app: object) -> dict[str, object]:
    routes = sorted(
        ({"method": method, "path": route.path} for route in app.routes if isinstance(route, APIRoute) for method in route.methods),
        key=lambda item: (item["path"], item["method"]),
    )
    return {"schema": "iz-desktop-routes-v1", "middleware": [item.cls.__name__ for item in app.user_middleware], "routes": routes}


def _safe_shapes(client: TestClient) -> dict[str, object]:
    version = client.get("/api/version")
    readiness = client.get("/api/readiness")
    bootstrap = client.post("/api/auth/login", json={"username": "admin", "password": "StrongLocalPass1"})
    headers = _auth_headers(client)
    dashboard = client.get("/api/v2/dashboard", headers=headers)
    patient_roster = client.get("/api/v2/patient-roster", headers=headers)
    treatment_plan_roster = client.get("/api/v2/treatment-plan-roster", headers=headers)
    denial = client.get("/api/users")
    live_sync = client.post("/api/v2/alleva-sync/run", headers=headers)
    from app.v2.services.deterministic_evaluator import evaluate_plan_version
    from app.v2.services.rule_package import load_rule_package
    from test_v2_deterministic_evaluator import _aggregate

    evaluation = evaluate_plan_version(_aggregate(), load_rule_package(), date(2026, 1, 23), "America/New_York")
    counts = Counter(item.status for item in evaluation.criteria)
    version_body, readiness_body, bootstrap_body, dashboard_body = version.json(), readiness.json(), bootstrap.json(), dashboard.json()
    return {
        "schema": "iz-desktop-safe-api-shapes-v1",
        "shapes": {
            "version": {"status_code": version.status_code, "body": {key: version_body[key] for key in ("version", "build", "release_channel", "stability", "is_prerelease", "active_runtime")}},
            "readiness": {"status_code": readiness.status_code, "body": {"status": readiness_body["status"], "runtime": readiness_body["runtime"], "checks": [{"name": item["name"], "status": item["status"]} for item in readiness_body["checks"]]}},
            "bootstrap_auth": {"status_code": bootstrap.status_code, "body": {key: bootstrap_body[key] for key in ("token_type", "must_reset_password", "auth_state")}},
            "rbac_denial": {"status_code": denial.status_code, "body": denial.json()},
            "dashboard": {"status_code": dashboard.status_code, "body": {"source_cards": [{"label": item["label"], "status": item["status"]} for item in dashboard_body["source_cards"]], "metrics": dashboard_body["metrics"], "blocker_count": len(dashboard_body["blockers"])}},
            "patient_roster": {"status_code": patient_roster.status_code, "body": patient_roster.json()},
            "treatment_plan_roster": {"status_code": treatment_plan_roster.status_code, "body": treatment_plan_roster.json()},
            "deterministic_evaluation": {"overall_status": evaluation.overall_status, "calculated_due_date": evaluation.calculated_due_date, "checklist_version": evaluation.checklist_version, "rules_version": evaluation.rules_version, "criterion_count": len(evaluation.criteria), "status_counts": dict(sorted(counts.items()))},
            "live_alleva_disabled": {"status_code": live_sync.status_code, "authorized": False, "detail_contains": "live treatment-plan import is not authorized" in live_sync.json()["detail"]},
        },
    }


def _assert_route_contract(observed: Mapping[str, object]) -> None:
    routes = observed.get("routes")
    assert isinstance(routes, list)
    identities = [(item.get("path"), item.get("method")) for item in routes if isinstance(item, dict)]
    assert len(identities) == len(set(identities)), "duplicate route"
    assert observed == _fixture("routes.json"), "route contract changed"


def _assert_safe_shapes(observed: Mapping[str, object]) -> None:
    assert observed == _fixture("safe-api-shapes.json"), "safe response shape changed"


def _require_execution_success(exit_code: int, stdout: str) -> None:
    del stdout
    assert exit_code == 0, "recorded command exit was nonzero"


@contextmanager
def _desktop_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    client = _fresh_client(tmp_path, monkeypatch)
    try:
        yield client
    finally:
        from app.v2.db import engine

        client.close()
        engine.dispose()


def test_current_desktop_routes_and_middleware_are_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the unchanged desktop ASGI application in an isolated local profile.
    with _desktop_client(tmp_path, monkeypatch) as client:
        routes = tuple(
            (route.path, method)
            for route in client.app.routes
            if isinstance(route, APIRoute)
            for method in route.methods
        )
        middleware = tuple(item.cls.__name__ for item in client.app.user_middleware)

    # When: its HTTP and middleware surfaces are normalized.
    unique_routes = frozenset(routes)

    # Then: the current portable surface has no ambiguous duplicate dispatch entries.
    assert len(routes) == 59
    assert len(unique_routes) == len(routes)
    assert middleware == ("CORSMiddleware", "TrustedHostMiddleware")


def test_current_safe_api_behavior_is_stable_without_live_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an isolated first-run profile whose socket transport fails closed.
    external_socket_attempts = 0
    original_connect = socket.socket.connect

    def reject_external_connect(active_socket: socket.socket, address: tuple[str, int]) -> None:
        nonlocal external_socket_attempts
        host, _port = address
        if host in {"127.0.0.1", "::1"}:
            original_connect(active_socket, address)
            return
        external_socket_attempts += 1
        raise AssertionError("desktop contract attempted an external network connection")

    monkeypatch.setattr(socket.socket, "connect", reject_external_connect)
    with _desktop_client(tmp_path, monkeypatch) as client:
        version = client.get("/api/version")
        readiness = client.get("/api/readiness")
        bootstrap = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "StrongLocalPass1"},
        )
        headers = _auth_headers(client)
        dashboard = client.get("/api/v2/dashboard", headers=headers)
        patient_roster = client.get("/api/v2/patient-roster", headers=headers)
        treatment_plan_roster = client.get("/api/v2/treatment-plan-roster", headers=headers)
        unauthenticated = client.get("/api/users")
        live_sync = client.post("/api/v2/alleva-sync/run", headers=headers)

    # When: only stable, non-secret response fields are observed.
    version_payload = version.json()
    readiness_payload = readiness.json()

    # Then: the existing readiness/auth/RBAC/dashboard/roster/gate behavior is unchanged.
    assert version.status_code == 200
    assert (version_payload["version"], version_payload["build"], version_payload["active_runtime"]) == (
        "2.0.0-beta.2",
        "2026.07.11.1",
        "v2",
    )
    assert readiness.status_code == 200
    assert readiness_payload["status"] == "warn"
    assert [(item["name"], item["status"]) for item in readiness_payload["checks"]] == [
        ("local_app_data", "ok"),
        ("database", "ok"),
        ("build_channel", "ok"),
        ("api_profile", "warn"),
        ("loc_change_blocker", "warn"),
    ]
    assert bootstrap.status_code == 200
    assert bootstrap.json()["auth_state"] == "password_change_required"
    assert bootstrap.json()["must_reset_password"] is True
    assert dashboard.status_code == 200
    assert dashboard.json()["metrics"]["active_patient_ids"] == 0
    assert patient_roster.status_code == 200 and patient_roster.json() == {"items": []}
    assert treatment_plan_roster.status_code == 200 and treatment_plan_roster.json() == {"items": []}
    assert unauthenticated.status_code == 401 and unauthenticated.json() == {"detail": "Not authenticated"}
    assert live_sync.status_code == 409
    assert "live treatment-plan import is not authorized" in live_sync.json()["detail"]
    assert external_socket_attempts == 0


def test_current_audit_counts_are_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a first-run profile with no previous audit history.
    with _desktop_client(tmp_path, monkeypatch) as client:
        headers = _auth_headers(client)

        # When: the administrator completes bootstrap and reads the audit ledger.
        response = client.get("/api/audit/logs", headers=headers)

    # Then: each current bootstrap transition is represented exactly once.
    assert response.status_code == 200
    actions = Counter(item["action"] for item in response.json()["items"])
    assert actions == Counter(
        {
            "auth.login.success": 2,
            "auth.bootstrap.completed": 1,
            "settings.legacy_api.migration": 1,
            "user.password.changed": 1,
        }
    )


def test_current_rules_and_encryption_resources_are_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the canonical checklist/rules and an isolated encryption key.
    with _desktop_client(tmp_path, monkeypatch):
        from app.v2.services.rule_package import load_rule_package
        from app.v2.services.secure_storage import decrypt_bytes, encrypt_bytes

        rule_package = load_rule_package()
        plaintext = b"synthetic desktop contract payload"

        # When: the application encrypts and decrypts a synthetic payload.
        encrypted = encrypt_bytes(plaintext)
        decrypted = decrypt_bytes(encrypted)

    # Then: checklist order/version and the local encryption envelope remain stable.
    assert len(rule_package.checklist.steps) == 42
    assert tuple(step.step for step in rule_package.checklist.steps) == tuple(range(1, 43))
    assert rule_package.checklist.version == "1.2.0"
    assert rule_package.rules.config_version == "1.2.0"
    assert rule_package.rules.checklist_version == "1.2.0"
    assert encrypted.startswith(b"IZCNA1:")
    assert plaintext not in encrypted
    assert decrypted == plaintext


def test_machine_readable_desktop_contract_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the current app and the externally reviewed, secret-free contract fixtures.
    with _desktop_client(tmp_path, monkeypatch) as client:
        routes = _route_contract(client.app)
        safe_shapes = _safe_shapes(client)

    # When: stable routes, response shapes, and immutable resources are normalized.
    _assert_route_contract(routes)
    _assert_safe_shapes(safe_shapes)
    resources = _fixture("resource-hashes.json")
    for item in resources["resources"]:
        resource = Path(__file__).resolve().parents[2] / item["path"]
        assert _resource_sha256(resource) == item["sha256"]
    fingerprint = hashlib.sha256((json.dumps({"routes": routes, "safe_api_shapes": safe_shapes}, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()

    # Then: the complete safe fingerprint remains byte-independent from volatile/private state.
    assert fingerprint == resources["contract_fingerprint_sha256"]


def test_resource_hash_is_line_ending_independent(tmp_path: Path) -> None:
    # Given: semantically identical synthetic text resources with LF and CRLF checkouts.
    lf_resource = tmp_path / "lf.json"
    crlf_resource = tmp_path / "crlf.json"
    lf_resource.write_bytes(b'{"synthetic": true}\n')
    crlf_resource.write_bytes(b'{"synthetic": true}\r\n')

    # When/Then: checkout line-ending policy cannot change the resource fingerprint.
    assert _resource_sha256(lf_resource) == _resource_sha256(crlf_resource)


def test_contract_rejects_duplicate_route() -> None:
    # Given: a forged route inventory containing one duplicated method/path pair.
    routes = deepcopy(_fixture("routes.json"))
    routes["routes"].append(deepcopy(routes["routes"][0]))

    # When/Then: duplicate dispatch identities fail before golden comparison.
    with pytest.raises(AssertionError, match="duplicate route"):
        _assert_route_contract(routes)


def test_contract_rejects_changed_safe_shape() -> None:
    # Given: a forged readiness response that weakens a warning to an OK result.
    shapes = deepcopy(_fixture("safe-api-shapes.json"))
    shapes["shapes"]["readiness"]["body"]["status"] = "ok"

    # When/Then: semantic response drift cannot update or pass the fixture.
    with pytest.raises(AssertionError, match="safe response shape changed"):
        _assert_safe_shapes(shapes)


def test_contract_does_not_trust_pass_text_when_assertion_fails() -> None:
    # Given: presentation text that claims PASS beside a recorded nonzero exit.
    # When/Then: the numeric result controls acceptance.
    with pytest.raises(AssertionError, match="exit"):
        _require_execution_success(23, "PASS")


def test_contract_fixtures_exclude_privacy_canary_and_volatile_values() -> None:
    # Given: every committed characterization fixture serialized as text.
    serialized = "\n".join((FIXTURE_ROOT / name).read_text(encoding="utf-8") for name in ("routes.json", "safe-api-shapes.json", "resource-hashes.json"))

    # When/Then: secrets, PHI canaries, runtime paths, and volatile fields are absent.
    forbidden = ("access_token", "password_hash", "ciphertext", "original_filename", "audit_chain", "refreshed_at", "git_commit", "git_dirty", "SYNTHETIC-PATIENT-NAME-MUST-NOT-CROSS", "C:\\\\Users")
    assert not any(marker in serialized for marker in forbidden)
