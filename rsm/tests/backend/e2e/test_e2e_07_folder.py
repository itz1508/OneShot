"""A3 end-to-end."""
from pathlib import Path
import tempfile
from rsm.extraction.folder import extract_folder


def test_folder_end_to_end():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "docs"
        root.mkdir()
        (root / "a.md").write_text("# a")
        (root / "b.txt").write_text("b")
        res = extract_folder(root)
        assert res.parent.provenance.origin == "folder"
        assert res.manifest["source_count"] == 2
