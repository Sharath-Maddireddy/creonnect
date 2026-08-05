# AI Image Editor Implementation Plan

## Goal

Build a new backend-owned AI image editor feature inside the Python repo that supports:

- deterministic `filter-only` editing as the default product behavior
- explicit `AI edit` mode as a separate, opt-in workflow
- persistent storage of original assets, edit requests, results, and benchmark runs
- an internal model comparison pipeline for Gemini vs GPT Image

This plan treats the received JSON config and PRD as the source of intended behavior, not the current frontend mock implementation.

## Product Direction

The new feature should be split into two modes.

### 1. Filter-Only Mode

This is the default editing path.

Requirements:

- always starts from the immutable original uploaded asset
- uses deterministic image processing only
- preserves source width, height, aspect ratio, crop, composition, geometry, text, logos, people, products, and background
- allows only approved global adjustments such as temperature, tint, exposure, contrast, highlights, shadows, saturation, vibrance, grain, vignette, bloom, and global sharpness
- returns one stable result per request
- deduplicates identical requests

This mode must **not** use a generative image model.

### 2. AI Edit Mode

This is a separate user action, not a fallback for filters.

Requirements:

- explicit user choice to enter AI edit mode
- backend-only provider calls
- full audit trail of prompt, model, latency, cost, retries, and result
- original asset remains immutable
- no silent switching from filter mode to AI mode

## Why We Are Building It This Way

The supplied `filter-only` config explicitly says:

- default engine should be deterministic and non-generative
- regeneration must always start from the original asset
- identical requests should be deduplicated
- GPT Image should only be used in an explicit AI edit mode

The current repo does not fully implement that behavior yet, so this backend feature becomes the new source of truth.

## Proposed Backend Architecture

### API Layer

Add a new route module:

- `backend/app/api/image_editor_routes.py`

Responsibilities:

- receive uploads and edit requests
- validate request mode and allowed operations
- issue async jobs when needed
- expose job polling and asset retrieval metadata

### Domain Models

Add a new domain module:

- `backend/app/domain/image_editor_models.py`

Suggested request and response models:

- `UploadImageResponse`
- `ImageEditorConfigResponse`
- `ApplyFilterRequest`
- `ApplyFilterResponse`
- `RegenerateFilterRequest`
- `AIModeEditRequest`
- `AIModeEditResponse`
- `ImageEditJobStatus`
- `BenchmarkRunRequest`
- `BenchmarkRunResponse`
- `BenchmarkResultResponse`
- `QualityRatingRequest`

### Service Layer

Add new service modules:

- `backend/app/services/image_editor_config_service.py`
- `backend/app/services/image_editor_asset_service.py`
- `backend/app/services/image_editor_filter_service.py`
- `backend/app/services/image_editor_ai_service.py`
- `backend/app/services/image_editor_benchmark_service.py`
- `backend/app/services/image_editor_jobs.py`

Responsibilities:

- config loading and validation
- immutable asset management
- deterministic filter compilation and execution
- AI edit orchestration
- benchmark orchestration and reporting
- background job processing

### Persistence Layer

Extend `backend/app/infra/models.py` with image-editor-specific tables.

Suggested tables:

- `ImageAsset`
- `ImageEditRequest`
- `ImageEditResult`
- `ImageEditJob`
- `ImageBenchmarkRun`
- `ImageBenchmarkResult`
- `ImageBenchmarkRating`

Create an Alembic migration for all new tables.

## Suggested Data Model

### ImageAsset

Purpose:

- store original and derived images

Suggested fields:

- `id`
- `account_id` or `user_id`
- `storage_key`
- `public_url` or signed access reference
- `mime_type`
- `width`
- `height`
- `file_size_bytes`
- `sha256`
- `is_original`
- `parent_asset_id`
- `created_at`

Rules:

- original uploaded image is immutable
- all regenerations reference the original asset id

### ImageEditRequest

Purpose:

- record the user request before processing

Suggested fields:

- `id`
- `account_id`
- `original_asset_id`
- `source_asset_id`
- `mode` (`filter_only`, `ai_edit`, `benchmark`)
- `config_version`
- `request_hash`
- `goal_id`
- `style_id`
- `intensity_id`
- `selected_controls_json`
- `compiled_prompt`
- `engine`
- `status`
- `dedupe_hit_request_id`
- `created_at`

### ImageEditResult

Purpose:

- store the output and execution metadata

Suggested fields:

- `id`
- `request_id`
- `result_asset_id`
- `engine`
- `provider`
- `model_id`
- `latency_ms`
- `cost_usd`
- `output_width`
- `output_height`
- `warnings_json`
- `assertions_passed_json`
- `created_at`

### ImageEditJob

Purpose:

- async processing and polling

Suggested fields:

- `id`
- `request_id`
- `account_id`
- `job_type`
- `status`
- `current_step`
- `total_steps`
- `step_label`
- `error_message`
- `retry_count`
- `started_at`
- `completed_at`

### ImageBenchmarkRun

Purpose:

- group one benchmark execution across many images

Suggested fields:

- `id`
- `created_by`
- `dataset_name`
- `status`
- `total_images`
- `total_tasks`
- `max_spend_usd`
- `notes`
- `started_at`
- `completed_at`

### ImageBenchmarkResult

Purpose:

- one model result for one image and one instruction

Suggested fields:

- `id`
- `benchmark_run_id`
- `image_asset_id`
- `model_provider`
- `model_id`
- `prompt`
- `edited_asset_id`
- `cost_usd`
- `latency_ms`
- `status`
- `retry_count`
- `http_status`
- `output_resolution`
- `error_code`
- `created_at`

## Configuration Strategy

The file `creonnect-image-filter-only-config-v3` should become backend-controlled configuration.

Recommended approach:

1. Store a normalized version under the repo, for example:
   - `backend/app/config/image_editor/filter_only_config_v3.json`
2. Load it only from the backend
3. Validate it on startup or first use
4. Include `config_version` in every request and result row
5. Never let the mobile or frontend client be the source of truth for protected rules

Config service responsibilities:

- load raw JSON
- validate required sections
- expose safe frontend-facing metadata
- compile mode-specific request policies

## Filter-Only Processing Engine

### Default Recommendation

Use a deterministic Python image-processing path as the default engine.

Initial choice:

- `Pillow`

Reason:

- simplest reliable path for deterministic global image filters
- suitable for brightness, contrast, color, sharpness, blur, overlays, vignette, and grain
- easier to validate than model-driven outputs

Possible future additions:

- OpenCV for more advanced deterministic operations
- GPU shader/native mobile path if the frontend later needs local previews

### Allowed Operations

Implement only approved global operations:

- white balance / temperature
- tint
- exposure
- contrast
- highlights
- shadows
- saturation
- vibrance
- tone curve
- uniform grain
- uniform vignette
- uniform bloom
- mild global sharpening

### Forbidden Operations

Hard reject requests containing or implying:

- crop
- reframe
- background blur
- background replacement
- object add/remove
- inpainting
- outpainting
- local retouching
- face/body/hand/hair repair
- text generation
- logo generation
- local relighting

### Deterministic Regeneration Rules

Every filter regeneration must:

- start from `original_asset_id`
- use a canonicalized request payload
- compute a request hash
- return existing completed result when the request hash already exists for the same original asset and config version

## AI Edit Mode

AI edit mode should be implemented only after filter mode is stable.

### Core Rules

- route must be separate from filter apply
- requires explicit mode selection
- prompt must be sanitized and stored
- provider selection must be backend-controlled
- output must be persisted with model and cost metadata

### Provider Support

Planned providers:

- OpenAI GPT Image
- Google Gemini image editing

### Safety Rules

- never expose API keys to client apps
- enforce max concurrent jobs per user
- require idempotency key from client or generate one server-side
- maintain retry limits and failure logging
- keep original asset immutable

## API Plan

### Asset Endpoints

- `POST /api/v1/image-editor/assets`
  - upload original image
- `GET /api/v1/image-editor/assets/{asset_id}`
  - fetch metadata

### Config Endpoint

- `GET /api/v1/image-editor/config`
  - returns frontend-safe config metadata
  - does not expose unsafe/internal processing rules beyond what the UI needs

### Filter-Only Endpoints

- `POST /api/v1/image-editor/filters/apply`
  - apply deterministic filter-only request
- `POST /api/v1/image-editor/filters/regenerate`
  - rerun from original asset using the saved filter recipe
- `GET /api/v1/image-editor/edits/{request_id}`
  - fetch request + latest result metadata

### AI Edit Endpoints

- `POST /api/v1/image-editor/ai-edits`
- `POST /api/v1/image-editor/ai-edits/{request_id}/retry`

### Job Endpoints

- `GET /api/v1/image-editor/jobs/{job_id}`

### Benchmark Endpoints

- `POST /api/v1/image-editor/benchmarks/runs`
- `GET /api/v1/image-editor/benchmarks/runs/{run_id}`
- `GET /api/v1/image-editor/benchmarks/results`
- `POST /api/v1/image-editor/benchmarks/results/{result_id}/rating`
- `GET /api/v1/image-editor/benchmarks/export`

## Background Jobs

Use RQ for asynchronous work where appropriate.

Recommended async tasks:

- large image filter exports
- AI edits
- benchmark batch runs
- benchmark retries

Suggested queue jobs:

- `run_filter_apply_job`
- `run_ai_edit_job`
- `run_benchmark_run_job`
- `run_benchmark_single_result_job`

Job rules:

- benchmark failures should not stop the full run
- retry up to configured limit
- persist progress for polling
- track per-job status and error details

## Storage Strategy

### Original and Result Assets

Use object storage-compatible design.

Suggested path structure:

- originals:
  - `image-editor/originals/{account_id}/{asset_id}.{ext}`
- results:
  - `image-editor/results/{account_id}/{request_id}/{result_id}.{ext}`
- benchmark outputs:
  - `image-editor/benchmarks/{run_id}/{model}/{image_id}.{ext}`

This repo already uses `boto3`, so S3-compatible storage is a natural fit.

### Metadata

Persist all request and result metadata in Postgres via SQLAlchemy models.

## Validation and Guardrails

Validation should happen before any processing starts.

Reject when:

- original immutable asset is missing
- selected control is not filter-only compatible during filter mode
- request attempts structural edits while in filter-only mode
- result dimensions would differ from source dimensions during filter-only mode
- processing engine is generative during strict filter-only mode

Warn when:

- source image is highly compressed
- filter profile uses extreme grain, contrast, vignette, or saturation

Post-process assertions for filter mode:

- output width equals source width
- output height equals source height
- no crop or resize occurred
- only approved global adjustments were applied

## Benchmarking Plan

The benchmark tool is internal and should compare Gemini vs GPT Image using the same dataset and prompts.

### What to Capture

Per benchmark result:

- source image
- output image
- prompt
- provider
- model id/version
- latency
- cost
- status
- retry count
- resolution
- timestamp
- optional manual quality rating

### Aggregate Views

Per model:

- average cost
- total cost
- average latency
- p90 latency
- p95 latency
- success rate
- average quality rating

### Operational Controls

- spend cap per benchmark run
- visible progress while running
- failures logged separately
- export results to CSV/JSON

## Dependency Changes

Recommended additions to `backend/requirements.txt`:

- `Pillow`

Optional later:

- `opencv-python-headless`

Do not add heavy image-edit dependencies until Phase 1 deterministic filter mode is underway and validated.

## Testing Plan

Add narrow backend tests under `backend/app/tests/`.

### Config Tests

- config loads successfully
- invalid config fails validation
- forbidden controls are rejected

### Filter Engine Tests

- identical request produces identical output metadata
- output size equals source size
- unsupported operation is rejected
- regeneration uses original asset id
- dedupe returns prior result

### API Tests

- upload asset works
- apply filter request validates correctly
- AI edit route cannot be called in filter-only mode
- job polling returns correct states

### Benchmark Tests

- batch run creates expected result rows
- one model failure does not stop other results
- aggregate metrics compute correctly

## Rollout Plan

### Phase 1

Backend-only filter engine MVP

- config loader
- asset upload
- deterministic filter apply
- immutable original storage
- dedupe
- request/result persistence

### Phase 2

Frontend integration to new Python endpoints

- editor fetches backend config
- filter actions call backend
- one result per request
- no direct provider calls from client

### Phase 3

Explicit AI edit mode

- provider-backed edits
- prompt and cost tracking
- retry and failure handling

### Phase 4

Model comparison benchmark tool

- dataset runner
- aggregate reporting
- export
- rating workflow

## Recommended First Build Slice

Start with the smallest backend slice that creates immediate value:

1. add `image_editor_models.py`
2. add config loader service
3. add asset table + upload route
4. add deterministic `filter-only` apply route using Pillow
5. add request hash deduplication
6. add tests for output dimension preservation and dedupe

This gives the team a usable backend-owned feature foundation before any AI model work begins.

## Open Decisions

Still to confirm with stakeholders:

- exact object storage target and bucket naming
- max upload size and allowed output formats
- whether filter jobs should be synchronous for small images or always async
- how manual quality review will be done for benchmarks
- whether end users will ever select Gemini vs GPT Image directly in production

## Summary

The new Python feature should make `filter-only` editing deterministic and backend-controlled, while reserving GPT Image and Gemini for an explicit AI edit path. That separation is the key architectural move that prevents the current inconsistent behavior where a simple edit can generate different images across repeated clicks.
