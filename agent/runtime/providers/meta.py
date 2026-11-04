"""Meta Muse Spark provider — OpenAI-compatible SDK with credential hygiene."""

from __future__ import annotations

import os
from typing import Any

from agent.runtime.providers.base import (
    CapabilityDescriptor,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)


class MetaProvider:
    """Meta Muse Spark provider adapter.

    Uses the OpenAI Python SDK with Meta's compatible endpoint.
    Credentials are read at call time from the environment — never persisted.
    """

    PROVIDER_NAME = "meta"
    DEFAULT_BASE_URL = "https://api.meta.ai/v1"
    DEFAULT_MODEL = "muse-spark-1.3"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        credential_ref: str = "MODEL_API_KEY",
    ) -> None:
        self._base_url = base_url or os.environ.get("META_MODEL_BASE_URL") or self.DEFAULT_BASE_URL
        self._model = model or os.environ.get("META_MODEL_ID") or self.DEFAULT_MODEL
        self._credential_ref = credential_ref
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy import and client creation at call time."""
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ProviderError("openai SDK not installed (pip install 'oneshot[meta]')") from e
        key = os.environ.get(self._credential_ref)
        if not key:
            raise ProviderError(f"environment variable {self._credential_ref} not set")
        self._client = OpenAI(api_key=key, base_url=self._base_url)
        return self._client

    def generate(self, request: ProviderRequest) -> ProviderResult:
        """Generate using Meta Muse Spark."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.prompt},
            ]
            if request.system_prompt
            else [{"role": "user", "content": request.prompt}],
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        choice = response.choices[0]
        return ProviderResult(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason or "stop",
            usage=(
                {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                }
                if response.usage
                else {}
            ),
            provider=self.PROVIDER_NAME,
            model=self._model,
        )

    def declared_capabilities(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            structured_outputs=True,
            streaming=True,
            batch=False,
            prompt_caching=False,
            strict_tool_schemas=True,
        )
