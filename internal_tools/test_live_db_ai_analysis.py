import asyncio
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / "backend" / ".env", override=True)

from backend.app.services.creator_pool_service import get_all_creators
from backend.app.services.account_analysis_jobs import run_account_analysis_job
from backend.app.infra.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ai")

async def main():
    await init_db(strict=True)
    creators = get_all_creators()
    if not creators:
        print("No creators in DB.")
        return
        
    creator = creators[0]
    account_id = creator.get("account_id")
    username = creator.get("username", account_id.replace("_id", ""))
    print(f"Triggering AI Analysis for Supabase Profile: {username} ({account_id})")
    
    payload = {
        "account_id": account_id,
        "username": username,
        "post_limit": 5  # keep it small for quick test
    }
    
    try:
        # We run it directly. It will fetch posts from BD, analyze them via AI, and save results!
        result = run_account_analysis_job(payload)
        print("Analysis completed successfully!")
        if "overall_score" in result:
            print(f"Overall Score: {result.get('overall_score')}")
        print(f"Keys in result: {list(result.keys())}")
    except Exception as e:
        logger.exception("Analysis failed")

if __name__ == "__main__":
    asyncio.run(main())
