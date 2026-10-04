"""stdout transport emits canonical JSON bytes."""

import io
import sys
import json

from rsm.extraction.text import extract_text
from rsm.transports.canonical import build_payload
from rsm.transports.stdout import to_stdout


def test_to_stdout_emits_canonical_json(monkeypatch):
    buf = io.BytesIO()

    class _OutShim:
        buffer = buf
        def flush(self): pass

    monkeypatch.setattr(sys, "stdout", _OutShim())
    b = extract_text("stdout test")
    payload = build_payload(b)
    to_stdout(payload)
    data = buf.getvalue()
    assert data.endswith(b"\n")
    body = json.loads(data.rstrip(b"\n"))
    assert body["schema_version"] == "1"
    assert body["bucket"]["bucket_id"] == b.bucket_id
    assert body["integrity"]["sha256"] == b.hash.value
