"""gRPC server for inter-service analysis orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from typing import Any, Awaitable, Callable

import grpc

from backend.app.services.account_analysis_jobs import (
    enqueue_account_analysis_job_async,
    get_account_analysis_job_status,
)
from backend.app.services.single_post_analysis_jobs import (
    enqueue_single_post_analysis_job_async,
    get_single_post_analysis_job_status,
)
from backend.app.utils.logger import logger


_GRPC_SERVICE_NAME = "creonnect.analysis.AnalysisService"
_GRPC_METHOD_START_ACCOUNT = f"/{_GRPC_SERVICE_NAME}/StartAccountAnalysis"
_GRPC_METHOD_GET_ACCOUNT_STATUS = f"/{_GRPC_SERVICE_NAME}/GetAccountAnalysisStatus"
_GRPC_METHOD_START_SINGLE_POST = f"/{_GRPC_SERVICE_NAME}/StartSinglePostAnalysis"
_GRPC_METHOD_GET_SINGLE_POST_STATUS = f"/{_GRPC_SERVICE_NAME}/GetSinglePostAnalysisStatus"
_GRPC_ALLOWED_SKEW_SECONDS = 300

_grpc_server: grpc.aio.Server | None = None


def _json_loads(data: bytes) -> dict[str, Any]:
    if not data:
        return {}
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("gRPC request payload must be a JSON object")
    return payload


def _json_dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str).encode("utf-8")


def _metadata_value(context: grpc.aio.ServicerContext, key: str) -> str | None:
    lowered = key.strip().lower()
    for meta in context.invocation_metadata():
        if meta.key.strip().lower() == lowered:
            return meta.value
    return None


def _verify_internal_hmac(context: grpc.aio.ServicerContext, request: bytes) -> None:
    secret = (os.getenv("CREONNECT_INTERNAL_HMAC_SECRET") or "").strip()
    if not secret:
        return

    raw_timestamp = (_metadata_value(context, "x-creonnect-timestamp") or "").strip()
    signature = (_metadata_value(context, "x-creonnect-signature") or "").strip().lower()
    if not raw_timestamp or not signature:
        raise PermissionError("Missing required internal auth metadata")

    try:
        request_ts = int(raw_timestamp)
    except ValueError as exc:
        raise PermissionError("Invalid internal auth timestamp") from exc

    if abs(int(time.time()) - request_ts) > _GRPC_ALLOWED_SKEW_SECONDS:
        raise PermissionError("Internal auth timestamp outside allowed window")

    payload = raw_timestamp.encode("utf-8") + b"." + request
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PermissionError("Invalid internal auth signature")


async def _start_account_handler(payload: dict[str, Any]) -> dict[str, Any]:
    result = await enqueue_account_analysis_job_async(payload)
    return {"ok": True, "data": result}


async def _get_account_status_handler(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": {"message": "job_id is required"}}
    status = get_account_analysis_job_status(job_id)
    if status is None:
        return {"ok": False, "error": {"message": f"Unknown job_id: {job_id}"}}
    return {"ok": True, "data": status}


async def _start_single_post_handler(payload: dict[str, Any]) -> dict[str, Any]:
    result = await enqueue_single_post_analysis_job_async(payload)
    return {"ok": True, "data": result}


async def _get_single_post_status_handler(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": {"message": "job_id is required"}}
    status = get_single_post_analysis_job_status(job_id)
    if status is None:
        return {"ok": False, "error": {"message": f"Unknown job_id: {job_id}"}}
    return {"ok": True, "data": status}


def _build_unary_unary_handler(
    func: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> grpc.RpcMethodHandler:
    async def _handler(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        try:
            _verify_internal_hmac(context, request)
            payload = _json_loads(request)
            response = await func(payload)
            return _json_dumps(response if isinstance(response, dict) else {"ok": False, "error": {"message": "Invalid response"}})
        except PermissionError as exc:
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details(str(exc))
            return _json_dumps({"ok": False, "error": {"type": exc.__class__.__name__, "message": str(exc)}})
        except Exception as exc:  # noqa: BLE001
            logger.exception("[gRPCAnalysis] Handler failed: %s", exc)
            return _json_dumps({"ok": False, "error": {"type": exc.__class__.__name__, "message": str(exc)}})

    return grpc.unary_unary_rpc_method_handler(
        _handler,
        request_deserializer=lambda x: x,
        response_serializer=lambda x: x,
    )


async def start_grpc_analysis_server() -> None:
    global _grpc_server
    if _grpc_server is not None:
        return
    enabled = str(os.getenv("PYTHON_GRPC_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("[gRPCAnalysis] Disabled via PYTHON_GRPC_ENABLED")
        return
    host = str(os.getenv("PYTHON_GRPC_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = int(os.getenv("PYTHON_GRPC_PORT", "50051"))
    server = grpc.aio.server()
    handlers = {
        "StartAccountAnalysis": _build_unary_unary_handler(_start_account_handler),
        "GetAccountAnalysisStatus": _build_unary_unary_handler(_get_account_status_handler),
        "StartSinglePostAnalysis": _build_unary_unary_handler(_start_single_post_handler),
        "GetSinglePostAnalysisStatus": _build_unary_unary_handler(_get_single_post_status_handler),
    }
    generic_handler = grpc.method_handlers_generic_handler(_GRPC_SERVICE_NAME, handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    await server.start()
    _grpc_server = server
    logger.info("[gRPCAnalysis] Server started at %s", bind_addr)


async def stop_grpc_analysis_server() -> None:
    global _grpc_server
    if _grpc_server is None:
        return
    try:
        await _grpc_server.stop(grace=3)
        logger.info("[gRPCAnalysis] Server stopped")
    finally:
        _grpc_server = None
