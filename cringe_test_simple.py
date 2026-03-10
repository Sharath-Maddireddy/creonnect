# -*- coding: utf-8 -*-
import sys
import os
import json
import re
import urllib.request
import io

sys.stdout.reconfigure(encoding='utf-8')

GEMINI_API_KEY = "AIzaSyAFQrQLbN2FoCQ4qBIdfJxdR27K97hC2Y8"
THUMBNAIL_URL = (
    "https://instagram.fhyd3-1.fna.fbcdn.net/v/t51.71878-15/"
    "622137790_2187922261949173_1738529400016264863_n.jpg"
    "?stp=dst-jpg_e15_tt6&_nc_cat=110"
    "&ig_cache_key=MzgxNzE4NzEyMTgyNDkzNzY2MQ%3D%3D.3-ccb7-5"
    "&ccb=7-5&_nc_sid=58cdad"
    "&efg=eyJ2ZW5jb2RlX3RhZyI6InhwaWRzLjY0MHg4MDAuc2RyLkMzIn0%3D"
    "&_nc_ohc=dOiLpRQkS2oQ7kNvwFuIOR3"
    "&_nc_oc=Admxfo5VAvZO0FMP5CBuWYwDhmPI5IYi-95Nkq2XqEXp8eFCMKRsnzfibb_HP7gTnJQ"
    "&_nc_ad=z-m&_nc_cid=0&_nc_zt=23&_nc_ht=instagram.fhyd3-1.fna"
    "&_nc_gid=tUWKtyj-_E1iHbuE9fcB1g&_nc_ss=8"
    "&oh=00_Afx3AZ7Ymy1n9c2ZungiUsfX5KpFQ1TFJqmO1KycH69EHQ&oe=69B508DD"
)

INSTRUCTION = (
    "Analyze this Instagram Reel thumbnail (fitness/gym creator in a gym doing leg exercises). "
    "The caption is: 'LEG AISHI K DURBIN SE BHI NAHI DEKH SAKTE. start your online training.' "
    "Post has 5800 likes and 877 comments.\n\n"
    "Return ONLY valid JSON with exactly these fields (no markdown, no extra text):\n"
    '{"objects":[],"scene_description":"","detected_text":null,"visual_style":"",'
    '"hook_strength_score":0.0,"dominant_focus":"","scene_type":"",'
    '"lighting_quality":"","subject_clarity":"","aesthetic_quality":"",'
    '"cringe_score":0,"cringe_signals":[],"cringe_fixes":[],'
    '"production_level":"low","adult_content_detected":false,"adult_content_confidence":0}\n\n'
    "Cringe rubric: 0-20=polished/natural, 21-40=minor awkwardness, 41-60=noticeable awkwardness, "
    "61-80=strong cringe (forced/confusing), 81-100=extreme cringe.\n"
    "hook_strength_score: 0=no hook, 1.0=very strong hook.\n"
    "production_level must be exactly: low, medium, or high."
)

print("Downloading thumbnail...", flush=True)
headers = {"User-Agent": "Mozilla/5.0"}
req = urllib.request.Request(THUMBNAIL_URL, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        image_bytes = resp.read()
    print(f"Downloaded {len(image_bytes):,} bytes", flush=True)
except Exception as e:
    print(f"Download failed: {e}")
    print("Trying fallback approach with requests...")
    try:
        import requests
        r = requests.get(THUMBNAIL_URL, headers=headers, timeout=15)
        image_bytes = r.content
        print(f"Downloaded {len(image_bytes):,} bytes via requests", flush=True)
    except Exception as e2:
        print(f"Both download methods failed: {e2}")
        sys.exit(1)

import google.generativeai as genai
import PIL.Image

print("Calling Gemini Vision (gemini-2.5-flash)...", flush=True)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")
image = PIL.Image.open(io.BytesIO(image_bytes))

try:
    response = model.generate_content([INSTRUCTION, image])
    raw = response.text
except Exception as e:
    print(f"Gemini error: {e}")
    sys.exit(1)

print("Raw Gemini response:", flush=True)
print(raw, flush=True)

# Parse JSON
cleaned = raw.strip()
if cleaned.startswith("```"):
    parts = cleaned.split("```")
    cleaned = parts[1] if len(parts) > 1 else cleaned
    if cleaned.startswith("json"):
        cleaned = cleaned[4:]
cleaned = cleaned.strip()

try:
    result = json.loads(cleaned)
except json.JSONDecodeError as e:
    print(f"\nJSON parse error: {e}")
    # Try to extract JSON from response
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
        except Exception:
            print("Could not parse JSON from response")
            sys.exit(1)
    else:
        sys.exit(1)

# Apply cringe floor logic
STRONG_SIGNAL_RE = re.compile(
    r"awkward|cringe|forced|overexaggerated|nonsens|confus|chaotic|low production|poor quality",
    re.IGNORECASE,
)
cringe_score = int(max(0, min(100, round(result.get("cringe_score", 0)))))
cringe_signals = result.get("cringe_signals", [])
signal_text = " ".join(str(s) for s in cringe_signals).lower()
strong_signal = bool(STRONG_SIGNAL_RE.search(signal_text))
if len(cringe_signals) >= 3 and strong_signal:
    cringe_score = max(cringe_score, 70)
elif len(cringe_signals) >= 2 and strong_signal:
    cringe_score = max(cringe_score, 60)
result["cringe_score"] = cringe_score

if cringe_score <= 30:
    label = "not_cringe"
elif cringe_score <= 59:
    label = "uncertain"
else:
    label = "cringe"
result["cringe_label"] = label
result["is_cringe"] = cringe_score >= 45

print("\n" + "="*60)
print("CRINGE ANALYSIS RESULTS")
print("="*60)
print(f"  Scene:          {result.get('scene_description', 'N/A')}")
print(f"  Visual Style:   {result.get('visual_style', 'N/A')}")
print(f"  Dominant Focus: {result.get('dominant_focus', 'N/A')}")
print(f"  Production:     {result.get('production_level', 'N/A').upper()}")
print(f"  Lighting:       {result.get('lighting_quality', 'N/A')}")
print(f"  Hook Strength:  {result.get('hook_strength_score', 0):.2f} / 1.0")
print()
print(f"  CRINGE SCORE:   {cringe_score}/100  [{label.upper()}]")
print(f"  Is Cringe:      {result['is_cringe']}")
print(f"  Cringe Signals:")
for s in cringe_signals:
    print(f"    - {s}")
print(f"  Suggested Fixes:")
for f in result.get("cringe_fixes", []):
    print(f"    => {f}")
print()
print(f"  Adult Content:  {result.get('adult_content_detected', False)}")
print(f"  Adult Conf:     {result.get('adult_content_confidence', 0)}%")
print()
print("Full JSON:")
print(json.dumps(result, indent=2, ensure_ascii=True))

# Write clean JSON to file for easy reading
with open("cringe_json_output.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print("JSON written to cringe_json_output.json")
