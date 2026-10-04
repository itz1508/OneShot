"""Daemon — authoritative orchestration + store + append-only event log.

Lazy exports — the submodules are not re-exported eagerly to avoid a cycle
with rsm.api (daemon.service imports rsm.api.errors; rsm.api.app imports
routers which import daemon.service).
"""
