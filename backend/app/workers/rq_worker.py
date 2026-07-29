"""RQ worker entrypoint for background queues."""

from __future__ import annotations

import os
import platform

from rq import SimpleWorker, Worker

from backend.app.utils.env import load_app_env
from backend.app.utils.logger import logger

load_app_env(override=False)

from backend.app.infra.redis_client import get_rq_redis

# Import job modules so the worker can resolve callable paths.
from backend.app.services import account_analysis_jobs as _account_analysis_jobs  # noqa: F401
from backend.app.services import reel_analysis_jobs as _reel_analysis_jobs  # noqa: F401
from backend.app.services import single_post_analysis_jobs as _single_post_analysis_jobs  # noqa: F401
from backend.app.services import content_suggestion_jobs as _content_suggestion_jobs  # noqa: F401
from backend.app.workers import embedding_worker as _embedding_worker  # noqa: F401


def main() -> None:
    print(f"worker vision_enabled={bool((os.getenv('GEMINI_API_KEY') or '').strip())}")
    connection = get_rq_redis()
    configured_queues = (os.getenv("RQ_QUEUES") or "").strip()
    queue_names = (
        [name.strip() for name in configured_queues.split(",") if name.strip()]
        if configured_queues
        else ["account-analysis", "single-post-analysis", "embedding-ingestion", "trend-analysis", "content-suggestions"]
    )
    # macOS and Windows are safer with SimpleWorker because forked work-horses
    # can crash when Objective-C runtime state is already initialized.
    worker_cls = SimpleWorker if platform.system() in {"Windows", "Darwin"} else Worker
    
    if platform.system() == "Windows":
        from rq.timeouts import BaseDeathPenalty
        class DummyDeathPenalty(BaseDeathPenalty):
            def setup_death_penalty(self):
                pass
            def cancel_death_penalty(self):
                pass
        worker_cls.death_penalty_class = DummyDeathPenalty
        Worker.death_penalty_class = DummyDeathPenalty
        SimpleWorker.death_penalty_class = DummyDeathPenalty

    logger.info(
        "[RQWorker] Starting worker queues=%s worker_cls=%s vision_enabled=%s",
        queue_names,
        worker_cls.__name__,
        bool((os.getenv("GEMINI_API_KEY") or "").strip()),
    )
    worker = worker_cls(queue_names, connection=connection)
    logger.info("[RQWorker] Worker ready queues=%s", queue_names)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
