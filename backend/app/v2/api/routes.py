from __future__ import annotations

from fastapi import APIRouter

from app.v2.api.correction_routes import router as correction_router
from app.v2.api.alleva_sync_routes import router as alleva_sync_router
from app.v2.api.foundation_routes import router as foundation_router
from app.v2.api.manual_upload_routes import router as manual_upload_router
from app.v2.api.openapi_routes import router as openapi_router
from app.v2.api.operation_routes import router as operation_router
from app.v2.api.runtime_routes import router as runtime_router
from app.v2.api.workflow_routes import router as workflow_router

router = APIRouter()
router.include_router(foundation_router)
router.include_router(correction_router)
router.include_router(alleva_sync_router)
router.include_router(manual_upload_router)
router.include_router(openapi_router)
router.include_router(operation_router)
router.include_router(runtime_router)
router.include_router(workflow_router)
