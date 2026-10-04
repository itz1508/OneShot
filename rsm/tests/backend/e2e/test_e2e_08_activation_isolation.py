from rsm.daemon.service import DaemonService
from rsm.daemon.store import FsStore
from rsm.daemon.eventlog import EventLog


def test_activation_moves_only_state(tmp_path):
    d = DaemonService(FsStore(tmp_path / "b"), EventLog(tmp_path / "e.log"))
    b = d.ingest_text("hi")
    d.transition(b.bucket_id, "STAGED")
    d.transition(b.bucket_id, "STORED")
    bucket = d.transition(b.bucket_id, "ACTIVATED")
    assert bucket.state == "ACTIVATED"
    # Content stays frozen
    assert bucket.full_content == "hi"
