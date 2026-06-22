"""Helper for enqueueing trend analysis jobs to RQ."""

from __future__ import annotations

from typing import Optional

from rq import Queue, Retry
from rq.job import Job

from backend.app.infra.redis_client import get_rq_redis
from backend.app.utils.logger import logger


def enqueue_trend_analysis_job(
    account_id: str,
    job_timeout: int = 600,
    result_ttl: int = 86400,
) -> Job:
    """Enqueue trend analysis to background RQ queue.
    
    Args:
        account_id: Creator's account ID
        job_timeout: Job timeout in seconds (default: 600 = 10 minutes)
        result_ttl: Result time-to-live in seconds (default: 86400 = 24 hours)
        
    Returns:
        RQ Job object with job_id for polling
    """
    try:
        connection = get_rq_redis()
        queue = Queue("trend-analysis", connection=connection)

        job = queue.enqueue(
            "backend.app.services.trend_analysis_jobs.run_trend_analysis",
            account_id,
            job_timeout=job_timeout,
            result_ttl=result_ttl,
            retry=Retry(max=2, interval=[10, 30]),  # 2 retries with 10s, 30s intervals
            job_id=f"trend-analysis:{account_id}:{int(__import__('time').time())}",
        )

        logger.info(
            f"[TrendAnalysisQueue] Enqueued job_id={job.id} "
            f"for account_id={account_id}"
        )

        return job

    except Exception as exc:
        logger.exception(f"[TrendAnalysisQueue] Failed to enqueue job: {exc}")
        raise


def get_trend_analysis_job_status(job_id: str) -> dict:
    """Get status of a queued trend analysis job.
    
    Args:
        job_id: Job ID from enqueue_trend_analysis_job()
        
    Returns:
        dict with status, result (if completed), or error details
    """
    try:
        connection = get_rq_redis()
        job = Job.fetch(job_id, connection=connection)

        status_map = {
            "queued": "queued",
            "started": "processing",
            "deferred": "scheduled",
            "finished": "completed",
            "stopped": "stopped",
            "scheduled": "scheduled",
            "failed": "failed",
            "canceled": "canceled",
        }

        result_data = {
            "job_id": job_id,
            "status": status_map.get(job.get_status(), "unknown"),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }

        if job.is_finished:
            result_data["result"] = job.result
        elif job.is_failed:
            result_data["error"] = job.exc_info

        return result_data

    except Exception as exc:
        logger.warning(f"[TrendAnalysisQueue] Failed to fetch job status: {exc}")
        return {
            "job_id": job_id,
            "status": "unknown",
            "error": str(exc)
        }


def cancel_trend_analysis_job(job_id: str) -> bool:
    """Cancel a queued trend analysis job.
    
    Args:
        job_id: Job ID to cancel
        
    Returns:
        True if cancelled, False if failed or not found
    """
    try:
        connection = get_rq_redis()
        job = Job.fetch(job_id, connection=connection)
        job.cancel()

        logger.info(f"[TrendAnalysisQueue] Cancelled job_id={job_id}")
        return True

    except Exception as exc:
        logger.warning(f"[TrendAnalysisQueue] Failed to cancel job: {exc}")
        return False
