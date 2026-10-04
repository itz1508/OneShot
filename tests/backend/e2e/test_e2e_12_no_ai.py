"""AC-12: no AI dependency is pulled in by import time."""
import importlib
import sys


def test_no_ai_module_after_import():
    import rsm  # noqa: F401
    importlib.import_module("rsm.bucket")
    importlib.import_module("rsm.lifecycle")
    importlib.import_module("rsm.transports")
    forbidden = {"openai", "anthropic", "langchain", "llama_index", "crewai"}
    assert forbidden.isdisjoint(sys.modules.keys())
