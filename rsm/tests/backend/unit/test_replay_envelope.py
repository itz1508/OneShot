"""Replay envelope (spec §14)."""

from rsm.classification.model import WorkClassification
from rsm.extraction.text import extract_text
from rsm.replay.envelope import build_replay_envelope


def test_envelope_shape():
    b = extract_text("hi")
    env = build_replay_envelope(b, classification=WorkClassification.STORE)
    assert env["source"] == "rsm"
    assert env["bucket_id"] == b.bucket_id
    assert env["schema_version"] == "1"
    assert env["work_classification"] == "STORE"
    assert env["replayability"] in {"REPLAYABLE", "NOT_YET_REPLAYABLE"}
    assert env["content"]["full_content"] == "hi"
    assert env["integrity"]["algorithm"] == "sha256"
    assert len(env["integrity"]["value"]) == 64
