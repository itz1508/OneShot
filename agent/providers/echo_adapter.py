"""`EchoAdapter` — the deterministic in-process reference adapter.

Used by:

* The default `OneShotController` provider path, so the controller can
  be exercised end-to-end without any vendor SDK, API key, or network
  reachability.
* Tests, so a stable sha-256 of the serialised request can be used as
  an oracle in red-first checks (G01-style identity-stability).

The adapter DOES NOT call out. `generate()` returns a response whose
`content` is the sha-256 of a canonical JSON encoding of the request
plus an `[echo]` prefix; `tool_calls` is empty; `finish_reason` is
`"stop"`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterable

from agent.providers.base import (
    ProviderAdapter,
    UnsupportedCapabilityError,
)
from agent.providers.types import (
    BatchHandle,
    ProviderCapabilities,
    UnifiedEvent,
    UnifiedRequest,
    UnifiedResponse,
    Usage,
)


class EchoAdapter(ProviderAdapter):
    """Deterministic reference adapter."""

    PROVIDER_KEY = "echo"

    def __init__(self, config):
        # Lazy import to avoid a circular reference when the registry
        # instantiates adapters.
        from agent.providers.types import ProviderConfig

        if not isinstance(config, ProviderConfig):
            raise TypeError(
                f"EchoAdapter requires a ProviderConfig; got {type(config).__name__}"
            )
        self._config = config

    # ---- declared capabilities --------------------------------------

    def capabilities(self) -> ProviderCapabilities:
        """Minimal capability set: structured outputs allowed because
        the echo content is already a deterministic JSON payload; other
        features are explicitly off so callers hit
        `UnsupportedCapabilityError` and know to pick a real adapter."""

        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            batch=False,
            prompt_caching=False,
            strict_tool_schemas=False,
        )

    # ---- generate ---------------------------------------------------

    def generate(self, request: UnifiedRequest) -> UnifiedResponse:
        """Return a deterministic response.

        `content` = ``f"[echo:{model}] {sha256(canonical_request)}"``

        The canonical request is a stable JSON serialisation of the
        REQUEST FIELDS ONLY (no clock reads, no secrets, no random
        state), so two identical requests always produce identical
        responses — the property tests rely on this.
        """

        if request.stream:
            raise UnsupportedCapabilityError(
                "streaming", self._config.provider,
                message=(
                    "EchoAdapter does not support streaming. Pass "
                    "`stream=False` or pick an adapter that declares "
                    "streaming=True."
                ),
            )

        canonical = json.dumps(
            request.model_dump(exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        text = f"[echo:{self._config.model}] {digest}"
        usage = Usage(
            input_tokens=len(canonical),
            output_tokens=len(text.encode("utf-8")),
        )
        return UnifiedResponse(
            content=text,
            tool_calls=[],
            finish_reason="stop",
            usage=usage,
            raw={
                "provider": self._config.provider,
                "model": self._config.model,
                "endpoint": self._config.endpoint,
                "request_sha256": digest,
            },
        )

    # ---- optional capabilities -------------------------------------

    def stream(self, request: UnifiedRequest) -> AsyncIterable[UnifiedEvent]:
        raise UnsupportedCapabilityError("streaming", self._config.provider)

    def batch(self, requests: list[UnifiedRequest]) -> BatchHandle:
        raise UnsupportedCapabilityError("batch", self._config.provider)
