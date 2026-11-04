"""Minimal Modal-only serverless deployment boundary for OneShot.

The existing Python host retains all task and authorization ownership.
"""

import modal

app = modal.App("oneshot-serverless")


@app.function(image=modal.Image.debian_slim(python_version="3.11"))
@modal.fastapi_endpoint(method="GET")
def health() -> dict[str, str]:
    """Liveness only: not an MCP, build, or task-execution endpoint."""
    return {"status": "ok", "service": "oneshot-serverless"}
