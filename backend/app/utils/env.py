"""Environment loading helpers for API, workers, and scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


_NON_PRODUCTION_ENVS = {"dev", "development", "test"}


def load_app_env(*, override: bool = True) -> None:
    """Load repo and backend dotenv files in a stable order.

    override=True ensures .env values always win over system env vars,
    which prevents stale keys from lingering after regeneration.
    """
    repo_root = Path(__file__).resolve().parents[3]
    root_env = repo_root / ".env"
    backend_env = repo_root / "backend" / ".env"

    load_dotenv(root_env, override=override)
    load_dotenv(backend_env, override=override)

def is_production_environment(*, env_value: str | None = None) -> bool:
    """Return True when ENV should be treated as production-like."""
    normalized_env = (env_value if env_value is not None else os.getenv("ENV", "dev")).strip().lower()
    return normalized_env not in _NON_PRODUCTION_ENVS


def is_feature_enabled(feature_name: str) -> bool:
    """Check whether a runtime feature flag is enabled.

    Environment variable: FEATURE_{name} (e.g., FEATURE_TREND_RECOMMENDATIONS_V2).
    Values: "true", "1", "yes" (case-insensitive) → enabled.
    """
    env_key = f"FEATURE_{feature_name}"
    raw = (os.getenv(env_key) or "").strip().lower()
    return raw in ("true", "1", "yes")


def get_rollout_pct(feature_name: str) -> int:
    """Get staged rollout percentage for a feature (default 100 if fully enabled, 0 if disabled)."""
    env_key = f"FEATURE_{feature_name}_ROLLOUT_PCT"
    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        # If no rollout pct set but feature is enabled, default to 100
        return 100 if is_feature_enabled(feature_name) else 0
    try:
        pct = int(raw)
        return max(0, min(100, pct))
    except ValueError:
        return 0

