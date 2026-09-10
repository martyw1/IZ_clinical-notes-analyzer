from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from test_v2_correction_queue import _counselor_headers
from test_v2_plan_version_actions import IdentityRuntime, _import, runtime as runtime


class FixedClock(datetime):
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return datetime(2026, 9, 10, 22, 58, 25, 133654, tzinfo=timezone.utc)


def test_distinct_manager_actions_survive_the_same_clock_tick(
    runtime: IdentityRuntime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: distinct actions arrive within the same system clock tick.
    selected = _import(runtime)
    _counselor_headers(runtime.client, runtime.headers)
    from app.v2 import models
    from app.v2.db import SessionLocal

    monkeypatch.setattr(models, "datetime", FixedClock)

    # When: the manager records all four actions for the same criterion.
    responses = [runtime.client.post(
        "/api/v2/treatment-plans/IDENTITY-001/manager-actions", headers=runtime.headers,
        json=selected | {"criterion_id": "confirm_current_loc", "action": action,
                         "comment": "Synthetic clock collision", "override_reason": "Synthetic reason",
                         "assigned_counselor_username": "counselor"},
    ) for action in ("approve", "comment", "override", "return_for_correction")]

    # Then: all distinct events persist without losing or duplicating actions.
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    with SessionLocal() as db:
        actions = db.execute(text("SELECT action FROM treatment_plan_manager_actions ORDER BY id")).scalars().all()
        dispositions = db.execute(text("SELECT status,created_at FROM manager_dispositions ORDER BY id")).all()
    assert actions == ["approve", "comment", "override", "return_for_correction"]
    assert [row[0] for row in dispositions] == actions
    assert len({row[1] for row in dispositions}) == 4
