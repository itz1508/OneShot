"""rsm.vision — small, framework-independent Vision capability.

Boundaries (same discipline as `rsm.snapshot.summary_provider`):

    VisionProvider           — Protocol: image bytes + prompt → bounded text.
    VisionResult             — Pydantic DTO carrying the bounded observation.
    VisionError              — Structured capability failure (never raised silently).
    VisionUnavailable        — Explicit no-provider sentinel.
    NullVisionProvider       — Default: raises VisionUnavailable.
    HttpChatVisionProvider — Reference adapter against a chat-completions
                               /v1/chat/completions endpoint
                               (NVIDIA NIM, hosted integrate.api.nvidia.com,
                                self-hosted vLLM / SGLang / TRT-LLM-serve).

This package is a Vision **capability**, not an application. It:

  * never imports an Agent SDK, LangChain, vendor SDK, Strands, or MCP;
  * uses only stdlib (urllib.request, base64, json, dataclasses) + pydantic;
  * never evaluates model output — the returned text is always a string;
  * never writes to disk; never shells out; never fetches arbitrary URLs
    (image bytes travel as a base64 data URI in the request body).

Consumers (Reader, main Agent, tests, ad-hoc tools) depend on
`VisionProvider` / `observe_image` and are free to supply any implementation.
This package does NOT decide when it is invoked; it only exposes the shape.
"""

from .model import (
    VisionError,
    VisionResult,
    VisionUnavailable,
)
from .provider import (
    ALLOWED_MIMES,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_TIMEOUT_S,
    HttpChatVisionProvider,
    NullVisionProvider,
    VisionProvider,
    observe_image,
)

__all__ = [
    "ALLOWED_MIMES",
    "DEFAULT_MAX_IMAGE_BYTES",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_TIMEOUT_S",
    "HttpChatVisionProvider",
    "NullVisionProvider",
    "VisionError",
    "VisionProvider",
    "VisionResult",
    "VisionUnavailable",
    "observe_image",
]
