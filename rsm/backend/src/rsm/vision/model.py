"""Vision capability DTOs. Pure data; no I/O; no framework.

Mirrors the small, bounded style of `rsm.reader.model` and
`rsm.snapshot.summary_provider`.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class VisionUnavailable(Exception):
    """Raised by NullVisionProvider when no real provider is configured.

    Reader is expected to translate this to its existing honest failure
    model (`FILE_FAILED(reason="vision_unavailable")`) rather than retry.
    """


class VisionError(Exception):
    """Structured capability failure. Carries a `kind` and `detail`.

    `kind` is one of:
        "input"              - caller supplied invalid arguments
        "limit"              - size cap exceeded before the call was made
        "network"            - transport failure (DNS, connect, timeout)
        "transport"          - unexpected non-HTTP transport failure
        "malformed_json"     - endpoint returned non-JSON
        "malformed_response" - JSON but missing choices[0].message.content
        "http_<code>"        - endpoint returned HTTP <code>; body in detail

    `detail` is a short, bounded string (never a traceback, never a credential).
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


class VisionResult(BaseModel):
    """Bounded textual visual observation.

    `text` is model output verbatim, bounded by the provider's
    `max_output_chars`. It is NEVER evaluated by this module; downstream
    consumers must treat it as inert text.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    text: str
    model: str = Field(..., min_length=1)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    truncated: bool = False
