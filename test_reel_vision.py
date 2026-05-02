#!/usr/bin/env python3
"""
Test Reel Vision Analysis with Instagram URL
Enqueues a reel analysis job and monitors the vision_status
"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from dotenv import load_dotenv

# Load env
_backend_env = Path('.') / 'backend' / '.env'
load_dotenv(_backend_env, override=False)

import os
import json
import time
import asyncio
import httpx
from urllib.parse import urlparse

print("=" * 100)
print("REEL VISION ANALYSIS TEST")
print("=" * 100)

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
INSTAGRAM_URL = "https://www.instagram.com/reel/DXH3GOjDNsN/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ=="

print(f"\n[Config]")
print(f"  Backend URL: {BACKEND_URL}")
print(f"  Instagram Reel: {INSTAGRAM_URL}")
print(f"  API Endpoint: {BACKEND_URL}/api/reel-analysis/enqueue")

# Step 1: Try to extract video URL from Instagram
print("\n[Step 1] Extracting video from Instagram URL...")
print("  ⚠️  Note: Instagram URLs require authentication or specific tools to extract")
print("  Attempting to get direct media URL...")

# Try using yt-dlp if available
try:
    import yt_dlp
    print("  ✓ yt-dlp found, extracting video...")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best[ext=mp4]/best',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(INSTAGRAM_URL, download=False)
        video_url = info.get('url') or info.get('formats', [{}])[-1].get('url')
        print(f"  ✓ Extracted video URL: {video_url[:80]}...")
except ImportError:
    print("  ✗ yt-dlp not installed")
    print("  Trying alternative approach...")
    video_url = None
except Exception as e:
    print(f"  ✗ Error extracting: {e}")
    video_url = None

# Step 2: If no video_url, use a test MP4 URL
if not video_url:
    print("\n[Step 2] Using test video URL instead...")
    # Use a publicly available test video
    test_urls = [
        "https://commondatastorage.googleapis.com/gtv-videos-library/sample/BigBuckBunny.mp4",
        "https://www.w3schools.com/html/mov_bbb.mp4",
    ]
    
    for test_url in test_urls:
        print(f"  Testing URL: {test_url[:60]}...")
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.head(test_url, follow_redirects=True)
                if response.status_code == 200:
                    video_url = test_url
                    print(f"  ✓ Found accessible video URL")
                    break
        except Exception as e:
            print(f"    ✗ Not accessible: {e}")
            continue

if not video_url:
    print("\n✗ ERROR: Could not get video URL")
    print("  Please provide a direct MP4 URL or install yt-dlp:")
    print("  pip install yt-dlp")
    sys.exit(1)

# Step 3: Enqueue reel analysis
print(f"\n[Step 3] Enqueueing reel analysis...")
print(f"  Video URL: {video_url[:80]}...")

payload = {
    "media_url": video_url,
    "caption_text": "Test reel analysis with vision",
    "audio_name": None,
    "watch_time_pct": 75.0,
}

print(f"  Payload: {json.dumps(payload, indent=2)}")

try:
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{BACKEND_URL}/api/reel-analysis/enqueue",
            json=payload,
        )
    
    if response.status_code != 200:
        print(f"\n✗ ERROR: API returned {response.status_code}")
        print(f"  Response: {response.text}")
        sys.exit(1)
    
    result = response.json()
    job_id = result.get("job_id")
    print(f"  ✓ Job enqueued successfully")
    print(f"  Job ID: {job_id}")
except Exception as e:
    print(f"\n✗ ERROR: Failed to enqueue: {e}")
    print("  Is the backend running at http://localhost:8000?")
    sys.exit(1)

# Step 4: Poll for job completion
print(f"\n[Step 4] Polling for job completion...")
print(f"  Job ID: {job_id}")

max_attempts = 30  # 30 seconds max
attempt = 0
@@job_status = None
@@# Step 4: Poll for job completion
@@print(f"\n[Step 4] Polling for job completion...")
@@print(f"  Job ID: {job_id}")
@@
@@max_attempts = 30  # 30 seconds max
@@attempt = 0
@@job_status = None
@@max_attempts = 30  # 30 seconds max
@@attempt = 0
@@job_status = None

while attempt < max_attempts:
    attempt += 1
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{BACKEND_URL}/api/reel-analysis/job/{job_id}")
        
        if response.status_code != 200:
            print(f"  ✗ Failed to get job status: {response.status_code}")
            break
        
        job_status = response.json()
        status = job_status.get("status")
        
        print(f"  [{attempt}] Status: {status}...", end="", flush=True)
        
        if status == "succeeded":
            print("\n  ✓ Job completed successfully!")
            break
        elif status == "failed":
            print("\n  ✗ Job failed!")
            break
        elif status in {"queued", "started"}:
            print(" waiting...", flush=True)
            time.sleep(1)
        else:
            print(f"\n  ? Unknown status: {status}")
            break
    
    except Exception as e:
        print(f"\n  ✗ Error polling: {e}")
        job_status = {"status": "error", "error": str(e)}
        break

# Step 5: Display results
@@# Step 5: Display results
@@print(f"\n[Step 5] Results:")
@@print(f"\nFull Job Status:")
@@if job_status:
@@    print(json.dumps(job_status, indent=2))
@@else:
@@    print("  (No job status retrieved)")
@@
@@if job_status and job_status.get("status") == "succeeded":
@@    result = job_status.get("result", {})
@@    print(f"\n[Vision Analysis Results]")
@@    print(f"  vision_status: {result.get('reel_vision_status', 'N/A')}")
@@    print(f"  vision_score: {result.get('vision_score', 'N/A')}")
@@    print(f"  total_score: {result.get('total', 'N/A')}")
@@    print(f"  raw_vision_signals: {json.dumps(result.get('raw_vision_signals', {}), indent=4)}")
@@    
@@    if result.get('reel_vision_status') == 'error':
@@        print(f"\n⚠️  VISION STATUS IS ERROR!")
@@        print(f"  Check error field above for details")
@@else:
@@    if job_status:
@@        error = job_status.get("error", {})
@@        print(f"\n[Error Details]")
@@        print(f"  Error Type: {error.get('type', 'N/A')}")
@@        print(f"  Error Message: {error.get('message', 'N/A')}")
@@    else:
@@        print("\n⚠️  No job status retrieved!")
@@
@@print("\n" + "=" * 100)
