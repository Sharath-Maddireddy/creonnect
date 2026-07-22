"""Redis-backed job status store for lightweight queue job tracking.

Used by job modules that manage status directly in Redis (e.g. reel and
account analysis jobs) rather than going through the database-backed
job_state_store.
"""

from __future__ import annotations

from typing import Any

from backend.app.infra.redis_client import get_json, set_json
from backend.app.utils.number_utils import now_iso


class RedisJobStore:
    """Manage read/write/update of job status dicts in Redis under a key prefix.

    Args:
        key_prefix: Redis key prefix (e.g. ``"reel_analysis:job:"``).
        ttl_seconds: TTL applied to every status write.
    """

    def __init__(self, key_prefix: str, ttl_seconds: int) -> None:
        self._prefix = key_prefix
        self._ttl = ttl_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}"

    def _write(self, job_id: str, payload: dict[str, Any]) -> None:
        set_json(self._key(job_id), payload, ttl_seconds=self._ttl)

    def _read(self, job_id: str) -> dict[str, Any] | None:
        return get_json(self._key(job_id))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def base_status(self, job_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a fresh queued-status dict for *job_id*.

        Pass *extra* to add module-specific keys (e.g. ``progress``,
        ``warnings``, ``quality``) beyond the common set.
        """
        status: dict[str, Any] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        if extra:
            status.update(extra)
        return status

    def initialize(self, job_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Write an initial queued-status payload and return it."""
        payload = self.base_status(job_id, extra)
        self._write(job_id, payload)
        return payload

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Read and return the current status payload, or None if missing."""
        return self._read(job_id)

    def write(self, job_id: str, payload: dict[str, Any]) -> None:
        """Persist an already-built status payload (use when the caller owns the dict)."""
        self._write(job_id, payload)

    def update(self, job_id: str, extra: dict[str, Any] | None = None, **updates: Any) -> dict[str, Any]:
        """Merge *updates* (and optional *extra* dict) into the stored payload and persist."""
        payload = self._read(job_id) or self.base_status(job_id, extra)
        payload.update(updates)
        if extra:
            payload.update(extra)
        self._write(job_id, payload)
        return payload