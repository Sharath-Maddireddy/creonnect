#!/usr/bin/env python3
"""Simple reel vision analysis test"""
import sys
sys.path.insert(0, '.')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.') / 'backend' / '.env', override=False)

import os, json, time, httpx

BACKEND_URL = "http://localhost:8000"
INSTA_URL = "https://www.instagram.com/reel/DXH3GOjDNsN/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ=="

print("="*100 + "\nREEL VISION ANALYSIS TEST\n" + "="*100)

# Extract video from Instagram
print("\n[1] Extracting Instagram video URL...")
video_url = None
try:
    import yt_dlp
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'format': 'best[ext=mp4]/best'}) as ydl:
        info = ydl.extract_info(INSTA_URL, download=False)
        video_url = info.get('url') or (info.get('formats', [{}])[-1].get('url') if info.get('formats') else None)
        if video_url:
            print(f"✓ Got video URL: {video_url[:50]}...")
except Exception as e:
    print(f"✗ Failed: {e}")

if not video_url:
    print("Using fallback test video...")
    video_url = "https://commondatastorage.googleapis.com/gtv-videos-library/sample/BigBuckBunny.mp4"

# Enqueue job
print(f"\n[2] Enqueueing reel analysis...")
try:
    with httpx.Client(timeout=10) as client:
        resp = client.post(f"{BACKEND_URL}/api/reel-analysis/enqueue", json={
            "media_url": video_url,
            "caption_text": "Test",
            "watch_time_pct": 75.0,
        })
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    job_id = resp.json()["job_id"]
    print(f"✓ Job ID: {job_id}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

# Poll for result  
print(f"\n[3] Polling for completion (timeout 30s)...")
for i in range(30):
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{BACKEND_URL}/api/reel-analysis/jobs/{job_id}")
        
        if resp.status_code == 404:
            print(f"✗ Job not found")
            break
        
        job_status = resp.json()
        status = job_status.get("status")
        print(f"  [{i+1:2d}] {status}", flush=True, end="\n" if status in {"succeeded", "failed"} else "\r")
        
        if status in {"succeeded", "failed"}:
            break
        time.sleep(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        break

# Display results
print(f"\n[4] Results:")
if 'job_status' in locals() and job_status:
    print("\nFull Response:")
    print(json.dumps(job_status, indent=2))
    
    if job_status.get("status") == "succeeded":
        result = job_status.get("result", {})
        vision_status = result.get('reel_vision_status')
        vision_signals = result.get('raw_vision_signals', {})
        print(f"\n✓ VISION STATUS: {vision_status}")
        print(f"✓ VISION SIGNALS:")
        print(json.dumps(vision_signals, indent=2))
    else:
        error = job_status.get("error", {})
        print(f"\n✗ Job Status: {job_status.get('status')}")
        print(f"✗ Error: {error}")
else:
    print("No status available")

print("\n" + "="*100)
