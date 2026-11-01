"""Provider adapter Protocol + typed error hierarchy.

Ownership rule (keep this short and visible):

    OneShot owns  the unified request/response/handoff/validation contract.
    Each adapter   owns  provider-specific API translation, authentication,
                   caching, streaming, batch execution, error normalisation.

Unsupported capabilities MUST be raised as `UnsupportedCapabilityError`
(never silently downgraded). Unknown providers at registry time MUST be
raised as `UnsupportedProviderError`.
"""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Protocol, runtime_checkable

from agent.providers.types import (
    BatchHandle,
    ProviderCapabilities,
    UnifiedEvent,
    UnifiedRequest,
    UnifiedResponse,
)


class UnsupportedProviderError(RuntimeError):
    """Raised by `ProviderRegistry.create` for an unknown provider key.

    Also raised by lazy stubs when a vendor SDK is missing at
    `.generate()` time, carrying the install hint in the message.
    """


class UnsupportedCapabilityError(RuntimeError):
    """Raised when a caller asks an adapter for a capability it does not
    declare.

    Attributes:
        capability: the capability name requested (e.g. ``"streaming"``).
    """

    def __init__(self, capability: str, provider: str, message: str | None = None):
        self.capability = capability
        self.provider = provider
        super().__init__(
            message
            or (
                f"Provider {provider!r} does not support capability "
                f"{capability!r}. Capabilities must be declared explicitly; "
                "silent downgrades are refused."
            )
        )


@runtime_checkable
class ProviderAdapter(Protocol):
    """The shape every registered adapter satisfies.

    Only `capabilities` and `generate` are required. `stream` and
    `batch` are optional; the registry calls `capabilities()` first so
    callers can gate on advertised support rather than probing.
    """

    def capabilities(self) -> ProviderCapabilities:
        ...

    def generate(self, request: UnifiedRequest) -> UnifiedResponse:
        ...

    def stream(  # pragma: no cover - optional
        self, request: UnifiedRequest
    ) -> AsyncIterable[UnifiedEvent]:
        ...

    def batch(  # pragma: no cover - optional
        self, requests: list[UnifiedRequest]
    ) -> BatchHandle:
        ...
