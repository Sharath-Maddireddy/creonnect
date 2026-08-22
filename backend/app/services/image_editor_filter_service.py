"""Shared Pillow image-effect helpers used by Creator Studio's export pipeline."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _apply_vignette(image: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return image
    width, height = image.size
    center_x = width / 2.0
    center_y = height / 2.0
    max_distance = (center_x ** 2 + center_y ** 2) ** 0.5
    strength = _clamp(amount / 100.0, 0.0, 1.0)
    y, x = np.ogrid[:height, :width]
    distance = np.hypot(x - center_x, y - center_y) / max_distance
    falloff = np.clip(1.0 - np.power(distance, 1.8) * 0.55 * strength, 0.0, 1.0)
    mask = Image.fromarray((falloff * 255).astype(np.uint8), mode="L")
    return Image.composite(image.convert("RGB"), Image.new("RGB", image.size, "black"), mask)
