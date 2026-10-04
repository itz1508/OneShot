from rsm.daemon.service import DaemonService
from rsm.daemon.store import FsStore
from rsm.daemon.eventlog import EventLog


def test_replay_leaves_content_frozen(tmp_path):
    d = DaemonService(FsStore(tmp_path / "b"), EventLog(tmp_path / "e.log"))
    b = d.ingest_text("hi")
    for to in ("STAGED", "STORED", "ACTIVATED", "REPLAYED"):
        d.transition(b.bucket_id, to)
    bucket = d.store.read(b.bucket_id)
    assert bucket.state == "REPLAYED"
    assert bucket.full_content == "hi"
