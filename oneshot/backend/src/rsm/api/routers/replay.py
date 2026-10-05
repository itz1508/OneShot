"""Replay router — thin re-export of interaction streaming.

/v1/interactions/{id}/stream is the authoritative replay surface
(ADR 0010). This router exists only so the OneShot repo layout
matches the published tree; it adds no new endpoints.
"""

from __future__ import annotations

from .interactions import router as _interactions_router

router = _interactions_router
