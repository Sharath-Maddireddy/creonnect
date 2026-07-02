"""
Template-based reel/script generator.

Generates short scripts based on creator profile, niche, and recent content context.
"""

from __future__ import annotations

import random
import re
from typing import Any


HOOK_TEMPLATES = {
    "fitness": [
        "Stop scrolling if you want to {goal}",
        "This one exercise changed everything for me",
        "The {duration} workout that actually works",
        "Most people get {topic} completely wrong",
        "Here's what no one tells you about {topic}",
    ],
    "lifestyle": [
        "Day {number} of doing this and I can't believe the results",
        "The habit that changed my life",
        "POV: You finally figured out {topic}",
        "This is your sign to {action}",
        "Things that just make sense when you're {age}",
    ],
    "food": [
        "The easiest {dish} you'll ever make",
        "I can't stop making this {dish}",
        "Restaurant quality {dish} at home",
        "This took me {duration} and tastes incredible",
        "Stop buying {item} when you can make it like this",
    ],
    "tech": [
        "{product} is a game changer - here's why",
        "The feature no one knows about",
        "Stop doing {task} the hard way",
        "I tested {product} for {duration} - honest review",
        "The setup that boosted my productivity",
    ],
    "fashion": [
        "The outfit formula that always works",
        "How to style {item} {number} ways",
        "Outfit check for {occasion}",
        "The piece everyone needs in their closet",
        "Rating my {season} wardrobe essentials",
    ],
    "general": [
        "Here's something you need to know",
        "I wish I knew this earlier",
        "The thing that changed everything",
        "Most people overlook this",
        "This simple trick works every time",
    ],
}

BODY_TEMPLATES = {
    "fitness": [
        "Focus on form over speed. Start with {reps} reps and build up gradually. The key is consistency.",
        "Combine this with proper recovery and you'll see results in {weeks} weeks.",
        "Most people skip this step, but it's the foundation of real progress.",
    ],
    "lifestyle": [
        "It's not about perfection, it's about progress. Small changes compound over time.",
        "I started doing this {duration} ago and haven't looked back since.",
        "The secret is making it part of your routine, not an extra task.",
    ],
    "food": [
        "The secret ingredient is {ingredient}. It adds that restaurant flavor everyone loves.",
        "Let it rest for {duration} - this step makes all the difference.",
        "The key is high heat and not overcrowding the pan.",
    ],
    "tech": [
        "This feature is hidden in settings, but once you enable it, everything changes.",
        "The integration with {service} saves me hours every week.",
        "Most people skip the initial setup, but it's worth the {duration} investment.",
    ],
    "fashion": [
        "The trick is layering and choosing the right proportions for your body type.",
        "Invest in quality basics and you can remix them endlessly.",
        "Color matching is everything - stick to {number} colors max per outfit.",
    ],
    "general": [
        "Once you understand why this works, you'll never go back to the old way.",
        "The principle is simple but most people overthink it.",
        "Start small and scale up once you see it working.",
    ],
}

CTA_TEMPLATES = {
    "fitness": [
        "Save this for your next workout!",
        "Drop a comment if you're trying this today",
        "Follow for more fitness tips that actually work",
        "Comment 'ROUTINE' and I'll send you the full workout",
    ],
    "lifestyle": [
        "Which of these resonated with you? Tell me below",
        "Save this for when you need a reminder",
        "Share with someone who needs to see this",
        "Follow for more real life tips",
    ],
    "food": [
        "Save this recipe for later!",
        "Would you try this? Comment below",
        "Follow for more easy recipes",
        "Tag someone who needs to make this",
    ],
    "tech": [
        "Follow for more tech tips",
        "Save this for your next setup",
        "Comment what product you want reviewed next",
        "Share this with someone who needs to know",
    ],
    "fashion": [
        "Save for outfit inspo!",
        "Which look is your favorite? Comment below",
        "Follow for more style tips",
        "Tag your fashion bestie",
    ],
    "general": [
        "Save this for later!",
        "Follow for more tips like this",
        "Share with someone who needs to see this",
        "Comment your thoughts below",
    ],
}


def _get_dominant_niche(niche_scores: dict[str, Any]) -> str:
    if not niche_scores:
        return "general"
    primary = niche_scores.get("primary_niche", "general")
    if isinstance(primary, str) and primary.strip():
        return primary.lower().strip()
    return "general"


def _select_template(templates: list[str]) -> str:
    return random.choice(templates) if templates else ""


def _fill_template(template: str, context: dict[str, Any]) -> str:
    placeholders = {
        "goal": context.get("goal", "transform your routine"),
        "duration": context.get("duration", "5 minutes"),
        "topic": context.get("topic", "this"),
        "number": str(random.randint(3, 10)),
        "action": context.get("action", "start"),
        "age": context.get("age", "in your 20s"),
        "dish": context.get("dish", "meal"),
        "item": context.get("item", "this"),
        "product": context.get("product", "this tool"),
        "task": context.get("task", "this task"),
        "occasion": context.get("occasion", "everyday"),
        "season": context.get("season", "fall"),
        "reps": str(random.randint(8, 15)),
        "weeks": str(random.randint(2, 6)),
        "ingredient": context.get("ingredient", "patience"),
        "service": context.get("service", "other apps"),
    }

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = placeholders.get(key, context.get(key, "this"))
        return str(value)

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", _replace, template)


def generate_reel_script(
    creator_profile: dict[str, Any],
    niche_scores: dict[str, Any],
    top_post: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a reel script based on creator context."""
    niche = _get_dominant_niche(niche_scores)

    context: dict[str, Any] = {}
    if top_post:
        caption = str(top_post.get("caption") or "")
        normalized_caption = caption.lower()
        if "workout" in normalized_caption or "gym" in normalized_caption:
            context["goal"] = "build strength"
            context["topic"] = "training"
        elif "recipe" in normalized_caption or "cook" in normalized_caption:
            context["dish"] = "this recipe"
            context["topic"] = "cooking"
        elif "style" in normalized_caption or "outfit" in normalized_caption:
            context["item"] = "this piece"
            context["topic"] = "styling"

    hooks = HOOK_TEMPLATES.get(niche, HOOK_TEMPLATES["general"])
    bodies = BODY_TEMPLATES.get(niche, BODY_TEMPLATES["general"])
    ctas = CTA_TEMPLATES.get(niche, CTA_TEMPLATES["general"])

    hook = _fill_template(_select_template(hooks), context)
    body = _fill_template(_select_template(bodies), context)
    cta = _select_template(ctas)

    return {
        "hook": hook,
        "body": body,
        "cta": cta,
        "niche": niche,
        "tone": f"{niche} creator style",
    }
