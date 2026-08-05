# AI Image Editor Filters PRD Implementation Plan

## Purpose

Implement the filter catalog in `Creonnect_Image_Editor_Filters_PRD.docx` inside the existing Python-backed Image Editor. This plan replaces the temporary AI style presets with a curated set of brand-production and trend filters.

## Product Rules

- Keep `filter-only` mode as the fast, deterministic path for basic global adjustments.
- Make transformative filters explicit `ai-edit` actions; never silently switch modes or providers.
- Start every operation from an immutable original asset.
- Deduplicate an identical original asset, filter specification, provider, and settings by returning its saved result.
- Do not use licensed third-party characters, costume designs, logos, or brand assets without verified permission.
- Require campaign-safe metadata for filters used with sponsored content.

## Scope

### Brand-production filters

1. **Brand-Kit Color Match**
   - Inputs: brand palette (one to five hex colors), optional strength, optional skin-tone preservation.
   - Output: controlled color-grade request, with palette and settings recorded for review.

2. **Product-Pop Enhancement**
   - Inputs: optional product region/mask when available; otherwise AI-detected product region.
   - Output: increased local clarity, lighting, and contrast on the product while avoiding excessive global saturation.

3. **Relight**
   - Inputs: lighting direction and mood preset.
   - Output: AI relight request with no identity, body, or product change instruction.

4. **Before/After Composite**
   - Inputs: two immutable source assets, split direction, divider label options.
   - Output: deterministic aligned split-view composite where possible; AI alignment is explicit and recorded if required.

5. **Placement Crop/Resize**
   - Inputs: `9:16`, `4:5`, or `1:1`; subject-aware framing enabled/disabled.
   - Output: derived placement asset with crop metadata. This is a deliberate exception to filter-only geometry preservation.

6. **Saved Looks**
   - Inputs: a name and current deterministic color/tone recipe.
   - Output: user-owned reusable preset that never stores a provider key or generated image prompt.

### Trend filters

1. **Original Superhero Suit**
   - Inputs: original suit family, mask toggle, emblem family, and color scheme.
   - Output: an AI costume transformation using Creonnect-owned prompt language only.
   - Guardrail: reject names or prompts requesting Marvel, Disney, Spider-Man, or other third-party character/costume IP.

2. **Authentic Grain**
   - Implement with the existing deterministic engine: grain, restrained light leak, and subtle desaturation.
   - This remains a low-latency filter-only option.

3. **Illustrated Portrait**
   - Original editorial illustration transformation; no named artist-style imitation.

4. **Miniature Collectible**
   - Original toy/collectible transformation with no third-party character or product branding.

## Architecture

### Backend

- Add a backend-owned filter catalog configuration containing:
  - filter ID, title, category, mode, inputs, provider preference, safety classification, campaign eligibility, and prompt template version.
- Extend image-editor request models with a typed `filter_id`, `settings`, optional `secondary_asset_id`, `campaign_id`, and optional `brand_kit_id`.
- Validate every setting server-side and compile prompts only on the backend.
- Route deterministic filters to Pillow; route transformative filters to the explicitly selected AI provider.
- Store input payload, compiled prompt version, provider/model, latency, usage metadata, result asset, and moderation outcome.
- Keep provider credentials isolated under `IMAGE_EDITOR_AZURE_*` and `IMAGE_EDITOR_GEMINI_*` variables.

### Data model and migrations

Add tables or columns for:

- `image_editor_filter_catalog_version` on each edit request.
- `image_editor_saved_looks`: account ID, name, deterministic recipe JSON, timestamps.
- `image_editor_brand_kits`: account/brand owner, display name, palette JSON, optional approved logo asset reference, timestamps.
- `image_editor_filter_usage`: account ID, campaign ID, filter ID, request ID, provider/model, latency, status, and moderation decision.
- `image_edit_requests`: filter ID, settings JSON, secondary source asset ID, campaign ID, compiled prompt version, provider/model, latency, and moderation metadata.

Migration requirements:

- Be idempotent for environments where `init_db()` created tables before Alembic ran.
- Preserve all existing image-editor records.
- Add indexes for account ID, campaign ID, filter ID, and request hash.

### API surface

- `GET /api/v1/image-editor/filter-catalog`
- `POST /api/v1/image-editor/filters/{filter_id}/apply`
- `POST /api/v1/image-editor/brand-kits`
- `GET /api/v1/image-editor/brand-kits`
- `POST /api/v1/image-editor/saved-looks`
- `GET /api/v1/image-editor/saved-looks`
- `POST /api/v1/image-editor/composites/before-after`
- `POST /api/v1/image-editor/crops`
- `GET /api/v1/image-editor/usage`

Existing deterministic endpoints remain supported during migration, then the frontend moves to the catalog endpoints.

## Frontend Experience

1. Replace the temporary AI preset dropdown with catalog-driven cards grouped into **Brand & Production** and **Trending**.
2. Show only the input controls required by the chosen filter.
3. Display mode and expectations before submission:
   - `Fast deterministic edit` for filter-only operations.
   - `AI transformation` for provider-backed operations.
4. Provide a second upload slot only for Before/After Composite.
5. Show crop placement previews for Reels/Stories, Feed, and Square.
6. Let users save a completed deterministic look with a name.
7. Show campaign-safety status and provider/result metadata after an edit.

## Safety and Compliance

- Maintain a denylist for requests that name protected characters, franchises, trademarks, or artist-style imitation.
- Compile the Superhero Suit prompt from allowed original attributes only.
- Moderate AI prompts before provider submission and retain the decision in the audit record.
- Hide trend transformations or require review when the request is associated with a sponsored campaign, pending the product approval workflow.
- Do not submit brand logos to a provider unless the user owns or is authorized to use them.

## Delivery Phases

### Phase 1: Catalog and deterministic production tools

- Replace temporary presets with the PRD catalog UI.
- Ship Authentic Grain, Brand-Kit Color Match (palette input), placement crop/resize, Before/After Composite, and Saved Looks.
- Add persistence, analytics, and campaign metadata.

### Phase 2: AI production tools

- Ship Product-Pop and Relight with GPT Image 2 as the primary provider.
- Add Gemini comparison support and a small internal evaluation set.
- Add latency, cost, and output-quality telemetry.

### Phase 3: Trend transformations

- Ship Original Superhero Suit, Illustrated Portrait, and Miniature Collectible.
- Enforce IP and campaign-safety controls before enabling each filter.

### Phase 4: Rollout and measurement

- Feature-flag the catalog by account cohort.
- Track filter adoption, editor sessions, generation failures, latency, moderation rate, and campaign complaints.
- Validate the PRD targets after 30 and 60 days.

## Verification

- Unit tests for catalog validation, prompt compilation, denylist rules, request hashes, and deterministic outputs.
- API tests for authorization, asset ownership, saved looks, brand kits, composite/crop inputs, and provider failures.
- Migration test against an already-initialized image-editor database.
- Provider contract tests with mocked GPT Image and Gemini responses; live smoke tests use a non-production account.
- Frontend build and interaction tests for each filter card and required input state.

## Assumptions To Validate

- Brand-kit data does not currently exist in the repo and will first be entered in the Image Editor.
- GPT Image 2 is the primary provider for quality-sensitive AI transforms; Gemini is a comparable provider, not an automatic fallback.
- Sponsored campaign approval workflow is not yet implemented, so campaign-linked trend filters will default to a visible warning until Trust & Safety defines the approval rule.
