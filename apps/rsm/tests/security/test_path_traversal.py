"""The FS store rejects traversal via mangled bucket IDs by replacing '/'."""
from rsm.daemon.store import FsStore


def test_bucket_id_with_slashes_is_sanitised(tmp_path):
    s = FsStore(tmp_path)
    p = s._path("../etc/passwd")  # noqa: SLF001 — testing the sanitiser
    # The sanitised path stays inside the store root
    assert tmp_path in p.parents
