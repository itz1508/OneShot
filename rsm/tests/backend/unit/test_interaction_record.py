"""V3 — InteractionRecord unit tests (ADR 0009)."""

from datetime import datetime, timezone

from rsm.interaction.model import DEFAULT_INTERACTION, InteractionRecord
from rsm.interaction.store import InteractionStore


def test_default_is_fail_closed():
    rec = DEFAULT_INTERACTION("x")
    assert rec.interaction_id == "x"
    assert rec.rsm_enabled is False
    assert rec.selected_bucket_id is None
    assert rec.last_streamed_at is None


def test_store_read_unknown_returns_default_without_persisting():
    s = InteractionStore()
    r = s.get("i-1")
    assert r.rsm_enabled is False
    assert s.exists("i-1") is False


def test_store_put_persists():
    s = InteractionStore()
    s.put(InteractionRecord(interaction_id="i-1", rsm_enabled=True, selected_bucket_id="bkt_x"))
    r = s.get("i-1")
    assert r.rsm_enabled is True
    assert r.selected_bucket_id == "bkt_x"
    assert s.exists("i-1") is True


def test_with_update_preserves_identity():
    r = InteractionRecord(interaction_id="i-1", rsm_enabled=False)
    r2 = r.with_update(rsm_enabled=True)
    assert r.rsm_enabled is False  # original unchanged
    assert r2.rsm_enabled is True
    assert r2.interaction_id == "i-1"


def test_with_update_unset_bucket():
    r = InteractionRecord(interaction_id="i-1", rsm_enabled=True, selected_bucket_id="bkt_x")
    r2 = r.with_update(unset_selected_bucket_id=True)
    assert r2.selected_bucket_id is None


def test_mark_streamed_updates_only_known_record():
    s = InteractionStore()
    assert s.mark_streamed("missing") is None
    s.put(InteractionRecord(interaction_id="i-1", rsm_enabled=True))
    r = s.mark_streamed("i-1")
    assert r is not None
    assert r.last_streamed_at is not None
    assert r.last_streamed_at.tzinfo is timezone.utc or r.last_streamed_at.utcoffset() is not None
    assert isinstance(r.last_streamed_at, datetime)


def test_extra_fields_rejected():
    import pydantic
    try:
        InteractionRecord(interaction_id="i-1", unknown_field="x")
    except pydantic.ValidationError:
        return
    raise AssertionError("extra fields should be rejected")
