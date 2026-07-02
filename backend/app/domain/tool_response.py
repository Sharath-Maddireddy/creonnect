"""Standardized tool response envelope models for brand tool-calling (FR-6)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolResponseMeta(BaseModel):
    """Structured metadata for tool responses as defined in PRD FR-6."""

    model_config = ConfigDict(extra="forbid")

    latency_ms: float
    result_count: int | None = None
    request_id: str | None = None


class ToolResponse(BaseModel):
    """Unified tool response envelope used by brand-side tools per PRD FR-6."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    tool: str
    message: str
    data: dict[str, Any] | list[Any] | None
    ui: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    @classmethod
    def ok(
        cls,
        tool: str,
        data: dict[str, Any] | list[Any] | None,
        message: str = "ok",
        ui: dict[str, Any] | None = None,
        meta: ToolResponseMeta | dict[str, Any] | None = None,
    ) -> "ToolResponse":
        """Build a successful FR-6 envelope."""
        serialized_meta = (
            meta.model_dump(mode="python")
            if isinstance(meta, ToolResponseMeta)
            else meta
        )
        return cls(
            success=True,
            tool=tool,
            message=message,
            data=data,
            ui=ui,
            meta=serialized_meta,
        )

    @classmethod
    def error(
        cls,
        tool: str,
        message: str,
        meta: ToolResponseMeta | dict[str, Any] | None = None,
    ) -> "ToolResponse":
        """Build an error FR-6 envelope."""
        serialized_meta = (
            meta.model_dump(mode="python")
            if isinstance(meta, ToolResponseMeta)
            else meta
        )
        return cls(
            success=False,
            tool=tool,
            message=message,
            data=None,
            ui=None,
            meta=serialized_meta,
        )
