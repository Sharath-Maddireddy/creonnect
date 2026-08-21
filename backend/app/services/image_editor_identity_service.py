"""Shared provider instructions for identity-preserving image edits."""


IDENTITY_LOCK_PROMPT = (
    "This is an image edit, not a new image recreation. The supplied image is the source of truth. "
    "Identity lock is the highest-priority instruction. Treat every face and head, especially every area protected "
    "by the opaque mask, as immutable source pixels: do not redraw, replace, reinterpret, beautify, retouch, age, "
    "de-age, or synthesize them. Keep each person exactly recognizable as the same individual. Preserve exact facial "
    "geometry, skin tone and natural texture, hairstyle, hairline, eyes, eyebrows, nose, mouth, teeth, facial hair, "
    "body proportions, pose, expression, and the number and placement of people. Preserve the original canvas "
    "orientation, camera viewpoint, framing, crop, perspective, and subject positions. Apply the requested style only "
    "to editable regions through lighting, color grading, atmosphere, and background treatment. If any requested "
    "effect conflicts with identity or composition preservation, skip that effect rather than changing a person."
)
