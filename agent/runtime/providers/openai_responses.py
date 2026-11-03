"""OpenAI Responses API adapter."""

from __future__ import annotations

from typing import Any

from agent.contracts.provider import ProviderConfig
from agent.runtime.provider_config import resolve_api_key, resolve_base_url, resolve_model


class OpenAIResponsesAdapter:
    """Adapter for the OpenAI Responses API."""

    def __init__(self, c: ProviderConfig, client: Any | None = None) -> None:
        self.config = c
        self.model_id = resolve_model(c)
        if client is not None:
            self.client = client
            return
        from openai import OpenAI

        kw: dict[str, Any] = {
            "api_key": resolve_api_key(c),
            "timeout": c.timeout_seconds,
            "max_retries": c.max_retries,
        }
        url = resolve_base_url(c)
        if url:
            kw["base_url"] = url
        self.client = OpenAI(**kw)

    def response(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> str:
        """Send a Responses API request and return the output text."""
        return self.client.responses.create(model=self.model_id, input=prompt, tools=tools or []).output_text  # type: ignore[no-any-return]
