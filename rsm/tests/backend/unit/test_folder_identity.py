"""A3 — folder manifest + per-source provenance."""

from pathlib import Path
import tempfile
from rsm.extraction.folder import extract_folder


def test_folder_manifest_counts_and_ordering():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "docs"
        (root / "sub").mkdir(parents=True)
        (root / "a.md").write_text("# a")
        (root / "b.txt").write_text("b-body")
        (root / "sub" / "c.md").write_text("# c")
        (root / "image.png").write_bytes(b"\x89PNG\r\n")
        (root / "weird.xyz").write_text("unsupported")

        res = extract_folder(root)

        m = res.manifest
        assert m["source_count"] == 3
        assert m["opaque_count"] == 1
        assert m["unsupported_count"] == 1
        assert m["skipped_permission_denied"] == 0
        assert m["deterministic_ordering"] == "sorted_posix_path_ascending"

        # Sorted by posix path
        supported = m["entries"]["supported"]
        assert supported == sorted(supported)

        # Parent hash is SHA-256 of canonical manifest
        assert len(res.parent.hash.value) == 64

        # Children all derive from parent
        assert all(c.provenance.derived_from == res.parent.bucket_id for c in res.children)
        assert len(res.children) == 3
