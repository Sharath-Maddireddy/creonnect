"""
TOON (Token-Oriented Object Notation) parser and encoder.

TOON is a minimal, indentation-based format similar to YAML but without
braces or commas. Nested objects are represented by 2-space indentation.
Lists are represented by "- " items.
"""

from __future__ import annotations

import json
from typing import Any


INDENT_SPACES = 2


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        inner = value[1:-1]
        if value[0] == '"':
            return (
                inner
                .replace("\\\\", "\\")
                .replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
                .replace('\\"', '"')
            )
        return (
            inner
            .replace("\\\\", "\\")
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace("\\'", "'")
        )
    return value


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        return _strip_quotes(raw)

    text = raw
    lowered = text.lower()
    if lowered in {"null", "none"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        return float(text)
    except ValueError:
        return text


def _split_inline_list_items(inner: str) -> list[str]:
    """Split bracket-list contents on top-level commas, respecting quotes."""
    items: list[str] = []
    current: list[str] = []
    quote_char: str | None = None
    for char in inner:
        if quote_char is not None:
            current.append(char)
            if char == quote_char:
                quote_char = None
            continue
        if char in {"'", '"'}:
            quote_char = char
            current.append(char)
            continue
        if char == ",":
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail or items:
        items.append(tail)
    return [item for item in items if item]


def _parse_inline_list(text: str) -> list[Any] | None:
    """Parse a bracket-style inline list, e.g. ``[a, "b, c", 3]``.

    Some LLM providers emit TOON list fields inline (JSON-like brackets)
    instead of the multi-line ``- item`` form. Without this, the entire
    bracket text was stored as one opaque string and then silently dropped
    by downstream ``isinstance(value, list)`` checks.
    """
    stripped = text.strip()
    if len(stripped) < 2 or stripped[0] != "[" or stripped[-1] != "]":
        return None
    inner = stripped[1:-1].strip()
    if not inner:
        return []
    return [_parse_scalar(item) for item in _split_inline_list_items(inner)]


def _needs_quoting(text: str) -> bool:
    if text == "" or " " in text or text.startswith("-") or text.startswith("#"):
        return True
    if len(text) >= 2 and text[0] == "[" and text[-1] == "]":
        return True
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return True
    if any(char in text for char in "\n\r\t"):
        return True

    lowered = text.lower()
    if lowered in {"null", "none", "true", "false"}:
        return True

    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return True
        float(text)
        return True
    except ValueError:
        return False


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _needs_quoting(text):
        escaped = (
            text
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace('"', '\\"')
        )
        return f"\"{escaped}\""
    return text


_FORMAT_LABEL_KEYS = {"toon", "json"}


def _strip_leading_format_label(text: str) -> str:
    """Drop a stray leading ``TOON:`` (or ``JSON:``) label line some models
    emit despite being told to return a bare object, and de-indent the rest
    of the document by one level to undo the accidental nesting it causes.

    Without this, a response like::

        TOON:
          hook_frame_score 0.7
          cringe_score 0

    parses as ``{"TOON": {"hook_frame_score": 0.7, "cringe_score": 0}}``
    instead of a flat object, silently defaulting every downstream field
    that reads top-level keys.
    """
    lines = text.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines):
        return text

    first = lines[start].strip()
    if not first.endswith(":"):
        return text
    if first[:-1].strip().lower() not in _FORMAT_LABEL_KEYS:
        return text

    remaining = lines[start + 1 :]
    if not remaining:
        return text

    dedented: list[str] = []
    for line in remaining:
        if not line.strip():
            dedented.append(line)
            continue
        stripped = line.lstrip(" ")
        removed = len(line) - len(stripped)
        dedented.append(" " * max(0, removed - INDENT_SPACES) + stripped)
    return "\n".join(dedented)


def loads(text: str) -> dict[str, Any]:
    """
    Parse TOON text into a Python dictionary.

    Rules:
    - 2-space indentation for nesting
    - key/value separated by a space
    - lists use "- " prefix
    """
    text = _strip_leading_format_label(text)
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(0, root)]
    pending: tuple[str, Any, Any] | None = None

    lines = text.splitlines()
    for raw_line in lines:
        if not raw_line.strip():
            continue

        raw_indent = len(raw_line) - len(raw_line.lstrip(" "))
        indent = (raw_indent // INDENT_SPACES) * INDENT_SPACES

        content = raw_line.lstrip(" ").rstrip()

        if indent > stack[-1][0]:
            if pending is None:
                raise ValueError(f"Unexpected indentation: {raw_line!r}")
            if content.startswith("-"):
                new_container: Any = []
            else:
                new_container = {}
            pending_type, pending_container, pending_key = pending
            if pending_type == "dict":
                pending_container[pending_key] = new_container
            else:
                pending_container[pending_key] = new_container
            stack.append((indent, new_container))
            pending = None
        elif indent < stack[-1][0]:
            while stack and indent < stack[-1][0]:
                stack.pop()
            pending = None
        else:
            pending = None

        container = stack[-1][1]
        if content.startswith("-"):
            if not isinstance(container, list):
                raise ValueError("List item found outside of list context.")
            item_text = content[1:].lstrip()
            if not item_text:
                container.append({})
                pending = ("list", container, len(container) - 1)
                continue
            inline_list = _parse_inline_list(item_text)
            container.append(inline_list if inline_list is not None else _parse_scalar(item_text))
            continue

        if " " in content:
            key, value_text = content.split(" ", 1)
            key = key.rstrip(":")
            if isinstance(container, dict):
                inline_list = _parse_inline_list(value_text)
                container[key] = inline_list if inline_list is not None else _parse_scalar(value_text)
            else:
                raise ValueError("Key/value pair found inside a list.")
            continue

        key = content.rstrip(":")
        if not isinstance(container, dict):
            raise ValueError("Nested object key found inside a list.")
        container[key] = {}
        pending = ("dict", container, key)

    return root


def loads_object(text: str) -> dict[str, Any]:
    """Parse text that should be one object, trying JSON before TOON.

    Providers prompted for TOON output (a token-saving format) sometimes
    emit plain JSON instead — observed in practice from Gemini reel
    analysis, whose braces/quoted-keys/trailing-commas the TOON parser
    cannot read at all. JSON is checked first since it is unambiguous
    when present; TOON is the fallback for genuinely TOON-shaped output.
    """
    stripped = text.strip()
    if "{" in stripped and "}" in stripped:
        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        try:
            candidate = json.loads(stripped[start:end])
        except (ValueError, json.JSONDecodeError):
            candidate = None
        if isinstance(candidate, dict):
            return candidate
    return loads(stripped)


def dumps(obj: dict[str, Any]) -> str:
    """
    Encode a Python dictionary into TOON text.
    """
    def _dump_value(value: Any, indent: int) -> list[str]:
        lines: list[str] = []
        prefix = " " * indent
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k}")
                    lines.extend(_dump_value(v, indent + INDENT_SPACES))
                else:
                    lines.append(f"{prefix}{k} {_format_scalar(v)}")
            return lines
        if isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    lines.extend(_dump_value(item, indent + INDENT_SPACES))
                else:
                    lines.append(f"{prefix}- {_format_scalar(item)}")
            return lines
        lines.append(f"{prefix}{_format_scalar(value)}")
        return lines

    if not isinstance(obj, dict):
        raise ValueError("TOON dumps expects a dict at the root.")
    return "\n".join(_dump_value(obj, 0))
