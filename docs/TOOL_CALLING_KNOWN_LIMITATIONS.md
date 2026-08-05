# Tool-Calling Known Limitations

This document captures currently accepted limitations for the brand tool-calling workflow.

## 1) `estimate_campaign_cost` is a heuristic

Location:

- `backend/app/services/tool_orchestrator.py` (`_estimate_campaign_cost`)

Current model:

- Base rate for `IMAGE`: `$10` per `10,000` followers.
- Multipliers:
  - `REEL`: `2.5x`
  - `STORY`: `0.5x`
  - `CAROUSEL`: `1.5x`
  - `PACKAGE`: `4x`
- High engagement premium:
  - If engagement rate is above `5%`, apply `+30%`.
- Output range:
  - `min_cost_usd = base * 0.8`
  - `max_cost_usd = base * 1.3`

Why this is acceptable now:

- Fast and deterministic.
- Useful for rough planning and triage.
- No external pricing dependency.

What it does NOT capture (known gaps):

- Region/currency variation.
- Category-specific creator pricing norms.
- Campaign complexity and rights/usage windows.
- Brand fit quality and safety premium/discount.
- Historical negotiated rates.

Operational guidance:

- Treat as planning guidance, not final pricing.
- Require human review before outreach/offer creation.

Future improvements (optional backlog):

1. Add segment multipliers by niche/market tier.
2. Use historical closed-deal data for calibration.
3. Include confidence interval based on data coverage.
4. Expose "estimate_explanation" metadata for transparency.
