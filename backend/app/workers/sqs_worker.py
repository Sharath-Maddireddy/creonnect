"""SQS worker entrypoint for background queues."""

from __future__ import annotations

import json
import time
from typing import Any

from backend.app.utils.env import load_app_env

load_app_env(override=False)

from backend.app.infra.job_queue import (
    ACCOUNT_ANALYSIS_JOB_NAME,
    ACCOUNT_ANALYSIS_QUEUE_NAME,
    EMBEDDING_INGESTION_JOB_NAME,
    EMBEDDING_INGESTION_QUEUE_NAME,
    REEL_ANALYSIS_JOB_NAME,
    REEL_ANALYSIS_QUEUE_NAME,
    SINGLE_POST_ANALYSIS_JOB_NAME,
    SINGLE_POST_ANALYSIS_QUEUE_NAME,
    get_registered_job_handler,
    get_sqs_queue_url,
    register_job_handler,
)
from backend.app.utils.logger import logger
from backend.app.services import account_analysis_jobs, reel_analysis_jobs, single_post_analysis_jobs
from backend.app.workers import embedding_worker


POLL_WAIT_TIME_SECONDS = 20
IDLE_SLEEP_SECONDS = 1.0
MAX_MESSAGES_PER_POLL = 1


def _get_sqs_client():
    from backend.app.infra.job_queue import _get_sqs_client

    return _get_sqs_client()


def _register_default_handlers() -> None:
    register_job_handler(ACCOUNT_ANALYSIS_JOB_NAME, account_analysis_jobs.run_account_analysis_job)
    register_job_handler(REEL_ANALYSIS_JOB_NAME, reel_analysis_jobs.run_reel_analysis_job)
    register_job_handler(EMBEDDING_INGESTION_JOB_NAME, embedding_worker.generate_creator_embedding)
    register_job_handler(SINGLE_POST_ANALYSIS_JOB_NAME, single_post_analysis_jobs.run_single_post_analysis_job)


def _decode_message(message: dict[str, Any]) -> dict[str, Any]:
    body = message.get("Body")
    if not isinstance(body, str):
        raise ValueError("SQS message body is missing or not a string.")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("SQS message body must decode to an object.")
    return payload


def _dispatch_message(queue_name: str, message: dict[str, Any]) -> None:
    payload = _decode_message(message)
    job_name = payload.get("job_name")
    job_payload = payload.get("payload")
    if not isinstance(job_name, str) or not job_name.strip():
        raise ValueError("SQS message is missing job_name.")
    handler = get_registered_job_handler(job_name)
    if handler is None:
        raise RuntimeError(f"No handler is registered for job_name={job_name!r}.")
    logger.info(
        "[SQSWorker] Dispatching queue=%s job_name=%s job_id=%s",
        queue_name,
        job_name,
        payload.get("job_id"),
    )
    handler(job_payload)


def main() -> None:
    _register_default_handlers()
    queue_names = [
        ACCOUNT_ANALYSIS_QUEUE_NAME,
        SINGLE_POST_ANALYSIS_QUEUE_NAME,
        EMBEDDING_INGESTION_QUEUE_NAME,
        REEL_ANALYSIS_QUEUE_NAME,
    ]
    queue_urls = {queue_name: get_sqs_queue_url(queue_name) for queue_name in queue_names}
    client = _get_sqs_client()
    logger.info("[SQSWorker] Starting worker queues=%s", queue_names)
    while True:
        handled_message = False
        for queue_name, queue_url in queue_urls.items():
            response = client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=MAX_MESSAGES_PER_POLL,
                WaitTimeSeconds=POLL_WAIT_TIME_SECONDS,
                VisibilityTimeout=300,
            )
            messages = response.get("Messages") or []
            if not messages:
                continue
            handled_message = True
            for message in messages:
                receipt_handle = message.get("ReceiptHandle")
                try:
                    _dispatch_message(queue_name, message)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("[SQSWorker] Failed queue=%s: %s", queue_name, exc)
                    continue
                if isinstance(receipt_handle, str) and receipt_handle:
                    client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
                    logger.debug("[SQSWorker] Deleted message queue=%s", queue_name)
        if not handled_message:
            time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
