"""Vision provider: Protocol + stdlib HTTP implementation.

HTTP shape is the standard chat-completions request body documented by:
  - NVIDIA NIM for VLMs 1.3.1
    docs.nvidia.com/nim/vision-language-models/1.3.1/examples/llama-nemotron-nano/api.html
  - NVIDIA hosted catalog
    https://integrate.api.nvidia.com/v1/chat/completions
  - Self-hosted vLLM-serve, SGLang-serve, TRT-LLM-serve

Image bytes are carried IN the request body as a base64 data URI
`data:<mime>;base64,<b64>`; the server never sees a filesystem path.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Optional, Protocol, runtime_checkable

from .model import VisionError, VisionResult, VisionUnavailable

# NIM VLM API doc: "Supported image formats are JPG, JPEG and PNG"
ALLOWED_MIMES = frozenset({"image/jpeg", "image/png"})

# NVIDIA does not publish per-request body-size caps — RSM-side guards.
DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024    # 8 MiB
DEFAULT_MAX_OUTPUT_CHARS = 32 * 1024         # 32 KiB cap on returned text
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_TOKENS = 1024


@runtime_checkable
class VisionProvider(Protocol):
    """Capability contract. Any implementation must obey the input bounds."""

    name: str

    def describe(
        self,
        *,
        image_bytes: bytes,
        mime: str,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> VisionResult: ...


class NullVisionProvider:
    """Explicit no-provider sentinel. Mirrors NullSummaryProvider.

    A Reader (or any other consumer) wired against this provider
    receives a `VisionUnavailable` and falls back to its existing
    honest failure path. This provider is deterministic, dependency-free,
    and safe as the default: it never performs network I/O.
    """

    name = "null"

    def describe(  # noqa: D401
        self,
        *,
        image_bytes: bytes,
        mime: str,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> VisionResult:
        raise VisionUnavailable(
            "No VisionProvider is configured; Vision cannot be used."
        )


class HttpChatVisionProvider:
    """Vision provider over a chat-completions HTTP endpoint.

    Instances carry endpoint + model + credential; one process may hold
    several of these for different endpoints. All I/O goes through
    `urllib.request` with a hard timeout; no third-party HTTP client,
    no vendor SDK, no LangChain.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        name: Optional[str] = None,
        max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.startswith(
            ("http://", "https://")
        ):
            raise VisionError(
                "input", f"base_url must start with http/https, got {base_url!r}"
            )
        if not isinstance(model, str) or not model.strip():
            raise VisionError("input", "model must be a non-empty string")
        if max_image_bytes <= 0:
            raise VisionError("input", "max_image_bytes must be positive")
        if max_output_chars <= 0:
            raise VisionError("input", "max_output_chars must be positive")

        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or ""
        self.max_image_bytes = int(max_image_bytes)
        self.max_output_chars = int(max_output_chars)
        # `name` is derived from endpoint host; never embed credentials.
        self.name = name or f"nim_http[{self.model}]"

    def describe(
        self,
        *,
        image_bytes: bytes,
        mime: str,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> VisionResult:
        if not isinstance(image_bytes, (bytes, bytearray)):
            raise VisionError("input", "image_bytes must be bytes")
        if mime not in ALLOWED_MIMES:
            raise VisionError(
                "input", f"mime {mime!r} not in {sorted(ALLOWED_MIMES)}"
            )
        if len(image_bytes) == 0:
            raise VisionError("input", "image_bytes is empty")
        if len(image_bytes) > self.max_image_bytes:
            raise VisionError(
                "limit",
                f"image size {len(image_bytes)} > max {self.max_image_bytes}",
            )
        if not isinstance(prompt, str) or not prompt.strip():
            raise VisionError("input", "prompt must be a non-empty string")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise VisionError("input", "max_tokens must be a positive integer")
        if not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise VisionError("input", "timeout_s must be a positive number")

        b64 = base64.b64encode(bytes(image_bytes)).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": int(max_tokens),
            "temperature": 0.0,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise VisionError(f"http_{e.code}", detail) from e
        except urllib.error.URLError as e:
            raise VisionError("network", str(e)) from e
        except Exception as e:  # noqa: BLE001 - last-resort transport guard
            raise VisionError("transport", f"{type(e).__name__}: {e}") from e

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise VisionError("malformed_json", str(e)) from e

        try:
            choice = obj["choices"][0]
            msg = choice["message"]
            text = msg.get("content") or ""
            if not isinstance(text, str):
                raise ValueError("content was not a string")
            finish = choice.get("finish_reason")
            usage = obj.get("usage") or {}
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise VisionError("malformed_response", str(e)) from e

        truncated = False
        if len(text) > self.max_output_chars:
            text = text[: self.max_output_chars]
            truncated = True

        return VisionResult(
            text=text,
            model=obj.get("model") or self.model,
            input_tokens=(
                usage.get("prompt_tokens") if isinstance(usage, dict) else None
            ),
            output_tokens=(
                usage.get("completion_tokens")
                if isinstance(usage, dict)
                else None
            ),
            finish_reason=finish,
            truncated=truncated,
        )


def observe_image(
    provider: VisionProvider,
    *,
    image_bytes: bytes,
    mime: str,
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> VisionResult:
    """Thin façade so consumers depend on the capability, not a class.

    Reader and the main Agent are both expected to call this function;
    neither of them should import `HttpChatVisionProvider` directly.
    """
    return provider.describe(
        image_bytes=image_bytes,
        mime=mime,
        prompt=prompt,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )
