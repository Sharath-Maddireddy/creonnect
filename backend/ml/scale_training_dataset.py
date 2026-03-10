from __future__ import annotations

import argparse
import json
import random
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.ai.rag import generate_action_plan
from backend.ml.clean_action_dataset import (
    EnrichedTrainingExample,
    TrainingExample,
    validate_jsonl_entry,
)


INPUT_PATH = ROOT_DIR / "backend" / "app" / "tests" / "training_data.jsonl"
OUTPUT_PATH = ROOT_DIR / "backend" / "data" / "training_data_scaled.jsonl"

DEFAULT_NICHES = [
    "fitness",
    "food",
    "travel",
    "tech",
    "fashion",
    "lifestyle",
    "nutrition",
    "career",
    "beauty",
    "gaming",
    "finance",
    "education",
    "music",
    "art",
    "sports",
    "business",
    "general",
]
DEFAULT_NICHE_KEEP_PROB = 0.6
RELATED_NICHES = {
    "fitness": ["nutrition", "sports", "lifestyle"],
    "nutrition": ["fitness", "food", "lifestyle"],
    "sports": ["fitness", "lifestyle"],
    "food": ["nutrition", "lifestyle", "travel", "art"],
    "travel": ["lifestyle", "food", "art", "business"],
    "tech": ["gaming", "business", "education", "career"],
    "gaming": ["tech", "music", "art"],
    "fashion": ["beauty", "lifestyle", "art"],
    "beauty": ["fashion", "lifestyle"],
    "lifestyle": ["fashion", "beauty", "travel", "food", "fitness", "music", "art"],
    "career": ["business", "education", "finance"],
    "business": ["career", "finance", "education", "tech"],
    "finance": ["business", "career", "education"],
    "education": ["career", "business", "tech"],
    "music": ["art", "lifestyle"],
    "art": ["music", "fashion", "lifestyle"],
    "general": [],
}


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            yield line_num, json.loads(line)


def _normalize_quality(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "good":
            return "high"
        if lowered == "ok":
            return "medium"
        if lowered == "bad":
            return "low"
    return value


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_niche(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned:
            return cleaned
    return None


def _select_primary_niche(
    original: Optional[str],
    rng: random.Random,
    all_niches: List[str],
    keep_prob: float,
    randomize_all: bool,
) -> str:
    choices = [n for n in all_niches if isinstance(n, str) and n.strip()]
    if not choices:
        choices = DEFAULT_NICHES[:]

    normalized_original = _normalize_niche(original)
    keep_prob = _clamp(keep_prob, 0.0, 1.0)
    if normalized_original and rng.random() < keep_prob:
        return normalized_original

    if randomize_all:
        return rng.choice(choices)

    if normalized_original:
        related = RELATED_NICHES.get(normalized_original, [])
        related_choices = [n for n in related if n in choices and n != normalized_original]
        if related_choices:
            return rng.choice(related_choices)
        # No related options available; keep original to avoid semantic drift.
        return normalized_original

    return rng.choice(choices)


def _scale_int(value: Any, factor: float) -> int:
    try:
        return max(0, int(round(float(value) * factor)))
    except (TypeError, ValueError):
        return 0


def _collect_niches(rows: List[Dict[str, Any]]) -> List[str]:
    found = set()
    for row in rows:
        output = row.get("output") if isinstance(row, dict) else None
        niche = output.get("niche") if isinstance(output, dict) else None
        primary = niche.get("primary_niche") if isinstance(niche, dict) else None
        if isinstance(primary, str) and primary.strip():
            found.add(primary.strip().lower())
    return sorted(found)


def _build_action_plan(entry: Dict[str, Any]) -> Dict[str, Any]:
    input_data = entry.get("input", {})
    profile = input_data.get("profile", {}) if isinstance(input_data, dict) else {}
    posts = input_data.get("posts", []) if isinstance(input_data, dict) else []
    output = entry.get("output") if isinstance(entry.get("output"), dict) else {}
    growth = output.get("growth", {})
    niche = output.get("niche", {})

    avg_views = float(profile.get("avg_views", 0) or 0)
    avg_likes = float(profile.get("avg_likes", 0) or 0)
    avg_comments = float(profile.get("avg_comments", 0) or 0)
    avg_engagement = (avg_likes + avg_comments) / avg_views if avg_views > 0 else 0.0

    creator_metrics = {
        "followers": profile.get("followers", 0),
        "growth_score": growth.get("growth_score", 0),
        "avg_views": avg_views,
        "avg_engagement_rate_by_views": avg_engagement,
        "posts_per_week": profile.get("posts_per_week", 0),
    }

    recent_posts = posts[-3:] if isinstance(posts, list) else []

    return generate_action_plan(
        creator_metrics=creator_metrics,
        niche_data=niche,
        momentum={},
        best_time={},
        recent_posts=recent_posts,
        knowledge_chunks=None,
    )


def _bucket(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(value / step) * step


def _action_plan_cache_key(entry: Dict[str, Any]) -> Tuple[Any, ...]:
    input_data = entry.get("input", {})
    profile = input_data.get("profile", {}) if isinstance(input_data, dict) else {}
    output = entry.get("output") if isinstance(entry.get("output"), dict) else {}
    growth = output.get("growth", {})
    niche = output.get("niche", {})

    avg_views = float(profile.get("avg_views", 0) or 0)
    avg_likes = float(profile.get("avg_likes", 0) or 0)
    avg_comments = float(profile.get("avg_comments", 0) or 0)
    avg_engagement = (avg_likes + avg_comments) / avg_views if avg_views > 0 else 0.0

    primary_niche = _normalize_niche(niche.get("primary_niche")) or "unknown"

    return (
        _bucket(float(profile.get("followers", 0) or 0), 100.0),
        _bucket(avg_views, 100.0),
        _bucket(avg_engagement, 0.005),
        _bucket(float(profile.get("posts_per_week", 0) or 0), 0.25),
        _bucket(float(growth.get("growth_score", 0) or 0), 5.0),
        primary_niche,
    )


def _build_action_plan_with_retries(
    entry: Dict[str, Any],
    max_retries: int,
    backoff_s: float,
) -> Tuple[Dict[str, Any], Optional[str], int]:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return _build_action_plan(entry), None, attempt
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(backoff_s * (2**attempt))

    error_msg = str(last_exc) if last_exc else "unknown error"
    fallback_plan = {
        "diagnosis": "Action plan unavailable due to upstream error.",
        "error": error_msg[:300],
    }
    return fallback_plan, error_msg, max_retries


def _vary_entry(
    base: Dict[str, Any],
    rng: random.Random,
    niches: List[str],
    keep_prob: float,
    randomize_all_niches: bool,
    max_retries: int,
    retry_backoff_s: float,
    cache_enabled: bool,
    action_plan_cache: Optional[Dict[Tuple[Any, ...], Dict[str, Any]]],
    stats: Dict[str, int],
) -> Dict[str, Any]:
    entry = deepcopy(base)

    entry["quality"] = _normalize_quality(entry.get("quality"))
    input_data = entry.get("input", {})
    if not isinstance(input_data, dict):
        input_data = {}
        entry["input"] = input_data

    profile = input_data.get("profile", {})
    if not isinstance(profile, dict):
        profile = {}
        input_data["profile"] = profile

    posts = input_data.get("posts", [])
    if not isinstance(posts, list):
        posts = []
        input_data["posts"] = posts

    output = entry.get("output", {})
    if not isinstance(output, dict):
        output = {}
        entry["output"] = output

    followers_factor = rng.uniform(0.8, 1.2)
    views_factor = rng.uniform(0.7, 1.3)
    posts_factor = rng.uniform(0.7, 1.3)
    engagement_factor = rng.uniform(0.85, 1.15)

    base_views = float(profile.get("avg_views", 0) or 0)
    base_likes = float(profile.get("avg_likes", 0) or 0)
    base_comments = float(profile.get("avg_comments", 0) or 0)
    base_total_engagement = base_likes + base_comments
    like_ratio = (base_likes / base_total_engagement) if base_total_engagement > 0 else 0.8

    new_views = _scale_int(base_views, views_factor)
    base_ratio = (base_total_engagement / base_views) if base_views > 0 else 0.05
    new_ratio = _clamp(base_ratio * engagement_factor, 0.005, 0.2)
    new_total_engagement = new_ratio * new_views
    new_likes = max(0, int(round(new_total_engagement * like_ratio)))
    new_comments = max(0, int(round(new_total_engagement * (1 - like_ratio))))

    profile["followers"] = _scale_int(profile.get("followers", 0), followers_factor)
    profile["avg_views"] = new_views
    profile["avg_likes"] = new_likes
    profile["avg_comments"] = new_comments
    profile["posts_per_week"] = round(
        max(0.5, float(profile.get("posts_per_week", 0) or 0) * posts_factor), 2
    )

    if isinstance(posts, list):
        for post in posts:
            if not isinstance(post, dict):
                continue
            post_views = _scale_int(post.get("views", 0), views_factor)
            post_likes = _scale_int(post.get("likes", 0), views_factor * engagement_factor)
            post_comments = _scale_int(post.get("comments", 0), views_factor * engagement_factor)
            post["views"] = post_views
            post["likes"] = post_likes
            post["comments"] = post_comments

    growth = output.get("growth") if isinstance(output, dict) else {}
    if not isinstance(growth, dict):
        growth = {}
    base_growth_score = float(growth.get("growth_score", 0) or 0)
    varied_score = _clamp(base_growth_score + rng.uniform(-15, 15), 0, 100)
    growth["growth_score"] = round(varied_score, 2)
    output["growth"] = growth

    niche = output.get("niche") if isinstance(output, dict) else {}
    if not isinstance(niche, dict):
        niche = {}
    original_primary = niche.get("primary_niche")
    niche["primary_niche"] = _select_primary_niche(
        original_primary,
        rng,
        niches or DEFAULT_NICHES,
        keep_prob,
        randomize_all_niches,
    )
    output["niche"] = niche

    entry["quality"] = (
        "high" if varied_score > 70 else "medium" if varied_score >= 40 else "low"
    )

    output = entry.get("output")
    if not isinstance(output, dict):
        output = {}
        entry["output"] = output
    cache_key = _action_plan_cache_key(entry) if cache_enabled else None
    if cache_enabled and cache_key in (action_plan_cache or {}):
        output["action_plan"] = deepcopy(action_plan_cache[cache_key])
        stats["cache_hits"] += 1
    else:
        if cache_enabled:
            stats["cache_misses"] += 1
        action_plan, error_msg, retries_used = _build_action_plan_with_retries(
            entry,
            max_retries=max_retries,
            backoff_s=retry_backoff_s,
        )
        stats["plan_retries"] += retries_used
        if error_msg:
            stats["plan_failures"] += 1
            print(f"[warn] action_plan failed after retries: {error_msg[:200]}")
        else:
            if cache_enabled and action_plan_cache is not None and cache_key is not None:
                action_plan_cache[cache_key] = deepcopy(action_plan)
        output["action_plan"] = action_plan

    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Scale training dataset with synthetic variations.")
    parser.add_argument("--multiplier", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    parser.add_argument(
        "--cache-action-plans",
        action="store_true",
        help="Reuse action plans for similar metric profiles to reduce LLM calls.",
    )
    parser.add_argument("--niche-keep-prob", type=float, default=DEFAULT_NICHE_KEEP_PROB)
    parser.add_argument(
        "--niche-randomize-all",
        action="store_true",
        help="Ignore related-niche constraints when randomizing primary_niche.",
    )
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        print(f"[error] Input dataset not found: {INPUT_PATH}")
        raise SystemExit(1)

    base_rows: List[Dict[str, Any]] = []
    for _, row in _read_jsonl(INPUT_PATH):
        row["quality"] = _normalize_quality(row.get("quality"))
        validate_jsonl_entry(row, TrainingExample)
        base_rows.append(row)

    niches = _collect_niches(base_rows) or DEFAULT_NICHES

    rng = random.Random(args.seed)
    scaled_rows: List[Dict[str, Any]] = []
    total_variants = len(base_rows) * args.multiplier
    print(f"Scaling {len(base_rows)} base rows x {args.multiplier} = {total_variants} variants")
    action_plan_cache: Optional[Dict[Tuple[Any, ...], Dict[str, Any]]] = (
        {} if args.cache_action_plans else None
    )
    stats = {
        "variants": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "plan_failures": 0,
        "plan_retries": 0,
    }
    for idx, base in enumerate(base_rows):
        for j in range(args.multiplier):
            local_rng = random.Random(rng.randint(0, 1_000_000_000) + idx * 1000 + j)
            varied = _vary_entry(
                base,
                local_rng,
                niches,
                keep_prob=args.niche_keep_prob,
                randomize_all_niches=args.niche_randomize_all,
                max_retries=args.max_retries,
                retry_backoff_s=args.retry_backoff,
                cache_enabled=args.cache_action_plans,
                action_plan_cache=action_plan_cache,
                stats=stats,
            )
            validated = validate_jsonl_entry(varied, EnrichedTrainingExample)
            scaled_rows.append(validated.model_dump(mode="json"))
            stats["variants"] += 1
            if args.log_every and stats["variants"] % args.log_every == 0:
                print(
                    "[progress] "
                    f"{stats['variants']}/{total_variants} variants | "
                    f"cache hits {stats['cache_hits']} | "
                    f"cache misses {stats['cache_misses']} | "
                    f"retries {stats['plan_retries']} | "
                    f"failures {stats['plan_failures']}"
                )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for row in scaled_rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

    print(
        f"Generated {len(scaled_rows)} examples -> {OUTPUT_PATH} "
        f"(failures: {stats['plan_failures']}, retries: {stats['plan_retries']})"
    )


if __name__ == "__main__":
    main()
