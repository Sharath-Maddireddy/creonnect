# -*- coding: utf-8 -*-
"""
Cringe analysis test for Instagram reel DVVu6XMki_J
with full TIME and COST tracking.

Run: python test_reel_with_metrics.py
"""
import sys
import os
import json
import re
import time
import io
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# ── Config ──────────────────────────────────────────────────────────────────
REEL_URL     = "https://www.instagram.com/reel/DVbTkfTE98X/"
GEMINI_API_KEY = "AIzaSyAFQrQLbN2FoCQ4qBIdfJxdR27K97hC2Y8"
MODEL_NAME   = "gemini-2.5-flash"

# Gemini 2.5 Flash pricing (as of 2025)
# Input:  $0.075 per 1M tokens (text), images counted as tokens too
# Output: $0.30  per 1M tokens
PRICE_INPUT_PER_1M  = 0.075   # USD
PRICE_OUTPUT_PER_1M = 0.30    # USD

# ── Timing bookmarks ─────────────────────────────────────────────────────────
t_script_start = time.perf_counter()
wall_start     = datetime.now()
timings        = {}

print("=" * 65)
print(f"  🎬  REEL CRINGE ANALYSIS  —  with TIME & COST TRACKING")
print("=" * 65)
print(f"  Reel URL : {REEL_URL}")
print(f"  Model    : {MODEL_NAME}")
print(f"  Started  : {wall_start.strftime('%Y-%m-%d %H:%M:%S')}")
print()

# ── Step 1: Fetch thumbnail from Instagram page (og:image) ───────────────────
print("📥  [1/4] Loading pre-fetched reel metadata from reel_info.json...")
t0 = time.perf_counter()

thumbnail_url = None
caption_text  = "No caption found"

try:
    with open("reel_info.json", "r", encoding="utf-8") as f:
        info = json.load(f)
    thumbnail_url = info.get("thumbnail_url")
    caption_text  = info.get("caption", "No caption found")
    print(f"     ✅  Loaded thumbnail URL and caption from reel_info.json")
except Exception as e:
    print(f"     ❌  Could not load reel_info.json: {e}")
    sys.exit(1)

timings["page_fetch_s"] = round(time.perf_counter() - t0, 3)
print(f"     ⏱  JSON load: {timings['page_fetch_s']}s")

print(f"\n     Thumbnail: {thumbnail_url[:90]}...")
print(f"     Caption  : {caption_text[:100]}")

# ── Step 2: Download thumbnail bytes ─────────────────────────────────────────
print("\n📥  [2/4] Downloading thumbnail image...")
t0 = time.perf_counter()

image_bytes = None
try:
    req2 = urllib.request.Request(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req2, timeout=20) as resp:
        image_bytes = resp.read()
    print(f"     ✅  Downloaded {len(image_bytes):,} bytes ({len(image_bytes)/1024:.1f} KB)")
except Exception as e:
    print(f"     ⚠️  urllib failed: {e} — trying requests...")
    try:
        import requests
        r = requests.get(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        image_bytes = r.content
        print(f"     ✅  Downloaded {len(image_bytes):,} bytes via requests")
    except Exception as e2:
        print(f"     ❌  Both download methods failed: {e2}")
        sys.exit(1)

timings["image_download_s"] = round(time.perf_counter() - t0, 3)
print(f"     ⏱  Image download: {timings['image_download_s']}s")

# ── Step 3: Gemini Vision API call ───────────────────────────────────────────
print(f"\n🤖  [3/4] Calling Gemini Vision API ({MODEL_NAME})...")

try:
    import google.generativeai as genai
    import PIL.Image
except ImportError:
    print("     ❌  Missing packages. Run: pip install google-generativeai pillow")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)
image = PIL.Image.open(io.BytesIO(image_bytes))

INSTRUCTION = f"""Analyze this Instagram Reel thumbnail image.
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
- Caption: "{caption_text[:300]}"
- Reel short-code: DVVu6XMki_J

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

t0 = time.perf_counter()
try:
    response = model.generate_content([INSTRUCTION, image])
    raw_text  = response.text
except Exception as e:
    print(f"     ❌  Gemini API error: {e}")
    sys.exit(1)

timings["gemini_api_s"] = round(time.perf_counter() - t0, 3)
print(f"     ✅  Response received")
print(f"     ⏱  Gemini API call: {timings['gemini_api_s']}s")

# ── Token / cost accounting ───────────────────────────────────────────────────
usage = getattr(response, "usage_metadata", None)
input_tokens  = getattr(usage, "prompt_token_count",     0) if usage else 0
output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
total_tokens  = getattr(usage, "total_token_count",      0) if usage else (input_tokens + output_tokens)

cost_input  = (input_tokens  / 1_000_000) * PRICE_INPUT_PER_1M
cost_output = (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_1M
cost_total  = cost_input + cost_output

print(f"\n     📊  TOKEN USAGE:")
print(f"         Input  tokens : {input_tokens:,}")
print(f"         Output tokens : {output_tokens:,}")
print(f"         Total  tokens : {total_tokens:,}")
print(f"\n     💰  COST ESTIMATE (gemini-2.5-flash pricing):")
print(f"         Input  cost   : ${cost_input:.6f}  ({input_tokens:,} × $0.075/1M)")
print(f"         Output cost   : ${cost_output:.6f}  ({output_tokens:,} × $0.30/1M)")
print(f"         ─────────────────────────────────────────")
print(f"         TOTAL COST    : ${cost_total:.6f} USD")

# ── Step 4: Parse JSON + apply cringe floor logic ────────────────────────────
print("\n🔍  [4/4] Parsing results...")
cleaned = raw_text.strip()
if cleaned.startswith("```"):
    parts = cleaned.split("```")
    cleaned = parts[1] if len(parts) > 1 else cleaned
    if cleaned.startswith("json"):
        cleaned = cleaned[4:]
cleaned = cleaned.strip()

try:
    result = json.loads(cleaned)
except json.JSONDecodeError:
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
        except Exception:
            print("     ❌  Could not parse JSON from response")
            print("Raw response:", raw_text)
            sys.exit(1)
    else:
        print("     ❌  No JSON found in response")
        print("Raw response:", raw_text)
        sys.exit(1)

# Cringe floor logic
STRONG_SIGNAL_RE = re.compile(
    r"awkward|cringe|forced|overexaggerated|nonsens|confus|chaotic|low production|poor quality",
    re.IGNORECASE,
)
cringe_score   = int(max(0, min(100, round(result.get("cringe_score", 0)))))
cringe_signals = result.get("cringe_signals", [])
signal_text    = " ".join(str(s) for s in cringe_signals).lower()
strong_signal  = bool(STRONG_SIGNAL_RE.search(signal_text))
if len(cringe_signals) >= 3 and strong_signal:
    cringe_score = max(cringe_score, 70)
elif len(cringe_signals) >= 2 and strong_signal:
    cringe_score = max(cringe_score, 60)
result["cringe_score"] = cringe_score

label = "not_cringe" if cringe_score <= 30 else ("uncertain" if cringe_score <= 59 else "cringe")
result["cringe_label"] = label
result["is_cringe"]    = cringe_score >= 45

# ── Final timing ─────────────────────────────────────────────────────────────
t_total = time.perf_counter() - t_script_start
timings["total_wall_s"] = round(t_total, 3)

# ── Results print-out ─────────────────────────────────────────────────────────
label_emoji = {"not_cringe": "✅", "uncertain": "🤔", "cringe": "😬"}.get(label, "❓")

print("\n" + "=" * 65)
print("  📊  VISION ANALYSIS RESULTS")
print("=" * 65)
print(f"  Scene:            {result.get('scene_description', 'N/A')}")
print(f"  Visual Style:     {result.get('visual_style', 'N/A')}")
print(f"  Dominant Focus:   {result.get('dominant_focus', 'N/A')}")
print(f"  Scene Type:       {result.get('scene_type', 'N/A')}")
print(f"  Production:       {result.get('production_level', 'N/A').upper()}")
print(f"  Lighting:         {result.get('lighting_quality', 'N/A')}")
print(f"  Subject Clarity:  {result.get('subject_clarity', 'N/A')}")
print(f"  Aesthetic:        {result.get('aesthetic_quality', 'N/A')}")
print(f"  Hook Strength:    {result.get('hook_strength_score', 0):.2f} / 1.0")
print(f"  Detected Text:    {result.get('detected_text', 'None')}")

print("\n  🤢  CRINGE ANALYSIS")
print("-" * 65)
print(f"  Cringe Score:    {cringe_score}/100  {label_emoji}  [{label.upper()}]")
print(f"  Is Cringe:       {result['is_cringe']}")
print(f"  Cringe Signals:")
for s in cringe_signals:
    print(f"    • {s}")
print(f"  Suggested Fixes:")
for f in result.get("cringe_fixes", []):
    print(f"    → {f}")

print("\n  🔒  CONTENT SAFETY")
print("-" * 65)
print(f"  Adult Content:   {result.get('adult_content_detected', False)}")
print(f"  Confidence:      {result.get('adult_content_confidence', 0)}%")

print("\n" + "=" * 65)
print("  ⏱  PERFORMANCE SUMMARY")
print("=" * 65)
print(f"  Page fetch time  : {timings.get('page_fetch_s', 'N/A')}s")
print(f"  Image download   : {timings.get('image_download_s', 'N/A')}s")
print(f"  Gemini API call  : {timings.get('gemini_api_s', 'N/A')}s")
print(f"  ─────────────────────────────────────────")
print(f"  TOTAL WALL TIME  : {timings['total_wall_s']}s")

print("\n" + "=" * 65)
print("  💰  COST SUMMARY")
print("=" * 65)
print(f"  Model            : {MODEL_NAME}")
print(f"  Input tokens     : {input_tokens:,}")
print(f"  Output tokens    : {output_tokens:,}")
print(f"  Total tokens     : {total_tokens:,}")
print(f"  Input cost       : ${cost_input:.6f}")
print(f"  Output cost      : ${cost_output:.6f}")
print(f"  ─────────────────────────────────────────")
print(f"  TOTAL COST       : ${cost_total:.6f} USD")
if cost_total > 0:
    print(f"  Calls per $1     : ~{int(1 / cost_total):,}")
print("=" * 65)

# ── Save results ──────────────────────────────────────────────────────────────
output = {
    "reel_url"       : REEL_URL,
    "model"          : MODEL_NAME,
    "run_at"         : wall_start.isoformat(),
    "thumbnail_url"  : thumbnail_url,
    "caption"        : caption_text,
    "analysis"       : result,
    "timings_seconds": timings,
    "tokens"         : {
        "input": input_tokens, "output": output_tokens, "total": total_tokens
    },
    "cost_usd"       : {
        "input": round(cost_input, 8),
        "output": round(cost_output, 8),
        "total": round(cost_total, 8),
    },
}

out_path = "reel_DVbTkfTE98X_result.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\n  💾  Full results saved → {out_path}")
print()
