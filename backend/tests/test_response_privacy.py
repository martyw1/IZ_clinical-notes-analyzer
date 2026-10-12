from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from v2_test_runtime import configured_client, prepare_app


class SyntheticResponseError(RuntimeError):
    pass


@pytest.mark.parametrize("path,status", [("/api/users/me", 401), ("/api/not-found", 404), ("/api/version", 200)])
def test_api_responses_prevent_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, status: int) -> None:
    # Given an isolated synthetic application.
    prepare_app(tmp_path, monkeypatch)
    client = configured_client()
    # When a public, unauthorized, or missing API endpoint responds.
    response = client.get(path)
    # Then browser storage and content interpretation are restricted.
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"


def test_authenticated_response_prevents_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given an authenticated synthetic administrator.
    from test_v2_manual_patient_correction import _auth_headers

    prepare_app(tmp_path, monkeypatch)
    client = configured_client()
    headers = _auth_headers(client)
    # When an account response is retrieved.
    response = client.get("/api/users/me", headers=headers)
    # Then it succeeds without allowing browser storage.
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_unhandled_api_errors_prevent_storage_without_hiding_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a synthetic route that raises an unexpected programming error.
    prepare_app(tmp_path, monkeypatch)
    from app.main import create_app

    app = create_app()

    @app.get("/api/synthetic-failure")
    def fail() -> None:
        raise SyntheticResponseError

    # When the server returns its generic error response.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/synthetic-failure")
    # Then no exception detail is disclosed or cached; server propagation survives.
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    with TestClient(app) as client, pytest.raises(SyntheticResponseError):
        client.get("/api/synthetic-failure")


def test_static_cache_policy_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a non-sensitive static response with its own cache policy.
    prepare_app(tmp_path, monkeypatch)
    from app.main import create_app

    app = create_app()

    @app.get("/assets/synthetic.css")
    def asset() -> Response:
        return Response("body{}", media_type="text/css", headers={"Cache-Control": "public, max-age=3600"})

    # When the asset is downloaded.
    with TestClient(app) as client:
        response = client.get("/assets/synthetic.css")
    # Then public assets keep their cache policy and correct MIME type.
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert response.headers["content-type"].startswith("text/css")
    assert response.headers["x-content-type-options"] == "nosniff"
