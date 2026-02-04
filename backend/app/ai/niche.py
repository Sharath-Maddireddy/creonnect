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
    secondary_idx = ranked_indices[1]

    primary_score = float(similarities[primary_idx])
    secondary_score = float(similarities[secondary_idx])

    confidence = round(
        primary_score / (primary_score + secondary_score + 1e-6),
        2
    )

    return {
        "primary_niche": NICHES[primary_idx],
        "secondary_niche": NICHES[secondary_idx],
        "confidence": confidence
    }
