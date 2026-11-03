"""Pytest configuration — ensures agent package is importable."""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
