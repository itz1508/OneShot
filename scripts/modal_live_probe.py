"""Verify a deployed OneShot ASGI audit demo over actual HTTPS.

This probe does not configure or invoke an MCP model. It keeps SSE open while
issuing Audit, preventing a single-container head-of-line blocking regression.
"""

from __future__ import annotations

import argparse
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Actual deployed HTTPS Modal URL")
    parser.add_argument("--verify-task-id", default="", help="Only check a task persisted before container replacement")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".modal.run"):
        parser.error("expected a real HTTPS *.modal.run endpoint")

    def get(path: str) -> bytes:
        with urlopen(f"{base}{path}", timeout=40) as response:
            if response.status != 200:
                raise RuntimeError(f"unexpected GET status: {response.status}")
            return response.read()

    def api(method: str, path: str, payload: dict[str, str] | None = None) -> object:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = Request(f"{base}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=120) as response:
                if response.status not in (200, 201):
                    raise RuntimeError(f"unexpected API status: {response.status}")
                return json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(f"{method} {path} returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {path} is unreachable") from exc

    if args.verify_task_id:
        if not re.fullmatch(r"[a-f0-9]{32}", args.verify_task_id):
            parser.error("invalid persisted task ID")
        task_id = args.verify_task_id
        restored = api("GET", f"/api/tasks/{task_id}")
        if not isinstance(restored, dict) or restored.get("execution_status") != "audit_completed":
            raise RuntimeError("Audit state was not retained across the container replacement")
        artifacts = api("GET", f"/api/tasks/{task_id}/artifacts")
        if not isinstance(artifacts, list) or not any(a.get("kind") == "audit" for a in artifacts):
            raise RuntimeError("Audit artifact was not retained across the container replacement")
        events = api("GET", f"/api/tasks/{task_id}/events?after=0")
        if not isinstance(events, list) or not any(event.get("type") == "audit_completed" for event in events):
            raise RuntimeError("Audit event log was not retained across the container replacement")
        print(json.dumps({"status": "recovered", "task_id": task_id, "events": len(events)}))
        return 0

    page = get("/live.html")
    if b"<html" not in page.lower() or b"/api/tasks" not in page:
        raise RuntimeError("deployed live page is not the expected OneShot application")
    health = api("GET", "/api/health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError("live API health check failed")
    if health.get("mcp_transport_configured") is not False:
        raise RuntimeError("public Audit demo must not enable MCP model execution")

    created = api("POST", "/api/tasks", {"prompt": "Audit deployed source-bundle integration", "purpose": "audit"})
    if not isinstance(created, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(created.get("task_id", ""))):
        raise RuntimeError("task creation failed")
    task_id = created["task_id"]

    # Hold an actual streaming connection open during POST Audit, as live.html
    # does. A Modal container with only one input slot would queue the POST.
    stream_request = Request(f"{base}/api/tasks/{task_id}/stream", method="GET")
    with urlopen(stream_request, timeout=40) as stream:
        if "text/event-stream" not in stream.headers.get("Content-Type", ""):
            raise RuntimeError("SSE content type missing")
        if not stream.readline().startswith(b"retry: "):
            raise RuntimeError("SSE stream did not start")
        audit = api("POST", f"/api/tasks/{task_id}/audit")
        if not isinstance(audit, dict) or audit.get("status") != "completed":
            raise RuntimeError("Audit did not complete while SSE remained connected")

    loaded = api("GET", f"/api/tasks/{task_id}")
    if not isinstance(loaded, dict) or loaded.get("execution_status") != "audit_completed":
        raise RuntimeError("Audit task state could not be restored")
    artifacts = api("GET", f"/api/tasks/{task_id}/artifacts")
    if not isinstance(artifacts, list) or not any(a.get("kind") == "audit" for a in artifacts):
        raise RuntimeError("persisted Audit artifact missing")
    events = api("GET", f"/api/tasks/{task_id}/events?after=0")
    if not isinstance(events, list) or not any(event.get("type") == "audit_completed" for event in events):
        raise RuntimeError("persisted Audit/SSE replay event missing")
    print(json.dumps({"status": "verified", "task_id": task_id, "events": len(events), "audit": audit["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
