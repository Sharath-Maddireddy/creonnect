import os
import sys
import json
import subprocess
from dotenv import load_dotenv
load_dotenv("backend/.env")

from backend.app.analytics.reel_gemini_engine import run_reel_gemini_analysis
from backend.app.analytics.reel_audio_engine import compute_reel_audio_score
from backend.app.analytics.reel_analysis_service import compute_reel_analysis

URL = "https://www.instagram.com/reel/DUQFZYQETvP/"

def test_reel():
    print(f"Fetching direct video URL for {URL}...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--get-url", URL],
            capture_output=True, text=True, check=True
        )
        media_url = result.stdout.strip().splitlines()[0]
        print(f"Direct media URL fetched: {media_url[:80]}...")
    except Exception as e:
        print(f"Failed to fetch media_url using yt-dlp: {e}")
        return

    # Attempt to fetch caption + audio name
    caption_text = ""
    audio_name = None
    try:
        meta_res = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--dump-json", URL],
            capture_output=True, text=True, check=True
        )
        meta = json.loads(meta_res.stdout.strip().splitlines()[0])
        caption_text = meta.get("description", "")
        audio_name = meta.get("track")
    except Exception as e:
        print(f"Failed to fetch metadata, continuing without caption: {e}")
    
    print("\nRunning Gemini analysis (this might take ~15-30s)...")
    vision_result = run_reel_gemini_analysis(media_url)
    
    vision_status = vision_result.get("status")
    print(f"Vision analysis completed with status: {vision_status}")
    signals = vision_result.get("signals", {})
    
    if vision_status != "ok":
        print(f"Error: {vision_result}")
        return

    audio_score = compute_reel_audio_score(
        audio_name=audio_name,
        caption_text=caption_text
    )
    
    reel_model = compute_reel_analysis(
        reel_vision_signals=signals,
        audio_score=audio_score,
        watch_time_pct=None, 
        reel_vision_status=vision_status
    )
    
    final_output = reel_model.model_dump()
    final_output["gemini_signals"] = signals
    
    print("\n================== REEL ANALYSIS RESULT ==================")
    print(f"Caption: {caption_text[:100]}...")
    print(f"Audio Track: {audio_name}")
    print("----------------------------------------------------------")
    print(json.dumps(final_output, indent=2))

if __name__ == "__main__":
    test_reel()
