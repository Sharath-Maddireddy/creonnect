"""RQ queue helper for account analysis background jobs."""

from __future__ import annotations

from rq import Queue

from backend.app.infra.job_defaults import (
    DEFAULT_FAILURE_TTL_SECONDS,
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_RESULT_TTL_SECONDS,
)
from backend.app.infra.redis_client import get_rq_redis


DEFAULT_QUEUE_NAME = "account-analysis"

def get_queue(name: str = DEFAULT_QUEUE_NAME) -> Queue:
    """Return RQ queue bound to configured Redis connection."""
    return Queue(
        name=name,
        connection=get_rq_redis(),
        default_timeout=DEFAULT_JOB_TIMEOUT_SECONDS,
        default_result_ttl=DEFAULT_RESULT_TTL_SECONDS,
        default_failure_ttl=DEFAULT_FAILURE_TTL_SECONDS,
    )
