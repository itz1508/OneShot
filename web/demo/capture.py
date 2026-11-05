"""Capture OneShot's saved work-screen visualizer in strictly synthetic video-demo mode.

This records Chromium rendering of event-driven sample playback, never a connected
production agent or an independently verified Build/E2E execution.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright  # deptry: ignore[DEP001] - optional video capture

SCENARIOS = ('happy', 'gap', 'blocked', 'recovery', 'mcp', 'audit')

def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def capture(browser, source: Path, dest: Path, scenario: str, base_url: str | None, hold_ms: int) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    images = dest / 'screenshots'
    images.mkdir(exist_ok=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 900},device_scale_factor=1,record_video_dir=str(dest),record_video_size={'width':1440,'height':900},accept_downloads=True)
    page=context.new_page()
    errors, requests = [], []
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r: requests.append(r.url) if '/api/' in r.url or '/mcp' in r.url else None)
    if base_url:
        page.goto(base_url.rstrip('/')+'/demo.html?scenario='+scenario,wait_until='domcontentloaded')
    else:
        page.set_content(source.read_text(encoding='utf-8'),wait_until='domcontentloaded')
        page.locator('#scenario').select_option(scenario)
    count=next(v['scenes'] for v in page.evaluate('window.__oneshotDemo.scenarios') if v['id']==scenario)
    visited=[]; storyboard=[]; last_stage=None
    for i in range(count):
        page.locator('#next').click()
        page.wait_for_timeout(max(hold_ms,75))
        state=page.evaluate('window.__oneshotDemo.getState()')
        step=page.locator('#demo-stage').inner_text()
        role=page.locator('#work-card').get_attribute('data-role')
        status=state['presentation']['status']
        assert state['sceneIndex']==i
        if step!=last_stage or status=='error' or i==count-1:
            im=images/f'{i+1:03}-{step.lower().replace(" ","-")}.png'
            page.screenshot(path=str(im))
            visited.append(im.name)
        storyboard.append({'scene_index':i,'stage':step,'role':role,'title':page.locator('#demo-scene-label').inner_text(),'status':status,'offset_ms':i*hold_ms})
        last_stage=step
    end=page.evaluate('window.__oneshotDemo.getState()')
    assert end['presentation']['status']==('error' if scenario=='blocked' else 'complete')
    assert not errors and not requests,{'pageErrors':errors,'apiRequests':requests}
    if scenario=='blocked': assert '_build.json' not in end['artifacts']
    if end['artifacts']:
        page.locator('#demo-artifacts').click()
        assert page.locator('#inspector').is_visible()
        assert '"synthetic": true' in page.locator('#inspect-content').inner_text()
        page.screenshot(path=str(images/'artifact-preview.png'))
        page.locator('#inspect-close').click()
    with page.expect_download() as d:
        page.locator('#export-demo').click()
    d.value.save_as(dest/'actions.jsonl')
    records=[json.loads(v) for v in (dest/'actions.jsonl').read_text().splitlines()]
    assert records[0]['not_verified_e2e'] is True
    assert sum(r.get('type')=='scene_shown' for r in records)==count
    (dest/'storyboard.json').write_text(json.dumps(storyboard,indent=2),encoding='utf-8')
    video=page.video
    page.close()
    recorded=Path(video.path())
    context.close()
    webm=dest/'workflow.webm'
    if recorded!=webm: shutil.move(str(recorded),str(webm))
    mp4=dest/'workflow.mp4'
    if shutil.which('ffmpeg'):
        res=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(webm),'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-movflags','+faststart',str(mp4)],capture_output=True,text=True)
        if res.returncode: mp4.unlink(missing_ok=True);print('FFmpeg skipped',res.stderr[:200])
    return {'scenario':scenario,'scenes':count,'screenshots':visited,'event_count':len(end['events']),'action_count':len(records)-1,'final_presentation_status':end['presentation']['status'],'api_requests':requests,'page_errors':errors,'mp4':mp4.is_file()}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parent/'demo.html')
    parser.add_argument('--out',type=Path,default=Path('oneshot-corrected-demo-capture'))
    parser.add_argument('--base-url',default=None)
    parser.add_argument('--chromium',default=None)
    parser.add_argument('--hold-ms',type=int,default=180)
    parser.add_argument('--scenario',choices=SCENARIOS+('all',),default='all')
    args=parser.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    with sync_playwright() as p:
        launch={'headless':True}
        if args.chromium:launch.update(executable_path=args.chromium,args=['--no-sandbox'])
        b=p.chromium.launch(**launch)
        try:
            results=[capture(b,args.source,args.out/s,s,args.base_url,args.hold_ms) for s in (SCENARIOS if args.scenario=='all' else (args.scenario,))]
        finally:b.close()
    files=sorted(x for x in args.out.rglob('*') if x.is_file() and x.name!='manifest.json')
    manifest={'title':'OneShot work-screen video visualization, synthetic playback','source_screen':'User Library OneShot_Agent_Live_Screen.html','source_repo':'itz1508/OneShot','synthetic':True,'not_verified_backend_e2e':True,'created_at_utc':datetime.now(timezone.utc).isoformat(),'scenarios':results,'totals':{'scenes':sum(v['scenes'] for v in results),'screenshots':sum(len(v['screenshots'])+1 for v in results),'videos':sum(int(v['mp4']) for v in results)},'sha256':{str(x.relative_to(args.out)):digest(x) for x in files}}
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'totals':manifest['totals'],'results':results},indent=2))

if __name__=='__main__':main()