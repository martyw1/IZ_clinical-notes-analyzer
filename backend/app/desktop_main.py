from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

from app.core.config import REPO_ROOT
from app.main import create_app


def _frontend_dist_dir() -> Path:
    packaged_candidate = Path(__file__).resolve().parent / "static"
    if packaged_candidate.exists():
        return packaged_candidate
    return REPO_ROOT / "frontend" / "dist"


def _frontend_missing_page() -> HTMLResponse:
    dist_dir = _frontend_dist_dir()
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        "<title>IZ Clinical Notes Analyzer V2 Beta</title></head><body><main>"
        "<h1>IZ Clinical Notes Analyzer V2 Beta backend is running</h1>"
        f"<p>The V2 browser build was not found at <code>{dist_dir}</code>.</p>"
        "<p>Run <code>cd frontend && npm run build</code>, then restart the desktop service.</p>"
        "</main></body></html>"
    )
    return HTMLResponse(html, headers={"cache-control": "no-store"})


def _html(index_file: Path) -> HTMLResponse:
    return HTMLResponse(index_file.read_text(encoding="utf-8"), headers={"cache-control": "no-store"})


def _mount_frontend(api: FastAPI) -> None:
    dist_dir = _frontend_dist_dir()
    index_file = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        api.mount("/assets", StaticFiles(directory=assets_dir), name="desktop-assets")

    @api.get("/", include_in_schema=False)
    def desktop_frontend_root() -> HTMLResponse:
        if index_file.exists():
            return _html(index_file)
        return _frontend_missing_page()

    @api.get("/desktop/{requested_path:path}", include_in_schema=False)
    def desktop_frontend_fallback(requested_path: str) -> HTMLResponse:
        if index_file.exists():
            return _html(index_file)
        return _frontend_missing_page()

    @api.get("/api-configuration", include_in_schema=False)
    def api_configuration_page() -> HTMLResponse:
        return HTMLResponse(
            (
                "<!doctype html><html lang=\"en\"><head><title>API Configuration and Connectivity Test</title></head>"
                "<body><main><h1>API Configuration and Connectivity Test</h1>"
                "<p>V2 API Testing Harness is active. Use the in-app API Testing Harness for bounded jobs.</p>"
                "</main></body></html>"
            ),
            headers={"cache-control": "no-store"},
        )

    @api.get("/app-not-built", include_in_schema=False)
    def app_not_built() -> HTMLResponse:
        return _frontend_missing_page()


app = create_app()
_mount_frontend(app)
