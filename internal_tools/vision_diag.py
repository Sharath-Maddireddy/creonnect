import asyncio
from pathlib import Path
from backend.app.services.ai_analysis_service import run_vision_analysis
from backend.app.domain.post_models import SinglePostInsights, CoreMetrics, DerivedMetrics, BenchmarkMetrics

REPO_ROOT = Path(__file__).resolve().parents[1]

async def diag():
    import os
    env_path = REPO_ROOT / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    
    post = SinglePostInsights(
        account_id="test_user",
        media_id="DV1UI3Dk2km",
        media_url="https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800",
        media_type="REEL",
        caption_text="Fuel the rage. Lift harder.",
        core_metrics=CoreMetrics(impressions=1000, likes=28, comments=1),
        derived_metrics=DerivedMetrics(),
        benchmark_metrics=BenchmarkMetrics()
    )
    
    import logging
    logging.basicConfig(level=logging.ERROR)
    
    # We want to see the error from run_vision_analysis explicitly
    # So we'll patch logger to print to stdout so we don't miss anything.
    import backend.app.services.ai_analysis_service as ai
    old_error = ai.logger.error
    def print_error(*args, **kwargs):
        print("LOGGER ERROR:", args, kwargs)
        old_error(*args, **kwargs)
    ai.logger.error = print_error

    res = await run_vision_analysis(post)
    print("Vision Res:", res)

if __name__ == "__main__":
    asyncio.run(diag())
