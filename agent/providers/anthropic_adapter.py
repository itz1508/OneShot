"""`anthropic` provider stub.

Install the vendor SDK with ``pip install 'oneshot[anthropic]'`` (adds
``anthropic>=0.25``). The stub registers itself and declares the
capabilities an Anthropic-backed adapter will expose once the live
translation layer is implemented.

The adapter owns:

* API translation (messages.create),
* `ANTHROPIC_API_KEY` resolution via `ProviderConfig.credential_ref`,
* tool_use schemas, prompt caching (``cache_control``),
* streaming server-sent events, Message Batches API.
"""

from __future__ import annotations

from agent.providers._lazy_stub import make_stub_adapter
from agent.providers.registry import ProviderRegistry
from agent.providers.types import ProviderCapabilities

AnthropicAdapter = make_stub_adapter(
    "anthropic",
    sdk_module="anthropic",
    extra="anthropic",
    capabilities=ProviderCapabilities(
        structured_outputs=False,
        streaming=True,
        batch=True,
        prompt_caching=True,
        strict_tool_schemas=True,
        extensions=["cache_control", "tool_use"],
    ),
)

ProviderRegistry.register("anthropic", AnthropicAdapter)

__all__ = ["AnthropicAdapter"]
