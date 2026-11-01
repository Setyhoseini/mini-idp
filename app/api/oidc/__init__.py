"""OIDC protocol router aggregator."""

from fastapi import APIRouter

from app.api.oidc.authorize import router as authorize_router
from app.api.oidc.discovery import router as discovery_router
from app.api.oidc.identity import router as identity_router
from app.api.oidc.management import router as management_router
from app.api.oidc.token import router as token_router

router = APIRouter()
router.include_router(discovery_router)
router.include_router(authorize_router)
router.include_router(token_router)
router.include_router(identity_router)
router.include_router(management_router)