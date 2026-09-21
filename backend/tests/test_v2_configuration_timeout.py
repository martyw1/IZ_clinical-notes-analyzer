from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from test_v2_manual_patient_correction import _auth_headers, _fresh_client


def test_fresh_timeout_matches_live_validation_and_saved_timeout_survives_restart(
    tmp_path: Path, monkeypatch: MonkeyPatch,
) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    configuration = client.get("/api/api-configuration", headers=headers)
    assert configuration.status_code == 200
    assert configuration.json()["timeout_seconds"] == 30

    saved = client.patch("/api/api-configuration", headers=headers, json={"timeout_seconds": 10})
    assert saved.status_code == 200
    assert saved.json()["timeout_seconds"] == 10
    unrelated = client.patch("/api/api-configuration", headers=headers, json={"api_enabled": False})
    assert unrelated.status_code == 200
    assert unrelated.json()["timeout_seconds"] == 10

    restarted = _fresh_client(tmp_path, monkeypatch)
    after_restart = restarted.get("/api/api-configuration", headers=_auth_headers(restarted))
    assert after_restart.status_code == 200
    assert after_restart.json()["timeout_seconds"] == 10
