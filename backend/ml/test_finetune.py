"""
Test the fine-tuned model vs base model side by side.
Sends the same creator profile to both and compares outputs.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from openai import OpenAI

FINE_TUNED_MODEL = "ft:gpt-4o-mini-2024-07-18:personal:creonnect-v1:DPYVeka2"
BASE_MODEL = "gpt-4o-mini"

# Test with a creator profile NOT in the training data
TEST_PROFILE = {
    "input": {
        "profile": {
            "username": "test_creator_99",
            "followers": 15200,
            "avg_likes": 420,
            "avg_comments": 65,
            "avg_views": 8900,
            "posts_per_week": 2.1,
            "snapshot_date": "2026-03-31",
            "niche": "fitness"
        },
        "posts": [
            {"caption": "Morning run in the rain - no excuses 🌧️💪", "likes": 580, "comments": 92, "views": 12400},
            {"caption": "Meal prep Sunday - chicken & rice bowls", "likes": 310, "comments": 45, "views": 6200},
            {"caption": "New PR on deadlift! 315lbs 🏋️", "likes": 890, "comments": 134, "views": 18500},
            {"caption": "Recovery day stretching routine", "likes": 210, "comments": 28, "views": 4100},
        ]
    }
}

SYSTEM_MSG = "You are an AI assistant that provides creator growth action plans."


def call_model(client: OpenAI, model: str, profile: dict) -> tuple[str, float]:
    """Call a model and return (response_text, duration_seconds)."""
    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": json.dumps(profile)},
        ],
        temperature=0.4,
        max_tokens=600,
    )
    duration = time.time() - start
    return response.choices[0].message.content.strip(), duration


def try_parse_json(text: str) -> dict | None:
    """Attempt to parse response as JSON."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def print_section(title: str, width: int = 60):
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def print_action_plan(parsed: dict):
    """Pretty-print the action plan."""
    ap = parsed.get("action_plan", parsed)

    diagnosis = ap.get("diagnosis", "N/A")
    print(f"\n  Diagnosis: {diagnosis}")

    weekly = ap.get("weekly_plan", [])
    if weekly:
        print("\n  Weekly Plan:")
        for item in weekly:
            print(f"    • {item}")

    content = ap.get("content_suggestions", [])
    if content:
        print("\n  Content Suggestions:")
        for item in content:
            print(f"    • {item}")

    schedule = ap.get("posting_schedule", [])
    if schedule:
        print("\n  Posting Schedule:")
        for item in schedule:
            print(f"    • {item}")

    cta = ap.get("cta_tips", [])
    if cta:
        print("\n  CTA Tips:")
        for item in cta:
            print(f"    • {item}")


def main():
    print_section("Creonnect Fine-Tune Test — Side-by-Side Comparison")

    print("\n  Test Profile:")
    p = TEST_PROFILE["input"]["profile"]
    print(f"    Username:   {p['username']}")
    print(f"    Followers:  {p['followers']:,}")
    print(f"    Avg Likes:  {p['avg_likes']}")
    print(f"    Avg Views:  {p['avg_views']:,}")
    print(f"    Posts/Week: {p['posts_per_week']}")
    print(f"    Niche:      {p['niche']}")

    client = OpenAI()

    # --- Base Model ---
    print_section(f"BASE MODEL: {BASE_MODEL}")
    print("  Calling...")
    base_response, base_time = call_model(client, BASE_MODEL, TEST_PROFILE)
    print(f"  Response time: {base_time:.2f}s")

    base_parsed = try_parse_json(base_response)
    if base_parsed:
        print("  Format: ✅ Valid JSON")
        print_action_plan(base_parsed)
    else:
        print("  Format: ❌ Not valid JSON")
        print(f"\n  Raw output:\n{base_response[:800]}")

    # --- Fine-Tuned Model ---
    print_section(f"FINE-TUNED: {FINE_TUNED_MODEL}")
    print("  Calling...")
    ft_response, ft_time = call_model(client, FINE_TUNED_MODEL, TEST_PROFILE)
    print(f"  Response time: {ft_time:.2f}s")

    ft_parsed = try_parse_json(ft_response)
    if ft_parsed:
        print("  Format: ✅ Valid JSON")
        print_action_plan(ft_parsed)
    else:
        print("  Format: ❌ Not valid JSON")
        print(f"\n  Raw output:\n{ft_response[:800]}")

    # --- Comparison ---
    print_section("COMPARISON")
    print(f"  {'Metric':<25} {'Base':<15} {'Fine-Tuned':<15}")
    print(f"  {'-'*55}")
    print(f"  {'Response time':<25} {base_time:.2f}s{'':<10} {ft_time:.2f}s")
    print(f"  {'Valid JSON':<25} {'✅' if base_parsed else '❌':<15} {'✅' if ft_parsed else '❌'}")

    if base_parsed and ft_parsed:
        base_ap = base_parsed.get("action_plan", base_parsed)
        ft_ap = ft_parsed.get("action_plan", ft_parsed)
        base_keys = set(base_ap.keys())
        ft_keys = set(ft_ap.keys())
        expected = {"diagnosis", "weekly_plan", "content_suggestions", "posting_schedule", "cta_tips"}

        base_has = len(expected & base_keys)
        ft_has = len(expected & ft_keys)
        print(f"  {'Schema completeness':<25} {base_has}/5 keys{'':<7} {ft_has}/5 keys")
        print(f"  {'Has diagnosis':<25} {'✅' if 'diagnosis' in base_ap else '❌':<15} {'✅' if 'diagnosis' in ft_ap else '❌'}")
        print(f"  {'Has weekly_plan':<25} {'✅' if 'weekly_plan' in base_ap else '❌':<15} {'✅' if 'weekly_plan' in ft_ap else '❌'}")
        print(f"  {'Has content_suggestions':<25} {'✅' if 'content_suggestions' in base_ap else '❌':<15} {'✅' if 'content_suggestions' in ft_ap else '❌'}")

    print(f"\n{'=' * 60}")
    print("  Test complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
