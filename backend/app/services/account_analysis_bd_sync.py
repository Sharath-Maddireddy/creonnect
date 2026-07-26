"""Creonnect-bd synchronization helpers for account analysis jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def connection_id_from_payload(payload: dict[str, Any]) -> str | None:
    value = payload.get("connection_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    source_meta = payload.get("source_meta")
    if isinstance(source_meta, dict):
        meta_value = source_meta.get("connection_id")
        if isinstance(meta_value, str) and meta_value.strip():
            return meta_value.strip()
    return None


def publish_result_to_creonnect_bd(
    *,
    payload: dict[str, Any],
    result_payload: dict[str, Any],
    job_id: str,
    client_factory: Callable[..., Any],
    run_coroutine_sync: Callable[[Any], Any],
    logger: Any,
) -> None:
    source = payload.get("source")
    if not (isinstance(source, str) and source.strip().lower() == "creonnect_bd"):
        return
    connection_id = connection_id_from_payload(payload)
    if not connection_id:
        logger.warning("[AccountAnalysisJob] Skipping creonnect-bd sync: missing connection_id job_id=%s", job_id)
        return

    account_level = dict(result_payload)
    posts_summary = account_level.pop("posts_summary", None)
    post_items: list[dict[str, Any]] = []
    if isinstance(posts_summary, list):
        for item in posts_summary:
            if not isinstance(item, dict):
                continue
            post_id = item.get("post_id")
            if not isinstance(post_id, str) or not post_id.strip():
                continue
            post_items.append(
                {
                    "post_id": post_id.strip(),
                    "ai_analysis": item,
                }
            )

    client = client_factory(
        base_url=payload.get("bd_base_url") if isinstance(payload.get("bd_base_url"), str) else None,
        timeout_seconds=payload.get("bd_timeout_seconds") if isinstance(payload.get("bd_timeout_seconds"), (int, float)) else None,
    )
    logger.info(
        "[AccountAnalysisJob] Syncing analysis to creonnect-bd job_id=%s connection_id=%s posts=%s",
        job_id,
        connection_id,
        len(post_items),
    )
    run_coroutine_sync(
        client.update_connection_ai_analysis(
            platform="instagram",
            connection_id=connection_id,
            ai_analysis=account_level,
        )
    )
    if post_items:
        run_coroutine_sync(
            client.update_posts_ai_analysis(
                platform="instagram",
                connection_id=connection_id,
                items=post_items,
            )
        )
    logger.info("[AccountAnalysisJob] Synced analysis to creonnect-bd job_id=%s connection_id=%s", job_id, connection_id)
