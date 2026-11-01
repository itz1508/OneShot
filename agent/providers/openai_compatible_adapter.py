"""`openai_compatible` provider stub.

Target: any inference service that speaks the OpenAI JSON contract on
a custom endpoint (vLLM, Together AI, Ollama's OpenAI shim, Fireworks,
Groq, and so on). Meta Llama, for example, runs through several such
services with differing capabilities — the config carries the endpoint
and the capability matrix stays per-adapter.

Install the vendor SDK with ``pip install 'oneshot[openai]'`` — the
same ``openai`` package is used because the wire format matches.

Declared capabilities are the LEAST COMMON DENOMINATOR; a concrete
service may override them when it subclasses this adapter.
"""

from __future__ import annotations

from agent.providers._lazy_stub import make_stub_adapter
from agent.providers.registry import ProviderRegistry
from agent.providers.types import ProviderCapabilities

OpenAICompatibleAdapter = make_stub_adapter(
    "openai_compatible",
    sdk_module="openai",
    extra="openai",
    capabilities=ProviderCapabilities(
        structured_outputs=False,
        streaming=True,
        batch=False,
        prompt_caching=False,
        strict_tool_schemas=False,
        extensions=["custom_endpoint"],
    ),
)

ProviderRegistry.register("openai_compatible", OpenAICompatibleAdapter)

__all__ = ["OpenAICompatibleAdapter"]
