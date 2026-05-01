"""Environment loading helpers for API, workers, and scripts."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_app_env(*, override: bool = False) -> None:
    """Load repo and backend dotenv files in a stable order."""
    repo_root = Path(__file__).resolve().parents[3]
    root_env = repo_root / ".env"
    backend_env = repo_root / "backend" / ".env"

    load_dotenv(root_env, override=override)
    load_dotenv(backend_env, override=override)

