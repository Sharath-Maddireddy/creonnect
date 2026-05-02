# Internal Tools & Scripts Documentation

This document describes utility scripts and diagnostic tools available in `internal_tools/` for engineering and operations.

## Overview

The `internal_tools/` directory contains standalone scripts for:
- **Diagnostics** — Inspect state of creators, posts, jobs
- **Data Management** — Populate databases, convert formats
- **Testing** — Smoke tests, end-to-end verification
- **Debugging** — Inspect worker jobs, cache, etc.

All scripts assume a configured `.env` file and running PostgreSQL/Redis.

---

## Running Scripts

**General pattern:**

```bash
# From repo root, with .venv activated
python internal_tools/script_name.py [args]
```

---

## Key Scripts

### 1. populate_redis.py

**Purpose:** Populate Redis with test data or refresh cache.

**Usage:**
```bash
python internal_tools/populate_redis.py
```

**What it does:**
- Seeds Redis with sample post snapshots, creator profiles, and cache entries.
- Useful for testing cache behavior without running full ingestion.

**Output:** Prints confirmation of keys written to Redis.

---

### 2. fetch_thumbnail.py

**Purpose:** Download and save thumbnail for a post/video.

**Usage:**
```bash
python internal_tools/fetch_thumbnail.py <media_url> [--output thumbnail.jpg]
```

**Arguments:**
- `media_url` — URL to media (image or video).
- `--output` — Optional output file path (default: `thumbnail.jpg`).

**What it does:**
- Fetches media from URL.
- For videos, extracts first frame.
- Saves to disk.

---

### 3. vision_diag.py

**Purpose:** Test Gemini vision API and inspect vision payloads.

**Usage:**
```bash
python internal_tools/vision_diag.py <image_url>
```

**What it does:**
- Calls Gemini vision API on provided image.
- Prints parsed vision signals (cringe score, production level, etc.).
- Useful for debugging vision analysis without full post analysis pipeline.

---

### 4. gemini_diag.py

**Purpose:** Test Gemini LLM API and inspect responses.

**Usage:**
```bash
python internal_tools/gemini_diag.py "<prompt>"
```

**What it does:**
- Calls Gemini LLM with provided prompt.
- Prints response.

---

### 5. run_smoke_test.py

**Purpose:** End-to-end smoke test of core workflows.

**Usage:**
```bash
python internal_tools/run_smoke_test.py
```

**What it does:**
- Tests key endpoints (health check, demo dashboard, post analysis).
- Verifies database connectivity.
- Verifies Redis connectivity.
- Reports pass/fail for each test.

**Example output:**
```
✓ Health check passed
✓ Demo dashboard loaded (12 posts)
✓ Post analysis completed
✓ Cringe summary retrieved
✓ All tests passed
```

---

### 6. run_creator_analysis.py

**Purpose:** Run full account analysis for a creator.

**Usage:**
```bash
python internal_tools/run_creator_analysis.py <creator_id> [--with-ai]
```

**Arguments:**
- `creator_id` — Instagram username or user ID.
- `--with-ai` — Include LLM/vision analysis (optional).

**What it does:**
- Fetches creator profile and posts (requires Instagram token).
- Runs dashboard and analytics pipeline.
- Prints summary of metrics, scores, action plan.

---

### 7. run_pool_analysis.py

**Purpose:** Analyze creator pools or batches.

**Usage:**
```bash
python internal_tools/run_pool_analysis.py <csv_file>
```

**Arguments:**
- `csv_file` — CSV with creator IDs/usernames (one per line).

**What it does:**
- Loads creators from CSV.
- Runs analysis for each.
- Outputs results to `artifacts/pool_analysis_results.json`.

---

### 8. run_test_reel.py

**Purpose:** Test reel-specific analysis and features.

**Usage:**
```bash
python internal_tools/run_test_reel.py <reel_url>
```

**What it does:**
- Downloads reel.
- Runs full analysis including vision (S1–S6 scoring).
- Prints detailed diagnostics.

---

### 9. post_analysis_diag.py

**Purpose:** Diagnose post analysis pipeline.

**Usage:**
```bash
python internal_tools/post_analysis_diag.py <post_id>
```

**What it does:**
- Retrieves cached post insights from Redis.
- Inspects derived metrics, benchmarks, content scores.
- Prints diagnostic report.

---

### 10. inspect_rq_job.py

**Purpose:** Inspect RQ background job status and results.

**Usage:**
```bash
python internal_tools/inspect_rq_job.py <job_id>
```

**What it does:**
- Connects to Redis RQ queue.
- Retrieves job by ID.
- Prints job status, progress, result, error.

**Output:**
```
Job ID: abc123
Status: completed
Started: 2026-04-30 14:32:00
Duration: 2.5 seconds
Result: {...}
```

---

### 11. read_job_status.py

**Purpose:** Poll and display RQ job progress in real-time.

**Usage:**
```bash
python internal_tools/read_job_status.py <job_id> [--poll 1]
```

**Arguments:**
- `job_id` — RQ job ID.
- `--poll` — Poll interval in seconds (default: 1).

**What it does:**
- Connects to RQ queue.
- Periodically fetches job status.
- Updates terminal output with progress.
- Exits when job completes.

---

### 12. reel_metrics_diag.py

**Purpose:** Analyze reel-specific metrics and performance.

**Usage:**
```bash
python internal_tools/reel_metrics_diag.py <creator_id>
```

**What it does:**
- Loads creator's reels from database or cache.
- Computes aggregate reel performance.
- Compares reel vs image metrics.
- Prints insights.

---

### 13. test_cristiano_account.py

**Purpose:** Test account analysis with a known creator (Cristiano Ronaldo for testing).

**Usage:**
```bash
python internal_tools/test_cristiano_account.py
```

**What it does:**
- Hardcoded to test against a specific creator account.
- Useful for regression testing; confirms core pipeline still works.

---

### 14. test_cristiano_post.py

**Purpose:** Test post analysis with a known post.

**Usage:**
```bash
python internal_tools/test_cristiano_post.py
```

**What it does:**
- Tests post analysis against a specific hardcoded post.
- Validates S1–S6 scoring, vision integration, etc.

---

### 15. convert_scraped_to_pool.py

**Purpose:** Convert scraped creator data (e.g., from web scraper) into pool format.

**Usage:**
```bash
python internal_tools/convert_scraped_to_pool.py <input_json> [--output output.json]
```

**What it does:**
- Loads scraped creator data from JSON.
- Normalizes and validates fields.
- Outputs pool-compatible JSON.
- Useful for bulk import workflows.

---

### 16. md_to_docx.py

**Purpose:** Convert Markdown docs to Word (.docx) format.

**Usage:**
```bash
python internal_tools/md_to_docx.py <md_file> [--output output.docx]
```

**Arguments:**
- `md_file` — Markdown file path.
- `--output` — Output DOCX file path (default: `output.docx`).

**What it does:**
- Parses Markdown.
- Converts to DOCX format.
- Useful for sharing documentation with non-technical stakeholders.

---

### 17. debug_worker.py

**Purpose:** Debug and test RQ worker behavior.

**Usage:**
```bash
python internal_tools/debug_worker.py
```

**What it does:**
- Starts an RQ worker process.
- Processes jobs from queue.
- Logs detailed diagnostic information.
- Useful for testing job processing without full deployment.

---

### 18. cringe_reel_diag.py, cringe_simple_diag.py

**Purpose:** Diagnostic tools for cringe analysis.

**Usage:**
```bash
python internal_tools/cringe_reel_diag.py <reel_url>
python internal_tools/cringe_simple_diag.py <image_url>
```

**What it does:**
- Runs vision analysis via Gemini.
- Extracts cringe signals and scores.
- Prints diagnostic report for brand safety.

---

### 19. analyze_user_post.py

**Purpose:** Deep analysis of a user's post across all dimensions.

**Usage:**
```bash
python internal_tools/analyze_user_post.py <user_id> <post_id>
```

**What it does:**
- Fetches user profile and specific post from Instagram.
- Runs full pipeline: derived metrics, benchmarking, content score, vision, AI.
- Outputs comprehensive JSON report.

---

### 20. verify_e2e.py

**Purpose:** End-to-end verification of full system.

**Usage:**
```bash
python internal_tools/verify_e2e.py
```

**What it does:**
- Tests all major workflows:
  - Database connectivity and queries.
  - Redis connectivity and caching.
  - LLM API calls.
  - Vision API calls.
  - Post analysis pipeline.
  - Dashboard generation.
- Reports overall system health.

---

## Artifacts & Fixtures

### Directory: `internal_tools/artifacts/`

Output directory for scripts. Contains:
- Analysis results (JSON)
- Logs
- Downloads (thumbnails, media files)
- Exported data

### Directory: `internal_tools/fixtures/`

Test data and fixtures for development:
- Sample post payloads
- Sample creator profiles
- Mock vision responses
- Mock LLM responses

Used by test scripts (e.g., `run_smoke_test.py`) to avoid calling real APIs.

### Directory: `internal_tools/scripts/`

Additional utility scripts (shell, Python) for common operations:
- Database migrations
- Cache flushes
- Data backups
- Environment setup

---

## Common Workflows

### Workflow 1: Smoke Test After Deployment

```bash
python internal_tools/run_smoke_test.py
```

Verify all core systems are operational.

### Workflow 2: Test a New Feature

```bash
# Set up test environment
python internal_tools/populate_redis.py

# Run smoke test
python internal_tools/run_smoke_test.py

# Test specific feature (e.g., post analysis)
python internal_tools/analyze_user_post.py demo_user demo_post
```

### Workflow 3: Debug a User's Account

```bash
python internal_tools/run_creator_analysis.py @username --with-ai

# If issues, dive deeper
python internal_tools/post_analysis_diag.py <post_id>
python internal_tools/vision_diag.py <image_url>
```

### Workflow 4: Inspect a Background Job

```bash
# Get job ID from frontend or logs
python internal_tools/inspect_rq_job.py <job_id>

# Or watch in real-time
python internal_tools/read_job_status.py <job_id>
```

### Workflow 5: Bulk Creator Analysis

```bash
# Create CSV with creator IDs
cat > creators.csv << EOF
creator1
creator2
creator3
EOF

# Run analysis
python internal_tools/run_pool_analysis.py creators.csv

# Results in artifacts/pool_analysis_results.json
```

---

## Environment Requirements

All scripts require:
- `.env` file with proper configuration (see `INFRASTRUCTURE.md`).
- PostgreSQL running and accessible.
- Redis running and accessible.
- OpenAI API key (for LLM scripts).
- Gemini API key (for vision scripts, optional).

To check connectivity:

```bash
python -c "from backend.app.infra.database import get_sync_sessionmaker; print('DB OK')"
python -c "from backend.app.infra.redis_client import get_redis; print('Redis OK')"
```

---

## Troubleshooting Scripts

### Script Fails: "Module not found"

```bash
# Ensure you're in virtualenv
source .venv/bin/activate
python internal_tools/script.py
```

### Script Fails: "Database connection refused"

```bash
# Check DATABASE_URL in .env
# Ensure PostgreSQL is running
psql -U postgres -d creonnect -c "SELECT 1"
```

### Script Fails: "Redis connection refused"

```bash
# Check REDIS_URL in .env
# Ensure Redis is running
redis-cli ping
```

### Script Fails: "API key invalid"

```bash
# Verify OPENAI_API_KEY and GEMINI_API_KEY in .env
# Check API quota and billing
```

---

## Adding New Scripts

1. Create `internal_tools/new_script.py`.
2. Import common utilities:
   ```python
   from backend.app.infra.database import get_sync_sessionmaker
   from backend.app.infra.redis_client import get_redis
   from backend.app.utils.logger import logger
   ```
3. Add docstring and CLI argument parsing (using `argparse`).
4. Log progress with `logger.info()`.
5. Handle errors gracefully.
6. Document in this file.

---

## Summary

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| run_smoke_test.py | System health check | None | Pass/fail report |
| run_creator_analysis.py | Account analysis | creator_id | Dashboard JSON |
| run_pool_analysis.py | Batch analysis | CSV file | Results JSON |
| post_analysis_diag.py | Post diagnostics | post_id | Diagnostic report |
| vision_diag.py | Vision API test | image_url | Vision signals |
| inspect_rq_job.py | Job status | job_id | Job details |
| populate_redis.py | Cache seeding | None | Keys written |
| verify_e2e.py | Full system test | None | Health report |

