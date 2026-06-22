# Deployment and Cost Planning

This note captures the operational assumptions from sections 6.1, 6.2, and 6.3.
It separates what is implemented in repo code from what must be provisioned in cloud infrastructure.

## 6.1 Infrastructure

Implemented in repo code:
- Gemini video analysis now pins the primary model to `gemini-2.5-flash-lite` and the fallback to `gemini-flash-lite-latest`.
- Gemini Flash-Lite pricing references are centralized in `backend/app/ai/gemini_constants.py`.

Requires external AWS infrastructure or deployment IaC:
- EC2 auto-scaling Option C as the default worker strategy.
- Reference manifest: `infra/ec2_autoscaling_option_c.yaml`.
- S3 Intelligent-Tiering from day one.
- Reference manifest: `infra/s3_intelligent_tiering_default.yaml`.
- VPC S3 Gateway Endpoint to remove S3 traffic from NAT Gateway charges.
- Reference manifest: `infra/s3_gateway_endpoint_default.yaml`.

Planning note:
- The repo does not currently contain AWS IaC for EC2, S3, or VPC networking, so these items remain deployment requirements rather than code changes.

## 6.2 Capacity Planning for High Concurrency

Operational guidance:
- Treat sub-120-second processing as a target for normal load, not a hard SLA at daily 500-concurrent peaks.
- Budget recurring 500-concurrent peaks with right-sized Spot workers and queue-depth autoscaling.
- Planning estimate: about `$47-$52/month` for EC2 at a daily recurring 500-concurrent peak versus about `$229.53/month` if provisioned for full sub-120-second concurrency.
- Keep capacity elastic enough to absorb spikes without paying for always-on full-concurrency throughput.

Repo status:
- The backend already uses queued background jobs for reel, account, and trend analysis.
- The frontend queue-position indicator is intentionally excluded from this change set.

## 6.3 Ongoing

Operational guidance:
- Verify cost estimates against AWS Cost Explorer and Google Cloud billing after a few weeks in production.
- Re-check Gemini token pricing whenever the model version changes, since output token pricing may shift with new model versions.
- Keep all figures in this document as planning estimates, not guarantees.

## Gemini Pricing Reference

Flash-Lite planning assumptions currently used in the repo:
- Input tokens: `$0.10 / 1M`
- Output tokens: `$0.40 / 1M`

These values are documentation-only unless a future cost model consumes them directly.






