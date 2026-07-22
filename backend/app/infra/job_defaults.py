"""Shared defaults/constants for background job orchestration."""

from __future__ import annotations


DEFAULT_JOB_TIMEOUT_SECONDS = 600
DEFAULT_RESULT_TTL_SECONDS = 86400
DEFAULT_FAILURE_TTL_SECONDS = 86400

ACTIVE_REUSABLE_STATUSES = {"queued", "started", "succeeded"}

