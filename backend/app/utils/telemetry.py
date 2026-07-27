"""Lightweight telemetry helpers for product analytics and observability.

No external deps — logs structured JSON to stdout for sidecar/Logstash ingestion.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any

from backend.app.utils.logger import logger


def emit_event(
    event_name: str,
    *,
    account_id: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Emit a structured product analytics event."""
    payload = {
        "event": event_name,
        "timestamp": time.time(),
    }
    if account_id:
        payload["account_id"] = account_id
    if properties:
        payload["properties"] = properties

    # Log as INFO for sidecar/Logstash to pick up
    logger.info("[Telemetry] %s", json.dumps(payload, default=str))


def emit_counter(
    counter_name: str,
    *,
    value: int = 1,
    account_id: str | None = None,
    tags: dict[str, str] | None = None,
) -> None:
    """Emit a counter metric."""
    payload = {
        "metric": "counter",
        "name": counter_name,
        "value": value,
        "timestamp": time.time(),
    }
    if account_id:
        payload["account_id"] = account_id
    if tags:
        payload["tags"] = tags

    logger.info("[Metrics] %s", json.dumps(payload, default=str))


def emit_histogram(
    histogram_name: str,
    *,
    value: float,
    account_id: str | None = None,
    tags: dict[str, str] | None = None,
) -> None:
    """Emit a histogram/stat distribution."""
    payload = {
        "metric": "histogram",
        "name": histogram_name,
        "value": value,
        "timestamp": time.time(),
    }
    if account_id:
        payload["account_id"] = account_id
    if tags:
        payload["tags"] = tags

    logger.info("[Metrics] %s", json.dumps(payload, default=str))


@contextmanager
def timed(histogram_name: str, account_id: str | None = None, **tags: str):
    """Context manager that emits a histogram of execution duration."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        emit_histogram(histogram_name, value=elapsed, account_id=account_id, tags=tags)