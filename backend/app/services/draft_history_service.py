from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select

from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import AccountAnalysisResult, CreatorDiscoveryMeta


@dataclass(slots=True)
class DraftHistoryContext:
    historical_posts: list[SinglePostInsights]
    account_data: dict[str, Any]


def _coerce_history_post(item: Any, *, account_id: str, follower_count: int | None) -> SinglePostInsights | None:
    if isinstance(item, dict):
        try:
            return SinglePostInsights.model_validate(item)
        except Exception:
            pass

    if not isinstance(item, dict):
        return None

    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    return SinglePostInsights(
        account_id=account_id,
        media_id=str(item.get("post_id") or ""),
        media_type=str(item.get("post_type") or "IMAGE"),
        media_url=str(item.get("media_url") or "") or None,
        caption_text=str(item.get("caption_preview") or ""),
        follower_count=follower_count,
        core_metrics=CoreMetrics(reach=None, impressions=None, likes=None, comments=None, saves=None, shares=None),
        derived_metrics=DerivedMetrics(
            engagement_rate=_safe_float(scores.get("predicted_er")),
        ),
        benchmark_metrics=BenchmarkMetrics(),
    )


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_draft_history_context(account_id: str, *, history_limit: int = 12) -> DraftHistoryContext:
    session_factory = get_sync_sessionmaker()
    account_data: dict[str, Any] = {"account_id": account_id}
    historical_posts: list[SinglePostInsights] = []

    with session_factory() as session:
        creator_meta = session.get(CreatorDiscoveryMeta, account_id)
        if creator_meta is not None:
            account_data.update(
                {
                    "username": creator_meta.username,
                    "follower_count": creator_meta.follower_count,
                    "creator_dominant_category": creator_meta.creator_dominant_category,
                    "niche_tags": list(creator_meta.niche_tags or []),
                    "bio": creator_meta.bio,
                }
            )

        statement = (
            select(AccountAnalysisResult)
            .where(AccountAnalysisResult.account_id == account_id)
            .where(AccountAnalysisResult.status == "succeeded")
            .order_by(desc(AccountAnalysisResult.updated_at))
            .limit(5)
        )
        rows = session.execute(statement).scalars().all()

    follower_count = account_data.get("follower_count")
    follower_count_int = int(follower_count) if isinstance(follower_count, int) else None

    for row in rows:
        request_meta = row.request_metadata_json if isinstance(row.request_metadata_json, dict) else {}
        result_json = row.result_json if isinstance(row.result_json, dict) else {}
        if "username" not in account_data and isinstance(row.username, str):
            account_data["username"] = row.username
        if "creator_dominant_category" not in account_data and isinstance(request_meta.get("creator_dominant_category"), str):
            account_data["creator_dominant_category"] = request_meta.get("creator_dominant_category")
        if not account_data.get("niche_tags") and isinstance(request_meta.get("niche_tags"), list):
            account_data["niche_tags"] = list(request_meta.get("niche_tags") or [])

        raw_history = result_json.get("draft_optimizer_history")
        if not isinstance(raw_history, list):
            raw_history = result_json.get("posts_summary")
        if not isinstance(raw_history, list):
            continue

        for item in raw_history:
            post = _coerce_history_post(item, account_id=account_id, follower_count=follower_count_int)
            if post is None:
                continue
            historical_posts.append(post)
            if len(historical_posts) >= history_limit:
                break
        if historical_posts:
            break

    deduped: list[SinglePostInsights] = []
    seen_media_ids: set[str] = set()
    for post in historical_posts:
        media_id = str(post.media_id or "")
        if media_id and media_id in seen_media_ids:
            continue
        if media_id:
            seen_media_ids.add(media_id)
        deduped.append(post)
        if len(deduped) >= history_limit:
            break

    return DraftHistoryContext(
        historical_posts=deduped,
        account_data=account_data,
    )

