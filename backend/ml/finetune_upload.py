"""
Creonnect Fine-Tuning Script
=============================
Uploads the cleaned training data to OpenAI and starts a fine-tuning job
for GPT-4o-mini.

Usage:
    python -m backend.ml.finetune_upload

Environment:
    OPENAI_API_KEY must be set.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

TRAIN_PATH = ROOT_DIR / "backend" / "data" / "fine_tune_upload.cleaned.jsonl"
VAL_PATH = ROOT_DIR / "backend" / "data" / "chat_val.jsonl"

BASE_MODEL = "gpt-4o-mini-2024-07-18"
SUFFIX = "creonnect-v1"
N_EPOCHS = 3


def _check_prerequisites() -> None:
    """Verify all prerequisites before starting."""
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable is not set.")
        print("  Set it with: $env:OPENAI_API_KEY = 'sk-...'")
        raise SystemExit(1)

    if not TRAIN_PATH.exists():
        print(f"ERROR: Training file not found: {TRAIN_PATH}")
        print("  Run the data pipeline first: python -m backend.ml.build_finetune_upload")
        raise SystemExit(1)

    if not VAL_PATH.exists():
        print(f"WARNING: Validation file not found: {VAL_PATH}")
        print("  Proceeding without validation set.")


def _upload_file(client, path: Path, purpose: str = "fine-tune"):
    """Upload a file to OpenAI and wait for processing."""
    print(f"\n  Uploading {path.name} ({path.stat().st_size // 1024}KB)...")
    with path.open("rb") as f:
        file_obj = client.files.create(file=f, purpose=purpose)
    print(f"  File ID: {file_obj.id}")
    print(f"  Status: {file_obj.status}")
    return file_obj


def _wait_for_job(client, job_id: str, poll_interval: int = 30) -> dict:
    """Poll the fine-tuning job until it completes or fails."""
    print(f"\n  Monitoring job {job_id}...")
    print(f"  (polling every {poll_interval}s — you can also check at https://platform.openai.com/finetune)\n")

    seen_events = set()
    while True:
        job = client.fine_tuning.jobs.retrieve(job_id)

        # Print new events
        try:
            events = client.fine_tuning.jobs.list_events(
                fine_tuning_job_id=job_id, limit=50
            )
            for event in reversed(events.data):
                if event.id not in seen_events:
                    seen_events.add(event.id)
                    ts = time.strftime("%H:%M:%S", time.localtime(event.created_at))
                    print(f"  [{ts}] {event.message}")
        except Exception:
            pass

        if job.status in ("succeeded", "failed", "cancelled"):
            return job

        time.sleep(poll_interval)


def main() -> None:
    print("=" * 60)
    print("  Creonnect Fine-Tuning — GPT-4o-mini")
    print("=" * 60)

    _check_prerequisites()

    from openai import OpenAI
    client = OpenAI()

    # ---- Step 1: Upload training file ----
    print("\n[Step 1/3] Uploading training data...")
    train_file = _upload_file(client, TRAIN_PATH)

    # ---- Step 2: Upload validation file (optional) ----
    val_file = None
    if VAL_PATH.exists():
        print("\n[Step 2/3] Uploading validation data...")
        val_file = _upload_file(client, VAL_PATH)
    else:
        print("\n[Step 2/3] Skipping validation file (not found)")

    # ---- Step 3: Create fine-tuning job ----
    print("\n[Step 3/3] Creating fine-tuning job...")
    job_params = {
        "training_file": train_file.id,
        "model": BASE_MODEL,
        "suffix": SUFFIX,
        "hyperparameters": {
            "n_epochs": N_EPOCHS,
        },
    }
    if val_file:
        job_params["validation_file"] = val_file.id

    job = client.fine_tuning.jobs.create(**job_params)
    print(f"  Job ID:    {job.id}")
    print(f"  Model:     {BASE_MODEL}")
    print(f"  Suffix:    {SUFFIX}")
    print(f"  Epochs:    {N_EPOCHS}")
    print(f"  Train:     {train_file.id} ({TRAIN_PATH.name})")
    if val_file:
        print(f"  Val:       {val_file.id} ({VAL_PATH.name})")
    print(f"  Status:    {job.status}")

    # ---- Wait for completion ----
    print("\n" + "-" * 60)
    print("  Waiting for fine-tuning to complete...")
    print("  (This typically takes 15-30 minutes for this dataset size)")
    print("-" * 60)

    completed_job = _wait_for_job(client, job.id)

    print("\n" + "=" * 60)
    if completed_job.status == "succeeded":
        model_name = completed_job.fine_tuned_model
        print(f"  FINE-TUNING COMPLETE!")
        print(f"  Fine-tuned model: {model_name}")
        print(f"\n  Next step: Update backend/app/ai/llm_client.py")
        print(f"  Change default model_name to:")
        print(f'    model_name: str = "{model_name}"')
    else:
        print(f"  FINE-TUNING {completed_job.status.upper()}")
        if hasattr(completed_job, "error") and completed_job.error:
            print(f"  Error: {completed_job.error}")
    print("=" * 60)


if __name__ == "__main__":
    main()
