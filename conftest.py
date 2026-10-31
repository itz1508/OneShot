"""Root conftest — injects project directories into sys.path automatically."""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
for subdir in ("tools", "agent", "agent/contracts", "agent/adapters"):
    path = str(_REPO_ROOT / subdir)
    if path not in sys.path:
        sys.path.insert(0, path)
