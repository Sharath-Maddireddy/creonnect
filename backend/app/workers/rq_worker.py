"""RQ worker entrypoint for account-analysis queue."""

from __future__ import annotations

import os
import platform

from dotenv import load_dotenv
from rq import Worker, SimpleWorker

from backend.app.infra.redis_client import get_redis

# Import job module so the worker can resolve callable paths.
from backend.app.services import account_analysis_jobs as _account_analysis_jobs  # noqa: F401

load_dotenv(override=False)


def main() -> None:
    print(f"worker vision_enabled={bool((os.getenv('GEMINI_API_KEY') or '').strip())}")
    connection = get_redis()
    # Windows lacks os.fork(); use SimpleWorker to avoid crash.
    worker_cls = SimpleWorker if platform.system() == "Windows" else Worker
    worker = worker_cls(["account-analysis"], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
