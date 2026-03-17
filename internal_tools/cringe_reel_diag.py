"""
Quick cringe analysis test for an Instagram reel thumbnail via Gemini.
Run: python internal_tools/cringe_reel_diag.py
"""
import os
import json
import sys

# Set API key from backend .env or pass directly
GEMINI_API_KEY = "AIzaSyAFQrQLbN2FoCQ4qBIdfJxdR27K97hC2Y8"

THUMBNAIL_URL = (
    "https://instagram.fhyd3-1.fna.fbcdn.net/v/t51.71878-15/"
    "622137790_2187922261949173_1738529400016264863_n.jpg"
    "?stp=dst-jpg_e15_tt6&_nc_cat=110&ig_cache_key=MzgxNzE4NzEyMTgyNDkzNzY2MQ%3D%3D.3-ccb7-5"
    "&ccb=7-5&_nc_sid=58cdad&_nc_ohc=dOiLpRQkS2oQ7kNvwFuIOR3"
    "&_nc_oc=Admxfo5VAvZO0FMP5CBuWYwDhmPI5IYi-95Nkq2XqEXp8eFCMKRsnzfibb_HP7gTnJQ"
    "&_nc_ad=z-m&_nc_cid=0&_nc_zt=23&_nc_ht=instagram.fhyd3-1.fna"
    "&_nc_gid=iLwyckOCOejSotKU-1puvg&_nc_ss=8"
    "&oh=00_Afx2pdqFAaM4PmBbHrBqckEilFnWaRano1mMh1RVI3X-dg&oe=69B4D09D"
)

CAPTION = "LEG AISHI K DURBIN SE BHI NAHI DEKH SAKTE 🤩💪 . start your online training and transform yourself."
HASHTAGS = "#onlineträning #fitness #natural #probodybuilder #onlinetrainingcoach"

INSTRUCTION = f"""Analyze this Instagram Reel thumbnail image for a fitness/bodybuilding creator.
Return ONLY valid JSON with exactly these fields (no markdown, no extra keys):

{{
  "objects": ["<list of objects detected>"],
  "scene_description": "<describe the scene>",
  "detected_text": "<any visible text in image, or null>",
  "visual_style": "<visual style descriptor>",
  "hook_strength_score": <float 0.0-1.0>,
  "dominant_focus": "<main subject>",
  "scene_type": "<scene category>",
  "lighting_quality": "<low|medium|high>",
  "subject_clarity": "<low|medium|high>",
  "aesthetic_quality": "<low|medium|high>",
  "cringe_score": <int 0-100>,
  "cringe_signals": ["<up to 3 specific cringe signals>"],
  "cringe_fixes": ["<up to 3 suggested fixes>"],
  "production_level": "<low|medium|high>",
  "adult_content_detected": <true|false>,
  "adult_content_confidence": <int 0-100>
}}

Context:
- Platform: Instagram Reel
- Caption: "{CAPTION}"
- Hashtags: {HASHTAGS}
- Engagement: 5800 likes, 877 comments

Cringe scoring rubric:
- 0-20: polished and natural
- 21-40: minor awkwardness
- 41-60: noticeable awkwardness OR weak concept
- 61-80: strong cringe (forced, confusing, low coherence)
- 81-100: extreme cringe
Floor rules: confusing or nonsensical concept → cringe_score >= 65;
repeated awkward posing/expression → cringe_score >= 55; both → cringe_score >= 75.
hook_strength_score: 0=no hook, 1=very strong hook.
"""

def main():
    try:
        import google.generativeai as genai
    except ImportError:
        print("ERROR: google-generativeai not installed. Run: pip install google-generativeai")
        sys.exit(1)

    print("=" * 60)
    print("🎬 CRINGE ANALYSIS — @indian_hulk_badal_fitness1 Reel")
    print("=" * 60)
    print(f"Thumbnail: {THUMBNAIL_URL[:80]}...")
    print(f"Caption: {CAPTION[:80]}")
    print()

    print("📥 Downloading reel thumbnail...")
    try:
        import urllib.request
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(THUMBNAIL_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_bytes = resp.read()
        print(f"   Downloaded {len(image_bytes):,} bytes")
    except Exception as e:
        print(f"❌ Failed to download thumbnail: {e}")
        sys.exit(1)

    print("🤖 Calling Gemini Vision API (gemini-2.5-flash)...")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    import PIL.Image
    import io
    image = PIL.Image.open(io.BytesIO(image_bytes))

    try:
        response = model.generate_content([INSTRUCTION, image])
        raw_text = response.text
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        sys.exit(1)

    # Parse JSON
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip().rstrip("```").strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print("Raw response:", raw_text)
        sys.exit(1)

    # Apply cringe floor logic (from cringe_analysis.py)
    import re
    STRONG_SIGNAL_RE = re.compile(
        r"awkward|cringe|forced|overexaggerated|nonsens|confus|chaotic|low production|poor quality",
        re.IGNORECASE,
    )
    cringe_score = int(max(0, min(100, round(result.get("cringe_score", 0)))))
    cringe_signals = result.get("cringe_signals", [])
    signal_text = " ".join(cringe_signals).lower()
    strong_signal = bool(STRONG_SIGNAL_RE.search(signal_text))
    if len(cringe_signals) >= 3 and strong_signal:
        cringe_score = max(cringe_score, 70)
    elif len(cringe_signals) >= 2 and strong_signal:
        cringe_score = max(cringe_score, 60)
    result["cringe_score"] = cringe_score

    # Derive cringe label
    if cringe_score <= 30:
        label = "not_cringe"
    elif cringe_score <= 59:
        label = "uncertain"
    else:
        label = "cringe"
    result["cringe_label"] = label
    result["is_cringe"] = cringe_score >= 45

    # Pretty print results
    print("\n📊 VISION ANALYSIS RESULTS")
    print("-" * 60)
    print(f"  Scene:           {result.get('scene_description', 'N/A')}")
    print(f"  Visual Style:    {result.get('visual_style', 'N/A')}")
    print(f"  Dominant Focus:  {result.get('dominant_focus', 'N/A')}")
    print(f"  Production:      {result.get('production_level', 'N/A').upper()}")
    print(f"  Lighting:        {result.get('lighting_quality', 'N/A')}")
    print(f"  Hook Strength:   {result.get('hook_strength_score', 0):.2f} / 1.0")
    print(f"  Detected Text:   {result.get('detected_text', 'None')}")

    print("\n🤢 CRINGE ANALYSIS")
    print("-" * 60)
    score = result["cringe_score"]
    label_emoji = {"not_cringe": "✅", "uncertain": "🤔", "cringe": "😬"}.get(label, "❓")
    print(f"  Cringe Score:   {score}/100  {label_emoji} [{label.upper()}]")
    print(f"  Is Cringe:      {result['is_cringe']}")
    print(f"  Cringe Signals:")
    for s in cringe_signals:
        print(f"    • {s}")
    print(f"  Suggested Fixes:")
    for f in result.get("cringe_fixes", []):
        print(f"    → {f}")

    print("\n🔒 CONTENT SAFETY")
    print("-" * 60)
    print(f"  Adult Content:  {result.get('adult_content_detected', False)}")
    print(f"  Confidence:     {result.get('adult_content_confidence', 0)}%")

    print("\n📦 FULL JSON OUTPUT")
    print("-" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
