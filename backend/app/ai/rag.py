"""
Simple RAG (Retrieval Augmented Generation) Engine

Uses sentence-transformers for embeddings (already used in niche.py).
Stores vectors in memory for simplicity.

Important: this engine intentionally uses a separate local embedding model and
vector space from the pgvector-backed creator pool. Do not persist these RAG
embeddings into ``creator_vectors`` without a full migration, because the
creator pool stores 1536-d OpenAI embeddings while this engine uses 384-d
sentence-transformer embeddings.
"""

import json
import os
from typing import List
from typing import TYPE_CHECKING
from threading import Lock
from pathlib import Path
import numpy as np

from backend.app.utils.logger import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


# ------------------------------------------------
# Configuration
# ------------------------------------------------

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
CHUNK_SIZE = 400  # Target characters per chunk
CHUNK_OVERLAP = 50  # Overlap between chunks
RAG_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
RAG_EMBEDDING_DIMENSION = 384

# Cache file paths
CACHE_DIR = Path(os.getenv("RAG_CACHE_DIR", ".rag_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
EMBEDDINGS_CACHE = CACHE_DIR / ".rag_embeddings.npy"
CHUNKS_CACHE = CACHE_DIR / ".rag_chunks.json"


# ------------------------------------------------
# Text Chunking
# ------------------------------------------------

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks.
    Tries to split on paragraph/sentence boundaries.
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    paragraphs = text.split("\n\n")

    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph exceeds chunk size, save current and start new
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from end of previous chunk
            current_chunk = current_chunk[-overlap:] + " " + para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


# ------------------------------------------------
# RAG Engine
# ------------------------------------------------

class RAGEngine:
    """
    Simple in-memory RAG engine.
    Loads markdown files, chunks them, embeds, and retrieves.
    """

    def __init__(self):
        self._model: SentenceTransformer | None = None
        self._chunks: List[str] = []
        self._embeddings: np.ndarray = None
        self._loaded = False
        self._model_lock = Lock()

    def _get_model(self) -> "SentenceTransformer":
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info("[RAG] Loading sentence-transformer model %s", RAG_EMBEDDING_MODEL_NAME)
                    self._model = SentenceTransformer(RAG_EMBEDDING_MODEL_NAME)
        return self._model

    def load_knowledge(self):
        """Load and process all markdown files from knowledge directory."""
        if self._loaded:
            return

        if not KNOWLEDGE_DIR.exists():
            print(f"[RAG] Warning: Knowledge directory not found: {KNOWLEDGE_DIR}")
            self._loaded = True
            return

        # Try to load from cache first
        if EMBEDDINGS_CACHE.exists() and CHUNKS_CACHE.exists():
            try:
                self._embeddings = np.load(EMBEDDINGS_CACHE)
                with open(CHUNKS_CACHE, "r", encoding="utf-8") as f:
                    self._chunks = json.load(f)
                print(f"[RAG] Loaded {len(self._chunks)} chunks from cache")
                self._loaded = True
                return
            except Exception as e:
                print(f"[RAG] Cache load failed, recomputing: {e}")

        # Compute embeddings from source files
        all_chunks = []

        for md_file in KNOWLEDGE_DIR.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                chunks = _chunk_text(content)
                # Tag chunks with source file
                for chunk in chunks:
                    if chunk.strip():
                        all_chunks.append(f"[{md_file.stem}] {chunk}")
            except Exception as e:
                print(f"[RAG] Error loading {md_file}: {e}")

        self._chunks = all_chunks

        if all_chunks:
            # Embed all chunks
            self._embeddings = self._get_model().encode(
                all_chunks,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            if self._embeddings.ndim == 2 and self._embeddings.shape[1] != RAG_EMBEDDING_DIMENSION:
                logger.warning(
                    "[RAG] Unexpected embedding width for %s: expected %s, got %s",
                    RAG_EMBEDDING_MODEL_NAME,
                    RAG_EMBEDDING_DIMENSION,
                    self._embeddings.shape[1],
                )
            # Save to cache
            try:
                np.save(EMBEDDINGS_CACHE, self._embeddings)
                with open(CHUNKS_CACHE, "w", encoding="utf-8") as f:
                    json.dump(self._chunks, f)
                print(f"[RAG] Saved {len(all_chunks)} chunks to cache")
            except Exception as e:
                print(f"[RAG] Failed to save cache: {e}")
            print(f"[RAG] Loaded {len(all_chunks)} chunks from {len(list(KNOWLEDGE_DIR.glob('*.md')))} files")
        else:
            self._embeddings = np.array([])
            print("[RAG] No knowledge chunks loaded")

        self._loaded = True

    def retrieve(self, query: str, k: int = 3) -> List[str]:
        """
        Retrieve top-k relevant chunks for a query.
        
        Args:
            query: Search query (e.g., "fitness creator growth strategies")
            k: Number of chunks to return
            
        Returns:
            List of relevant text chunks
        """
        if not self._loaded:
            self.load_knowledge()

        if not self._chunks or len(self._embeddings) == 0:
            return []

        # Embed query
        query_embedding = self._get_model().encode(
            query,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        # Compute similarities
        similarities = np.dot(self._embeddings, query_embedding)

        # Get top-k indices
        top_indices = similarities.argsort()[::-1][:k]

        # Return top chunks
        return [self._chunks[i] for i in top_indices]


# ------------------------------------------------
# Singleton instance
# ------------------------------------------------

_rag_engine = None
_rag_engine_lock = Lock()


def get_rag_engine() -> RAGEngine:
    """Get or create the singleton RAG engine."""
    global _rag_engine
    if _rag_engine is None:
        with _rag_engine_lock:
            if _rag_engine is None:
                _rag_engine = RAGEngine()
    return _rag_engine


def retrieve(query: str, k: int = 3) -> List[str]:
    """
    Convenience function to retrieve from RAG.
    
    Args:
        query: Search query
        k: Number of chunks to return
        
    Returns:
        List of relevant text chunks
    """
    engine = get_rag_engine()
    return engine.retrieve(query, k)


# ------------------------------------------------
# Action Plan Generator
# ------------------------------------------------

def _build_planner_context(
    creator_metrics: dict,
    niche_data: dict,
    momentum: dict,
    best_time: dict,
    recent_posts: list,
) -> dict:
    """
    Build a structured context dict from deterministic signals.
    Used as input to the LLM planner prompt.
    """
    followers = creator_metrics.get("followers", 0) or 0
    growth_score = creator_metrics.get("growth_score", 0) or 0
    avg_views = creator_metrics.get("avg_views", 0) or 0
    avg_engagement = creator_metrics.get("avg_engagement_rate_by_views", 0) or 0
    posts_per_week = creator_metrics.get("posts_per_week", 0) or 0
    primary_niche = (niche_data or {}).get("primary_niche", "general")
    momentum_label = (momentum or {}).get("momentum_label", "flat")
    momentum_value = (momentum or {}).get("momentum_value", 0)
    best_hours = (best_time or {}).get("best_posting_hours", [])
    return {
        "followers": followers,
        "growth_score": growth_score,
        "avg_views": avg_views,
        "avg_engagement_rate": avg_engagement,
        "posts_per_week": posts_per_week,
        "primary_niche": primary_niche,
        "momentum_label": momentum_label,
        "momentum_value": round(float(momentum_value), 2),
        "best_posting_hours": best_hours[:3],
        "recent_post_count": len(recent_posts) if recent_posts else 0,
    }


def _deterministic_fallback(context: dict) -> dict:
    primary_niche = str(context.get("primary_niche", "general") or "general")
    momentum_label = str(context.get("momentum_label", "flat") or "flat")
    momentum_value = float(context.get("momentum_value", 0) or 0)
    growth_score = float(context.get("growth_score", 0) or 0)
    avg_engagement = float(context.get("avg_engagement_rate", 0) or 0)
    posts_per_week = float(context.get("posts_per_week", 0) or 0)
    best_hours = context.get("best_posting_hours", []) or []

    if momentum_label == "accelerating":
        diagnosis = f"Your account is growing at {abs(momentum_value):.0f} followers/day. Engagement is healthy."
    elif momentum_label == "declining":
        diagnosis = f"Growth has slowed - losing {abs(momentum_value):.0f} followers/day. Focus on engagement."
    else:
        diagnosis = "Growth is stable but flat. Time to experiment with new content strategies."

    if growth_score >= 70:
        diagnosis += " Overall growth score is strong."
    elif growth_score >= 50:
        diagnosis += " Growth score is moderate - room for improvement."
    else:
        diagnosis += " Growth score needs attention - prioritize consistency."

    weekly_plan = []
    if posts_per_week < 3:
        weekly_plan.append("Increase posting frequency to at least 3-4 times per week")
    elif posts_per_week > 7:
        weekly_plan.append("Maintain consistent high-frequency posting")
    else:
        weekly_plan.append(f"Keep up your {posts_per_week:.1f} posts/week cadence")

    if avg_engagement < 0.05:
        weekly_plan.append("Add engaging CTAs to every post to boost interactions")

    weekly_plan.append(f"Focus content on your {primary_niche} niche for audience alignment")

    if momentum_label == "declining":
        weekly_plan.append("Engage with 10+ accounts in your niche daily to boost visibility")

    content_suggestions = []
    niche_ideas = {
        "fitness": ["Workout transformation reel", "Quick exercise tutorial", "Meal prep timelapse"],
        "lifestyle": ["Day in my life vlog", "Room/space tour", "Morning routine"],
        "food": ["Recipe tutorial reel", "Restaurant review", "What I eat in a day"],
        "tech": ["Product unboxing", "Quick tip tutorial", "Before/after setup reveal"],
        "fashion": ["Outfit transition reel", "Styling tips", "Haul with try-on"],
        "general": ["Behind-the-scenes content", "Q&A with audience", "Tutorial in your expertise"],
    }

    ideas = niche_ideas.get(primary_niche.lower(), niche_ideas["general"])
    content_suggestions.extend(ideas[:2])

    if avg_engagement > 0.05:
        content_suggestions.append("Double down on your top-performing content format")

    posting_schedule = []
    if best_hours:
        hour_labels = {
            6: "6 AM", 7: "7 AM", 8: "8 AM", 9: "9 AM", 10: "10 AM", 11: "11 AM",
            12: "12 PM", 13: "1 PM", 14: "2 PM", 15: "3 PM", 16: "4 PM", 17: "5 PM",
            18: "6 PM", 19: "7 PM", 20: "8 PM", 21: "9 PM", 22: "10 PM",
        }
        for hour in best_hours[:2]:
            label = hour_labels.get(hour, f"{hour}:00")
            posting_schedule.append(f"Post between {label} - your audience is most active")
    else:
        posting_schedule.append("Experiment with posting between 6-8 PM for best reach")

    posting_schedule.append("Tuesday and Thursday typically have highest engagement")
    posting_schedule.append("Avoid posting back-to-back - space content 6+ hours apart")

    cta_tips = [
        "End captions with a question to encourage comments",
        "Use 'Save this for later' to boost save rate",
        "Add 'Share with someone who needs this' for viral potential",
        "Pin your best comment to spark discussion",
    ]

    if avg_engagement < 0.03:
        cta_tips.insert(0, "Start every post with a hook in the first 3 seconds")

    return {
        "diagnosis": diagnosis,
        "weekly_plan": weekly_plan[:3],
        "content_suggestions": content_suggestions[:2],
        "posting_schedule": posting_schedule[:3],
        "cta_tips": cta_tips[:2],
    }


def generate_action_plan(
    creator_metrics: dict,
    niche_data: dict,
    momentum: dict,
    best_time: dict,
    recent_posts: list,
    knowledge_chunks: list = None
) -> dict:
    """
    Generate an actionable growth plan using LLM + RAG context.
    Falls back to deterministic rule-based output if LLM fails.
    """
    context = _build_planner_context(
        creator_metrics, niche_data, momentum, best_time, recent_posts
    )
    rag_context = ""
    if knowledge_chunks:
        rag_context = "\n\n".join(knowledge_chunks[:3])

    system_prompt = (
        "You are an expert Instagram growth strategist. "
        "You give concise, actionable, specific recommendations. "
        "You always respond with valid JSON only — no prose outside the JSON."
    )
    user_prompt = f"""You are analysing an Instagram creator account.
Creator context:
- Niche: {context['primary_niche']}
- Followers: {context['followers']:,}
- Growth score: {context['growth_score']}/100
- Average views per post: {context['avg_views']:,}
- Average engagement rate: {context['avg_engagement_rate']:.1%}
- Posts per week: {context['posts_per_week']:.1f}
- Momentum: {context['momentum_label']} ({context['momentum_value']:+.1f} followers/day)
- Best posting hours: {context['best_posting_hours']}
- Recent posts analysed: {context['recent_post_count']}
Relevant knowledge:
{rag_context if rag_context else "No additional knowledge context available."}
Return a JSON object with EXACTLY these keys:
{{
  "diagnosis": "<1-2 sentence summary of where the account stands>",
  "weekly_plan": ["<action 1>", "<action 2>", "<action 3>"],
  "content_suggestions": ["<idea 1>", "<idea 2>"],
  "posting_schedule": ["<tip 1>", "<tip 2>", "<tip 3>"],
  "cta_tips": ["<cta tip 1>", "<cta tip 2>"]
}}
Rules:
- Each string must be a concrete, specific recommendation (not generic advice).
- weekly_plan: exactly 3 items.
- content_suggestions: exactly 2 items.
- posting_schedule: exactly 3 items.
- cta_tips: exactly 2 items.
- Tailor ALL advice to the {context['primary_niche']} niche specifically.
"""

    try:
        from backend.app.ai.llm_client import LLMClient
        from backend.app.ai.toon import loads as parse_toon

        llm = LLMClient(model_name="gpt-4o-mini", temperature=0.5, max_tokens=600)
        response_text = llm.generate({"system": system_prompt, "user": user_prompt})
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError("LLM returned empty response")

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            parsed = parse_toon(response_text)

        if not isinstance(parsed, dict):
            raise ValueError(f"LLM returned non-dict: {type(parsed)}")

        required_keys = {
            "diagnosis",
            "weekly_plan",
            "content_suggestions",
            "posting_schedule",
            "cta_tips",
        }
        if not required_keys.issubset(parsed.keys()):
            raise ValueError(f"LLM response missing keys: {required_keys - parsed.keys()}")

        logger.info("[RAG] LLM action plan generated successfully.")
        return {
            "diagnosis": str(parsed.get("diagnosis", "")),
            "weekly_plan": [str(item) for item in parsed.get("weekly_plan", []) if isinstance(item, str)][:3],
            "content_suggestions": [str(item) for item in parsed.get("content_suggestions", []) if isinstance(item, str)][:2],
            "posting_schedule": [str(item) for item in parsed.get("posting_schedule", []) if isinstance(item, str)][:3],
            "cta_tips": [str(item) for item in parsed.get("cta_tips", []) if isinstance(item, str)][:2],
        }
    except Exception as exc:
        logger.warning("[RAG] LLM planner failed, using deterministic fallback: %s", exc)
        return _deterministic_fallback(context)



