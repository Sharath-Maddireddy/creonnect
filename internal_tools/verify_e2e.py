import os
import time
import requests

API_URL = "http://localhost:8000"

def test_pipeline():
    print("🚀 Starting End-to-End Pipeline Verification...")
    
    # 1. Start Analysis Job (Simulating a scrape)
    print("\n[1/3] Triggering Account Analysis Job...")
    try:
        response = requests.post(
            f"{API_URL}/api/account-analysis",
            json={
                "account_id": "cristiano",
                "post_limit": 5
            }
        )
        if response.status_code != 200:
            print(f"❌ Failed to enqueue job. Is the FastAPI server running? Status: {response.status_code}")
            return
            
        job_id = response.json().get("job_id")
        print(f"✅ Job Enqueued successfully! Job ID: {job_id}")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API. Make sure FastAPI is running (npm run dev or uvicorn backend.main:app).")
        return

    # 2. Poll for Completion
    print("\n[2/3] Polling for Job Completion (Waiting for RQ Worker)...")
    max_attempts = 30
    for i in range(max_attempts):
        poll_res = requests.get(f"{API_URL}/api/account-analysis/{job_id}")
        if poll_res.status_code == 200:
            status_data = poll_res.json()
            status = status_data.get("status")
            print(f"   ⏳ Attempt {i+1}: Status is '{status}'...")
            
            if status == "succeeded":
                print("✅ Job Succeeded!")
                print("   Niche detected:", status_data.get("result", {}).get("pillars"))
                print("   Account Health:", status_data.get("result", {}).get("ahs_score"))
                break
            elif status == "failed":
                print("❌ Job Failed in the worker. Check worker logs.")
                print(status_data.get("error"))
                return
        time.sleep(2)
    else:
        print("❌ Job timed out or worker is not running.")
        return

    # 3. Test Brand Match (Vector Search)
    print("\n[3/3] Testing Semantic Brand Matchmaking (pgvector)...")
    brand_prompt = "Looking for a legendary soccer player who posts fitness and lifestyle content."
    print(f"   Prompt: '{brand_prompt}'")
    
    match_res = requests.post(
        f"{API_URL}/api/campaigns/match",
        json={
            "prompt": brand_prompt,
            "top_k": 3
        }
    )
    
    if match_res.status_code == 200:
        matches = match_res.json().get("matches", [])
        if matches:
            print("✅ Vector Search Successful! Found matches:")
            for idx, match in enumerate(matches):
                print(f"   {idx+1}. {match.get('account_id')} (Score: {match.get('match_score')})")
        else:
            print("⚠️ Search completed, but no matches were returned. Ensure the database is populated.")
    else:
        print(f"❌ Failed to run brand match. Status: {match_res.status_code}")

    print("\n🎉 E2E Verification Script Complete!")

if __name__ == "__main__":
    test_pipeline()
