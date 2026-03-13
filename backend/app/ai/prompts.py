from typing import Dict, List


# -----------------------------
# Prompt Builders (LLM-agnostic)
# -----------------------------

def creator_profile_explanation(
    niche_data: Dict,
    growth_data: Dict
) -> str:
    """
    Explain creator profile and growth score in plain English.
    """

    primary = niche_data.get("primary_niche")
    secondary = niche_data.get("secondary_niche")
    confidence = niche_data.get("confidence")

    score = growth_data.get("growth_score")
    breakdown = growth_data.get("breakdown", {})

    return f"""
You are primarily a {primary} creator, with secondary relevance in {secondary}.
This classification has a confidence of {confidence * 100:.0f}%.

Your overall growth score is {score}/100.

Here’s what that means:
- Engagement strength: {breakdown.get("engagement")} / 30
- Posting consistency: {breakdown.get("consistency")} / 20
- Audience size: {breakdown.get("audience")} / 20
- Content performance: {breakdown.get("content")} / 20
- Growth momentum: {breakdown.get("growth_trend")} / 10

This score reflects how attractive your profile is to brands today,
and how strong your growth fundamentals are.
""".strip()


def post_performance_explanation(
    post_insights: Dict
) -> str:
    """
    Explain post-level performance using modern Instagram signals.
    """

    engagement = post_insights.get("engagement_rate_by_views", 0)
    caption_context = post_insights.get("caption_context_present", False)
    cta = post_insights.get("cta_present", False)
    insights = post_insights.get("insights", [])

    advice = []

    if not caption_context:
        advice.append(
            "Consider adding a bit more context in the caption so viewers immediately understand the post."
        )

    if not cta:
        advice.append(
            "You could experiment with a light call-to-action (question, save, or comment) to encourage interaction."
        )

    engagement_pct = (
        f"{engagement * 100:.2f}"
        if isinstance(engagement, (int, float))
        else "N/A"
    )

    return f"""
This post achieved an engagement rate of {engagement_pct}%.

Key observations:
- Caption provides context: {"Yes" if caption_context else "No"}
- Call-to-action present: {"Yes" if cta else "No"}

What the data shows:
{chr(10).join(f"- {i}" for i in insights)}

Recommended next actions:
{chr(10).join(f"- {a}" for a in advice) if advice else "- Maintain this format, as it aligns well with your current performance."}
""".strip()


# -----------------------------
# Advanced Post Analysis Prompts
# -----------------------------

S1_VISION_EVALUATION_PROMPT = """
You are an expert Social Media Art Director and Computer Vision analysis engine.
Analyze the provided Instagram media (image/frame) strictly through the lens of technical visual quality and compositional structure. 

Return ONLY valid JSON. Your output must exactly match the schema requested. Do not include markdown formatting or extra text.

You must evaluate the image objectively on the following deterministic rules to calculate the S1 (Visual Quality) sub-scores:

1. **COMPOSITION (0-10):**
   - Does it strictly follow the Rule of Thirds or intentional symmetry? (Yes: +3, No: -2)
   - Is there a clear, immediate focal point (dominant_focus)? (Yes: +4, No: -3)
   - Is the background cluttered or distracted by >4 primary objects? (Yes: -3)
   - Are there awkward crops (e.g., cutting off limbs/faces unintentionally)? (Yes: -3)
   - Score the remaining points (0-3) based on depth-of-field and subject isolation.

2. **LIGHTING_QUALITY (0-10):**
   - Is the subject clearly illuminated with sufficient contrast from the background? (Yes: +4)
   - Are there blown-out highlights (pure white patches losing detail) or completely crushed blacks (losing shadow detail)? (Yes: -3)
   - Does the lighting create intentional depth (e.g., rim lighting, softbox, golden hour) vs. flat overhead/harsh flash lighting? (Intentional: +3, Flat: +1)
   - Is there noticeable color cast or poor white balance? (Yes: -2)
   - Score remaining points based on cinematic/aesthetic lighting execution.

3. **SUBJECT_CLARITY (0-10):**
   - Is the primary subject sharply in focus? (Yes: +5, No: -3)
   - Is there clear separation between the foreground subject and background? (Yes: +3)
   - If the subject is human, are the facial features visible and expressive? (Yes: +2)

4. **AESTHETIC_QUALITY (0-10):**
   - Does the image look professionally color graded or intentionally styled? (Yes: +3)
   - Is the overall color palette harmonious (analogous, complementary, monochrome)? (Yes: +2)
   - Are there disruptive, low-quality text overlays natively burned into the image? (Heavy Text: -3, Very Heavy Text: -5)
   - Score the remaining points on the overall premium "feel" and stopping-power (hook strength) of the visual.

OUTPUT SCHEMA (STRICT JSON ONLY):
{
    "objects": ["array", "of", "detected", "primary", "items"],
    "dominant_focus": "string (the main subject, or null if ambiguous)",
    "visual_style": "string (e.g., 'Minimalist Portrait', 'Gritty Street', 'High-key studio')",
    "scene_type": "string (e.g., 'Indoor gym', 'Outdoor cafe')",
    "visual_quality_score": {
        "composition": 0.0,
        "lighting": 0.0,
        "subject_clarity": 0.0,
        "aesthetic_quality": 0.0
    },
    "technical_flaws": ["array", "of", "strings", "describing", "specific", "composition/lighting errors identified", "max 3"],
    "detected_text": "string (any embedded text read via OCR, or null)"
}
"""

S2_CAPTION_EVALUATION_PROMPT = """
You are an expert Social Media Copywriter and Engagement Strategist.
Analyze the following Instagram caption strictly through the lens of psychological engagement and structural copywriting best practices.

Return ONLY valid JSON matching the exact schema requested. Do not include markdown formatting or extra text.

Evaluate the caption on the following deterministic rules to calculate the S2 (Caption Effectiveness) sub-scores on a 0-100 scale:

1. HOOK_SCORE (0-100):
   - Read ONLY the first sentence/line of the caption (the part visible before "Read more").
   - Is it compelling? Does it trigger curiosity, offer immediate value, or ask a controversial/engaging question?
   - Do NOT just check for keywords. Grade the semantic power of the hook to stop a scrolling user.
   - Examples: Generic "Happy Monday" = 30. Compelling "Here is the exact framework I used to double my revenue:" = 95.

2. LENGTH_SCORE (0-100):
   - Analyze the total character count (excluding hashtags).
   - Micro-blogging or storytelling (250+ chars) that provides high value = 100.
   - Punchy, perfect context (100-249 chars) = 85.
   - Too short to provide context (<50 chars) = 30.
   - Walls of text without proper line breaks/spacing = Max 60.

3. HASHTAG_SCORE (0-100):
   - Evaluate the hashtags applied to the post.
   - 4 to 12 highly relevant, niche-specific hashtags = 100.
   - Spamming 20+ generic hashtags (e.g., #instagood #love) = 40.
   - No hashtags at all = 20.

4. CTA_SCORE (0-100):
   - Is there a clear, frictionless Call-To-Action (CTA)?
   - Strong CTA asking for a specific, easy behavior ("Comment 'GUIDE' below", "Save this for later") = 100.
   - Weak/Generic CTA ("Thoughts?", "Link in bio") = 60.
   - Missing or confusing CTA = 20.

OUTPUT SCHEMA (STRICT JSON ONLY):
{
    "hook_score_0_100": <integer 0-100>,
    "length_score_0_100": <integer 0-100>,
    "hashtag_score_0_100": <integer 0-100>,
    "cta_score_0_100": <integer 0-100>,
    "s2_raw_0_100": <integer 0-100> (Calculate the weighted average: hook*0.30 + length*0.20 + hashtag*0.25 + cta*0.25),
    "technical_flaws": ["array", "of", "strings", "describing", "specific", "weaknesses in the copy", "max 3"],
    "improved_hook_suggestion": "string (Rewrite the first line to be maximally engaging)"
}

CAPTION TO ANALYZE:
"{caption_text}"
"""


# -----------------------------
# S4 Audience Relevance Prompt
# -----------------------------

S4_AUDIENCE_RELEVANCE_PROMPT = """
You are an expert Social Media Algorithm Demographic Analyst.
Your job is to determine the exact audience overlap between a Creator's core demographic and the specific topic of a single social media post.

Return ONLY valid JSON matching the exact schema requested. Do not include markdown formatting or extra text.

Evaluate the relevance on the following strict 0-100 scale to calculate the S4 (Audience Relevance) score:

AFFINITY BAND RUBRIC:
- EXACT (100 points): The post topic perfectly matches the creator's main niche.
- HIGH_OVERLAP (85 points): The topics differ but the audiences heavily overlap.
- ADJACENT (65 points): Loosely related under a broad lifestyle umbrella.
- UNRELATED (15 points): A complete pivot with low audience overlap.
- UNKNOWN (50 points): If either category is missing or blank, return 50.

OUTPUT SCHEMA (STRICT JSON ONLY):
{
    "s4_raw_0_100": <integer 15, 50, 65, 85, or 100>,
    "affinity_band": <string: "EXACT", "HIGH_OVERLAP", "ADJACENT", "UNRELATED", or "UNKNOWN">,
    "audience_overlap_explanation": "string (1-sentence explanation)"
}

INPUT DATA:
Creator Dominant Niche: "{creator_category}"
Current Post Topic: "{post_category}"
"""


