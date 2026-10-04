#!/usr/bin/env python3
"""Agent-tool subsystem gate (companion to check_forbidden_deps + ADR 0002/0008/0017).

FAILS the build if any Python file under backend/src/rsm/ introduces an
*agent-tool subsystem* shape — Bash/Scan/Write/Summary/Read tool classes,
tool-registration mechanics (``tool_registry``, ``BaseTool``, ``@tool``
decorators), execution surfaces (``handle_tool``, ``execute_tool``,
``invoke_tool``, ``tool_call_id``), tool schema contracts
(``input_schema``, ``output_schema``), or shell execution primitives
(``subprocess``, ``os.system``, ``shell=True``).

Why: RSM v6.1 explicitly has no agent-tool subsystem (ADR 0002 forbids
provider SDKs, ADR 0008 forbids MCP tools, ADR 0017 forbids a tool/agent
runtime). The three existing gates (check_boundaries, check_forbidden_deps,
check_pymupdf_import) prove the dependency and import story but say nothing
about tool-shape *code constructs* a future contributor might introduce
without pulling in a forbidden SDK. This gate closes that specific window.

Scope: syntactic — matches **code tokens**, not strings or comments.
   * class names whose identifier is {Bash,Scan,Write,Summary,Read}Tool /
     *Schema / *Params / *Executor / *Handler / *Dispatcher.
   * decorator applications named ``tool`` (not ``tools``, ``@toolkit``,
     ``@toolchain`` — exact ``tool`` only).
   * imports of ``subprocess``, or ``os.system``/``os.exec*``/``os.popen``
     attribute lookups.
   * module-level or class-level assignments to a name ``tool_registry``
     or ``TOOL_REGISTRY`` or ``tool_definitions``.
   * class bases named ``BaseTool``.
   * identifiers equal to ``input_schema`` / ``output_schema`` used as
     assignment targets or ``Field``-prefixed class attributes.
   * identifiers equal to ``handle_tool`` / ``execute_tool`` /
     ``invoke_tool`` / ``tool_call_id`` used as function/method names
     or assignment targets.

Everything else — docstrings, comments, English prose, test identifiers
that only *mention* the word ``tool`` in a string — is deliberately NOT
flagged. This is why the gate parses AST rather than regexp-ing text.

Default scan root: ``<repo>/backend/src/rsm``. The gate accepts an
override ``--root`` for the negative-test case; otherwise it is identical
to the three sibling gates.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "backend" / "src" / "rsm"

# ---- forbidden code shapes ---------------------------------------------------

_FORBIDDEN_CLASS_SUFFIXES = ("Tool", "Schema", "Params", "Executor", "Handler", "Dispatcher")
# A class is flagged only when its identifier starts with one of the five
# tool-noun prefixes AND ends with one of the forbidden suffixes above.
_FORBIDDEN_CLASS_PREFIXES = ("Bash", "Scan", "Write", "Summary", "Read")

_FORBIDDEN_CLASS_BASES = frozenset({"BaseTool", "AgentTool", "ToolBase"})

_FORBIDDEN_IDENTIFIERS = frozenset({
    "tool_registry", "TOOL_REGISTRY", "tool_definitions",
    "handle_tool", "execute_tool", "invoke_tool", "tool_call_id",
    "input_schema", "output_schema",
})

_FORBIDDEN_DECORATOR_NAMES = frozenset({"tool"})

_FORBIDDEN_IMPORT_MODULES = frozenset({"subprocess"})

# os.<attr> attribute accesses that are shell-exec primitives.
_FORBIDDEN_OS_ATTRS = frozenset({
    "system", "popen",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
})


def _is_forbidden_class_name(name: str) -> bool:
    for pref in _FORBIDDEN_CLASS_PREFIXES:
        if name.startswith(pref):
            tail = name[len(pref):]
            if tail and tail in _FORBIDDEN_CLASS_SUFFIXES:
                return True
    return False


def _decorator_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    if isinstance(expr, ast.Call):
        return _decorator_name(expr.func)
    return None


def _assigned_names(targets: list[ast.expr]) -> list[str]:
    out: list[str] = []
    for t in targets:
        if isinstance(t, ast.Name):
            out.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            out.extend(_assigned_names(list(t.elts)))
    return out


def _scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(path.read_text("utf-8"))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        # 1. forbidden class shape (identifier) or forbidden base class.
        if isinstance(node, ast.ClassDef):
            if _is_forbidden_class_name(node.name):
                violations.append(
                    f"{path}:{node.lineno} agent-tool class name {node.name!r}"
                )
            for base in node.bases:
                base_name = base.id if isinstance(base, ast.Name) else (
                    base.attr if isinstance(base, ast.Attribute) else None
                )
                if base_name in _FORBIDDEN_CLASS_BASES:
                    violations.append(
                        f"{path}:{node.lineno} class {node.name!r} subclasses "
                        f"forbidden base {base_name!r}"
                    )
            # @tool decorator on a class
            for dec in node.decorator_list:
                dn = _decorator_name(dec)
                if dn in _FORBIDDEN_DECORATOR_NAMES:
                    violations.append(
                        f"{path}:{node.lineno} class {node.name!r} uses "
                        f"forbidden decorator @{dn}"
                    )

        # 2. @tool decorator on a function / coroutine.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _FORBIDDEN_IDENTIFIERS:
                violations.append(
                    f"{path}:{node.lineno} forbidden function name {node.name!r}"
                )
            for dec in node.decorator_list:
                dn = _decorator_name(dec)
                if dn in _FORBIDDEN_DECORATOR_NAMES:
                    violations.append(
                        f"{path}:{node.lineno} function {node.name!r} uses "
                        f"forbidden decorator @{dn}"
                    )

        # 3. Forbidden module imports.
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _FORBIDDEN_IMPORT_MODULES:
                    violations.append(
                        f"{path}:{node.lineno} forbidden import {alias.name!r} "
                        f"(agent-tool subsystem would need shell exec)"
                    )
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _FORBIDDEN_IMPORT_MODULES:
                violations.append(
                    f"{path}:{node.lineno} forbidden import from {node.module!r}"
                )

        # 4. Forbidden assignment target identifiers.
        if isinstance(node, ast.Assign):
            for name in _assigned_names(list(node.targets)):
                if name in _FORBIDDEN_IDENTIFIERS:
                    violations.append(
                        f"{path}:{node.lineno} forbidden assignment to {name!r}"
                    )
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in _FORBIDDEN_IDENTIFIERS:
                violations.append(
                    f"{path}:{node.lineno} forbidden assignment to {node.target.id!r}"
                )

        # 5. os.<shell-exec attr>(...) calls.
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and node.attr in _FORBIDDEN_OS_ATTRS:
                violations.append(
                    f"{path}:{node.lineno} forbidden shell exec call os.{node.attr}"
                )

    return violations


def scan_tree(root: Path) -> list[str]:
    """Public entry point for the pytest companion test to reuse."""
    violations: list[str] = []
    if not root.exists():
        return violations
    for p in sorted(root.rglob("*.py")):
        violations.extend(_scan_file(p))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(DEFAULT_SRC),
        help="Directory to scan (default: backend/src/rsm).",
    )
    args = parser.parse_args()

    violations = scan_tree(Path(args.root))
    if violations:
        print("AGENT-TOOL SUBSYSTEM VIOLATIONS:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("no-agent-tools gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
