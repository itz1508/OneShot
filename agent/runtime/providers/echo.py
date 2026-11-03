"""Echo provider — deterministic test double, not runtime default."""

from __future__ import annotations

import hashlib

from agent.runtime.providers.base import (
    CapabilityDescriptor,
    ProviderRequest,
    ProviderResult,
)


class EchoProvider:
    """Deterministic echo provider for CI and tests.

    Response content maps to sha256(canonical_request) so two identical
    requests produce byte-identical responses.
    """

    PROVIDER_NAME = "echo"

    def generate(self, request: ProviderRequest) -> ProviderResult:
        canonical = f"{request.run_id}:{request.prompt}:{request.system_prompt}"
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return ProviderResult(
            content=f"echo:{digest[:16]}",
            finish_reason="stop",
            usage={"total_tokens": len(canonical)},
            provider=self.PROVIDER_NAME,
            model="echo-1.0",
        )

    def declared_capabilities(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            structured_outputs=False,
            streaming=False,
            batch=False,
            prompt_caching=False,
            strict_tool_schemas=False,
        )
