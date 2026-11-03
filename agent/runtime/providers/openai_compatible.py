"""OpenAI-compatible adapter for native OpenAI and verified compatible endpoints."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, TypeVar

from pydantic import BaseModel

from agent.contracts.provider import ProviderConfig
from agent.runtime.provider_config import resolve_api_key, resolve_base_url, resolve_model
from agent.runtime.streaming import StreamEvent, StreamEventType

T = TypeVar("T", bound=BaseModel)


class OpenAICompatibleAdapter:
    """One adapter for native OpenAI and verified OpenAI-compatible endpoints."""

    def __init__(self, config: ProviderConfig, client: Any | None = None) -> None:
        self.config = config
        self.model_id = resolve_model(config)
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install provider dependencies with uv sync") from exc
        kwargs: dict[str, Any] = {
            "api_key": resolve_api_key(config),
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if base_url := resolve_base_url(config):
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def chat(self, messages: list[dict[str, Any]]) -> Any:
        """Send a chat completion request."""
        return self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            **self.config.options.get("chat", {}),
        )

    def stream(self, messages: list[dict[str, Any]]) -> Iterator[StreamEvent]:
        """Stream a chat completion with usage events."""
        chunks = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **self.config.options.get("streaming", {}),
        )
        for chunk in chunks:
            usage = getattr(chunk, "usage", None)
            if usage:
                yield StreamEvent(
                    StreamEventType.USAGE,
                    self.config.provider_id,
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                )
            choices = getattr(chunk, "choices", [])
            if choices and (content := getattr(choices[0].delta, "content", None)):
                yield StreamEvent(
                    StreamEventType.TEXT_DELTA,
                    self.config.provider_id,
                    content=content,
                )
        yield StreamEvent(StreamEventType.COMPLETED, self.config.provider_id)

    def structured_output(self, prompt: str, output_model: type[T]) -> T:
        """Request a structured output response parsed into a Pydantic model."""
        parse = getattr(self.client.chat.completions, "parse", None)
        if parse is not None:
            response = parse(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                response_format=output_model,
                **self.config.options.get("structured_output", {}),
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise RuntimeError("Provider returned no parsed structured output")
            return parsed  # type: ignore[no-any-return]
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            **self.config.options.get("structured_output", {}),
        )
        return output_model.model_validate_json(response.choices[0].message.content)

    def tool_roundtrip(self, prompt: str, tool_schema: dict[str, Any], executor: Any) -> str:
        """Execute a tool-calling roundtrip: prompt -> tool call -> result -> final."""
        messages: list[Any] = [{"role": "user", "content": prompt}]
        tools = [{"type": "function", "function": tool_schema}]
        first = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            **self.config.options.get("tool_calling", {}),
        )
        message = first.choices[0].message
        if not message.tool_calls:
            raise RuntimeError("Provider did not request the tool")
        messages.append(message)
        for call in message.tool_calls:
            arguments = json.loads(call.function.arguments)
            result = executor(call.function.name, arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )
        final = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            tools=tools,
            **self.config.options.get("tool_calling", {}),
        )
        content = final.choices[0].message.content
        if not content:
            raise RuntimeError("Provider returned no final tool result")
        return content  # type: ignore[no-any-return]

    def vision(self, prompt: str, image_url: str) -> str:
        """Send a vision request with text and image."""
        response = self.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ]
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Provider returned no vision result")
        return content  # type: ignore[no-any-return]

    def response(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> Any:
        """Send a Responses API request."""
        return self.client.responses.create(
            model=self.model_id,
            input=prompt,
            tools=tools or [],
            **self.config.options.get("responses", {}),
        )
