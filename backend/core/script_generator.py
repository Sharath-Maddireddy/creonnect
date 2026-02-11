"""
AI Reel/Script Generator

Generates reel scripts based on creator profile, niche, and top-performing content.
"""

import random
from typing import Dict, List


# Niche-specific templates
HOOK_TEMPLATES = {
    "fitness": [
        "Stop scrolling if you want to {goal}",
        "This one exercise changed everything for me",
        "The {duration} workout that actually works",
        "Most people get {topic} completely wrong",
        "Here's what no one tells you about {topic}"
    ],
    "lifestyle": [
        "Day {number} of doing this and I can't believe the results",
        "The habit that changed my life",
        "POV: You finally figured out {topic}",
        "This is your sign to {action}",
        "Things that just make sense when you're {age}"
    ],
    "food": [
        "The easiest {dish} you'll ever make",
        "I can't stop making this {dish}",
        "Restaurant quality {dish} at home",
        "This took me {duration} and tastes incredible",
        "Stop buying {item} when you can make it like this"
    ],
    "tech": [
        "{product} is a game changer - here's why",
        "The feature no one knows about",
        "Stop doing {task} the hard way",
        "I tested {product} for {duration} - honest review",
        "The setup that boosted my productivity"
    ],
    "fashion": [
        "The outfit formula that always works",
        "How to style {item} {number} ways",
        "Outfit check for {occasion}",
        "The piece everyone needs in their closet",
        "Rating my {season} wardrobe essentials"
    ],
    "general": [
        "Here's something you need to know",
        "I wish I knew this earlier",
        "The thing that changed everything",
        "Most people overlook this",
        "This simple trick works every time"
    ]
}

BODY_TEMPLATES = {
    "fitness": [
        "Focus on form over speed. Start with {reps} reps and build up gradually. The key is consistency.",
        "Combine this with proper recovery and you'll see results in {weeks} weeks.",
        "Most people skip this step, but it's the foundation of real progress."
    ],
    "lifestyle": [
        "It's not about perfection, it's about progress. Small changes compound over time.",
        "I started doing this {duration} ago and haven't looked back since.",
        "The secret is making it part of your routine, not an extra task."
    ],
    "food": [
        "The secret ingredient is {ingredient}. It adds that restaurant flavor everyone loves.",
        "Let it rest for {duration} - this step makes all the difference.",
        "The key is high heat and not overcrowding the pan."
    ],
    "tech": [
        "This feature is hidden in settings, but once you enable it, everything changes.",
        "The integration with {service} saves me hours every week.",
        "Most people skip the initial setup, but it's worth the {duration} investment."
    ],
    "fashion": [
        "The trick is layering and choosing the right proportions for your body type.",
        "Invest in quality basics and you can remix them endlessly.",
        "Color matching is everything - stick to {number} colors max per outfit."
    ],
    "general": [
        "Once you understand why this works, you'll never go back to the old way.",
        "The principle is simple but most people overthink it.",
        "Start small and scale up once you see it working."
    ]
}

CTA_TEMPLATES = {
    "fitness": [
        "Save this for your next workout!",
        "Drop a 💪 if you're trying this today",
        "Follow for more fitness tips that actually work",
        "Comment 'ROUTINE' and I'll send you the full workout"
    ],
    "lifestyle": [
        "Which of these resonated with you? Tell me below",
        "Save this for when you need a reminder",
        "Share with someone who needs to see this",
        "Follow for more real life tips"
    ],
    "food": [
        "Save this recipe for later!",
        "Would you try this? Comment below",
        "Follow for more easy recipes",
        "Tag someone who needs to make this"
    ],
    "tech": [
        "Follow for more tech tips",
        "Save this for your next setup",
        "Comment what product you want reviewed next",
        "Share this with someone who needs to know"
    ],
    "fashion": [
        "Save for outfit inspo!",
        "Which look is your favorite? Comment below",
        "Follow for more style tips",
        "Tag your fashion bestie"
    ],
    "general": [
        "Save this for later!",
        "Follow for more tips like this",
        "Share with someone who needs to see this",
        "Comment your thoughts below"
    ]
}


def _get_dominant_niche(niche_scores: dict) -> str:
    """Extract dominant niche from niche scores."""
    if not niche_scores:
        return "general"
    
    primary = niche_scores.get("primary_niche", "general")
    if primary:
        return primary.lower()
    
    return "general"


def _select_template(templates: List[str]) -> str:
    """Randomly select a template from list."""
    return random.choice(templates) if templates else ""


def _fill_template(template: str, context: dict) -> str:
    """Fill template placeholders with context values."""
    # Common placeholder values
    placeholders = {
        "goal": context.get("goal", "transform your routine"),
        "duration": context.get("duration", "5 minutes"),
        "topic": context.get("topic", "this"),
        "number": str(random.randint(3, 10)),
        "action": context.get("action", "start"),
        "age": "in your 20s",
        "dish": context.get("dish", "meal"),
        "item": context.get("item", "this"),
        "product": context.get("product", "this tool"),
        "task": context.get("task", "this task"),
        "occasion": context.get("occasion", "everyday"),
        "season": context.get("season", "fall"),
        "reps": str(random.randint(8, 15)),
        "weeks": str(random.randint(2, 6)),
        "ingredient": context.get("ingredient", "patience"),
        "service": context.get("service", "other apps")
    }
    
    result = template
    for key, value in placeholders.items():
        result = result.replace(f"{{{key}}}", value)
    
    return result


def generate_reel_script(
    creator_profile: dict,
    niche_scores: dict,
    top_post: dict = None
) -> dict:
    """
    Generate a reel script based on creator context.
    
    Args:
        creator_profile: Dict with username, followers, bio, etc.
        niche_scores: Dict with primary_niche, secondary_niches, confidence
        top_post: Dict with caption, likes, comments, views from best post
        
    Returns:
        Script dict with hook, body, cta
    """
    # Get dominant niche
    niche = _get_dominant_niche(niche_scores)
    
    # Build context from top post
    context = {}
    if top_post:
        caption = top_post.get("caption", "") or ""
        # Extract keywords from caption for context
        if "workout" in caption.lower() or "gym" in caption.lower():
            context["goal"] = "build strength"
            context["topic"] = "training"
        elif "recipe" in caption.lower() or "cook" in caption.lower():
            context["dish"] = "this recipe"
            context["topic"] = "cooking"
        elif "style" in caption.lower() or "outfit" in caption.lower():
            context["item"] = "this piece"
            context["topic"] = "styling"
    
    # Get templates for niche
    hooks = HOOK_TEMPLATES.get(niche, HOOK_TEMPLATES["general"])
    bodies = BODY_TEMPLATES.get(niche, BODY_TEMPLATES["general"])
    ctas = CTA_TEMPLATES.get(niche, CTA_TEMPLATES["general"])
    
    # Generate script
    hook_template = _select_template(hooks)
    body_template = _select_template(bodies)
    cta_template = _select_template(ctas)
    
    hook = _fill_template(hook_template, context)
    body = _fill_template(body_template, context)
    cta = cta_template  # CTAs don't need filling
    
    return {
        "hook": hook,
        "body": body,
        "cta": cta,
        "niche": niche,
        "tone": f"{niche} creator style"
    }


