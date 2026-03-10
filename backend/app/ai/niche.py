import re
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput


# -----------------------------
# Niche Taxonomy (V1)
# -----------------------------

NICHES = [
    "fitness",
    "nutrition",
    "fashion",
    "beauty",
    "skincare",
    "technology",
    "finance",
    "crypto",
    "education",
    "career",
    "entrepreneurship",
    "marketing",
    "travel",
    "food",
    "lifestyle",
    "parenting",
    "gaming",
    "music",
    "photography",
    "videography"
]

_SECONDARY_EVIDENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fitness": ("fitness", "workout", "gym", "training", "exercise", "leg day", "ab routine"),
    "nutrition": ("nutrition", "meal prep", "protein", "diet", "healthy meal", "shake recipe", "macro"),
    "fashion": ("fashion", "style", "outfit", "wardrobe", "ootd", "capsule", "thrift"),
    "beauty": ("beauty", "makeup", "cosmetic", "glam", "grwm", "get ready with me"),
    "skincare": ("skincare", "skin care", "serum", "moisturizer", "spf", "acne"),
    "technology": ("technology", "tech", "gadget", "app", "software", "coding", "iphone", "android"),
    "finance": ("finance", "investing", "budget", "savings", "money", "stocks"),
    "crypto": ("crypto", "bitcoin", "ethereum", "web3", "blockchain", "token"),
    "education": ("education", "tutorial", "lesson", "learn", "study", "teaching"),
    "career": ("career", "job", "office", "corporate", "interview", "resume", "hiring", "promotion"),
    "entrepreneurship": ("entrepreneur", "startup", "founder", "business", "solopreneur"),
    "marketing": ("marketing", "brand strategy", "seo", "content strategy", "funnel"),
    "travel": ("travel", "trip", "itinerary", "destination", "flight", "hotel"),
    "food": ("food", "recipe", "cook", "cooking", "meal", "dessert", "chef"),
    "lifestyle": ("lifestyle", "daily routine", "morning routine", "self care", "wellness", "mindset", "gratitude"),
    "parenting": ("parenting", "mom life", "dad life", "kids", "toddler", "newborn"),
    "gaming": ("gaming", "gameplay", "stream", "esports", "fps", "rpg"),
    "music": ("music", "song", "singing", "beat", "producer", "guitar"),
    "photography": ("photography", "camera", "photo", "lens", "lighting"),
    "videography": ("videography", "video editing", "cinematic", "b-roll", "filmmaking"),
}


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _keyword_hit_count(text: str, keywords: tuple[str, ...]) -> int:
    if not text:
        return 0
    hits = 0
    for keyword in keywords:
        escaped = re.escape(keyword.strip().lower()).replace(r"\ ", r"\s+")
        pattern = re.compile(rf"\b{escaped}\b")
        if pattern.search(text):
            hits += 1
    return hits


def _has_secondary_niche_evidence(
    *,
    secondary_niche: str,
    primary_niche: str,
    combined_text: str,
) -> bool:
    if not secondary_niche or secondary_niche == primary_niche:
        return False
    normalized = _normalize_text(combined_text)
    keywords = _SECONDARY_EVIDENCE_KEYWORDS.get(secondary_niche, (secondary_niche,))
    return _keyword_hit_count(normalized, keywords) > 0


# -----------------------------
# Load model once
# -----------------------------

_model = SentenceTransformer("all-MiniLM-L6-v2")


# -----------------------------
# Public API
# -----------------------------

def detect_creator_niche(
    profile: CreatorProfileAIInput,
    posts: List[CreatorPostAIInput]
) -> dict:
    """
    Detect primary and secondary niche using bio + post captions.
    Accepts posts as List[CreatorPostAIInput] and extracts captions internally.
    """

    # Extract captions from posts
    recent_captions = [p.caption_text for p in posts if p.caption_text]

    combined_text = (profile.bio_text or "") + " " + " ".join(recent_captions)

    if not combined_text.strip():
        return {
            "primary_niche": None,
            "secondary_niche": None,
            "confidence": 0.0
        }

    text_embedding = _model.encode(
        combined_text,
        normalize_embeddings=True
    )

    niche_embeddings = _model.encode(
        NICHES,
        normalize_embeddings=True
    )

    similarities = np.dot(niche_embeddings, text_embedding)

    ranked_indices = similarities.argsort()[::-1]

    primary_idx = ranked_indices[0]
    primary_score = float(similarities[primary_idx])
    secondary_idx: int | None = None
    secondary_fallback_score = float(similarities[ranked_indices[1]]) if len(ranked_indices) > 1 else 0.0
    for candidate_idx in ranked_indices[1:]:
        candidate_niche = NICHES[candidate_idx]
        candidate_score = float(similarities[candidate_idx])
        # Keep secondary only when semantically plausible and explicitly evidenced in text.
        if (primary_score - candidate_score) > 0.25:
            continue
        if _has_secondary_niche_evidence(
            secondary_niche=candidate_niche,
            primary_niche=NICHES[primary_idx],
            combined_text=combined_text,
        ):
            secondary_idx = int(candidate_idx)
            break

    secondary_score = float(similarities[secondary_idx]) if secondary_idx is not None else secondary_fallback_score
    primary_non_negative = max(primary_score, 0.0)
    secondary_non_negative = max(secondary_score, 0.0)
    confidence = round(
        primary_non_negative / (primary_non_negative + secondary_non_negative + 1e-6),
        2,
    )
    confidence = max(0.0, min(1.0, confidence))

    return {
        "primary_niche": NICHES[primary_idx],
        "secondary_niche": NICHES[secondary_idx] if secondary_idx is not None else None,
        "confidence": confidence
    }


