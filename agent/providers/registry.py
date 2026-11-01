"""`ProviderRegistry` — pure factory keyed by `provider` string.

The registry is a thin dispatch table. No vendor SDK is imported at
module-load time; adapter classes are registered as callables and
instantiated on demand by `.create(config)`.

Default registrations (installed by `_register_defaults`):

* `echo` — the deterministic reference adapter (`EchoAdapter`). No
  network, no SDK. Used in tests and whenever the caller does not want
  to pay for a live provider.
* `openai` — stub registration (see `agent/providers/openai_adapter.py`).
  Imports the vendor SDK lazily at `.generate()` time; raises
  `UnsupportedProviderError` with an install hint if `openai` is missing.
* `anthropic` — stub registration (see `agent/providers/anthropic_adapter.py`).
* `openai_compatible` — stub registration for Meta-Llama / Together /
  vLLM-style endpoints that speak the OpenAI JSON shape.

Callers add their own provider by:

    from agent.providers import ProviderRegistry
    ProviderRegistry.register("custom", CustomAdapter)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from agent.providers.base import ProviderAdapter, UnsupportedProviderError
from agent.providers.types import ProviderConfig

AdapterFactory = Callable[[ProviderConfig], ProviderAdapter]


class ProviderRegistry:
    """Factory for `ProviderAdapter`s.

    The registry is a class-level dict so multiple callers see the same
    adapter table. Register adapters at import time; create instances
    at use time.
    """

    _factories: ClassVar[dict[str, AdapterFactory]] = {}
    _defaults_installed: ClassVar[bool] = False

    @classmethod
    def register(cls, provider: str, factory: AdapterFactory) -> None:
        """Register an adapter class / factory under a provider key.

        Re-registering the SAME key with the SAME factory is a no-op
        (idempotent). Re-registering with a DIFFERENT factory raises
        `ValueError` — this prevents a late `import` from silently
        shadowing a built-in adapter.
        """

        cls._install_defaults()
        existing = cls._factories.get(provider)
        if existing is not None and existing is not factory:
            raise ValueError(
                f"Provider key {provider!r} is already registered to a "
                f"different factory ({existing!r}); refusing to shadow."
            )
        cls._factories[provider] = factory

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove a provider key. Used by test setup/teardown."""

        cls._factories.pop(provider, None)

    @classmethod
    def known_providers(cls) -> list[str]:
        """Return the sorted list of registered provider keys."""

        cls._install_defaults()
        return sorted(cls._factories.keys())

    @classmethod
    def create(cls, config: ProviderConfig) -> ProviderAdapter:
        """Instantiate the adapter registered under ``config.provider``.

        Raises:
            UnsupportedProviderError: ``config.provider`` is not
                registered.
        """

        cls._install_defaults()
        factory = cls._factories.get(config.provider)
        if factory is None:
            known = ", ".join(sorted(cls._factories.keys())) or "(none)"
            raise UnsupportedProviderError(
                f"Unsupported provider: {config.provider!r}. "
                f"Known providers: {known}. "
                "Register the adapter via ProviderRegistry.register(name, cls)."
            )
        return factory(config)

    # ------------------------------------------------------------------
    # Default registrations are installed on first use so a bare
    # `agent.providers.registry` import never pulls in optional stubs.
    # ------------------------------------------------------------------

    @classmethod
    def _install_defaults(cls) -> None:
        if cls._defaults_installed:
            return
        cls._defaults_installed = True

        # EchoAdapter — always available, zero deps.
        from agent.providers.echo_adapter import EchoAdapter

        cls._factories.setdefault("echo", EchoAdapter)

        # Stubs for the three documented vendors. Each stub registers
        # itself at import time but does NOT import its SDK until
        # `.generate()` runs. We attempt the imports here but tolerate
        # ImportError so a stripped-down install (no vendor SDKs) still
        # works end-to-end against the Echo adapter.
        from importlib import import_module

        for mod_name in (
            "agent.providers.openai_adapter",
            "agent.providers.anthropic_adapter",
            "agent.providers.openai_compatible_adapter",
        ):
            try:
                import_module(mod_name)
            except ImportError:
                # Adapter stub itself failed to import; skip it. The
                # registry still works for every OTHER provider key.
                continue
