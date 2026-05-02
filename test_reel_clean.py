print(f"\n[Step 4] Polling for completion...")
job_status = None
for i in range(30):
    try:
    with httpx.Client(timeout=5) as client:
#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.') / 'backend' / '.env', override=False)

import os, json, time, httpx

print("="*100)
print("REEL VISION ANALYSIS TEST")
print("="*100)

BACKEND_URL = "http://localhost:8000"
INSTAGRAM_URL = "https://www.instagram.com/reel/DXH3GOjDNsN/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ=="

print(f"\n[Step 1] Extracting Instagram video...")
video_url = None
try:
    import yt_dlp
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'format': 'best[ext=mp4]/best'}) as ydl:
        info = ydl.extract_info(INSTAGRAM_URL, download=False)
        video_url = info.get('url') or (info.get('formats', [{}])[-1].get('url') if info.get('formats') else None)
        if video_url:
            print(f"  ✓ Extracted: {video_url[:60]}...")
except:
    print("  ✗ Failed to extract from Instagram")

if not video_url:
    print("[Step 2] Using test video...")
    video_url = "https://commondatastorage.googleapis.com/gtv-videos-library/sample/BigBuckBunny.mp4"
    print(f"  Using: {video_url[:60]}...")

print(f"\n[Step 3] Enqueueing reel analysis...")
try:
    with httpx.Client(timeout=10) as client:
        resp = client.post(f"{BACKEND_URL}/api/reel-analysis/enqueue", json={
            "media_url": video_url,
            "caption_text": "Test reel",
            "audio_name": None,
            "watch_time_pct": 75.0,
        })
    if resp.status_code != 200:
        print(f"  ✗ ERROR {resp.status_code}: {resp.text}")
        sys.exit(1)
    job_id = resp.json().get("job_id")
    print(f"  ✓ Job ID: {job_id}")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

print(f"\n[Step 4] Polling for completion...")
job_status = None
for i in range(30):
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{BACKEND_URL}/api/reel-analysis/jobs/{job_id}")
            if resp.status_code != 200:
                    print(f"  ✗ Status error {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ✗ Status error {resp.status_code}")
            break
        job_status = resp.json()
        status = job_status.get("status")
        print(f"  [{i+1}] {status}...", end=" ", flush=True)
        if status in {"succeeded", "failed"}:
            print(f"\n  ✓ Done!")
            break
        time.sleep(1)
    except Exception as e:
        print(f"\n  ✗ Poll error: {e}")
        break

print(f"\n[Step 5] Results:")
if job_status:
    print(json.dumps(job_status, indent=2))
    if job_status.get("status") == "succeeded":
        result = job_status.get("result", {})
        print(f"\n[VISION STATUS]: {result.get('reel_vision_status')}")
        print(f"[VISION SIGNALS]: {json.dumps(result.get('raw_vision_signals', {}), indent=2)}")
else:
    print("No status retrieved")
print("="*100)
