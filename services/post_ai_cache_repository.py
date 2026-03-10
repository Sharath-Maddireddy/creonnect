"""
Temporary in-memory cache repository for post AI analysis.

This abstraction is intentionally storage-agnostic so the internal in-memory
stores can be replaced by Redis later without changing public method signatures.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, Optional


class PostAICacheRepository:
    """
    In-memory cache repository for AI post analysis and regeneration locks.

    Cache TTL:
    - Analysis payload: 24 hours
    - Regeneration lock: 2 hours
    """

    ANALYSIS_TTL_SECONDS: int = 24 * 60 * 60
    REGEN_LOCK_TTL_SECONDS: int = 2 * 60 * 60

    def __init__(self) -> None:
        # In-memory store behind a repository interface so backing storage
        # can be swapped to Redis later without changing callers.
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}
        # Guards compound cache operations (read/check-ttl/pop/write) to prevent
        # TOCTOU races between concurrent readers/writers.
        self._analysis_cache_mutex = threading.Lock()
        self._regen_locks: Dict[str, Dict[str, float]] = {}
        self._regen_lock_mutex = threading.Lock()
        self._cleanup_interval_seconds = 3600  # Run every hour.
        self._start_cleanup_thread()

    def _start_cleanup_thread(self) -> None:
        """Start background eviction of expired cache entries."""
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        """Periodically evict expired analysis and lock entries."""
        while True:
            time.sleep(self._cleanup_interval_seconds)
            self._evict_expired_analysis_entries()
            self._evict_expired_regen_locks()

    def _evict_expired_analysis_entries(self) -> None:
        with self._analysis_cache_mutex:
            expired_keys = [
                key
                for key, entry in self._analysis_cache.items()
                if self._is_analysis_expired(float(entry.get("created_at", 0.0)))
            ]
            for key in expired_keys:
                self._analysis_cache.pop(key, None)

    def _evict_expired_regen_locks(self) -> None:
        with self._regen_lock_mutex:
            expired_keys = [
                key
                for key, entry in self._regen_locks.items()
                if self._is_lock_expired(float(entry.get("created_at", 0.0)))
            ]
            for key in expired_keys:
                self._regen_locks.pop(key, None)

    # NOTE:
    # Cache keys include score version to prevent cross-version contamination
    # when scoring models are upgraded in future releases.
    def _make_key(
        self,
        account_id: str,
        media_id: str,
        score_version: int = 1,
    ) -> str:
        """Build repository key in stable `account_id:media_id:v{score_version}` format."""
        return f"{account_id}:{media_id}:v{score_version}"

    def _is_analysis_expired(self, created_at: float) -> bool:
        """Check whether an analysis cache entry exceeded its TTL."""
        return (time.time() - created_at) >= self.ANALYSIS_TTL_SECONDS

    def _is_lock_expired(self, created_at: float) -> bool:
        """Check whether a regeneration lock entry exceeded its TTL."""
        return (time.time() - created_at) >= self.REGEN_LOCK_TTL_SECONDS

    def get_cached_analysis(self, account_id: str, media_id: str) -> dict | None:
        """
        Return cached AI analysis payload if present and not expired.

        Entries are expired lazily when accessed.
        """
        key = self._make_key(account_id, media_id, score_version=1)
        with self._analysis_cache_mutex:
            entry = self._analysis_cache.get(key)
            if entry is None:
                return None

            created_at = float(entry.get("created_at", 0.0))
            # Lazy expiration: stale entries are evicted on access.
            if self._is_analysis_expired(created_at):
                self._analysis_cache.pop(key, None)
                return None

            payload = entry.get("payload")
            if not isinstance(payload, dict):
                self._analysis_cache.pop(key, None)
                return None
            # Return a defensive deep copy so callers cannot mutate nested cache state.
            return copy.deepcopy(payload)

    def set_cached_analysis(self, account_id: str, media_id: str, payload: dict) -> None:
        """
        Store AI analysis payload with creation timestamp.
        """
        key = self._make_key(account_id, media_id, score_version=1)
        with self._analysis_cache_mutex:
            self._analysis_cache[key] = {
                # Persist a deep copy so caller-side nested mutations after set() do not leak into cache.
                "payload": copy.deepcopy(payload),
                "created_at": time.time(),
            }

    def acquire_regen_lock(self, account_id: str, media_id: str) -> bool:
        """
        Acquire regeneration lock for a post.

        Returns:
        - True: lock created (missing or expired)
        - False: lock already exists and is still active

        Locks are expired lazily when accessed.
        """
        with self._regen_lock_mutex:
            key = self._make_key(account_id, media_id, score_version=1)
            now = time.time()

            lock_entry = self._regen_locks.get(key)
            if lock_entry is not None:
                created_at = float(lock_entry.get("created_at", 0.0))
                # Lazy expiration: keep lock until first access after TTL.
                if not self._is_lock_expired(created_at):
                    return False
                self._regen_locks.pop(key, None)

            self._regen_locks[key] = {
                "created_at": now,
            }
            return True

    def release_regen_lock(self, account_id: str, media_id: str) -> None:
        """Release regeneration lock for a post if present."""
        with self._regen_lock_mutex:
            key = self._make_key(account_id, media_id, score_version=1)
            self._regen_locks.pop(key, None)
