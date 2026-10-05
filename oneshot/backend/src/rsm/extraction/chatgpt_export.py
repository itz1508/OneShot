"""ChatGPT export extractor — stdlib json only; produces a canonical bucket.

The vendor's export JSON is parsed with stdlib json, converted into a
canonical RSM shape, and the original messages are preserved verbatim
inside full_content so that §E2E-05 round-trip can read them back.
No vendor SDK is installed or imported.
"""

from __future__ import annotations

import json
from typing import Any

from ..bucket.model import Bucket
from ._common import build_bucket


def extract_chatgpt_export(
    raw: str | bytes | dict[str, Any],
    *,
    source_uri: str | None = None,
) -> Bucket:
    if isinstance(raw, (str, bytes)):
        parsed = json.loads(raw)
    else:
        parsed = raw

    # Preserve exact export bytes under full_content so the bucket owns the
    # vendor payload verbatim (RSM speaks its own schema; the raw export is
    # the material).
    full_content = json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    metadata = {"vendor": "chatgpt_export"}
    if isinstance(parsed, dict):
        for key in ("title", "model", "create_time", "update_time"):
            if key in parsed:
                metadata[key] = parsed[key]
        conv = parsed.get("conversation") or parsed.get("messages")
        if isinstance(conv, list):
            metadata["message_count"] = len(conv)

    return build_bucket(
        origin="chatgpt_export",
        full_content=full_content,
        source_uri=source_uri,
        metadata=metadata,
    )
