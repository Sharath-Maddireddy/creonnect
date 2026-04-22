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

Return ONLY valid TOON format (Token-Oriented Object Notation, YAML-like indentation, no braces, no quotes). Do not include markdown formatting or extra text.

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

OUTPUT EXAMPLE (STRICT TOON ONLY):
objects
  - person
  - dumbbell
dominant_focus athlete
visual_style Minimalist Portrait
scene_type Indoor gym
visual_quality_score
  composition 8.5
  lighting 7.5
  subject_clarity 9.0
  aesthetic_quality 8.0
technical_flaws
  - Slight background clutter
detected_text null
"""

S2_CAPTION_EVALUATION_PROMPT = """
You are an expert Social Media Copywriter and Engagement Strategist.
Analyze the following Instagram caption strictly through the lens of psychological engagement and structural copywriting best practices.

Return ONLY valid TOON format (Token-Oriented Object Notation, YAML-like indentation, no braces, no quotes). Do not include markdown formatting or extra text.

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

OUTPUT EXAMPLE (STRICT TOON ONLY):
hook_score_0_100 92
length_score_0_100 85
hashtag_score_0_100 78
cta_score_0_100 88
s2_raw_0_100 86
predicted_audience_sentiment Curious
retention_probability_0_100 73
technical_flaws
  - CTA could be more specific
  - Hook takes too long to get to the payoff
improved_hook_suggestion Lead with the transformation in the first line

CAPTION TO ANALYZE:
"{caption_text}"
"""


S3_CLARITY_EVALUATION_PROMPT = """
You are an expert Social Media Creative Strategist and Content Clarity evaluator.
Analyze the Instagram post using the caption and the summarized S1 vision payload.

Return ONLY valid TOON format (Token-Oriented Object Notation, YAML-like indentation, no braces, no quotes). Do not include markdown formatting or extra text.

Score each field as an integer from 0 to 10:

1. MESSAGE_SINGULARITY_0_10
   - Measures whether the post communicates one clear primary idea instead of multiple competing messages.
   - High score when the content has a single dominant subject or takeaway.
   - Low score when the visual is cluttered, text-heavy, or conceptually scattered.

2. CONTEXT_CLARITY_0_10
   - Measures how easy it is to understand what is happening and why it matters.
   - Consider caption clarity, scene context, and whether the viewer can quickly orient themselves.

3. CAPTION_ALIGNMENT_0_10
   - Measures how well the caption reinforces the visual message instead of drifting away from it.
   - High score when caption and visual clearly support the same message.

4. VISUAL_MESSAGE_SUPPORT_0_10
   - Measures whether the visual elements strengthen the intended message.
   - High score when the image/frame itself carries or supports the idea clearly.

5. COGNITIVE_LOAD_0_10
   - Measures ease of comprehension.
   - High score means low overload and easy comprehension.
   - Low score means too much clutter, too much text, too many competing objects, or a confusing caption.

Also output:
- technical_flaws: array of short strings describing the main clarity problems or diagnostics

OUTPUT EXAMPLE (STRICT TOON ONLY):
message_singularity_0_10 8
context_clarity_0_10 7
caption_alignment_0_10 8
visual_message_support_0_10 7
cognitive_load_0_10 6
technical_flaws
  - Slight visual clutter
  - Caption could clarify the payoff sooner

INPUT DATA:
Caption:
{caption_text}

Vision Signals JSON:
{vision_signals}
"""


REEL_VISION_EVALUATION_PROMPT = """
You are an expert short-form video creative strategist analyzing an Instagram Reel.
Watch the full video before scoring. Evaluate what is actually visible and audible in the clip.
Do not invent details that are not present.

Return ONLY valid TOON format (Token-Oriented Object Notation, YAML-like indentation, no braces, no quotes). Use 2-space indentation for nesting and '-' for list items. Do not include markdown, commentary, or extra keys.

Return exactly these keys:
- hook_frame_score (float 0-1): how visually arresting the first 3 seconds are
- hook_text_overlay (string or null): any text shown in the first 3 seconds that acts as a hook
- pacing_label (fast|medium|slow)
- cut_count_estimate (integer): estimated total scene cuts
- dominant_emotion (string): primary emotional tone such as excitement, curiosity, calm, humour
- retention_signal (float 0-1): estimated likelihood viewers keep watching
- audio_visual_sync (float 0-1): how well visuals, cuts, gestures, and motion match the audio beat/mood/message
- objects (array of strings): main visible subjects or objects
- scene_description (string): concise summary of what happens in the reel
- detected_text (string or null): notable on-screen text
- visual_style (string): style such as talking-head, b-roll, cinematic, tutorial, animation, vlog
- hook_strength_score (float 0-1): overall hook quality across visual motion, framing, text, face presence, and opening energy
- cringe_score (integer 0-100): 0 polished, 100 extreme cringe
- cringe_signals (array of strings, max 3)
- cringe_fixes (array of strings, max 3)
- production_level (low|medium|high)
- adult_content_detected (boolean)

Scoring rubric for hook_strength_score (0-1):
- 0.90-1.00: elite hook; first 2 seconds contain multiple strong hook signals such as immediate motion, high-contrast framing, clear subject, compelling text or payoff, and the opening feels impossible to ignore. If spoken/audio-led, the audio hook is strong immediately. Face or clear subject is typically visible early.
- 0.75-0.89: strong hook; opening is engaging and clear with noticeable motion, a clear subject, and at least one strong attention device such as text, expression, surprise, or dramatic visual change.
- 0.50-0.74: decent hook; opening is understandable and somewhat engaging, but lacks exceptional urgency, novelty, or stopping power.
- 0.30-0.49: weak hook; opening is slow, generic, poorly framed, visually flat, or does not make the viewer curious quickly.
- 0.10-0.29: very weak hook; slow pacing, low energy, poor lighting, no meaningful text, unclear subject, or the reel takes too long to reveal what it is about.
- 0.00-0.09: failed hook; opening is confusing, static, dark, empty, or likely to cause immediate scroll-away.

Hard constraints for hook_strength_score:
- Do not score above 0.90 unless the opening shows clear early stopping power, not just a nice-looking frame.
- Do not score above 0.80 if the first 2-3 seconds are visually static and offer no strong curiosity trigger.
- Do not score above 0.70 if the main subject is unclear in the opening.
- Slow pacing, dark lighting, no text, and no clear motion should generally land in 0.10-0.30.

Scoring rubric for audio_visual_sync (0-1):
- 0.90-1.00: visuals are tightly synchronized to the audio beat, spoken emphasis, or mood; cuts, gestures, captions, and action feel intentionally timed.
- 0.75-0.89: strong sync; most transitions and visual moments fit the audio well with only minor drift.
- 0.50-0.74: moderate sync; audio and visuals broadly fit, but timing is inconsistent or only loosely coordinated.
- 0.30-0.49: weak sync; visuals often feel disconnected from the audio tone, rhythm, or message.
- 0.10-0.29: poor sync; cuts, pacing, and subject action noticeably clash with the audio.
- 0.00-0.09: no meaningful sync; audio and visuals feel unrelated or actively conflicting.

Hard constraints for audio_visual_sync:
- If there is little or no usable audio, score based on whether the visuals still align with any spoken or rhythmic structure present; otherwise keep the score conservative.
- Do not score above 0.85 unless there are clear timed cuts, gestures, text reveals, or motion beats matching the audio.
- If the audio mood and the visuals feel mismatched, keep the score below 0.50.

Additional guidance:
- Prefer conservative scoring over generous scoring.
- Keep cringe_signals and cringe_fixes specific and actionable.
- If on-screen text is absent, return null for hook_text_overlay or detected_text where appropriate.
- adult_content_detected must be true only when sexual nudity or explicit adult sexual framing is actually present.

OUTPUT EXAMPLE (STRICT TOON ONLY):
hook_frame_score 0.72
hook_text_overlay Stop scrolling
pacing_label fast
cut_count_estimate 11
dominant_emotion curiosity
retention_signal 0.68
audio_visual_sync 0.74
objects
  - creator
  - phone
scene_description Creator points at text callouts while demonstrating a quick workflow
detected_text 3 editing mistakes
visual_style talking-head tutorial
hook_strength_score 0.78
cringe_score 18
cringe_signals
  - Slightly generic thumbnail pose
cringe_fixes
  - Start with the strongest payoff frame
production_level medium
adult_content_detected false
"""


# -----------------------------
# S4 Audience Relevance Prompt
# -----------------------------

S4_AUDIENCE_RELEVANCE_PROMPT = """
You are an expert Social Media Algorithm Demographic Analyst.
Your job is to determine the exact audience overlap between a Creator's core demographic and the specific topic of a single social media post.

Return ONLY valid TOON format (Token-Oriented Object Notation, YAML-like indentation, no braces, no quotes). Do not include markdown formatting or extra text.

Evaluate the relevance on the following strict 0-100 scale to calculate the S4 (Audience Relevance) score:

AFFINITY BAND RUBRIC:
- EXACT (100 points): The post topic perfectly matches the creator's main niche.
- HIGH_OVERLAP (85 points): The topics differ but the audiences heavily overlap.
- ADJACENT (65 points): Loosely related under a broad lifestyle umbrella.
- UNRELATED (15 points): A complete pivot with low audience overlap.
- UNKNOWN (50 points): If either category is missing or blank, return 50.

OUTPUT EXAMPLE (STRICT TOON ONLY):
s4_raw_0_100 85
affinity_band HIGH_OVERLAP
audience_overlap_explanation The post topic is different from the creator niche but strongly appeals to the same audience segment

INPUT DATA:
Creator Dominant Niche: "{creator_category}"
Current Post Topic: "{post_category}"
"""


