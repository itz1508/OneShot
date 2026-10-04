"""Processor contract freeze tests (RSM V3 — invariants A..G).

These tests are deliberately small. They freeze the boundary without
inflating the codebase.

A. Source immutability — Bucket.hash is unchanged after scan / read /
   snapshot / replay-envelope.
B. Prepared representation stays derived — Snapshot.provenance.derived_from
   .bucket_hash matches the live Bucket.hash.value.
C. Replay delivers unchanged — the stream payload's `snapshot.content.text`
   equals the Snapshot the daemon built directly from the Bucket; the
   stream payload's `replay.integrity.value` equals Bucket.hash.value.
D. Reader output is RSM-sourced, not Agent output — replay envelope stamps
   source="rsm" with provenance; Reader produces events bound to the
   authoritative Bucket (never an Agent-generated derivation).
E. Agent/provider boundary — grep every module file under rsm/ for
   forbidden SDK names; also confirm rsm.reader / rsm.snapshot /
   rsm.replay / rsm.interaction do not import any provider SDK (reinforces
   `backend/tools/check_forbidden_deps.py`).
F. Reader failure isolation — one failed File must not fail the whole
   Reader operation; already covered by test_reader.py; this freezes the
   invariant text.
G. Browser authority — the authority-fields (`latest_index`, `discovered`,
   `failures`) are produced by `rsm.reader.ReaderTrace`; no frontend
   source derives them from timers / fake progress.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rsm.api.app import create_app
from rsm.bucket.serializer import canonical_dumps
from rsm.extraction.text import extract_text
from rsm.reader import read_bucket, scan_bucket
from rsm.replay.envelope import build_replay_envelope
from rsm.snapshot import BudgetUnit, ContextBudget, PrefixSummaryProvider, build_snapshot


# ---- A — Source immutability ----

def test_A_bucket_hash_unchanged_after_scan_read_snapshot_replay():
    b = extract_text("the authoritative source material", source_uri="demo.txt")
    before_hash = b.hash.value
    before_bytes = canonical_dumps(b.model_dump(mode="json"))

    # SCAN
    _ = scan_bucket(b)
    # READER
    _ = read_bucket(b)
    # PROCESSOR (Snapshot build)
    budget = ContextBudget(unit=BudgetUnit.CHARACTERS, value=200)
    snap = build_snapshot(b, budget=budget, summary_provider=PrefixSummaryProvider())
    _ = snap
    # REPLAY envelope
    _ = build_replay_envelope(b)

    assert b.hash.value == before_hash
    assert canonical_dumps(b.model_dump(mode="json")) == before_bytes


# ---- B — Prepared representation is derived ----

def test_B_snapshot_provenance_matches_bucket_hash():
    b = extract_text("source body")
    snap = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=200))
    assert snap.provenance["derived_from"]["kind"] == "rsm_bucket"
    assert snap.provenance["derived_from"]["bucket_id"] == b.bucket_id
    assert snap.provenance["derived_from"]["bucket_hash"] == b.hash.value


# ---- C — Replay delivers unchanged ----

def _client(tmp_path, monkeypatch):
    from rsm.daemon import service as svc
    from rsm.daemon.eventlog import EventLog
    from rsm.daemon.store import FsStore
    from rsm.interaction.store import InteractionStore

    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "buckets"),
        eventlog=EventLog(tmp_path / "events.log"),
        interactions=InteractionStore(),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)
    return TestClient(create_app()), daemon


def test_C_replay_does_not_transform_prepared_representation(tmp_path, monkeypatch):
    c, daemon = _client(tmp_path, monkeypatch)
    r = c.post("/v1/buckets/", json={"content": "payload", "kind": "text"})
    bid = r.json()["bucket"]["bucket_id"]
    c.put(
        "/v1/interactions/i-1",
        json={"rsm_enabled": True, "selected_bucket_id": bid},
    )
    stream = c.get(
        "/v1/interactions/i-1/stream",
        params={"budget_unit": "characters", "budget_value": 1000},
    )
    assert stream.status_code == 200
    body = stream.json()

    # Replay envelope's integrity is the authoritative Bucket.hash — unchanged.
    bucket = daemon.store.read(bid)
    assert bucket is not None
    assert body["replay"]["integrity"]["algorithm"] == "sha256"
    assert body["replay"]["integrity"]["value"] == bucket.hash.value

    # The snapshot delivered by the stream has the SAME content.text as
    # a freshly-built Snapshot of the same Bucket + budget. The stream
    # does not transform; the Snapshot is the prepared representation.
    direct = build_snapshot(
        bucket, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=1000)
    )
    assert body["snapshot"]["content"]["text"] == direct.content.text
    assert body["snapshot"]["content"]["kind"] == direct.content.kind.value
    assert (
        body["snapshot"]["provenance"]["derived_from"]["bucket_hash"]
        == direct.provenance["derived_from"]["bucket_hash"]
    )


# ---- D — Reader output is RSM-sourced, not Agent output ----

def test_D_reader_envelope_source_is_rsm():
    b = extract_text("not agent output")
    env = build_replay_envelope(b)
    assert env["source"] == "rsm"
    # The replay envelope projects authoritative bucket fields verbatim.
    assert env["content"]["full_content"] == b.full_content
    # Nothing in Reader output claims to be Agent output.
    r = read_bucket(b)
    assert all(ev.file_id.startswith(b.bucket_id) for ev in r.events)


# ---- E — Agent/provider boundary ----

_RSM_SRC = Path(__file__).resolve().parents[3] / "backend" / "src" / "rsm"
_FORBIDDEN = (
    "openai", "anthropic", "google.generativeai", "cohere", "mistralai",
    "together", "fireworks", "nebius", "ollama", "langchain", "langgraph",
    "llama_index", "llamaindex", "haystack", "dspy", "crewai", "autogen",
    "pydantic_ai", "pydanticai",
)


def test_E_no_agent_sdk_in_rsm_core_modules():
    assert _RSM_SRC.is_dir(), _RSM_SRC
    for p in _RSM_SRC.rglob("*.py"):
        text = p.read_text("utf-8")
        for bad in _FORBIDDEN:
            assert bad not in text, f"{p}: references {bad!r}"


def test_E_processor_modules_do_not_import_providers():
    for subpkg in ("reader", "snapshot", "replay", "interaction"):
        base = _RSM_SRC / subpkg
        for p in base.rglob("*.py"):
            text = p.read_text("utf-8")
            for bad in _FORBIDDEN:
                assert bad not in text, f"{p}: references {bad!r}"


# ---- F — Reader failure isolation (invariant freeze) ----

def test_F_reader_isolation_invariant_text_is_frozen(tmp_path):
    # The invariant: ONE_FILE_FAILURE != WHOLE_READER_FAILURE.
    from rsm.extraction.folder import extract_folder

    root = tmp_path / "r"
    root.mkdir()
    (root / "ok.txt").write_text("fine")
    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # opaque
    res = extract_folder(root)
    r = read_bucket(res.parent)
    assert r.trace.complete is True
    assert r.trace.observed_count >= 1
    assert r.trace.failed_count >= 1
    # Successful observations survive the per-file failure.
    assert any(c.status.value == "OBSERVED" for c in r.trace.coverage)


# ---- G — Browser is not authoritative ----

def test_G_authority_fields_originate_in_backend():
    # The authority-fields latest_index, discovered, and failures[*] must be
    # emitted by the Python ReaderTrace model, not derived from timers in TS.
    b = extract_text("one file source")
    r = read_bucket(b)
    for field in ("latest_index", "discovered", "failures"):
        assert field in r.trace.model_dump(mode="json")


def test_G_frontend_has_no_fake_progress_timer():
    # Belt-and-suspenders grep: the frontend trace surface must not invent
    # progress via setInterval/setTimeout against latest_index. Polling the
    # backend trace endpoint on an interval IS allowed (and is how the
    # real surface stays live) — what we forbid is a timer that advances
    # `latest_index` locally.
    web = Path(__file__).resolve().parents[3] / "frontend" / "web" / "src"
    offenders: list[str] = []
    for p in web.rglob("*.tsx"):
        text = p.read_text("utf-8")
        # Fake-progress patterns: anything that assigns latest_index from a
        # local counter rather than from the API response.
        if "latest_index +" in text or "latest_index++" in text:
            offenders.append(str(p))
        if "latestIndex +" in text or "latestIndex++" in text:
            offenders.append(str(p))
    assert offenders == [], offenders
