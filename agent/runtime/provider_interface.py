"""Provider-neutral execution interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class ProviderEvent(Protocol):
    """Protocol for events emitted by a provider."""

    event_type: str


class ProviderAdapter(Protocol):
    """Protocol for provider adapters."""

    async def start_task(self, task_id: str, prompt: str) -> AsyncIterator[ProviderEvent]:
        """Start a new task with the provider."""
        ...

    async def resume_task(self, session_id: str, prompt: str) -> AsyncIterator[ProviderEvent]:
        """Resume an existing task session."""
        ...

    async def interrupt_task(self, session_id: str) -> None:
        """Interrupt a running task."""
        ...
