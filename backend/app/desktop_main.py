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
from starlette.responses import FileResponse, JSONResponse

from app.api.rules_routes import router as rules_router
from app.core.config import REPO_ROOT
from app.main import create_app


def _frontend_dist_dir() -> Path:
    packaged_candidate = Path(__file__).resolve().parent / 'static'
    if packaged_candidate.exists():
        return packaged_candidate
    return REPO_ROOT / 'frontend' / 'dist'


def _mount_frontend(api: FastAPI) -> None:
    dist_dir = _frontend_dist_dir()
    index_file = dist_dir / 'index.html'
    assets_dir = dist_dir / 'assets'
    if not index_file.exists():
        return
    if assets_dir.exists():
        api.mount('/assets', StaticFiles(directory=assets_dir), name='desktop-assets')

    @api.get('/', include_in_schema=False)
    def desktop_frontend_root():
        return FileResponse(index_file)

    @api.get('/desktop/{requested_path:path}', include_in_schema=False)
    def desktop_frontend_fallback(requested_path: str):
        return FileResponse(index_file)

    @api.get('/app-not-built', include_in_schema=False)
    def app_not_built():
        return JSONResponse({'detail': 'The frontend build was not found. Run npm run build in frontend or use a packaged release.'})


app = create_app()
app.include_router(rules_router)
_mount_frontend(app)
