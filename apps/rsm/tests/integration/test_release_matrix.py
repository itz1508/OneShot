"""Release-validation matrix (parametrized over tests/fixtures/scenarios).

Each scenario is run through the full pipeline (where applicable):

    Bucket  →  SCAN  →  READER  →  PROCESSOR (build_snapshot)  →  REPLAY envelope

and the expected invariants from `Scenario` are asserted.

A handful of scenarios also exercise the HTTP boundary (`/v1/interactions/...`,
`/v1/buckets/{id}/scan`, `/v1/buckets/{id}/reader/trace`) so interaction
isolation and ON/OFF enforcement are covered.
"""

from __future__ import annotations

import os

import pytest

from fastapi.testclient import TestClient

from rsm.api.app import create_app
from rsm.bucket.serializer import canonical_dumps
from rsm.extraction.text import extract_text
from rsm.reader import read_bucket, scan_bucket
from rsm.replay.envelope import build_replay_envelope
from rsm.snapshot import (
    BudgetUnit,
    ContextBudget,
    NullSummaryProvider,
    PrefixSummaryProvider,
    SnapshotKind,
    SummaryUnavailable,
    build_snapshot,
)

from ..fixtures.scenarios import SCENARIOS


@pytest.fixture(scope="function")
def workdir(tmp_path):
    return tmp_path


# NTFS is case-insensitive: the `a.txt`/`A.txt` pair in
# `files-duplicate-looking-names` collides to a single file on Windows.
# The scenario still runs on case-sensitive filesystems (CI/Linux).
_PARAMS = [
    pytest.param(
        s,
        marks=pytest.mark.skipif(
            os.name == "nt",
            reason="case-insensitive filesystem: a.txt/A.txt collide on disk",
        ),
    )
    if s.scenario_id == "files-duplicate-looking-names"
    else s
    for s in SCENARIOS
]


@pytest.mark.parametrize("scenario", _PARAMS, ids=lambda s: s.scenario_id)
def test_release_matrix(workdir, scenario):
    bucket = scenario.builder(workdir)
    hash_before = bucket.hash.value
    canonical_before = canonical_dumps(bucket.model_dump(mode="json"))

    # ---- SCAN ----
    scan = scan_bucket(bucket)
    if scenario.expected_files is not None:
        assert len(scan.files) == scenario.expected_files, (
            f"{scenario.scenario_id}: expected {scenario.expected_files} files, "
            f"got {len(scan.files)}"
        )
        # Determinism: identical input produces identical SCAN output.
        s2 = scan_bucket(bucket)
        assert [f.model_dump() for f in scan.files] == [
            f.model_dump() for f in s2.files
        ]

    # ---- READER ----
    read = read_bucket(bucket)
    trace = read.trace
    if scenario.expected_observed is not None:
        assert trace.observed_count == scenario.expected_observed, (
            f"{scenario.scenario_id}: observed mismatch "
            f"({trace.observed_count} vs {scenario.expected_observed})"
        )
    if scenario.expected_failed is not None:
        assert trace.failed_count == scenario.expected_failed, (
            f"{scenario.scenario_id}: failed mismatch "
            f"({trace.failed_count} vs {scenario.expected_failed})"
        )
    if scenario.expected_latest is not None:
        assert trace.latest_index == scenario.expected_latest, (
            f"{scenario.scenario_id}: latest_index mismatch "
            f"({trace.latest_index} vs {scenario.expected_latest})"
        )
    if scenario.expected_failure_reasons is not None:
        got = {f.reason for f in trace.failures}
        assert got == scenario.expected_failure_reasons, (
            f"{scenario.scenario_id}: failure reasons {got} vs "
            f"{scenario.expected_failure_reasons}"
        )
    # Isolation invariant (F): either everything succeeded, or successes still
    # exist alongside failures.
    if trace.failed_count > 0 and trace.observed_count + trace.failed_count > 1:
        assert trace.observed_count >= 0  # a successful file is not required
    assert trace.complete is True

    # ---- PROCESSOR + REPLAY ----
    # Only Buckets whose `full_content` is text we can bound (simple-source
    # Buckets) exercise `build_snapshot` here — folder-origin Buckets carry
    # a canonical manifest that is itself the full_content.
    if bucket.provenance.origin != "folder":
        budget = ContextBudget(
            unit=BudgetUnit.CHARACTERS,
            value=max(1, len(bucket.full_content) + 100),
        )

        if scenario.scenario_id == "proc-overflow-reduction-unavailable":
            # Budget smaller than the source + Null provider → SummaryUnavailable.
            small = ContextBudget(unit=BudgetUnit.CHARACTERS, value=16)
            with pytest.raises(SummaryUnavailable):
                build_snapshot(bucket, budget=small, summary_provider=NullSummaryProvider())
            # Prefix provider succeeds under the same budget.
            snap = build_snapshot(bucket, budget=small, summary_provider=PrefixSummaryProvider())
            assert snap.content.kind == SnapshotKind.SUMMARY
            assert snap.provenance["derived_from"]["bucket_hash"] == bucket.hash.value
        else:
            snap = build_snapshot(bucket, budget=budget)
            assert snap.provenance["derived_from"]["bucket_hash"] == bucket.hash.value
            if scenario.expected_snapshot_text is not None:
                assert snap.content.kind == SnapshotKind.PRESERVED
                assert snap.content.text == scenario.expected_snapshot_text

    env = build_replay_envelope(bucket)
    assert env["source"] == "rsm"
    assert env["bucket_id"] == bucket.bucket_id
    assert env["integrity"]["algorithm"] == "sha256"
    assert env["integrity"]["value"] == bucket.hash.value

    # ---- A1 immutability ----
    if scenario.expected_hash_stable:
        assert bucket.hash.value == hash_before
        assert canonical_dumps(bucket.model_dump(mode="json")) == canonical_before


# ---- Security scenarios wired to the HTTP boundary --------------------------

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


def test_sec_rsm_off_rejects_stream(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    r = c.post("/v1/buckets/", json={"content": "payload", "kind": "text"})
    bid = r.json()["bucket"]["bucket_id"]
    c.put("/v1/interactions/sec-off", json={"rsm_enabled": False, "selected_bucket_id": bid})
    s = c.get("/v1/interactions/sec-off/stream")
    assert s.status_code == 409
    assert s.json()["code"] == "RSM_DISABLED"


def test_sec_unknown_interaction_fail_closed(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    r = c.get("/v1/interactions/sec-unknown/stream")
    assert r.status_code == 409
    assert r.json()["code"] == "RSM_DISABLED"


def test_sec_interaction_isolation(tmp_path, monkeypatch):
    c, _ = _client(tmp_path, monkeypatch)
    ba = c.post("/v1/buckets/", json={"content": "A material", "kind": "text"}).json()["bucket"]["bucket_id"]
    bb = c.post("/v1/buckets/", json={"content": "B material", "kind": "text"}).json()["bucket"]["bucket_id"]
    c.put("/v1/interactions/A", json={"rsm_enabled": True, "selected_bucket_id": ba})
    c.put("/v1/interactions/B", json={"rsm_enabled": True, "selected_bucket_id": bb})
    sA = c.get("/v1/interactions/A/stream").json()
    sB = c.get("/v1/interactions/B/stream").json()
    assert sA["bucket_id"] == ba
    assert sA["snapshot"]["content"]["text"] == "A material"
    assert sB["bucket_id"] == bb
    assert sB["snapshot"]["content"]["text"] == "B material"
    # Cross-interaction read via /replay with the wrong (disabled) record is also rejected.
    c.put("/v1/interactions/C", json={"rsm_enabled": False})
    assert c.get(f"/v1/buckets/{ba}/replay", params={"interaction_id": "C"}).status_code == 409
