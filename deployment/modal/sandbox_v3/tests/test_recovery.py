import pytest

from modal_build_sandbox.recovery import AttemptStore


def test_durable_precreate_and_cas(tmp_path):
    path = tmp_path / "attempts.sqlite"
    db = AttemptStore(path)
    assert db.start("o", "a", "sandbox-a")["state"] == "INTENT_RECORDED"
    with pytest.raises(ValueError, match="duplicate"):
        db.start("o", "a", "sandbox-a")
    db.transition("o", "a", "INTENT_RECORDED", "SANDBOX_CREATED", sandbox_id="sb-1")
    with pytest.raises(ValueError, match="stale"):
        db.transition("o", "a", "INTENT_RECORDED", "INPUT_UPLOADED")
    fresh = AttemptStore(path)
    assert fresh.get("o", "a")["sandbox_id"] == "sb-1"
    assert len(fresh.unresolved()) == 1
    assert [r["state"] for r in fresh.transitions("o", "a")] == ["INTENT_RECORDED", "SANDBOX_CREATED"]
