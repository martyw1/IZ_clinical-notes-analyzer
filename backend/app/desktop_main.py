from __future__ import annotations

"""Desktop runtime entrypoint.

This module keeps the existing FastAPI app intact while adding desktop-specific
behavior: the YAML rules API and static React UI serving when frontend/dist is
present. Windows launch scripts use this module so the local app can run as a
single localhost service.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

from app.api.rules_routes import router as rules_router
from app.core.config import REPO_ROOT
from app.main import create_app


def _frontend_dist_dir() -> Path:
    packaged_candidate = Path(__file__).resolve().parent / 'static'
    if packaged_candidate.exists():
        return packaged_candidate
    return REPO_ROOT / 'frontend' / 'dist'


def _frontend_missing_page() -> HTMLResponse:
    dist_dir = _frontend_dist_dir()
    html = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>IZ Clinical Notes Analyzer - Local Runtime</title>
        <style>
          body {{ font-family: Segoe UI, Arial, sans-serif; margin: 2rem; line-height: 1.45; color: #1f2937; }}
          main {{ max-width: 880px; }}
          code, pre {{ background: #f3f4f6; border-radius: 6px; padding: 0.15rem 0.35rem; }}
          pre {{ padding: 1rem; overflow-x: auto; }}
          .ok {{ color: #047857; font-weight: 700; }}
          .warn {{ color: #92400e; font-weight: 700; }}
          a {{ color: #1d4ed8; }}
        </style>
      </head>
      <body>
        <main>
          <h1>IZ Clinical Notes Analyzer local backend is running</h1>
          <p class="ok">The local FastAPI service started successfully.</p>
          <p class="warn">The browser UI build was not found at <code>{dist_dir}</code>, so the React app cannot be served yet.</p>
          <h2>Useful local checks</h2>
          <ul>
            <li><a href="/api/health">API health</a></li>
            <li><a href="/api/readiness">Runtime readiness</a></li>
            <li><a href="/docs">API documentation</a></li>
          </ul>
          <h2>Build the browser UI from a source checkout</h2>
          <p>From the repo root, install/build the frontend if Node.js/npm is available:</p>
          <pre>cd frontend
npm install
npm run build</pre>
          <p>Then restart <code>scripts\\startup-windows-local.ps1</code>. Packaged end-user releases should already include the built UI.</p>
        </main>
      </body>
    </html>
    """
    return HTMLResponse(html)


def _mount_frontend(api: FastAPI) -> None:
    dist_dir = _frontend_dist_dir()
    index_file = dist_dir / 'index.html'
    assets_dir = dist_dir / 'assets'
    if assets_dir.exists():
        api.mount('/assets', StaticFiles(directory=assets_dir), name='desktop-assets')

    @api.get('/', include_in_schema=False)
    def desktop_frontend_root():
        if index_file.exists():
            return FileResponse(index_file)
        return _frontend_missing_page()

    @api.get('/desktop/{requested_path:path}', include_in_schema=False)
    def desktop_frontend_fallback(requested_path: str):
        if index_file.exists():
            return FileResponse(index_file)
        return _frontend_missing_page()

    @api.get('/app-not-built', include_in_schema=False)
    def app_not_built():
        return _frontend_missing_page()


app = create_app()
app.include_router(rules_router)
_mount_frontend(app)
