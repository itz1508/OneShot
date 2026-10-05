"""Cross-app workspace layout guard (root pytest config: testpaths=['oneshot/tests']).

The RSM v6 refactor splits the monolith into ``oneshot/backend`` + ``oneshot``
with a shared root (pyproject, pnpm workspace, tools/verification, ADRs,
store scaffolding). Per-app tests live under ``oneshot/*/tests``; this tree is
for contract checks that span both apps, so bare ``uv run pytest`` from the
repo root must collect real tests (exit 0 instead of exit 5).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_workspace_member_packages_exist() -> None:
    assert (ROOT / "oneshot" / "backend" / "src" / "rsm" / "__init__.py").is_file()
    assert (ROOT / "oneshot" / "src" / "oneshot" / "__init__.py").is_file()
    assert (ROOT / "oneshot" / "backend" / "pyproject.toml").is_file()
    assert (ROOT / "oneshot" / "pyproject.toml").is_file()


def test_verification_gates_exist() -> None:
    gates = ROOT / "tools" / "verification"
    for name in (
        "check_boundaries.py",
        "check_forbidden_deps.py",
        "check_pymupdf_import.py",
        "check_no_agent_tools.py",
    ):
        assert (gates / name).is_file(), name


def test_shared_root_artifacts_exist() -> None:
    # research.md §"Config change": keep the example next to oneshot/backend/pyproject.toml
    assert (ROOT / "oneshot" / "backend" / "rsm.conf.toml.example").is_file()
    assert (ROOT / "pnpm-workspace.yaml").is_file()
    assert (ROOT / "docs" / "decisions" / "0002-forbidden-dependencies.md").is_file()
    assert (ROOT / "oneshot" / "frontend" / "packages" / "rsm-client" / "package.json").is_file()
    assert (ROOT / "oneshot" / "frontend" / "packages" / "rsm-client" / "tsconfig.json").is_file()


def test_store_scaffolding_committed() -> None:
    for rel in ("store/buckets/.gitkeep", "store/snapshots/.gitkeep"):
        assert (ROOT / rel).is_file(), rel
