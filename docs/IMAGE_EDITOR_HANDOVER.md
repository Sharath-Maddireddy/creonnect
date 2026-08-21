# Image Editor — Handover

**Branch:** `feat/creator-trend-results`
**Date:** 2026-08-19
**Scope:** Creator Image Editor filter quality (`/api/v1/creator/image-editor`)

---

## 1. Context

Reported problem: gen-AI filters in the Creator Image Editor "didn't have a wow factor" —
results looked indistinguishable from a plain deterministic filter.

### Root cause
Every one of the 9 style prompts in `ai_filter_prompts_v1.json` used an identical, very
restrictive template: *"Only apply a [style] look through [color/lighting/grain]... Preserve
facial geometry, ... position, camera viewpoint, framing, crop, perspective, objects... Do not
redraw, beautify, replace, or reinterpret any person."* This capped every style to
color/lighting/grain adjustments only — the same vocabulary a deterministic filter uses — so
results never looked like a real generative transformation.

---

## 2. Fix: two-tier category system

Added a `category` field (`brand-production` | `trending`) to the style config and split the
prompt strategy accordingly:

- **`brand-production`** (4 styles) — kept the original strict, identity-locked, campaign-safe
  template. These are meant to be subtle/professional, not dramatic.
- **`trending`** (8 styles) — rewritten to explicitly request a **"bold, fully committed style
  transformation... with noticeable intensity so the result reads as a clear before/after."**
  Still keeps the person recognizable and blocks adding/removing people or objects, but no
  longer caps every edit to color/lighting tweaks.

### Ported filters
3 filters were ported in from a legacy catalog as `brand-production` styles:
`brand_kit_color_match`, `product_pop_enhancement`, `relight`. Ported "as fixed styles"
(baked-in default prompt, no new per-style settings UI) — matching how the other 9 styles
already work.

### Final catalog (12 styles)

| Category | Styles |
|---|---|
| `trending` | Lofi Dusk, Sun-Kissed, Old Fuji, Y2K Digicam, Disposable Flash, Golden Hour Film, VSCO Muted, Polaroid Vintage |
| `brand-production` | Luxury Product, Brand-Kit Color Match, Product-Pop Enhancement, Relight |

### Files touched
- [backend/app/domain/image_editor_models.py](../backend/app/domain/image_editor_models.py) — added `category` to `CreatorImageEditorStyle`
- [backend/app/services/creator_image_editor_config_service.py](../backend/app/services/creator_image_editor_config_service.py) — pass `category` through
- [backend/app/config/image_editor/creator_image_editor_v1.json](../backend/app/config/image_editor/creator_image_editor_v1.json) — 12 styles with `category`
- [backend/app/config/image_editor/ai_filter_prompts_v1.json](../backend/app/config/image_editor/ai_filter_prompts_v1.json) — rewritten prompts, 12 entries
- [backend/app/services/creator_image_editor_job_service.py](../backend/app/services/creator_image_editor_job_service.py) — removed dead deterministic-fallback code path
- [backend/app/tests/test_creator_image_editor.py](../backend/app/tests/test_creator_image_editor.py) — updated for 12-style split, dual prompt templates

---

## 3. Verified with real Gemini calls

- `lofi_dusk` (trending) on a real 2-person photo: faces/pose/clothing preserved exactly, but
  the scene was genuinely reinterpreted — daytime blue court → moody dusk atmosphere, grain,
  cooler color science. Clear "wow" difference from a filter.
- `relight` (brand-production) on the same photo: same composition, just clean added studio
  lighting — correctly conservative.

---

## 4. Local dev setup

Added to `backend/.env` (gitignored, local-only) to allow browser testing without real Instagram
OAuth:

```
DEV_AUTH_BYPASS=1
DEV_AUTH_BYPASS_ACCOUNT_ID=local-dev-user
```

This only activates when `is_production_environment()` is false — see
`backend/app/api/instagram_auth_routes.py:43-52`. **Remove or leave unset before deploying.**

`.claude/launch.json` created with two dev-server configs:

```json
{
  "configurations": [
    {"name": "backend", "runtimeExecutable": ".venv/Scripts/python.exe",
     "runtimeArgs": ["-m", "uvicorn", "backend.main:app", "--reload", "--port", "8000"], "port": 8000},
    {"name": "frontend", "runtimeExecutable": "npm",
     "runtimeArgs": ["--prefix", "frontend", "run", "dev"], "port": 3000}
  ]
}
```

Manual equivalent:
```bash
# backend
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
# frontend
npm --prefix frontend run dev
```
Editor UI: `http://localhost:3000/creator/image-editor`

---

## 5. Demo script for the team

[scripts/demo_image_editor.py](../scripts/demo_image_editor.py) reproduces the side-by-side
comparison from §3 for anyone on the team to run themselves. Stdlib-only, no extra pip installs.

```bash
python scripts/demo_image_editor.py --image path/to/photo.jpg
```

Submits the same photo through one `trending` style (`lofi_dusk` by default) and one
`brand-production` style (`relight` by default), polls both jobs to completion, and saves both
results to `./demo_results/`. Run `--help` for options (custom styles, base URL, output dir).

---

## 6. Test status

- Targeted suite (creator image editor, creator studio, job idempotency, outbound media):
  **34/34 passing**.
- Full backend suite: **620 passed, 4 skipped, 6 failed**. The 6 failures are all in
  `test_rq_account_analysis_orchestration.py`, pre-existing and unrelated to this work — root
  cause identified: those specific tests never authenticate (missing
  `app.dependency_overrides[get_current_instagram_user]`, unlike the one test in that file that
  does), so they legitimately 401 against the real auth dependency. Confirmed via
  `git log`/`git diff` that the file has no uncommitted changes and wasn't touched this session.
  **Not fixed** — left out of scope per direction.

---

## 7. Open items / suggested follow-ups

1. **`DEV_AUTH_BYPASS`** in `backend/.env` should be removed/unset before any shared or
   production deploy.
2. Nothing has been **committed** — all changes are in the working tree on
   `feat/creator-trend-results`. Review `git status`/`git diff` and commit when ready.
3. Untested: identity preservation on `trending` styles other than `lofi_dusk` (e.g. Y2K
   Digicam, Disposable Flash) — worth a couple more real-photo runs before considering this
   fully validated across the catalog.
