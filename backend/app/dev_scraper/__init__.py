"""DEV ONLY: for fixture generation/testing. Not used in production."""

from backend.app.dev_scraper.instagram_profile import fetch_instagram_profile

import warnings

warnings.warn(
    "dev_scraper is deprecated. Use backend.app.ingestion.instagram_oauth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["fetch_instagram_profile"]
