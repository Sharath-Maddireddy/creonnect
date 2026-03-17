"""
TOON (Token-Oriented Object Notation) parser and encoder.

TOON is a minimal, indentation-based format similar to YAML but without
braces or commas. Nested objects are represented by 2-space indentation.
Lists are represented by "- " items.
"""

from __future__ import annotations

from typing import Any


INDENT_SPACES = 2


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('\\"', '"')
        return inner.replace("\\'", "'")
    return value


def _parse_scalar(value: str) -> Any:
    text = _strip_quotes(value.strip())
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


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or " " in text or text.startswith("-") or text.startswith("#"):
        escaped = text.replace('"', '\\"')
        return f"\"{escaped}\""
    return text


def loads(text: str) -> dict[str, Any]:
    """
    Parse TOON text into a Python dictionary.

    Rules:
    - 2-space indentation for nesting
    - key/value separated by a space
    - lists use "- " prefix
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(0, root)]
    pending: tuple[str, Any, Any] | None = None

    lines = text.splitlines()
    for raw_line in lines:
        if not raw_line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % INDENT_SPACES != 0:
            raise ValueError(f"Invalid indentation: {raw_line!r}")

        content = raw_line[indent:].rstrip()

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
            value = _parse_scalar(item_text)
            container.append(value)
            continue

        if " " in content:
            key, value_text = content.split(" ", 1)
            if isinstance(container, dict):
                container[key] = _parse_scalar(value_text)
            else:
                raise ValueError("Key/value pair found inside a list.")
            continue

        key = content.rstrip(":")
        if not isinstance(container, dict):
            raise ValueError("Nested object key found inside a list.")
        container[key] = {}
        pending = ("dict", container, key)

    return root


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
