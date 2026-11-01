"""OneShot provider abstraction.

Provider-agnostic client stack. The hierarchy is:

    ProviderConfig --> ProviderRegistry --> ProviderAdapter --> OneShotController

OneShot owns:
  * the unified request / response / capabilities types (see `types.py`),
  * the ProviderAdapter Protocol (see `base.py`),
  * the ProviderRegistry factory keyed by `provider` string (see `registry.py`),
  * the deterministic `EchoAdapter` reference implementation (default,
    requires no vendor SDK).

Each adapter owns:
  * API translation to its vendor (OpenAI / Anthropic / OpenAI-compatible),
  * authentication, prompt caching, strict tool schemas, structured outputs,
  * streaming, batch execution, and error normalization.

Unsupported capabilities MUST be reported explicitly via
`UnsupportedCapabilityError` — never silently downgraded. The workflow is
identical regardless of which supported provider executes it.

Separation of configuration axes (provider != model != endpoint):

    ProviderConfig(
        provider="openai_compatible",
        model="meta-llama/Meta-Llama-3-70B-Instruct",
        endpoint="https://api.together.xyz/v1",
        credential_ref="TOGETHER_API_KEY",
    )

The `provider` string chooses the adapter; `model` and `endpoint` are
adapter inputs; `credential_ref` names an environment variable the
adapter reads at `.generate()` time (never at import time).
"""

from agent.providers.base import (
    ProviderAdapter,
    UnsupportedCapabilityError,
    UnsupportedProviderError,
)
from agent.providers.echo_adapter import EchoAdapter
from agent.providers.registry import ProviderRegistry
from agent.providers.types import (
    BatchHandle,
    ProviderCapabilities,
    ProviderConfig,
    UnifiedEvent,
    UnifiedRequest,
    UnifiedResponse,
)

__all__ = [
    "BatchHandle",
    "EchoAdapter",
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderConfig",
    "ProviderRegistry",
    "UnifiedEvent",
    "UnifiedRequest",
    "UnifiedResponse",
    "UnsupportedCapabilityError",
    "UnsupportedProviderError",
]
