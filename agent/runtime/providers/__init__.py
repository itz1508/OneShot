"""OneShot provider adapters — provider-neutral model access."""

from agent.runtime.providers.base import (
    CapabilityDescriptor,
    ProviderAdapter,
    ProviderError,
    ProviderEvent,
    ProviderRequest,
    ProviderResult,
    UnsupportedCapabilityError,
    UnsupportedProviderError,
)
from agent.runtime.providers.echo import EchoProvider
from agent.runtime.providers.registry import ProviderRegistry

__all__ = [
    "CapabilityDescriptor",
    "EchoProvider",
    "ProviderAdapter",
    "ProviderError",
    "ProviderEvent",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResult",
    "UnsupportedCapabilityError",
    "UnsupportedProviderError",
]
