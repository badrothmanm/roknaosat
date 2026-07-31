"""
Base protocol for publishing adapters.
"""

from __future__ import annotations

from typing import Any, Protocol


class AdAdapter(Protocol):
    """
    Adapter protocol contract.
    Any publishing channel adapter should implement this interface.
    """

    provider: str

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute publish flow for a channel and return normalized result payload.
        """
        ...

