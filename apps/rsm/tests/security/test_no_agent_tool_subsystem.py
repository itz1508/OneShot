"""Repository-state invariant: RSM Core carries NO agent-tool subsystem.

Three ADRs (0002 — forbidden provider SDKs, 0008 — MCP resources only / no
tools, 0017 — no agent runtime / session / event manager) and the project
README all commit to this. The existing CI gates
(``check_boundaries.py`` / ``check_forbidden_deps.py`` /
``check_pymupdf_import.py``) prove the dependency / import story but say
nothing about *tool-shape code constructs* a future contributor could
introduce without pulling in a forbidden SDK — e.g. defining a ``BashTool``
Pydantic model, a ``@tool``-decorated function, a module-level
``tool_registry``, or a ``subprocess`` import.

This test enforces the invariant by reusing the single
``backend/tools/check_no_agent_tools.py`` scanner. The scanner is strict
(AST-driven, code-token-only — docstrings and prose are not flagged) so
the test is deterministic and cheap. Three guarantees:

1. The RSM Core tree (``backend/src/rsm/``) is clean.
2. The scanner can detect a representative violation (so the test's
   silence on the real tree is meaningful).
3. The scanner's clean verdict matches the preceding research pass
   (``TOOL_PARAMETER_CONTRACTS_INVESTIGATION.md`` /
   ``EXTERNAL_CAPABILITY_GAP_RESEARCH.md``) — RSM has no agent tools and
   none were quietly added.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCANNER_PATH = _REPO_ROOT / "tools" / "verification" / "check_no_agent_tools.py"
_RSM_SRC = _REPO_ROOT / "apps" / "rsm" / "src" / "rsm"


def _load_scanner():
    spec = importlib.util.spec_from_file_location(
        "check_no_agent_tools", str(_SCANNER_PATH)
    )
    assert spec is not None and spec.loader is not None, _SCANNER_PATH
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scanner_exists_at_known_path() -> None:
    """The gate must be checked in — it is the single source of truth."""
    assert _SCANNER_PATH.is_file(), _SCANNER_PATH


def test_rsm_core_has_no_agent_tool_subsystem() -> None:
    """backend/src/rsm/ must be clean under the scanner."""
    mod = _load_scanner()
    violations = mod.scan_tree(_RSM_SRC)
    assert violations == [], (
        "Agent-tool subsystem shapes were introduced into RSM Core. "
        "ADR 0002 / 0008 / 0017 forbid them. Violations:\n  - "
        + "\n  - ".join(violations)
    )


def test_scanner_detects_bash_tool_class(tmp_path: Path) -> None:
    """A disposable BashTool stub in a tmp dir must trigger the gate."""
    (tmp_path / "evil.py").write_text(
        textwrap.dedent(
            """
            class BashTool:
                def run(self, command: str, timeout: int) -> str:
                    return ""
            """
        ).lstrip(),
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert any("BashTool" in v for v in violations), violations


def test_scanner_detects_tool_registry(tmp_path: Path) -> None:
    (tmp_path / "evil.py").write_text(
        "tool_registry = {}\n",
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert any("tool_registry" in v for v in violations), violations


def test_scanner_detects_subprocess_import(tmp_path: Path) -> None:
    (tmp_path / "evil.py").write_text(
        "import subprocess\nsubprocess.run(['ls'])\n",
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert any("subprocess" in v for v in violations), violations


def test_scanner_detects_tool_decorator(tmp_path: Path) -> None:
    (tmp_path / "evil.py").write_text(
        textwrap.dedent(
            """
            def tool(fn):
                return fn

            @tool
            def run_scan():
                return 0
            """
        ).lstrip(),
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert any("@tool" in v for v in violations), violations


def test_scanner_detects_os_system_call(tmp_path: Path) -> None:
    (tmp_path / "evil.py").write_text(
        "import os\nos.system('echo pwn')\n",
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert any("os.system" in v for v in violations), violations


def test_scanner_ignores_english_prose(tmp_path: Path) -> None:
    """The gate is AST-driven: 'tool' / 'BashTool' in docstrings must NOT fire.

    This is the invariant that keeps the gate honest when ADR text uses the
    word 'tool' as English (e.g. 'resources only, no MCP tools').
    """
    (tmp_path / "innocent.py").write_text(
        textwrap.dedent(
            '''
            """This module mentions BashTool and tool_registry in prose only.

            It is NOT a tool. ADR 0008 says 'resources only, no MCP tools.'
            """

            def harmless() -> int:
                # Even an inline comment about tool_registry is fine.
                return 1
            '''
        ).lstrip(),
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert violations == [], violations


def test_scanner_handles_missing_root(tmp_path: Path) -> None:
    """Scanning a non-existent root returns [] (no false positives)."""
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path / "does_not_exist")
    assert violations == []


def test_scanner_handles_syntax_errors(tmp_path: Path) -> None:
    """A broken .py file is skipped, not reported as a violation."""
    (tmp_path / "broken.py").write_text(
        "def oops(:\n    pass\n",  # intentional SyntaxError
        encoding="utf-8",
    )
    mod = _load_scanner()
    violations = mod.scan_tree(tmp_path)
    assert violations == []
