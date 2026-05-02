"""Base interface for account sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.account_sources.models import AccountSourceRequest, NormalizedAccountPayload


class AccountSource(ABC):
    """Abstract base for upstream account sources."""

    @abstractmethod
    async def load(self, request: AccountSourceRequest) -> NormalizedAccountPayload:
        """Materialize one normalized account payload."""
