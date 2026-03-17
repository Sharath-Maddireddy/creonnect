"""Debug RQ worker - run with full error output."""
import os
import traceback
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from rq import SimpleWorker
from backend.app.infra.redis_client import get_redis
from backend.app.services import account_analysis_jobs as _account_analysis_jobs  # noqa: F401

try:
    connection = get_redis()
    print(f"[debug-worker] Connected to Redis: {connection.ping()}")
    worker = SimpleWorker(["account-analysis"], connection=connection)
    print("[debug-worker] Worker created, starting work loop...")
    worker.work(with_scheduler=False, burst=True)
    print("[debug-worker] Worker finished (burst mode)")
except Exception:
    traceback.print_exc()
