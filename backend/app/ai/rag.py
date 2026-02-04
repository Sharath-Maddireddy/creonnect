"""
Simple RAG (Retrieval Augmented Generation) Engine

Uses sentence-transformers for embeddings (already used in niche.py).
Stores vectors in memory for simplicity.
"""

import os
import json
from typing import List
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer


# ------------------------------------------------
# Configuration
# ------------------------------------------------

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
CHUNK_SIZE = 400  # Target characters per chunk
CHUNK_OVERLAP = 50  # Overlap between chunks

# Cache file paths
EMBEDDINGS_CACHE = KNOWLEDGE_DIR / ".rag_embeddings.npy"
CHUNKS_CACHE = KNOWLEDGE_DIR / ".rag_chunks.json"


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
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._chunks: List[str] = []
        self._embeddings: np.ndarray = None
        self._loaded = False

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
            self._embeddings = self._model.encode(
                all_chunks,
                normalize_embeddings=True,
                show_progress_bar=False
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
        query_embedding = self._model.encode(
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


def get_rag_engine() -> RAGEngine:
    """Get or create the singleton RAG engine."""
    global _rag_engine
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
