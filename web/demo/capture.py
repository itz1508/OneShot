"""Record synthetic OneShot demo interactions for future video assembly.

Requires Python Playwright and a Chromium browser. This script never calls OneShot APIs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

SCENARIOS = ("happy", "gap", "blocked", "recovery", "mcp", "audit")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_scenario(browser, src: Path, target: Path, scenario: str, *, base_url: str | None, hold_ms: int) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    image_dir = target / "screenshots"
    image_dir.mkdir(exist_ok=True)
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        device_scale_factor=1,
        record_video_dir=str(target),
        record_video_size={"width": 1440, "height": 900},
        accept_downloads=True,
    )
    page = context.new_page()
    errors = []
    api_requests = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("request", lambda req: api_requests.append(req.url) if "/api/" in req.url or "/mcp" in req.url else None)
    if base_url:
        page.goto(urljoin(base_url.rstrip("/") + "/", f"demo.html?scenario={scenario}"), wait_until="domcontentloaded")
    else:
        # Offline fallback for restricted test environments. This still runs a real
        # Chromium page and tests user-visible interaction, but not HTTP routing.
        page.set_content((src / "demo.html").read_text(encoding="utf-8"), wait_until="domcontentloaded")
        page.add_style_tag(content=(src / "demo.css").read_text(encoding="utf-8"))
        page.add_script_tag(content=(src / "demo.js").read_text(encoding="utf-8"))
        page.evaluate("history.replaceState = () => {}")
        page.locator("#scenario").select_option(scenario)
    assert page.get_by_text("SIMULATED · NO BACKEND").is_visible()
    scene_count = page.evaluate("window.__oneshotDemo.scenarios.find(s => s.id === document.querySelector('#scenario').value).scenes")
    first = None
    screenshots = []
    storyboard = []
    for index in range(scene_count):
        page.locator("#next").click()
        state = page.evaluate("window.__oneshotDemo.getState()")
        scene = state["events"][-1]
        stage = scene["stage"]
        if stage != first or scene["status"] == "blocked" or index + 1 == scene_count:
            safe = "".join(c if c.isalnum() else "-" for c in stage.lower()).strip("-")
            image_path = image_dir / f"{index+1:03}-{safe}.png"
            page.screenshot(path=str(image_path))
            screenshots.append(image_path)
        storyboard.append({
            "scene": index + 1, "stage": stage, "title": scene["title"],
            "actor": scene["actor"], "status": scene["status"], "artifact": scene["artifact"],
            "suggested_offset_ms": index * hold_ms,
        })
        first = stage
        page.wait_for_timeout(hold_ms)
    state = page.evaluate("window.__oneshotDemo.getState()")
    assert len(state["events"]) == scene_count
    assert page.locator("#percent").inner_text() == "100%"
    assert not errors, f"JavaScript errors: {errors}"
    assert not api_requests, f"Unexpected API/MCP requests: {api_requests}"
    if scenario == "blocked":
        assert "_build.json" not in state["artifacts"]
    if state["artifacts"]:
        page.locator(".artifact-row").first.click()
        assert page.locator("#fileEditor").get_attribute("readonly") is not None
        assert '"synthetic": true' in page.locator("#fileEditor").input_value()
        page.screenshot(path=str(image_dir / "artifact-preview.png"))
        page.wait_for_timeout(450)
        page.locator("#modalDone").click()
    with page.expect_download(timeout=8000) as download_event:
        page.locator("#export").click()
    download = download_event.value
    downloaded = target / download.suggested_filename
    download.save_as(downloaded)
    actions = target / "actions.jsonl"
    actions.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in state["actionLog"]) + "\n", encoding="utf-8")
    (target / "storyboard.json").write_text(json.dumps(storyboard, indent=2, ensure_ascii=False), encoding="utf-8")
    video = page.video
    page.close()
    video_path = Path(video.path())
    context.close()
    final_webm = target / "workflow.webm"
    if video_path != final_webm:
        shutil.move(str(video_path), str(final_webm))
    mp4 = target / "workflow.mp4"
    if shutil.which("ffmpeg"):
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(final_webm),
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            mp4.unlink(missing_ok=True)
            print(f"warning: mp4 encoding skipped: {result.stderr[:180]}")
    return {
        "scenario_id": scenario, "scene_count": scene_count, "event_count": len(state["events"]),
        "screenshot_count": len(screenshots) + bool(state["artifacts"]),
        "blocked": scenario == "blocked", "api_requests": len(api_requests), "javascript_errors": errors,
        "video": final_webm.name, "mp4": mp4.name if mp4.is_file() else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "public")
    parser.add_argument("--out", type=Path, default=Path("demo-capture"))
    parser.add_argument("--base-url", default=None, help="URL of a running server (omit for offline Chromium render)")
    parser.add_argument("--chromium", default=None, help="Optional path to Chromium executable")
    parser.add_argument("--scenario", choices=SCENARIOS + ("all",), default="all")
    parser.add_argument("--hold-ms", type=int, default=260)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = []
    with sync_playwright() as p:
        launch_args = {"headless": True}
        if args.chromium:
            launch_args.update({"executable_path": args.chromium, "args": ["--no-sandbox"]})
        browser = p.chromium.launch(**launch_args)
        try:
            for name in SCENARIOS if args.scenario == "all" else [args.scenario]:
                print(f"capturing {name}...", flush=True)
                summary.append(capture_scenario(browser, args.source, args.out / name, name, base_url=args.base_url, hold_ms=args.hold_ms))
        finally:
            browser.close()
    files = sorted(f for f in args.out.rglob("*") if f.is_file() and f.name != "manifest.json")
    manifest = {
        "title": "OneShot synthetic frontend video capture",
        "synthetic": True,
        "not_evidence_of_backend_e2e": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "itz1508/OneShot",
        "scenarios": summary,
        "totals": {"scenes": sum(x["scene_count"] for x in summary), "screenshots": sum(x["screenshot_count"] for x in summary)},
        "sha256": {str(f.relative_to(args.out)): digest(f) for f in files},
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["totals"], indent=2))


if __name__ == "__main__":
    main()