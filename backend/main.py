"""
Creonnect Backend - FastAPI Application
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.account_analysis_routes import router as account_analysis_router
from backend.app.api.post_analysis_routes import router as post_analysis_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.utils.logger import logger


load_dotenv(override=False)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    vision_enabled = bool((os.getenv("GEMINI_API_KEY") or "").strip())
    _app.state.vision_enabled = vision_enabled
    logger.info("vision_enabled=%s", vision_enabled)
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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(dashboard_router)
app.include_router(account_analysis_router)
app.include_router(post_analysis_router)


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok"}



