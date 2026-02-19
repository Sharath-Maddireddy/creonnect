from __future__ import annotations

import argparse
import json
import random
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

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
    input_data = entry["input"]
    profile = input_data["profile"]
    posts = input_data["posts"]
    growth = entry["output"].get("growth", {}) if isinstance(entry.get("output"), dict) else {}
    niche = entry["output"].get("niche", {}) if isinstance(entry.get("output"), dict) else {}

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


def _vary_entry(base: Dict[str, Any], rng: random.Random, niches: List[str]) -> Dict[str, Any]:
    entry = deepcopy(base)

    entry["quality"] = _normalize_quality(entry.get("quality"))
    input_data = entry["input"]
    profile = input_data["profile"]
    posts = input_data["posts"]
    output = entry["output"]

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
    if niches:
        niche["primary_niche"] = rng.choice(niches)
    else:
        niche["primary_niche"] = rng.choice(DEFAULT_NICHES)
    output["niche"] = niche

    entry["quality"] = (
        "high" if varied_score > 70 else "medium" if varied_score >= 40 else "low"
    )

    output = entry.get("output")
    if not isinstance(output, dict):
        output = {}
        entry["output"] = output
    output["action_plan"] = _build_action_plan(entry)

    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Scale training dataset with synthetic variations.")
    parser.add_argument("--multiplier", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1337)
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
    for idx, base in enumerate(base_rows):
        for j in range(args.multiplier):
            local_rng = random.Random(rng.randint(0, 1_000_000_000) + idx * 1000 + j)
            varied = _vary_entry(base, local_rng, niches)
            validated = validate_jsonl_entry(varied, EnrichedTrainingExample)
            scaled_rows.append(validated.model_dump(mode="json"))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for row in scaled_rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

    print(f"Generated {len(scaled_rows)} examples -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
