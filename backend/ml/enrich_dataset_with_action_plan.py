from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from typing import Any, Dict

from backend.app.ai.rag import retrieve, generate_action_plan
from backend.core.best_time import get_best_posting_hours
from backend.core.momentum import calculate_momentum


INPUT_PATH = Path("backend/data/training_data.jsonl")
OUTPUT_PATH = Path("backend/data/training_data_with_actions.jsonl")


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_num, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_num}: {exc}") from exc


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _build_momentum(followers: int) -> Dict[str, Any]:
    # Mirror dashboard_service simulated snapshots
    base_followers = max(followers - 500, 0)
    simulated_snapshots = [
        {"date": f"day_{i}", "followers": base_followers + (i * 80)}
        for i in range(7)
    ]
    return calculate_momentum(simulated_snapshots)


def _build_best_time(posts: list) -> Dict[str, Any]:
    posts_for_time_analysis = []
    for p in posts:
        posts_for_time_analysis.append(
            {
                "created_at": p.get("posted_at"),
                "likes": p.get("likes", 0),
                "comments": p.get("comments", 0),
                "views": p.get("views", 0) or 0,
            }
        )
    return get_best_posting_hours(posts_for_time_analysis)


def _build_action_plan(row: Dict[str, Any]) -> Dict[str, Any]:
    input_data = row.get("input") or {}
    output_data = row.get("output") or {}

    profile = input_data.get("profile") or {}
    posts = input_data.get("posts") or []

    niche = output_data.get("niche") or {}
    growth = output_data.get("growth") or {}
    growth_metrics = growth.get("metrics") or {}

    followers = profile.get("followers", 0) or 0
    momentum = _build_momentum(followers)
    best_time = _build_best_time(posts)

    query = f"{niche.get('primary_niche', 'creator')} growth strategies engagement tips"
    knowledge_chunks = retrieve(query, k=3)

    creator_metrics = {
        "followers": followers,
        "growth_score": growth.get("growth_score"),
        "avg_views": growth_metrics.get("avg_views"),
        "avg_engagement_rate_by_views": growth_metrics.get("avg_engagement_rate_by_views"),
        "posts_per_week": growth_metrics.get("posts_per_week") or profile.get("posts_per_week"),
    }

    recent_posts = [
        {
            "likes": p.get("likes", 0),
            "comments": p.get("comments", 0),
            "views": p.get("views", 0) or 0,
        }
        for p in posts[-3:]
    ]

    return generate_action_plan(
        creator_metrics=creator_metrics,
        niche_data=niche,
        momentum=momentum,
        best_time=best_time,
        recent_posts=recent_posts,
        knowledge_chunks=knowledge_chunks,
    )


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    total = 0
    enriched = 0
    skipped = 0
    output_rows = []

    for line_num, row in _read_jsonl(INPUT_PATH):
        total += 1
        if total % 10 == 0:
            print(f"[enrich] processed={total} enriched={enriched} skipped={skipped}")

        try:
            action_plan = _build_action_plan(row)
            output = row.get("output") or {}
            output["action_plan"] = action_plan
            row["output"] = output
            output_rows.append(row)
            enriched += 1
        except Exception as exc:
            example_id = row.get("example_id", "unknown")
            print(f"[warn] skipped example_id={example_id} line={line_num}: {exc}")
            skipped += 1

    _write_jsonl(OUTPUT_PATH, output_rows)
    print("[enrich] done")
    print(f"total processed: {total}")
    print(f"total enriched: {enriched}")
    print(f"total skipped: {skipped}")


if __name__ == "__main__":
    main()
