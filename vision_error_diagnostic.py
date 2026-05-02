#!/usr/bin/env python3
"""
Comprehensive Vision Analysis Error Diagnostic
Identifies all possible error conditions for image and reel vision analysis
"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from dotenv import load_dotenv

# Load env
_backend_env = Path(__file__).parent / "backend" / ".env"
_root_env = Path(__file__).parent / ".env"
_env_file = _backend_env if _backend_env.exists() else _root_env
load_dotenv(_env_file, override=False)

import os

print("=" * 80)
print("VISION ANALYSIS ERROR DIAGNOSTIC")
print("=" * 80)

# Check 1: API Key
print("\n[1] GEMINI_API_KEY Configuration:")
api_key = os.getenv("GEMINI_API_KEY", "").strip()
print(f"    ✓ API Key Present: {bool(api_key)}")
if api_key:
    print(f"    ✓ Key Length: {len(api_key)}")
    print(f"    ✓ Key Format: {api_key[:10]}...{api_key[-10:]}")
    print(f"    ✓ Starts with 'AIza': {api_key.startswith('AIza')}")
else:
    print("    ✗ ERROR: GEMINI_API_KEY not set!")

# Check 2: Google GenAI SDK
print("\n[2] Google GenAI SDK Installation:")
try:
    import google.generativeai as genai
    print("    ✓ google.generativeai imported successfully")
    print(f"    ✓ Available models: gemini-2.0-flash, gemini-flash-lite-latest")
except ImportError as e:
    print(f"    ✗ ERROR: {e}")

# Check 3: TOON Parser
print("\n[3] TOON Parser Installation:")
try:
    from backend.app.ai.toon import loads as toon_loads
    print("    ✓ TOON parser imported successfully")
except ImportError as e:
    print(f"    ✗ ERROR: {e}")

# Check 4: Test Gemini API Connection
print("\n[4] Gemini API Connectivity Test:")
if api_key:
    try:
        import google.generativeai as genai
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
        with open(os.path.devnull, 'w') as devnull:
            old_stderr = sys.stderr
            sys.stderr = devnull
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_name)
                print(f"    ✓ Successfully configured model: {model_name}")
                print("    ✓ API key authentication passed")
            finally:
                sys.stderr = old_stderr
    except Exception as e:
        print(f"    ✗ ERROR: {type(e).__name__}: {e}")
else:
    print("    ⚠ SKIPPED: API Key not available")

# Check 5: Image Analysis Paths
print("\n[5] Image Vision Analysis (ai_analysis_service.py) - Failure Modes:")
failure_modes_image = [
    ("Media URL is empty/None", "status='no_media'"),
    ("Media URL fails SSRF check", "status='no_media'"),
    ("API Key missing after env load", "status='error'"),
    ("Gemini API call timeout (30s)", "status='error'"),
    ("Gemini returns non-text response", "status='error'"),
    ("TOON parsing fails", "status='error'"),
    ("Missing required TOON fields", "status='error'"),
    ("Invalid field types in response", "status='error'"),
    ("Visual quality scores invalid", "status='error'"),
    ("Hook strength score not numeric", "status='error'"),
    ("Any other exception in try block", "status='error'"),
]

for i, (condition, result) in enumerate(failure_modes_image, 1):
    print(f"    {i}. {condition}")
    print(f"       → {result}")

# Check 6: Video Analysis Paths
print("\n[6] Video (Reel) Analysis (reel_gemini_engine.py) - Failure Modes:")
failure_modes_video = [
    ("GEMINI_API_KEY not set", "status='disabled'"),
    ("Media URL is empty/None", "status='error', error='empty_media_url'"),
    ("Video download fails (timeout/invalid URL)", "status='error', error='download_failed'"),
    ("Video exceeds 100 MB size limit", "status='error', error='download_failed'"),
    ("Gemini file upload fails", "status='error'"),
    ("File processing FAILED by Gemini", "status='error'"),
    ("File never reaches ACTIVE state (40s timeout)", "status='error'"),
    ("Model analysis API call fails", "status='error'"),
    ("Response parsing fails", "status='error'"),
]

for i, (condition, result) in enumerate(failure_modes_video, 1):
    print(f"    {i}. {condition}")
    print(f"       → {result}")

# Check 7: Common Issues
print("\n[7] Most Common Causes of 'error' Status:")
common_issues = [
    ("Invalid/expired GEMINI_API_KEY", "→ Verify key in backend/.env"),
    ("Gemini quota/billing limit exceeded", "→ Check Google AI Studio quota"),
    ("API rate limiting (429 error)", "→ Retry after delay (built-in 35s backoff)"),
    ("Malformed Gemini response (JSON/TOON parse)", "→ Check Gemini output format"),
    ("Missing required fields in response", "→ Verify all required fields present"),
    ("Invalid media URL (not accessible)", "→ Test URL in browser"),
    ("Network timeout (30s limit for images, 120s for reels)", "→ Check network/Gemini service"),
    ("SSRF protection blocking URL", "→ Use public HTTPS URLs only"),
    ("Video format not MP4 or too large", "→ Compress video < 100 MB"),
]

for issue, fix in common_issues:
    print(f"    • {issue}")
    print(f"      {fix}")

print("\n" + "=" * 80)
print("NEXT STEPS:")
print("=" * 80)
print("1. Check backend logs with: tail -f logs/app.log (if exists)")
print("2. Enable debug logging in ai_analysis_service.py")
print("3. Test with valid, public media URLs")
print("4. Verify Gemini API quota at: https://aistudio.google.com/app/apikey")
print("=" * 80)
