"""Baseten OpenAI-compatible provider adapter.

The Baseten inference service speaks the OpenAI JSON contract on
``https://inference.baseten.co/v1``. We reuse the ``openai`` SDK —
same wire format — but add Baseten-specific key handling:

Credential hygiene (reviewer rule, strict)
------------------------------------------
* The adapter does NOT store the key as a class/instance attribute.
* The adapter reads the key from ``config.api_key_file`` at
  ``.generate()`` call time, passes it as a function-local ``str`` to
  the ``openai.OpenAI(...)`` client, and dereferences the local
  immediately after dispatch. No long-lived in-memory copy.
* Nothing is written to disk — the key file is read with mode ``r``
  only; no local cache file is created.
* ``api_key_env`` is honoured as an alternative: the environment is
  read directly at call time and NOT snapshotted.

Capabilities
------------
The adapter advertises ``structured_outputs=True`` because the Judge
contract requires it; we honour ``UnifiedRequest.output_schema`` by
appending a strict schema-mention system message AND setting
``response_format={"type": "json_object"}``. The schema itself is
rendered JSON-canonicalised so the model sees a deterministic
prompt.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from agent.providers.base import (
    ProviderAdapter,
    UnsupportedCapabilityError,
    UnsupportedProviderError,
)
from agent.providers.registry import ProviderRegistry
from agent.providers.types import (
    BatchHandle,
    Message,
    ProviderCapabilities,
    ProviderConfig,
    UnifiedRequest,
    UnifiedResponse,
    Usage,
)

BASETEN_BASE_URL = "https://inference.baseten.co/v1"


class BasetenAdapter(ProviderAdapter):
    """ProviderAdapter that routes to Baseten's OpenAI-compat endpoint.

    Construction expects ``config.provider == "baseten"`` and one of:
      * ``config.credential_ref`` — the FILESYSTEM PATH to a file
        whose first non-blank line is the API key (e.g.
        ``/files/ppf.XYZ``), OR
      * ``config.credential_env`` — the name of an environment
        variable holding the key.

    Reading from the environment is a convenience path for the Judge
    config's ``api_key_env`` fallback. The reviewer's hygiene rules
    apply to both: no snapshot, no cache, read at call time.
    """

    PROVIDER_KEY = "baseten"

    def __init__(self, config: ProviderConfig):
        if not isinstance(config, ProviderConfig):
            raise TypeError(
                "BasetenAdapter requires a ProviderConfig; got "
                f"{type(config).__name__}"
            )
        if config.provider != "baseten":
            raise ValueError(
                f"BasetenAdapter: provider must be 'baseten'; got "
                f"{config.provider!r}"
            )
        self._config = config
        # Base URL comes from ProviderConfig.endpoint, defaulting to the
        # public Baseten endpoint. Never store the key.
        self._base_url = (config.endpoint or BASETEN_BASE_URL)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            batch=False,
            prompt_caching=False,
            strict_tool_schemas=False,
            extensions=["custom_endpoint"],
        )

    def generate(self, request: UnifiedRequest) -> UnifiedResponse:
        caps = self.capabilities()
        if request.stream and not caps.streaming:
            raise UnsupportedCapabilityError("streaming", self.PROVIDER_KEY)

        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise UnsupportedProviderError(
                "'openai' SDK is not installed; pip install 'openai>=1.0' "
                "to enable the BasetenAdapter."
            ) from exc

        # ----- credential hygiene -----
        api_key = self._read_api_key_at_call_time()
        if not api_key:
            raise UnsupportedProviderError(
                "BasetenAdapter: credential resolution produced an empty "
                "key. Check config.credential_ref / credential_env."
            )

        client = OpenAI(base_url=self._base_url, api_key=api_key)
        # Zero out the local ASAP. Python can't force immediate memory
        # scrubbing, but we at least drop the reference so the key is
        # eligible for GC the moment the OpenAI client finishes with it.
        api_key = ""  # noqa: F841 - deliberate dereference

        # ----- translate UnifiedRequest -----
        oai_messages = [_to_oai_message(m) for m in request.messages]
        kwargs: dict[str, Any] = {
            "model": _resolve_model(request, self._config),
            "messages": oai_messages,
        }
        if request.temperature is not None:
            kwargs["temperature"] = float(request.temperature)
        if request.max_tokens is not None:
            kwargs["max_tokens"] = int(request.max_tokens)

        # Structured outputs — honour UnifiedRequest.output_schema by
        # (a) telling the model to emit JSON matching the schema, and
        # (b) setting response_format={"type":"json_object"}. We do
        # NOT use "json_schema" response_format because Baseten/muse-
        # spark may not support it; the json_object fallback is the
        # OpenAI-wire-level universal.
        if request.output_schema is not None:
            schema_text = json.dumps(
                request.output_schema, sort_keys=True, separators=(",", ":")
            )
            # Append the schema instruction as a FINAL system message
            # so it dominates earlier instructions. We don't mutate
            # the caller's list.
            oai_messages = [
                *oai_messages,
                {
                    "role": "system",
                    "content": (
                        "Return ONLY a JSON object that validates against "
                        f"this schema: {schema_text}"
                    ),
                },
            ]
            kwargs["messages"] = oai_messages
            kwargs["response_format"] = {"type": "json_object"}

        # ----- dispatch -----
        completion = client.chat.completions.create(**kwargs)

        # ----- normalise response -----
        choice = completion.choices[0]
        content = choice.message.content or ""
        finish_reason = _normalise_finish_reason(choice.finish_reason)
        usage = _normalise_usage(completion)
        return UnifiedResponse(
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            raw={
                "model": getattr(completion, "model", kwargs["model"]),
                "id": getattr(completion, "id", ""),
            },
        )

    # ------------------------------------------------------------------
    # Optional capabilities (declared False) — explicit refusal.
    # ------------------------------------------------------------------

    def stream(self, request: UnifiedRequest):  # type: ignore[override]
        raise UnsupportedCapabilityError("streaming", self.PROVIDER_KEY)

    def batch(self, requests: list[UnifiedRequest]) -> BatchHandle:
        raise UnsupportedCapabilityError("batch", self.PROVIDER_KEY)

    # ------------------------------------------------------------------
    # Credential resolution — reader-at-call-time, no persistence.
    # ------------------------------------------------------------------

    def _read_api_key_at_call_time(self) -> str:
        """Resolve the API key WITHOUT caching it.

        ``config.credential_ref`` is interpreted as either:
          * a filesystem path (first non-blank line is the key) when it
            looks like a path, or
          * an environment variable name otherwise.
        """
        ref = (self._config.credential_ref or "").strip()
        if not ref:
            return ""
        if _looks_like_path(ref):
            try:
                text = Path(ref).read_text(encoding="utf-8")
            except OSError:
                return ""
            for line in text.splitlines():
                s = line.strip()
                if s:
                    return s
            return ""
        return os.environ.get(ref, "").strip()


def _looks_like_path(value: str) -> bool:
    return value.startswith("/") or ("/" in value and " " not in value)


def _to_oai_message(m: Message) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": m.role, "content": m.content}
    return msg


def _resolve_model(request: UnifiedRequest, config: ProviderConfig) -> str:
    """Pick the model name for this call.

    Priority: ``request.metadata['judge_model']`` (set by LLMJudge) →
    ``config.model`` (set at ProviderConfig construction) → raise.
    """
    judge_model = (request.metadata or {}).get("judge_model")
    if isinstance(judge_model, str) and judge_model:
        return judge_model
    cfg_model = getattr(config, "model", None)
    if isinstance(cfg_model, str) and cfg_model:
        return cfg_model
    raise ValueError(
        "BasetenAdapter.generate: no model specified. Pass model via "
        "UnifiedRequest.metadata['judge_model'] or ProviderConfig.model."
    )


def _normalise_finish_reason(
    reason: str | None,
) -> Literal["stop", "length", "tool_calls", "content_filter", "error"]:
    if reason == "length":
        return "length"
    if reason in ("tool_calls", "function_call"):
        return "tool_calls"
    if reason == "content_filter":
        return "content_filter"
    return "stop"


def _normalise_usage(completion: Any) -> Usage:
    """Pull token counts from the OpenAI-shaped usage block."""
    usage = getattr(completion, "usage", None)
    if usage is None:
        return Usage()
    return Usage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


# Register with the ProviderRegistry so ProviderRegistry.create(cfg) works.
ProviderRegistry.register("baseten", BasetenAdapter)


__all__ = ["BasetenAdapter", "BASETEN_BASE_URL"]
