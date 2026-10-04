"""FastAPI HTTP transport for the daemon (Spec §11.1)."""
# NOTE: do NOT eagerly import create_app here — doing so pulls in routers,
# which import daemon.service, which imports api.errors, forming a cycle.
# Consumers should `from rsm.api.app import create_app` directly.
