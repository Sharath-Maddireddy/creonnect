"""Common background-job queue abstraction backed by AWS SQS."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from backend.app.utils.logger import logger


ACCOUNT_ANALYSIS_QUEUE_NAME = "account-analysis"
EMBEDDING_INGESTION_QUEUE_NAME = "embedding-ingestion"
REEL_ANALYSIS_QUEUE_NAME = "reel-analysis"
SINGLE_POST_ANALYSIS_QUEUE_NAME = "single-post-analysis"

ACCOUNT_ANALYSIS_JOB_NAME = "account_analysis.run"
EMBEDDING_INGESTION_JOB_NAME = "embedding_ingestion.generate_creator_embedding"
REEL_ANALYSIS_JOB_NAME = "reel_analysis.run"
SINGLE_POST_ANALYSIS_JOB_NAME = "single_post_analysis.run"

_JOB_HANDLERS: dict[str, Callable[..., Any]] = {}
_SQS_CLIENT = None

DEFAULT_JOB_TIMEOUT_SECONDS = 600
DEFAULT_RESULT_TTL_SECONDS = 86400
DEFAULT_FAILURE_TTL_SECONDS = 86400


def _json_default(value: Any) -> Any:
    """Serialize non-JSON-native values for SQS payloads."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


@dataclass(slots=True)
class EnqueuedJob:
    backend: str
    queue_name: str
    job_id: str | None
    raw_status: str | None = None


def register_job_handler(job_name: str, handler: Callable[..., Any]) -> None:
    """Register a job handler name for SQS worker dispatch."""
    _JOB_HANDLERS[job_name] = handler


def get_registered_job_handler(job_name: str) -> Callable[..., Any] | None:
    """Return a registered job handler by name."""
    return _JOB_HANDLERS.get(job_name)


def _get_sqs_client():
    global _SQS_CLIENT
    if _SQS_CLIENT is not None:
        return _SQS_CLIENT
    import boto3

    client_kwargs: dict[str, Any] = {}
    region_name = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip()
    endpoint_url = (os.getenv("AWS_SQS_ENDPOINT_URL") or "").strip()
    if region_name:
        client_kwargs["region_name"] = region_name
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    _SQS_CLIENT = boto3.client("sqs", **client_kwargs)
    return _SQS_CLIENT


def _queue_url_env_var(queue_name: str) -> str:
    normalized = queue_name.replace("-", "_").upper()
    return f"AWS_SQS_{normalized}_QUEUE_URL"


def get_sqs_queue_url(queue_name: str) -> str:
    """Resolve an SQS queue URL for a logical queue name."""
    env_var = _queue_url_env_var(queue_name)
    queue_url = (os.getenv(env_var) or "").strip()
    if not queue_url:
        raise RuntimeError(f"SQS queue URL is not configured for {queue_name!r}. Set {env_var}.")
    return queue_url


def _build_sqs_message(
    *,
    queue_name: str,
    job_name: str,
    payload: Any,
    job_id: str | None,
    timeout_seconds: int,
    result_ttl_seconds: int,
    failure_ttl_seconds: int,
    retry_max: int | None,
    retry_intervals: list[int] | None,
) -> dict[str, Any]:
    return {
        "queue_name": queue_name,
        "job_name": job_name,
        "job_id": job_id,
        "payload": payload,
        "options": {
            "timeout_seconds": timeout_seconds,
            "result_ttl_seconds": result_ttl_seconds,
            "failure_ttl_seconds": failure_ttl_seconds,
            "retry_max": retry_max,
            "retry_intervals": retry_intervals or [],
        },
    }


def enqueue_callable(
    *,
    queue_name: str,
    job_name: str,
    func: Callable[..., Any],
    payload: Any,
    job_id: str | None = None,
    timeout_seconds: int = DEFAULT_JOB_TIMEOUT_SECONDS,
    result_ttl_seconds: int = DEFAULT_RESULT_TTL_SECONDS,
    failure_ttl_seconds: int = DEFAULT_FAILURE_TTL_SECONDS,
    retry_max: int | None = None,
    retry_intervals: list[int] | None = None,
) -> EnqueuedJob:
    """Enqueue a job via AWS SQS."""
    queue_url = get_sqs_queue_url(queue_name)
    message_body = json.dumps(
        _build_sqs_message(
            queue_name=queue_name,
            job_name=job_name,
            payload=payload,
            job_id=job_id,
            timeout_seconds=timeout_seconds,
            result_ttl_seconds=result_ttl_seconds,
            failure_ttl_seconds=failure_ttl_seconds,
            retry_max=retry_max,
            retry_intervals=retry_intervals,
        ),
        ensure_ascii=True,
        separators=(",", ":"),
        default=_json_default,
    )
    client = _get_sqs_client()
    send_kwargs: dict[str, Any] = {
        "QueueUrl": queue_url,
        "MessageBody": message_body,
    }
    if queue_url.endswith(".fifo"):
        send_kwargs["MessageGroupId"] = queue_name
        send_kwargs["MessageDeduplicationId"] = job_id or f"{job_name}:{hash(message_body)}"
    response = client.send_message(**send_kwargs)
    message_id = response.get("MessageId")
    logger.info(
        "[JobQueue] Enqueued backend=sqs queue=%s job_name=%s job_id=%s message_id=%s",
        queue_name,
        job_name,
        job_id,
        message_id,
    )
    return EnqueuedJob(
        backend="sqs",
        queue_name=queue_name,
        job_id=job_id,
        raw_status=message_id if isinstance(message_id, str) else None,
    )
