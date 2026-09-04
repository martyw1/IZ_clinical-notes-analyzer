from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

from v2_test_runtime import fresh_client as _fresh_client


def test_beta3_version_surfaces_match_release_metadata(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    expected_version = "2.0.0-beta.3"
    expected_build = "2026.09.03.1"
    expected_channel = "beta-local-desktop-v2"

    metadata = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
    package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    lockfile = json.loads((root / "frontend" / "package-lock.json").read_text(encoding="utf-8"))

    assert (root / "VERSION").read_text(encoding="utf-8").strip() == expected_version
    assert metadata["version"] == expected_version
    assert metadata["build"] == expected_build
    assert metadata["release_channel"] == expected_channel
    assert metadata["stability"] == "beta"
    assert metadata["is_prerelease"] is True
    assert package["version"] == expected_version
    assert lockfile["version"] == expected_version
    assert lockfile["packages"][""]["version"] == expected_version

    client = _fresh_client(tmp_path, monkeypatch)
    version_response = client.get("/api/version")
    assert version_response.status_code == 200
    version_payload = version_response.json()
    assert version_payload["version"] == expected_version
    assert version_payload["build"] == expected_build
    assert version_payload["release_channel"] == expected_channel
    assert version_payload["stability"] == "beta"
    assert version_payload["is_prerelease"] is True

    sample_openapi_response = client.get("/api/api-configuration/sample-openapi.json")
    assert sample_openapi_response.status_code == 200
    assert sample_openapi_response.json()["info"]["version"] == expected_version

    from app.core.config import settings

    assert settings.app_version == expected_version
    assert settings.build_channel == expected_channel

    preflight_source = (root / "scripts" / "preflight-windows.ps1").read_text(encoding="utf-8")
    shell_source = (root / "frontend" / "src" / "v2" / "components" / "AppShell.tsx").read_text(encoding="utf-8")

    assert f'version.get("version") != "{expected_version}"' in preflight_source
    assert f"{expected_version} | build {expected_build} | {expected_channel}" in shell_source
