from __future__ import annotations

from sqlalchemy import event

from test_v2_evaluation_persistence import _aggregate
from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_default_rule_package_is_reused_between_display_evaluations() -> None:
    # Given: the canonical rule package is immutable for one running app process.
    from app.v2.services.rule_package import load_rule_package

    # When: separate treatment-plan evaluations request the default package.
    first = load_rule_package()
    second = load_rule_package()

    # Then: display work reuses the parsed package instead of rereading two local files per plan.
    assert first is second


def test_display_endpoints_do_not_rewrite_current_evaluation_ledgers(tmp_path, monkeypatch) -> None:
    # Given: one synthetic treatment plan already has a current persisted evaluation.
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    payload = _aggregate("MRN-DISPLAY-PERF").model_dump(mode="json")
    payload["content_snapshot"]["plan_id"] = "plan-display-perf"
    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-aggregate",
        headers=headers,
        json=payload,
    )
    assert imported.status_code == 201

    from app.v2.db import engine

    evaluation_writes: list[str] = []

    def capture_evaluation_writes(connection, cursor, statement, parameters, context, executemany) -> None:
        normalized = statement.lower()
        if "insert into evaluation_runs" in normalized or "insert or ignore into criterion_results" in normalized:
            evaluation_writes.append(statement)

    event.listen(engine, "before_cursor_execute", capture_evaluation_writes)
    try:
        # When: each of the five reported data screens loads through its real API boundary.
        endpoints = (
            "/api/v2/dashboard",
            "/api/v2/patient-roster",
            "/api/v2/patients/MRN-DISPLAY-PERF?source_mode=manual_upload",
            "/api/v2/treatment-plans/MRN-DISPLAY-PERF/plan-display-perf?source_mode=manual_upload",
            "/api/v2/treatment-plan-roster",
        )
        for endpoint in endpoints:
            evaluation_writes.clear()
            response = client.get(endpoint, headers=headers)

            # Then: displaying already-evaluated data never repeats the 42-row evaluation write loop.
            assert response.status_code == 200, endpoint
            assert evaluation_writes == [], endpoint
    finally:
        event.remove(engine, "before_cursor_execute", capture_evaluation_writes)
