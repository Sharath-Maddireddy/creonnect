"""
Structured logging utility for Creonnect backend.
Provides consistent logging across all modules.
"""

import logging
import os

# Configure logging based on environment
log_level = logging.DEBUG if os.getenv("ENV") == "dev" else logging.INFO

logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("creonnect")
