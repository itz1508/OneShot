"""Test workflow YAML files parse correctly."""

from pathlib import Path

import yaml


def test_workflow_files_parse():
    root = Path("agent/workflows/stages")
    files = list(root.glob("*.yaml"))
    assert len(files) == 6
    for path in files:
        data = yaml.safe_load(path.read_text())
        assert data.get("id") or data.get("stage")
        assert data["version"] >= 1
