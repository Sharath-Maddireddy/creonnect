"""Shared Gemini model and pricing constants."""

from __future__ import annotations


PRIMARY_GEMINI_MODEL = "gemini-2.5-flash-lite"
FALLBACK_GEMINI_MODEL = "gemini-flash-lite-latest"

# Planning reference for Flash-Lite budgeting.
# Re-check output token pricing whenever the Gemini model version changes.
FLASH_LITE_INPUT_COST_PER_1M_TOKENS_USD = 0.10
FLASH_LITE_OUTPUT_COST_PER_1M_TOKENS_USD = 0.40



