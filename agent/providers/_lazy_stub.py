"""Shared helper for the lazy vendor-adapter stubs.

Each stub (`openai_adapter`, `anthropic_adapter`, `openai_compatible_adapter`)
follows the same pattern:

1. Import this helper at module scope — no vendor SDK touched.
2. Call `make_stub_adapter(name, sdk_module_name, extra_hint)` to build
   a class that satisfies the `ProviderAdapter` Protocol.
3. Register the class with `ProviderRegistry`.

When a caller actually invokes `.generate()`, the stub tries to import
the vendor SDK. If that fails, it raises `UnsupportedProviderError`
carrying the exact `pip install oneshot[<extra>]` hint. If the import
succeeds, the stub currently refuses to make a real call (the full
request translation is a follow-up change); callers who need live
provider traffic MUST subclass the stub and implement `generate` in
their own extension. The important properties this stub DOES deliver:

* adapter imports without the SDK installed,
* capabilities are declared explicitly,
* an unsupported capability raises `UnsupportedCapabilityError`,
* a missing SDK raises `UnsupportedProviderError` with install hint —
  it never silently downgrades.
"""

from __future__ import annotations

from collections.abc import AsyncIterable
from importlib import import_module

from agent.providers.base import (
    ProviderAdapter,
    UnsupportedCapabilityError,
    UnsupportedProviderError,
)
from agent.providers.types import (
    BatchHandle,
    ProviderCapabilities,
    ProviderConfig,
    UnifiedEvent,
    UnifiedRequest,
    UnifiedResponse,
)


def make_stub_adapter(
    provider_name: str,
    sdk_module: str,
    extra: str,
    *,
    capabilities: ProviderCapabilities,
) -> type[ProviderAdapter]:
    """Return a stub adapter class for one vendor provider.

    Args:
        provider_name: the key passed in `ProviderConfig.provider`.
        sdk_module: the Python module the stub will try to import on
            `.generate()` (e.g. ``"openai"``, ``"anthropic"``).
        extra: the install-extra name documented in `pyproject.toml`
            (e.g. ``"openai"``, ``"anthropic"``). Interpolated into the
            exception message as ``pip install oneshot[<extra>]``.
        capabilities: the capability matrix this provider WILL expose
            once the adapter is implemented. Pinned here so callers can
            gate on advertised support before the real adapter lands.
    """

    class _Stub(ProviderAdapter):
        PROVIDER_KEY = provider_name

        def __init__(self, config: ProviderConfig):
            if not isinstance(config, ProviderConfig):
                raise TypeError(
                    f"{provider_name} adapter requires a ProviderConfig; "
                    f"got {type(config).__name__}"
                )
            self._config = config

        def capabilities(self) -> ProviderCapabilities:
            return capabilities

        def generate(self, request: UnifiedRequest) -> UnifiedResponse:
            # Honour the declared capability matrix even before the SDK
            # lookup — a caller asking for streaming on a stub that
            # advertises streaming=False gets the capability error, not
            # the "SDK missing" error.
            if request.stream and not capabilities.streaming:
                raise UnsupportedCapabilityError("streaming", provider_name)

            try:
                import_module(sdk_module)
            except ImportError as exc:
                raise UnsupportedProviderError(
                    f"{sdk_module!r} SDK is not installed; "
                    f"pip install 'oneshot[{extra}]' to enable the "
                    f"{provider_name!r} adapter."
                ) from exc

            raise NotImplementedError(
                f"{provider_name!r} adapter stub: the vendor SDK is "
                "installed, but the live translation layer is a "
                "follow-up change. Subclass this adapter and implement "
                "`generate()` to send real traffic."
            )

        def stream(self, request: UnifiedRequest) -> AsyncIterable[UnifiedEvent]:
            if not capabilities.streaming:
                raise UnsupportedCapabilityError("streaming", provider_name)
            raise NotImplementedError(
                f"{provider_name!r} adapter stub: `stream` is declared "
                "supported but no concrete implementation ships yet."
            )

        def batch(self, requests: list[UnifiedRequest]) -> BatchHandle:
            if not capabilities.batch:
                raise UnsupportedCapabilityError("batch", provider_name)
            raise NotImplementedError(
                f"{provider_name!r} adapter stub: `batch` is declared "
                "supported but no concrete implementation ships yet."
            )

    _Stub.__name__ = f"{provider_name.title().replace('_', '')}Adapter"
    _Stub.__qualname__ = _Stub.__name__
    return _Stub
