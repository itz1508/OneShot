"""Audit Discovery subsystem.

Audit Discovery is OPT-IN: it produces a ``RunPlan`` from a
prompt-authoring prompt revision (or a declarative handoff) and
hands it off to ``agent.start()`` for execution. The deterministic
Research / Plan / Build code paths in ``agent.__main__`` are
untouched; Audit Discovery is a parallel route for prompt-driven
build sequences.
"""

from agent.audit_discovery.runner import (
    AuditDiscoveryRunner,
    DiscoveryHandoff,
    DiscoveryHandoffError,
)

__all__ = [
    "AuditDiscoveryRunner",
    "DiscoveryHandoff",
    "DiscoveryHandoffError",
]
