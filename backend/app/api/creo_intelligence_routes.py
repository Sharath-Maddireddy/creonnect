"""Creo Intelligence API routes.

Endpoints:
  POST   /api/creo-intelligence/chat          — SSE streaming chat turn
  DELETE /api/creo-intelligence/session/{id}  — Clear conversation history
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.auth import verify_api_key
from backend.app.api.rate_limiter import InMemoryRateLimiter
from backend.app.services.creo_intelligence_service import creo_intelligence_stream
from backend.app.services.creo_session_store import get_session_store
from backend.app.utils.logger import logger

router = APIRouter(prefix="/api/creo-intelligence", tags=["Creo Intelligence"])
_rate_limiter = InMemoryRateLimiter(max_requests=20, window_seconds=60)

_MIN_MESSAGE_LEN = 2
_MAX_MESSAGE_LEN = 2000
_MAX_SESSION_ID_LEN = 128


# ── Auth + rate limiting ───────────────────────────────────────────────────────


def _require_api_key_with_rate_limit(
    api_key: str = Depends(verify_api_key),
) -> str:
    """Verify API key and apply per-key rate limiting."""
    if _rate_limiter.check(api_key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for Creo Intelligence. Please wait before sending another message.",
        )
    return api_key


# ── Request / Response models ──────────────────────────────────────────────────


class CreoChatRequest(BaseModel):
    """Request body for a Creo Intelligence chat turn."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(
        min_length=1,
        max_length=_MAX_SESSION_ID_LEN,
        description="Opaque client session identifier. Generate a UUID on the frontend.",
    )
    message: str = Field(
        min_length=_MIN_MESSAGE_LEN,
        max_length=_MAX_MESSAGE_LEN,
        description="The brand user's message.",
    )
    brand_name: str | None = Field(
        default=None,
        max_length=200,
        description="Optional brand name for context.",
    )


class CreoSessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool
    detail: str


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/chat",
    summary="Creo Intelligence chat (SSE streaming)",
    response_description="Server-Sent Events stream of tokens and metadata",
    responses={
        200: {
            "description": "SSE stream",
            "content": {"text/event-stream": {}},
        },
        429: {"description": "Rate limit exceeded"},
        422: {"description": "Validation error"},
    },
)
async def creo_chat(
    request: CreoChatRequest,
    _api_key: str = Depends(_require_api_key_with_rate_limit),
) -> StreamingResponse:
    """Stream a Creo Intelligence chat response as Server-Sent Events.

    SSE event types:
    - ``tool_call`` — fired for each tool the AI uses (zero or more)
    - ``token``     — one per streamed response token
    - ``done``      — final metadata (tool_calls_made, session_id, latency_ms)
    - ``error``     — emitted if the request fails, then stream closes

    The frontend should use the native ``EventSource`` API or ``fetch`` with
    ``ReadableStream`` to consume this endpoint.
    """
    logger.info(
        "[CreoIntelligenceRoutes] Chat request: session=%s brand=%s",
        request.session_id,
        request.brand_name,
    )

    async def _event_generator():
        try:
            async for chunk in creo_intelligence_stream(
                session_id=request.session_id,
                user_message=request.message,
                brand_name=request.brand_name,
            ):
                yield chunk
        except Exception:  # noqa: BLE001
            logger.exception("[CreoIntelligenceRoutes] Unhandled error in SSE generator.")
            error_event = 'event: error\ndata: {"detail": "Internal server error."}\n\n'
            yield error_event

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


@router.delete(
    "/session/{session_id}",
    response_model=CreoSessionDeleteResponse,
    summary="Clear Creo Intelligence conversation history",
)
async def delete_creo_session(
    session_id: str,
    _api_key: str = Depends(verify_api_key),
) -> CreoSessionDeleteResponse:
    """Delete the conversation history for a session.

    Call this when the user clicks "New Chat" to reset the context window.
    Returns ``deleted: true`` if the session existed, ``deleted: false`` if it
    was already empty or expired.
    """
    if not session_id or len(session_id) > _MAX_SESSION_ID_LEN:
        raise HTTPException(status_code=422, detail="Invalid session_id.")

    store = get_session_store()
    try:
        deleted = await store.delete_session(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("[CreoIntelligenceRoutes] Failed to delete session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to clear session.") from exc

    return CreoSessionDeleteResponse(
        session_id=session_id,
        deleted=deleted,
        detail="Session cleared." if deleted else "Session not found (may have already expired).",
    )
