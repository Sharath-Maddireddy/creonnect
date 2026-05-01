"""Lightweight creator-intelligence rollup used by dashboard and account analysis."""

from __future__ import annotations

from collections import Counter

from backend.app.domain.account_models import CreatorBrandFit, CreatorIntelligence
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger


def _clean_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text[:limit] if text else None


def _collect_top_words(posts: list[SinglePostInsights]) -> list[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "your",
        "have",
        "about",
        "into",
        "just",
        "they",
        "them",
        "their",
        "been",
        "were",
        "what",
        "when",
        "where",
        "will",
        "would",
        "there",
        "here",
        "more",
        "than",
        "then",
        "also",
        "https",
        "reel",
        "video",
        "post",
    }
    counts: Counter[str] = Counter()
    for post in posts:
        caption = _clean_text(post.caption_text, limit=400) or ""
        for token in caption.lower().replace("#", " ").split():
            word = "".join(ch for ch in token if ch.isalnum())
            if len(word) < 4 or word in stop_words:
                continue
            counts[word] += 1
    return [word for word, _ in counts.most_common(5)]


def _infer_persona(
    username: str | None,
    creator_dominant_category: str | None,
    niche_tags: list[str] | None,
    follower_count: int | None,
) -> str | None:
    category = _clean_text(creator_dominant_category, limit=80)
    tags = [_clean_text(tag, limit=40) for tag in (niche_tags or [])]
    tags = [tag for tag in tags if tag]
    if category and tags:
        return f"{category} creator focused on {', '.join(tags[:2])}."
    if category:
        return f"{category} creator with a consistent niche-led presence."
    if tags:
        return f"Creator focused on {', '.join(tags[:2])}."
    if username and follower_count:
        scale = "emerging" if follower_count < 100_000 else "established"
        return f"{scale.title()} creator profile for @{username}."
    return None


def _infer_content_style(posts: list[SinglePostInsights]) -> str | None:
    media_types = Counter(
        (post.media_type or "").upper()
        for post in posts
        if isinstance(post.media_type, str) and post.media_type.strip()
    )
    top_words = _collect_top_words(posts)
    leading_media_type = media_types.most_common(1)[0][0] if media_types else None

    parts: list[str] = []
    if leading_media_type:
        parts.append(f"Leans heavily on {leading_media_type.lower()} content.")
    if top_words:
        parts.append(f"Recurring themes include {', '.join(top_words[:3])}.")
    return " ".join(parts)[:240] if parts else None


def _infer_fit_categories(
    creator_dominant_category: str | None,
    niche_tags: list[str] | None,
    top_words: list[str],
) -> list[str]:
    candidates: list[str] = []
    if creator_dominant_category:
        candidates.append(creator_dominant_category)
    candidates.extend(niche_tags or [])
    candidates.extend(top_words[:2])

    seen: set[str] = set()
    normalized: list[str] = []
    for item in candidates:
        text = _clean_text(item, limit=60)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
    return normalized[:5]


def _infer_red_flags(posts: list[SinglePostInsights]) -> list[str]:
    red_flags: list[str] = []
    flagged_posts = 0
    low_brand_safety_posts = 0

    for post in posts:
        first_signal = None
        if post.vision_analysis and post.vision_analysis.signals:
            first_signal = post.vision_analysis.signals[0]
        if first_signal and (
            getattr(first_signal, "adult_content_detected", None) is True
            or getattr(first_signal, "is_cringe", None) is True
        ):
            flagged_posts += 1
        if (post.brand_safety_score.total_0_50 or 0) < 25:
            low_brand_safety_posts += 1

    if flagged_posts:
        red_flags.append(f"{flagged_posts} post(s) flagged by vision safety signals.")
    if low_brand_safety_posts:
        red_flags.append(f"{low_brand_safety_posts} post(s) have weak brand-safety scores.")
    return red_flags[:5]


async def generate_creator_intelligence(
    posts: list[SinglePostInsights],
    account_id: str | None = None,
    username: str | None = None,
    bio: str | None = None,
    niche_tags: list[str] | None = None,
    creator_dominant_category: str | None = None,
    follower_count: int | None = None,
) -> CreatorIntelligence:
    """Build a lightweight creator-intelligence rollup without external model calls."""

    del account_id, bio

    logger.info(
        "[CreatorIntelligence] Start username=%s post_count=%d category=%s niche_tag_count=%d",
        username,
        len(posts),
        creator_dominant_category,
        len(niche_tags or []),
    )
    top_words = _collect_top_words(posts)
    fit_categories = _infer_fit_categories(creator_dominant_category, niche_tags, top_words)
    red_flags = _infer_red_flags(posts)
    logger.debug(
        "[CreatorIntelligence] Derived themes=%s fit_categories=%s red_flags=%s",
        top_words[:5],
        fit_categories,
        red_flags,
    )
    result = CreatorIntelligence(
        creator_persona=_infer_persona(username, creator_dominant_category, niche_tags, follower_count),
        content_style_summary=_infer_content_style(posts),
        top_performing_themes=top_words[:5],
        brand_fit=CreatorBrandFit(
            fit_categories=fit_categories,
            red_flags=red_flags,
        ),
    )
    logger.info(
        "[CreatorIntelligence] Completed username=%s theme_count=%d red_flag_count=%d",
        username,
        len(result.top_performing_themes or []),
        len(result.brand_fit.red_flags or []),
    )
    return result
