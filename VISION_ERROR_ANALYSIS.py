"""
Complete Vision Status Error Analysis for Images & Videos
=========================================================

This document lists ALL possible reasons for vision_status="error" in Creonnect.
Based on code analysis of ai_analysis_service.py and reel_gemini_engine.py
"""

print("=" * 100)
print("VISION STATUS ERROR ANALYSIS - Complete Error Scenarios")
print("=" * 100)

# ============================================================================
# IMAGE VISION ANALYSIS (ai_analysis_service.py, run_vision_analysis function)
# ============================================================================

print("\n" + "=" * 100)
print("IMAGE ANALYSIS - run_vision_analysis() in ai_analysis_service.py")
print("=" * 100)

image_errors = {
    "Status Code": "no_media",
    "Conditions": [
        "post.media_url is None or empty string",
        "post.media_url doesn't have http/https scheme",
        "URL hostname is not public (fails SSRF check)",
        "Hostname is in private IP range (127.*, 10.*, 172.16-31.*, 192.168.*)",
        "Hostname is localhost, .local, or other reserved domains",
    ]
}

print("\n[1] MEDIA URL VALIDATION FAILURE:")
for condition in image_errors["Conditions"]:
    print(f"    • {condition}")
    print(f"      → returns status='no_media'")

print("\n[2] API KEY MISSING (after env load):")
print("    • GEMINI_API_KEY not in environment at run time")
print("      → returns status='error'")
print("    Note: This should NOT happen now since we fixed backend/main.py")

print("\n[3] GEMINI API CALL TIMEOUT:")
print("    • _generate_gemini_vision_json() takes > 30 seconds")
print("      → asyncio.TimeoutError raised")
print("      → returns status='error'")
print("    Note: Typical causes:")
print("      - Network latency to Google API")
print("      - Gemini service overloaded")
print("      - Large image size (> 20MB)")

print("\n[4] GEMINI RESPONSE FORMAT ERRORS:")
errors_format = [
    ("Gemini returns null/empty text", "ValueError: Gemini response did not include text output"),
    ("Response is not JSON or TOON", "Parsing error in toon_loads()"),
    ("Output is dict but missing required fields", "ValueError: Gemini TOON schema mismatch"),
]
for scenario, error in errors_format:
    print(f"    • {scenario}")
    print(f"      Error: {error}")
    print(f"      → returns status='error'")

print("\n[5] RESPONSE VALIDATION ERRORS:")
validation_errors = [
    ("objects is not a list", "ValueError: Invalid objects field"),
    ("dominant_focus is not string/null", "ValueError: Invalid dominant_focus field"),
    ("scene_description is not string", "ValueError: Invalid scene_description field"),
    ("detected_text is not string/null", "ValueError: Invalid detected_text field"),
    ("visual_style is not string", "ValueError: Invalid visual_style field"),
    ("scene_type is not string/null", "ValueError: Invalid scene_type field"),
    ("visual_quality_score is not dict", "ValueError: Invalid visual_quality_score field"),
    ("technical_flaws is not list of strings", "ValueError: Invalid technical_flaws field"),
    ("hook_strength_score is not numeric", "ValueError: Invalid hook_strength_score field"),
]
for scenario, error in validation_errors:
    print(f"    • {scenario}")
    print(f"      → {error}")
    print(f"      → returns status='error'")

print("\n[6] VISUAL QUALITY SCORE VALIDATION:")
print("    • composition/lighting/subject_clarity/aesthetic_quality missing")
print("      → normalized_visual_quality = None (passes validation)")
print("      → but could indicate incomplete response")

print("\n[7] ANY OTHER EXCEPTION:")
print("    • Database error while saving analysis")
print("    • Out of memory processing large image")
print("    • Unexpected error in payload parsing")
print("    • Unexpected error in cringe floor enforcement")
print("      → Caught by outer try/except")
print("      → returns status='error'")

# ============================================================================
# VIDEO/REEL VISION ANALYSIS (reel_gemini_engine.py)
# ============================================================================

print("\n" + "=" * 100)
print("VIDEO ANALYSIS - run_reel_gemini_analysis() in reel_gemini_engine.py")
print("=" * 100)

print("\n[1] API KEY NOT SET:")
print("    • GEMINI_API_KEY is empty or missing at runtime")
print("      → returns {'status': 'disabled', 'signals': {}}")
print("    Note: This is 'disabled', not 'error'")

print("\n[2] INVALID OR EMPTY MEDIA URL:")
print("    • media_url is None, empty, or not a string")
print("      → returns {'status': 'error', 'error': 'empty_media_url'}")

print("\n[3] VIDEO DOWNLOAD FAILURE:")
print("    • URL download times out (30 second limit)")
print("    • HTTP status code is not 200 (e.g., 404, 403)")
print("    • Network error (connection refused, DNS failure)")
print("    • Video size exceeds 100 MB limit")
print("      → returns {'status': 'error', 'error': 'download_failed'}")

print("\n[4] GEMINI FILE UPLOAD FAILURE:")
print("    • Upload request fails with HTTP error")
print("    • API returns null/empty file name")
print("    • Invalid credentials or quota exceeded")
print("      → RuntimeError raised")
print("      → returns {'status': 'error', 'error': str(exception)}")

print("\n[5] GEMINI FILE PROCESSING TIMEOUT:")
print("    • File processing takes > 40 seconds (20 attempts × 2 second delay)")
print("    • File never reaches 'ACTIVE' state within timeout")
print("      → TimeoutError raised")
print("      → returns {'status': 'error', 'error': str(exception)}")

print("\n[6] GEMINI FILE PROCESSING FAILED:")
print("    • Gemini marks file state as 'FAILED'")
print("    • Unsupported video format (not MP4)")
print("    • Corrupted video file")
print("      → RuntimeError: 'Gemini file processing FAILED'")
print("      → returns {'status': 'error', 'error': str(exception)}")

print("\n[7] GEMINI MODEL ANALYSIS FAILURE:")
print("    • Model returns error instead of response")
print("    • Rate limited with 429 error")
print("      - Retries after 35 second backoff, tries both models")
print("      - If still fails, exception is raised")
print("    • Quota exceeded")
print("    • Invalid API key")
print("    • Model unavailable")
print("      → Exception raised (retried twice per model)")
print("      → returns {'status': 'error', 'error': str(exception)}")

print("\n[8] RESPONSE PARSING FAILURE:")
print("    • Response has no text field")
print("    • Response text is not string")
print("    • TOON parsing fails on response")
print("      → ValueError raised")
print("      → returns {'status': 'error', 'error': str(exception)}")

print("\n[9] ANY OTHER EXCEPTION:")
print("    • Worker timeout (120 second job timeout)")
print("    • Out of memory processing large video")
print("    • Redis connection error saving job status")
print("      → Exception logged and caught")
print("      → returns {'status': 'error', 'error': str(exception)}")

# ============================================================================
# COMMON ROOT CAUSES
# ============================================================================

print("\n" + "=" * 100)
print("TOP 10 MOST LIKELY ROOT CAUSES FOR vision_status='error'")
print("=" * 100)

root_causes = [
    ("1. Invalid/Expired GEMINI_API_KEY", [
        "Key is incorrect or revoked in Google AI Studio",
        "Key has wrong permissions/project",
        "Check: https://aistudio.google.com/app/apikey",
    ]),
    ("2. Gemini API Quota Exceeded", [
        "Billing disabled on Google Cloud project",
        "Request rate limit exceeded",
        "Total API usage limit reached",
        "Check quota at: https://aistudio.google.com/app/apikey",
    ]),
    ("3. Media URL Not Accessible", [
        "URL returns 404, 403, or other error",
        "URL redirects to HTTPS but has mixed content",
        "URL is blocked by firewall or regional restrictions",
        "Video file is corrupted or invalid format",
        "Test: Paste URL in browser to verify",
    ]),
    ("4. Gemini Response Parsing Failure", [
        "API response is malformed JSON/TOON",
        "Missing required fields in response",
        "Field types don't match expected types",
        "TOON parser fails on valid-looking response",
    ]),
    ("5. Network/Connectivity Issue", [
        "No internet connectivity",
        "Firewall blocking Google API requests",
        "DNS resolution failure",
        "Proxy misconfiguration",
    ]),
    ("6. Video Size/Format Issues (Reels Only)", [
        "Video > 100 MB (too large)",
        "Not MP4 format",
        "Corrupted video file",
        "Unsupported codec",
    ]),
    ("7. Media URL Blocked by SSRF Protection", [
        "URL points to private IP (10.*, 192.168.*, 127.*)",
        "URL uses non-http scheme (ftp://, file://)",
        "Hostname resolves to localhost or reserved address",
    ]),
    ("8. Gemini Rate Limiting (429 Error)", [
        "Too many requests too quickly",
        "Built-in 35s backoff + retry handles single 429",
        "But consecutive rate limits will fail",
    ]),
    ("9. Timeout During API Call", [
        "Image analysis timeout: > 30 seconds",
        "Video upload/processing timeout: > 40 seconds",
        "Slow network + large media = timeout",
    ]),
    ("10. Required Response Fields Missing", [
        "Gemini omits: objects, scene_description, visual_style, detected_text, hook_strength_score",
        "Visual quality scores missing: composition, lighting, subject_clarity, aesthetic_quality",
        "Field validation rejects incomplete response",
    ]),
]

for title, details in root_causes:
    print(f"\n{title}")
    for detail in details:
        print(f"    • {detail}")

# ============================================================================
# DEBUGGING STEPS
# ============================================================================

print("\n" + "=" * 100)
print("DEBUGGING STEPS")
print("=" * 100)

print("\n[Step 1] Check API Key")
print("    cd backend")
print("    grep GEMINI_API_KEY .env")
print("    # Should output: GEMINI_API_KEY=AIza...")

print("\n[Step 2] Check Backend Logs")
print("    # Look for lines with [Vision] in logs")
print("    grep -i '\\[Vision\\]\\|vision.*error' logs/*.log")
print("    # Or check application stderr during run")

print("\n[Step 3] Test with Valid Public URL")
print("    # Use this URL for testing (publicly accessible)")
print("    https://cdn.shopify.com/s/files/1/0387/4512/8255/products/d5a3de_4_480x480.jpg")

print("\n[Step 4] Check Gemini Quota")
print("    # Visit and verify:")
print("    https://aistudio.google.com/app/apikey")
print("    # Look for:")
print("    • API key listed and enabled")
print("    • No billing restrictions")
print("    • Usage statistics (if available)")

print("\n[Step 5] Test Gemini API Directly (if SDK installed)")
print("    import google.generativeai as genai")
print("    genai.configure(api_key='YOUR_KEY')")
print("    model = genai.GenerativeModel('gemini-2.0-flash')")
print("    response = model.generate_content('Hello')")
print("    print(response.text)")

print("\n[Step 6] Check Network Connectivity")
print("    # From your server, verify can reach Google")
print("    curl -I https://generativelanguage.googleapis.com")
print("    # Should return 404 (Not Found) not connection refused")

print("\n" + "=" * 100)
