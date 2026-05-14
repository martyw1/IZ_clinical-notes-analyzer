from __future__ import annotations

"""Desktop runtime entrypoint.

This module keeps the existing FastAPI app intact while adding desktop-specific
behavior: the YAML rules API, the API configuration/test UI, the clinical notes
intake UI, and static React UI serving when frontend/dist is present. Windows
launch scripts use this module so the local app can run as a single localhost
service.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

from app.api.api_config_routes import router as api_config_router
from app.api.api_config_ui_routes import router as api_config_ui_router
from app.api.clinical_notes_ui_routes import router as clinical_notes_ui_router
from app.api.rules_routes import router as rules_router
from app.core.config import REPO_ROOT
from app.main import create_app


def _app_version() -> str:
    version_file = REPO_ROOT / 'VERSION'
    if version_file.exists():
        value = version_file.read_text(encoding='utf-8').strip()
        if value:
            return value
    return '0.0.0-local.unknown'


def _desktop_chrome() -> str:
    version = _app_version()
    return f"""
    <style id="iz-cna-desktop-chrome-style">
      .iz-cna-desktop-shortcuts {{
        position: fixed;
        right: 18px;
        bottom: 18px;
        z-index: 999999;
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
        justify-content: flex-end;
        font-family: Segoe UI, Arial, sans-serif;
      }}
      .iz-cna-desktop-shortcuts a,
      .iz-cna-desktop-version {{
        border: 1px solid rgba(15, 23, 42, 0.18);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.94);
        color: #0f172a;
        box-shadow: 0 8px 28px rgba(15, 23, 42, 0.14);
        font-size: 12px;
        font-weight: 700;
        line-height: 1;
        padding: 9px 12px;
        text-decoration: none;
        backdrop-filter: blur(6px);
      }}
      .iz-cna-desktop-shortcuts a {{
        background: #065f46;
        border-color: #065f46;
        color: #ffffff;
      }}
      .iz-cna-desktop-shortcuts a.secondary {{
        background: #ffffff;
        border-color: rgba(15, 23, 42, 0.18);
        color: #0f172a;
      }}
      .iz-cna-desktop-shortcuts a:hover {{ background: #047857; color: #ffffff; }}
      @media print {{ .iz-cna-desktop-shortcuts {{ display: none; }} }}
    </style>
    <div class="iz-cna-desktop-shortcuts" aria-label="Application shortcuts and version">
      <a href="/clinical-notes-intake" target="_blank" rel="noopener noreferrer">Clinical Notes Intake</a>
      <a class="secondary" href="/api-configuration" target="_blank" rel="noopener noreferrer">API Connectivity</a>
      <span class="iz-cna-desktop-version">v{version}</span>
    </div>
    """


def _html_with_desktop_chrome(index_file: Path) -> HTMLResponse:
    html = index_file.read_text(encoding='utf-8')
    chrome = _desktop_chrome()
    if '</body>' in html:
        html = html.replace('</body>', f'{chrome}\n</body>', 1)
    else:
        html = f'{html}\n{chrome}'
    return HTMLResponse(html, headers={'cache-control': 'no-store'})


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
            <li><a href="/clinical-notes-intake">Clinical notes intake</a></li>
            <li><a href="/api-configuration">API configuration and connectivity test</a></li>
            <li><a href="/docs">API documentation</a></li>
          </ul>
          <h2>Build the browser UI from a source checkout</h2>
          <p>From the repo root, install/build the frontend if Node.js/npm is available:</p>
          <pre>cd frontend
npm install
npm run build</pre>
          <p>Then restart <code>scripts\\startup-windows-local.ps1</code>. Packaged end-user releases should already include the built UI.</p>
        </main>
        {_desktop_chrome()}
      </body>
    </html>
    """
    return HTMLResponse(html, headers={'cache-control': 'no-store'})


def _mount_frontend(api: FastAPI) -> None:
    dist_dir = _frontend_dist_dir()
    index_file = dist_dir / 'index.html'
    assets_dir = dist_dir / 'assets'
    if assets_dir.exists():
        api.mount('/assets', StaticFiles(directory=assets_dir), name='desktop-assets')

    @api.get('/', include_in_schema=False)
    def desktop_frontend_root():
        if index_file.exists():
            return _html_with_desktop_chrome(index_file)
        return _frontend_missing_page()

    @api.get('/desktop/{requested_path:path}', include_in_schema=False)
    def desktop_frontend_fallback(requested_path: str):
        if index_file.exists():
            return _html_with_desktop_chrome(index_file)
        return _frontend_missing_page()

    @api.get('/app-not-built', include_in_schema=False)
    def app_not_built():
        return _frontend_missing_page()


app = create_app()
app.include_router(rules_router)
app.include_router(api_config_router)
app.include_router(api_config_ui_router)
app.include_router(clinical_notes_ui_router)
_mount_frontend(app)
