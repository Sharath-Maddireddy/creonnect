"""
Creonnect Demo Script

Demonstrates the full AI pipeline with synthetic data:
- Niche classification
- Growth score computation
- Post insights analysis
- Context building
- LLM explanation

Run with: python -m backend.app.demo
"""

from pathlib import Path

from backend.app.ai.niche import detect_creator_niche
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.post_insights import analyze_post
from backend.app.ai.context import build_creator_context
from backend.app.ai.explain import CreatorExplanationService

# Import synthetic data loader and generator
from backend.app.demo.synthetic_loader import load_synthetic, DATA_PATH
from backend.app.demo.generate_fake_instagram import save_synthetic_creator


def ensure_synthetic_data_exists():
    """Generate synthetic data if it doesn't exist."""
    if not DATA_PATH.exists():
        print("[Setup] Generating synthetic creator data...")
        save_synthetic_creator(
            output_path=DATA_PATH,
            niche="fitness",
            followers=75000,
            num_posts=10
        )
        print()


def main():
    print("\n" + "=" * 60)
    print("CREONNECT DEMO - Creator Intelligence Pipeline")
    print("=" * 60 + "\n")

    # Ensure synthetic data exists
    ensure_synthetic_data_exists()

    # Load synthetic creator data
    print("[Loading] Synthetic creator data...")
    profile, posts = load_synthetic()

    print(f"Creator: @{profile.username}")
    print(f"Followers: {profile.followers_count:,}")
    print(f"Posts analyzed: {len(posts)}")
    print("-" * 40)

    # Step 1: Classify niche
    print("\n[1/4] Classifying niche...")
    niche_result = detect_creator_niche(profile, posts)
    print(f"  Primary niche: {niche_result.get('primary_niche', 'unknown')}")
    print(f"  Confidence: {niche_result.get('confidence', 0):.2f}")

    # Step 2: Compute growth score
    print("\n[2/4] Computing growth score...")
    growth_result = compute_growth_score(profile, posts)
    print(f"  Growth score: {growth_result.get('growth_score', 0)}/100")
    breakdown = growth_result.get("breakdown", {})
    print(f"  Breakdown: Engagement={breakdown.get('engagement', 0)}, "
          f"Content={breakdown.get('content', 0)}, "
          f"Consistency={breakdown.get('consistency', 0)}")

    # Step 3: Analyze posts
    print("\n[3/4] Analyzing posts...")
    post_insights = []
    for post in posts:
        insight = analyze_post(post, profile)
        post_insights.append(insight)
        engagement_rate = insight.get("engagement_rate_by_views", 0) or 0
        print(f"  Post {post.post_id}: {engagement_rate * 100:.2f}% engagement")

    # Step 4: Generate explanation
    print("\n[4/4] Generating AI explanation...")
    ai_outputs = {
        "niche": niche_result,
        "growth": growth_result,
        "posts": post_insights
    }

    service = CreatorExplanationService()
    explanation = service.explain_creator(profile, posts, ai_outputs)

    print("\n" + "=" * 60)
    print("AI EXPLANATION")
    print("=" * 60)

    if isinstance(explanation, dict):
        print(f"\nStatus: {explanation.get('status', 'unknown')}")
        print(f"Message: {explanation.get('message', 'No message')}")
        print(f"Growth data available: {'Yes' if explanation.get('growth') else 'No'}")
    else:
        print(f"\n{explanation}")

    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()


