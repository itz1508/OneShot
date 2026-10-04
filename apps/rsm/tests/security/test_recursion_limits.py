"""The folder extractor records max_depth_observed and respects os.walk depth."""
from pathlib import Path
import tempfile
from rsm.extraction.folder import extract_folder


def test_max_depth_observed():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "deep"
        p = root
        for i in range(5):
            p = p / f"d{i}"
        p.mkdir(parents=True)
        (p / "leaf.md").write_text("hi")
        res = extract_folder(root)
        assert res.manifest["max_depth_observed"] >= 5
