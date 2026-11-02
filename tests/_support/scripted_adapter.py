"""Scripted (replay) provider adapter for M3 fixture evaluation.

Design pins (reviewer directive 3):

* "Keep independently authored expected results separate from recorded model
  responses." This adapter returns the RECORDED model response for a given
  canonicalised request. The GOLDEN "what the output ought to be" lives in
  a separate directory (`tests/_support/golden/`) and is referenced from the
  fixture, NOT from the recording. The behavior axes assert the recording
  against the golden; the recording never grades itself.

* Lookup key = SHA-256 of `UnifiedRequest.model_dump(exclude_none=True)`
  with sort_keys + compact separators — same canonicalisation EchoAdapter
  uses, so a recording made against one is replayable by the other.

* Missing recording -> `KeyError` with the request hash in the message,
  not a silent fallback. Tests must opt into "unknown-request" behaviour
  explicitly by registering it.

* The adapter advertises the capabilities of the recorded responses,
  defaulting to the EchoAdapter capability set: `structured_outputs=True`,
  everything else `False`. Capabilities are overridable at construction
  for tests that need to assert the fail-closed path.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterable
from pathlib import Path

from agent.providers.base import (
    ProviderAdapter,
    UnsupportedCapabilityError,
)
from agent.providers.types import (
    BatchHandle,
    ProviderCapabilities,
    ProviderConfig,
    UnifiedEvent,
    UnifiedRequest,
    UnifiedResponse,
    Usage,
)


def canonical_request_sha256(request: UnifiedRequest) -> str:
    """Deterministic SHA-256 of a UnifiedRequest's canonical JSON form."""
    canonical = json.dumps(
        request.model_dump(exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class ScriptedAdapter(ProviderAdapter):
    """Replay adapter: canonical-request-hash -> pre-recorded UnifiedResponse.

    Two sources of recordings:
      (1) `recordings` dict kwarg — maps request_sha256 -> UnifiedResponse (or
          dict kwargs for one). Useful for inline tests.
      (2) `recordings_dir` — directory of JSON files named `<request_sha256>.json`.
          Each file contains a UnifiedResponse-shaped dict. Lets integration
          tests version-control the recordings.

    Lookup order is (1) first, then (2). The two sources never overlap in
    practice because the key is a content hash; a collision would mean two
    identical requests have different recorded answers, which is a bug.
    """

    PROVIDER_KEY = "scripted"

    def __init__(
        self,
        config: ProviderConfig,
        *,
        recordings: dict[str, UnifiedResponse | dict] | None = None,
        recordings_dir: str | Path | None = None,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        if not isinstance(config, ProviderConfig):
            raise TypeError(
                f"ScriptedAdapter requires a ProviderConfig; got {type(config).__name__}"
            )
        self._config = config
        self._recordings: dict[str, UnifiedResponse] = {}
        if recordings:
            for key, value in recordings.items():
                self._recordings[key] = (
                    value if isinstance(value, UnifiedResponse)
                    else UnifiedResponse.model_validate(value)
                )
        self._recordings_dir = Path(recordings_dir) if recordings_dir else None
        self._capabilities = capabilities or ProviderCapabilities(
            structured_outputs=True
        )

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def generate(self, request: UnifiedRequest) -> UnifiedResponse:
        if request.stream:
            raise UnsupportedCapabilityError(
                "streaming", self._config.provider,
                message="ScriptedAdapter does not support streaming.",
            )
        key = canonical_request_sha256(request)
        if key in self._recordings:
            recorded = self._recordings[key]
        elif self._recordings_dir and (self._recordings_dir / f"{key}.json").is_file():
            raw = json.loads(
                (self._recordings_dir / f"{key}.json").read_text(encoding="utf-8")
            )
            recorded = UnifiedResponse.model_validate(raw)
        else:
            raise KeyError(
                f"ScriptedAdapter: no recording for request_sha256={key!r}. "
                "Record the response (recordings= kwarg or recordings_dir file) "
                "before running the test."
            )
        # Overlay provider/model into raw so the runner captures them.
        raw = dict(recorded.raw or {})
        raw.setdefault("provider", self._config.provider)
        raw.setdefault("model", self._config.model)
        raw["request_sha256"] = key
        return UnifiedResponse(
            content=recorded.content,
            tool_calls=list(recorded.tool_calls or []),
            finish_reason=recorded.finish_reason,
            usage=recorded.usage or Usage(),
            raw=raw,
        )

    def register_recording(self, request: UnifiedRequest, response: UnifiedResponse) -> str:
        """Convenience for tests that build (request, response) pairs inline."""
        key = canonical_request_sha256(request)
        self._recordings[key] = response
        return key

    def stream(self, request: UnifiedRequest) -> AsyncIterable[UnifiedEvent]:
        raise UnsupportedCapabilityError("streaming", self._config.provider)

    def batch(self, requests: list[UnifiedRequest]) -> BatchHandle:
        raise UnsupportedCapabilityError("batch", self._config.provider)


__all__ = ["ScriptedAdapter", "canonical_request_sha256"]
