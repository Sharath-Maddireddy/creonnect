from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from openai import OpenAI


TRAIN_PATH = Path("backend/ml/chat_train.jsonl")
VAL_PATH = Path("backend/ml/chat_val.jsonl")
MODEL_NAME = "gpt-4o-mini"
POLL_SECONDS = 30


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    _require_file(TRAIN_PATH)
    _require_file(VAL_PATH)

    client = OpenAI(api_key=api_key)

    with TRAIN_PATH.open("rb") as f:
        train_file = client.files.create(file=f, purpose="fine-tune")
    print(f"training_file_id: {train_file.id}")

    with VAL_PATH.open("rb") as f:
        val_file = client.files.create(file=f, purpose="fine-tune")
    print(f"validation_file_id: {val_file.id}")

    job = client.fine_tuning.jobs.create(
        model=MODEL_NAME,
        training_file=train_file.id,
        validation_file=val_file.id,
    )
    print(f"fine_tune_job_id: {job.id}")

    while True:
        job = client.fine_tuning.jobs.retrieve(job.id)
        status = job.status
        print(f"status: {status}")
        if status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(POLL_SECONDS)

    if job.status == "succeeded":
        print(f"fine_tuned_model_id: {job.fine_tuned_model}")
    else:
        print("fine_tune did not succeed")
        if getattr(job, "error", None):
            print(f"error: {job.error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}")
        sys.exit(1)
