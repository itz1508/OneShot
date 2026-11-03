"""Boundary tests — B01: contracts have no runtime imports."""

import ast
import pathlib


class TestImportBoundaries:
    def _get_imports(self, filepath):
        """Extract module-level imports from a Python file."""
        with open(filepath) as f:
            tree = ast.parse(f.read())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        return imports

    RUNTIME_MODULES = {
        "agent.runtime.artifact_store",
        "agent.runtime.receipt_store",
        "agent.runtime.checkpoint_store",
        "agent.runtime.authorization",
        "agent.runtime.controller",
        "agent.runtime.effect_executor",
        "agent.runtime.specification_freezer",
        "agent.runtime.package_lock",
        "agent.runtime.build_admission",
        "agent.runtime.scanner_gateway",
        "agent.runtime.recovery",
        "agent.runtime.event_store",
        "agent.runtime.loaders",
    }

    def test_contracts_no_runtime_imports(self):
        """B01: Contract modules do not import runtime modules."""
        contracts_dir = pathlib.Path("agent/contracts")
        for py_file in contracts_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            imports = self._get_imports(py_file)
            for imp in imports:
                for rt_mod in self.RUNTIME_MODULES:
                    if imp == rt_mod or imp.startswith(rt_mod + "."):
                        raise AssertionError(f"contract {py_file} imports runtime module {imp}")

    def test_validation_no_io_imports(self):
        """B01b: Validation modules do not import IO modules."""
        validation_dir = pathlib.Path("agent/contracts/validation")
        io_modules = {"sqlite3", "os", "pathlib", "shutil", "subprocess", "socket"}
        for py_file in validation_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            imports = self._get_imports(py_file)
            for imp in imports:
                root = imp.split(".")[0]
                if root in io_modules:
                    raise AssertionError(f"validation module {py_file} imports IO module {imp}")
