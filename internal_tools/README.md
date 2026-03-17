# Internal Tools

This folder contains development-only scripts, fixture assets, and generated artifacts that support the product but are not part of the launch-facing app surface.

- `artifacts/`: local outputs from diagnostics and smoke runs
- `fixtures/`: raw Instagram fixture inputs for internal tooling
- `scripts/`: auxiliary automation scripts
- `*.py`: standalone diagnostics and ops helpers

Run these scripts from the repo root so imports resolve consistently, for example:

```bash
python internal_tools/run_profile_analysis.py --fixture internal_tools/fixtures/ig_dhirendra_raw.json
python internal_tools/run_smoke_test.py
python internal_tools/analyze_user_post.py
```
