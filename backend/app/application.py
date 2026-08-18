from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.services.audit import log_event
from app.v2.api.routes import router as v2_router
from app.v2.db import init_database
from app.v2.route_registry import assert_routes_classified


@asynccontextmanager
async def application_lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.local_app_data_dir.mkdir(parents=True, exist_ok=True)
    settings.api_harness_runs_dir.mkdir(parents=True, exist_ok=True)
    settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    init_database()
    log_event(
        action="app.start",
        entity_type="application",
        entity_reference="v2",
        details={"runtime": "v2"},
    )
    yield


def create_application() -> FastAPI:
    api = FastAPI(
        title=f"{settings.app_name} V2 Beta",
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
        lifespan=application_lifespan,
    )
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.include_router(v2_router)
    assert_routes_classified(api)
    return api
