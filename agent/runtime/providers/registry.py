"""Provider registry — provider-neutral adapter registration."""

from __future__ import annotations

from agent.runtime.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderRequest,
    ProviderResult,
    UnsupportedProviderError,
)
from agent.runtime.providers.echo import EchoProvider


class ProviderRegistry:
    """Provider-neutral registry with lazy stub registration.

    - Adapters register by key.
    - Vendor SDKs imported lazily at generate() time.
    - ImportError tolerated for stripped-down installs.
    - register() prevents shadowing existing providers.
    - create() raises UnsupportedProviderError for unknown keys.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, type] = {}
        self._instances: dict[str, ProviderAdapter] = {}
        # Register echo by default — zero-dep, always available
        self.register("echo", EchoProvider)
        self._default = "echo"

    def register(self, key: str, adapter_class: type) -> None:
        """Register an adapter class. Prevents shadowing."""
        if key in self._adapters:
            raise ProviderError(f"provider already registered: {key}")
        self._adapters[key] = adapter_class

    def create(self, key: str) -> ProviderAdapter:
        """Create or return cached adapter instance."""
        if key not in self._adapters:
            raise UnsupportedProviderError(f"unsupported provider: {key}")
        if key not in self._instances:
            self._instances[key] = self._adapters[key]()
        return self._instances[key]

    def generate(self, key: str, request: ProviderRequest) -> ProviderResult:
        """Generate using a named provider."""
        adapter = self.create(key)
        return adapter.generate(request)

    @property
    def default_provider(self) -> str:
        return self._default

    @default_provider.setter
    def default_provider(self, key: str) -> None:
        if key not in self._adapters:
            raise UnsupportedProviderError(f"cannot set default to unknown provider: {key}")
        self._default = key

    @property
    def registered_providers(self) -> tuple[str, ...]:
        return tuple(self._adapters.keys())
