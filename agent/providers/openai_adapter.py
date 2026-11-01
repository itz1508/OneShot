"""`openai` provider stub.

Install the vendor SDK with ``pip install 'oneshot[openai]'`` (adds
``openai>=1.0``). The stub registers itself with `ProviderRegistry`
and declares the capabilities an OpenAI-backed adapter will expose
once the live translation layer is implemented.

The adapter owns:

* API translation (chat.completions.create / responses.create),
* `OPENAI_API_KEY` resolution via `ProviderConfig.credential_ref`,
* strict tool schemas, structured outputs (`response_format`),
* prompt caching flags, streaming, batch processing (Batch API).
"""

from __future__ import annotations

from agent.providers._lazy_stub import make_stub_adapter
from agent.providers.registry import ProviderRegistry
from agent.providers.types import ProviderCapabilities

OpenAIAdapter = make_stub_adapter(
    "openai",
    sdk_module="openai",
    extra="openai",
    capabilities=ProviderCapabilities(
        structured_outputs=True,
        streaming=True,
        batch=True,
        prompt_caching=True,
        strict_tool_schemas=True,
        extensions=["json_schema_response_format", "responses_api"],
    ),
)

ProviderRegistry.register("openai", OpenAIAdapter)

__all__ = ["OpenAIAdapter"]
