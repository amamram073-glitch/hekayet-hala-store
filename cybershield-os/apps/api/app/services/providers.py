"""Provider contracts for future integrations; no third-party provider is enabled by default.

Adapters should be registered by deployment configuration, receive only tenant-scoped
records, enforce their own timeouts/rate limits, and never return credentials to the UI.
"""
from typing import Any, Protocol


class EventSourceAdapter(Protocol):
    name: str
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]: ...


class ThreatIntelProvider(Protocol):
    name: str
    async def lookup(self, indicator_type: str, value: str) -> dict[str, Any] | None: ...


class NotificationProvider(Protocol):
    name: str
    async def send(self, event_type: str, payload: dict[str, Any]) -> str: ...


class TicketingProvider(Protocol):
    name: str
    async def create_ticket(self, payload: dict[str, Any]) -> dict[str, str]: ...


class CloudLogProvider(Protocol):
    name: str
    async def pull_events(self, cursor: str | None = None) -> tuple[list[dict[str, Any]], str | None]: ...


class ProviderRegistry:
    """In-memory adapter registry; deliberately has no implicit network-backed defaults."""
    def __init__(self):
        self._providers: dict[tuple[str, str], object] = {}

    def register(self, category: str, name: str, provider: object) -> None:
        if not category or not name or (category, name) in self._providers:
            raise ValueError("Provider key must be unique and non-empty")
        self._providers[(category, name)] = provider

    def get(self, category: str, name: str):
        return self._providers.get((category, name))

    def names(self, category: str) -> list[str]:
        return sorted(name for kind, name in self._providers if kind == category)


registry = ProviderRegistry()
