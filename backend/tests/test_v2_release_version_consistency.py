from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch
from sqlalchemy import text

from v2_test_runtime import fresh_client as _fresh_client


def test_production_version_surfaces_match_release_metadata(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[2]
    expected_version = "1.0.0"
    expected_build = "2026.09.21.2"
    expected_channel = "stable-local-desktop"

    metadata = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
    package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    lockfile = json.loads((root / "frontend" / "package-lock.json").read_text(encoding="utf-8"))

    assert (root / "VERSION").read_text(encoding="utf-8").strip() == expected_version
    assert metadata["version"] == expected_version
    assert metadata["build"] == expected_build
    assert metadata["release_channel"] == expected_channel
    assert metadata["release_date"] == "2026-09-21"
    assert metadata["stability"] == "stable"
    assert metadata["is_prerelease"] is False
    assert metadata["version_name"] == "Production 1.0"
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
    assert version_payload["stability"] == "stable"
    assert version_payload["is_prerelease"] is False
    assert version_payload["version_name"] == "Production 1.0"
    assert version_payload["active_runtime"] == "v2"

    sample_openapi_response = client.get("/api/api-configuration/sample-openapi.json")
    assert sample_openapi_response.status_code == 200
    assert sample_openapi_response.json()["info"]["version"] == expected_version

    from app.core.config import settings
    from app.v2.db import SessionLocal

    assert settings.app_version == expected_version
    assert settings.build_channel == expected_channel
    with SessionLocal() as db:
        assert db.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar_one() == 12

    app_source = (root / "frontend" / "src" / "v2" / "AppV2.tsx").read_text(encoding="utf-8")
    shell_source = (root / "frontend" / "src" / "v2" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    help_source = (root / "frontend" / "src" / "v2" / "pages" / "HelpPage.tsx").read_text(encoding="utf-8")
    index_source = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    main_source = (root / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    desktop_source = (root / "backend" / "app" / "desktop_main.py").read_text(encoding="utf-8")

    assert "Production 1.0" in app_source
    assert f"{expected_version} | build {expected_build} | {expected_channel}" in shell_source
    assert f"{expected_version} · build {expected_build} · {expected_channel}" in help_source
    assert "Full production qualification remains pending." in help_source
    assert "IZ Clinical Notes Analyzer Production 1.0" in index_source
    assert 'title=f"{settings.app_name} Production 1.0"' in main_source
    assert "IZ Clinical Notes Analyzer Production 1.0" in desktop_source


def test_production_version_fallbacks_are_stable(monkeypatch: MonkeyPatch) -> None:
    from app.services import version as version_service

    monkeypatch.setattr(version_service, "_read_metadata", lambda: {})
    monkeypatch.setattr(version_service, "_git_value", lambda *_args: version_service.UNKNOWN)
    payload = version_service.build_version_payload()

    assert payload["version"] == "1.0.0"
    assert payload["release_channel"] == "stable-local-desktop"
    assert payload["stability"] == "stable"
    assert payload["is_prerelease"] is False
    assert payload["version_name"] == "Production 1.0"
    assert payload["active_runtime"] == "v2"
