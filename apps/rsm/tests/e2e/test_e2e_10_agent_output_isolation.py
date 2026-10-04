"""No vendor SDK is in requirements — scanning the module tree confirms it."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def test_no_vendor_sdk_imports():
    for p in (ROOT / "src" / "rsm").rglob("*.py"):
        text = p.read_text("utf-8")
        for bad in ("openai", "anthropic", "langchain", "llama_index", "pydantic_ai"):
            assert bad not in text, f"{p} references {bad}"
