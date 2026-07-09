from __future__ import annotations

from fastapi import APIRouter

from app.v2.api.foundation_routes import router as foundation_router
from app.v2.api.manual_upload_routes import router as manual_upload_router
from app.v2.api.runtime_routes import router as runtime_router

router = APIRouter()
router.include_router(foundation_router)
router.include_router(manual_upload_router)
router.include_router(runtime_router)
