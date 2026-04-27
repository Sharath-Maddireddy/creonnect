"""
Creonnect Backend - FastAPI Application
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from backend.app.api.account_analysis_routes import router as account_analysis_router
from backend.app.api.brand_match_routes import router as brand_match_router
from backend.app.api.brand_post_analysis_routes import router as brand_post_analysis_router
from backend.app.api.campaign_routes import router as campaign_router
from backend.app.api.post_analysis_routes import router as post_analysis_router
from backend.app.api.reel_analysis_routes import router as reel_analysis_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.instagram_auth_routes import router as instagram_auth_router
from backend.app.infra.database import init_db, initialize_database_engines
from backend.app.utils.logger import logger


load_dotenv(override=False)


_DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _is_production_environment() -> bool:
    return os.getenv("ENV", "dev").lower() not in {"dev", "development", "test"}


def _resolve_session_secret() -> str:
    configured_secret = (os.getenv("CREONNECT_SESSION_SECRET") or "").strip()
    if configured_secret:
        return configured_secret

    if _is_production_environment():
        raise RuntimeError("CREONNECT_SESSION_SECRET must be set in production environments")

    logger.warning("CREONNECT_SESSION_SECRET is not set; using ephemeral secret (dev only).")
    return secrets.token_urlsafe(32)


def _get_cors_origins() -> list[str]:
    configured_origins = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if configured_origins:
        return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    return _DEFAULT_CORS_ORIGINS


SESSION_SECRET = _resolve_session_secret()


def _validate_brand_api_key_configuration() -> bool:
    brand_api_key = (os.getenv("BRAND_API_KEY") or "").strip()
    if brand_api_key:
        return True

    message = (
        "BRAND_API_KEY is not set. Brand-protected endpoints will reject requests until this "
        "environment variable is configured."
    )
    if _is_production_environment():
        raise RuntimeError(message)

    logger.error(message)
    return False


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    _app.state.brand_api_key_configured = _validate_brand_api_key_configuration()
    vision_enabled = bool((os.getenv("GEMINI_API_KEY") or "").strip())
    _app.state.vision_enabled = vision_enabled
    logger.info("vision_enabled=%s", vision_enabled)
    initialize_database_engines()
    await init_db()
    yield

app = FastAPI(
    title="Creonnect API",
    description="Creator Intelligence Backend",
    version="1.0.0",
    lifespan=_app_lifespan,
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=_is_production_environment(),
)

# Register routers
app.include_router(dashboard_router)
app.include_router(account_analysis_router)
app.include_router(brand_match_router)
app.include_router(brand_post_analysis_router)
app.include_router(campaign_router)
app.include_router(post_analysis_router)
app.include_router(reel_analysis_router)
app.include_router(instagram_auth_router)


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok"}



