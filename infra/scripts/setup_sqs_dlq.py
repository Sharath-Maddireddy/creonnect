#!/usr/bin/env python3
"""Create SQS Dead-Letter Queues for all Creonnect queues.

Usage:
    python infra/scripts/setup_sqs_dlq.py
    AWS_REGION=us-east-1 python infra/scripts/setup_sqs_dlq.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Final

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

QUEUE_NAMES: Final[tuple[str, ...]] = (
    "account-analysis",
    "single-post-analysis",
    "embedding-ingestion",
    "reel-analysis",
)
DLQ_RETENTION_SECONDS: Final[str] = "1209600"
MAX_RECEIVE_COUNT: Final[str] = "3"


def _get_queue_url(sqs: BaseClient, queue_name: str) -> str | None:
    """Return queue URL when it exists, otherwise None."""
    try:
        response = sqs.get_queue_url(QueueName=queue_name)
        url = response.get("QueueUrl")
        return url if isinstance(url, str) and url else None
    except sqs.exceptions.QueueDoesNotExist:
        return None


def _ensure_dlq(sqs: BaseClient, dlq_name: str) -> str:
    """Create DLQ if missing and enforce retention period."""
    dlq_url = _get_queue_url(sqs, dlq_name)
    if dlq_url is None:
        created = sqs.create_queue(
            QueueName=dlq_name,
            Attributes={"MessageRetentionPeriod": DLQ_RETENTION_SECONDS},
        )
        dlq_url = str(created["QueueUrl"])

    sqs.set_queue_attributes(
        QueueUrl=dlq_url,
        Attributes={"MessageRetentionPeriod": DLQ_RETENTION_SECONDS},
    )
    return dlq_url


def _get_queue_arn(sqs: BaseClient, queue_url: str) -> str:
    """Fetch QueueArn for a queue URL."""
    response = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
    attributes = response.get("Attributes") or {}
    arn = attributes.get("QueueArn")
    if not isinstance(arn, str) or not arn:
        raise RuntimeError(f"QueueArn missing for queue URL: {queue_url}")
    return arn


def _configure_redrive_policy(sqs: BaseClient, main_queue_url: str, dlq_arn: str) -> None:
    """Apply redrive policy to the main queue."""
    redrive_policy = json.dumps(
        {
            "maxReceiveCount": MAX_RECEIVE_COUNT,
            "deadLetterTargetArn": dlq_arn,
        }
    )
    sqs.set_queue_attributes(
        QueueUrl=main_queue_url,
        Attributes={"RedrivePolicy": redrive_policy},
    )


def _configure_queue(sqs: BaseClient, queue_name: str) -> None:
    """Configure a single main queue with its DLQ and redrive policy."""
    main_queue_url = _get_queue_url(sqs, queue_name)
    if main_queue_url is None:
        raise RuntimeError(f"Main queue does not exist: {queue_name}")

    dlq_name = f"{queue_name}-dlq"
    dlq_url = _ensure_dlq(sqs, dlq_name)
    dlq_arn = _get_queue_arn(sqs, dlq_url)
    _configure_redrive_policy(sqs, main_queue_url, dlq_arn)

    print(f"[OK] {queue_name} \u2192 DLQ: {dlq_name} (maxReceiveCount=3)")


def main() -> int:
    """Entrypoint for DLQ setup script."""
    region = os.getenv("AWS_REGION", "ap-south-1")
    sqs = boto3.client("sqs", region_name=region)

    for queue_name in QUEUE_NAMES:
        _configure_queue(sqs, queue_name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        print(f"[ERROR] AWS ClientError: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)

