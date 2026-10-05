"""Cross-app workspace layout guard (root pytest config: testpaths=['tests']).

The RSM v6 refactor splits the monolith into ``apps/rsm`` + ``apps/oneshot``
with a shared root (pyproject, pnpm workspace, tools/verification, ADRs,
store scaffolding). Per-app tests live under ``apps/*/tests``; this tree is
for contract checks that span both apps, so bare ``uv run pytest`` from the
repo root must collect real tests (exit 0 instead of exit 5).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_workspace_member_packages_exist() -> None:
    assert (ROOT / "apps" / "rsm" / "src" / "rsm" / "__init__.py").is_file()
    assert (ROOT / "apps" / "oneshot" / "src" / "oneshot" / "__init__.py").is_file()
    assert (ROOT / "apps" / "rsm" / "pyproject.toml").is_file()
    assert (ROOT / "apps" / "oneshot" / "pyproject.toml").is_file()


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
    # research.md §"Config change": keep the example next to apps/rsm/pyproject.toml
    assert (ROOT / "apps" / "rsm" / "rsm.conf.toml.example").is_file()
    assert (ROOT / "pnpm-workspace.yaml").is_file()
    assert (ROOT / "docs" / "decisions" / "0002-forbidden-dependencies.md").is_file()
    assert (ROOT / "packages" / "rsm-client" / "package.json").is_file()
    assert (ROOT / "packages" / "rsm-client" / "tsconfig.json").is_file()


def test_web_app_layout() -> None:
    assert (ROOT / "apps" / "web" / "package.json").is_file()
    assert (ROOT / "apps" / "web" / "src" / "app" / "layout.tsx").is_file()
    assert (ROOT / "apps" / "web" / "tests" / "e2e" / "playwright.config.ts").is_file()


def test_store_scaffolding_committed() -> None:
    for rel in ("store/buckets/.gitkeep", "store/snapshots/.gitkeep"):
        assert (ROOT / rel).is_file(), rel
