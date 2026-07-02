"""Environment numeric parsing helpers."""

from __future__ import annotations

import os

from backend.app.utils.logger import logger


def get_int_env(name: str, default: int) -> int:
    """Return integer env var with safe fallback + warning on invalid values."""
    raw_value = (os.getenv(name) or "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %s", name, raw_value, default)
        return default

