"""RSM V1 — authoritative daemon package.

Boundary rules (enforced by backend/tools/check_boundaries.py):

- rsm.bucket.*       : stdlib + pydantic only.
- rsm.lifecycle.*    : stdlib + rsm.bucket only.
- rsm.transports.*   : no imports from daemon / cli / api / mcp_server.
"""

__version__ = "0.0.0"
