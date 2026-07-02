"""Shared vector math helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable


def cosine_similarity(vec1: Iterable[float], vec2: Iterable[float]) -> float:
    """Return cosine similarity for equally-sized vectors, else 0.0."""
    values1 = list(vec1)
    values2 = list(vec2)
    if not values1 or not values2 or len(values1) != len(values2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(values1, values2))
    magnitude1 = math.sqrt(sum(a * a for a in values1))
    magnitude2 = math.sqrt(sum(b * b for b in values2))
    if magnitude1 == 0.0 or magnitude2 == 0.0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)
