async (page) => {
  const evidence = {};
  await page.setViewportSize({width:1440,height:900});
  await page.waitForFunction(() => !document.querySelector('#workbench').inert && document.querySelector('#source-count').textContent === '9');
  await page.screenshot({path:'output/playwright/gap-desktop.png'});
  evidence.baseline = await page.evaluate(() => ({count:document.querySelector('#source-count').textContent,panels:[...document.querySelectorAll('.panel')].map(el=>({id:el.id,width:el.getBoundingClientRect().width})),url:location.href}));
  const checkbox = page.locator('[data-select]').first();
  await checkbox.focus();
  evidence.focusBefore = await page.evaluate(() => ({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label')}));
  await page.keyboard.press('Space');
  evidence.focusAfter = await page.evaluate(() => ({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label')}));
  await page.keyboard.press('Tab');
  evidence.nextFocus = await page.evaluate(() => ({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label'),text:document.activeElement.textContent.slice(0,80)}));
  evidence.layouts=[];
  for (const size of [{width:1280,height:600},{width:390,height:844},{width:320,height:640},{width:800,height:450}]) {
    await page.setViewportSize(size);
    if(size.width<=960) await page.locator('.view-switcher [data-view="sources"]').click();
    evidence.layouts.push(await page.evaluate(() => ({viewport:{width:innerWidth,height:innerHeight},docWidth:document.documentElement.scrollWidth, controls:['#sources-panel','#source-tree','.start-banner','#start-button','#add-source','.statusbar'].map(selector=>{const el=document.querySelector(selector),r=el.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;const hit=document.elementFromPoint(x,y);return {selector,x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,centerReachable:!!hit&&(hit===el||el.contains(hit)),overflowY:getComputedStyle(el).overflowY}})})));
    await page.screenshot({path:`output/playwright/gap-${size.width}x${size.height}.png`});
  }
  await page.setViewportSize({width:1440,height:900});
  await page.locator('[data-resize="agent"]').focus();
  for(let i=0;i<30;i++) await page.keyboard.press('ArrowRight');
  await page.locator('[data-resize="sources"]').focus();
  for(let i=0;i<30;i++) await page.keyboard.press('ArrowRight');
  evidence.resize=await page.evaluate(() => ({viewport:innerWidth,docWidth:document.documentElement.scrollWidth,panels:[...document.querySelectorAll('.panel')].map(el=>{const r=el.getBoundingClientRect();return {id:el.id,x:r.x,width:r.width,right:r.right}})}));
  await page.screenshot({path:'output/playwright/gap-resize.png'});
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#workbench').inert);
  const second = await page.context().newPage();
  await second.goto('http://127.0.0.1:4173');
  await second.waitForFunction(()=>!document.querySelector('#workbench').inert);
  await page.locator('#add-source').click();
  await page.locator('[data-source-action="input"]').click();
  await page.locator('#text-source-name').fill('market-audit-saved.txt');
  await page.locator('#text-source-content').fill('Saved source created in tab A during the market gap audit.');
  await page.locator('#text-source-form button[type="submit"]').click();
  await page.waitForFunction(()=>document.querySelector('#source-count').textContent==='10');
  evidence.tabAAfterCreate=await page.evaluate(async()=>{const {loadWorkspace}=await import('./lib/storage.js');const data=await loadWorkspace();return {persistedSources:data.sources.map(x=>x.name),saveStatus:document.querySelector('#save-status').textContent}});
  await second.locator('#agent-input').fill('An unrelated draft in tab B');
  await second.waitForFunction(()=>document.querySelector('#save-status').textContent==='Workspace saved in this browser');
  evidence.tabBAfterDraft=await second.evaluate(async()=>{const {loadWorkspace}=await import('./lib/storage.js');const data=await loadWorkspace();return {persistedSources:data.sources.map(x=>x.name),agentDraft:data.agentDraft,saveStatus:document.querySelector('#save-status').textContent}});
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#workbench').inert);
  evidence.tabAReload={sourceCount:await page.locator('#source-count').textContent(),lostSource:await page.locator('[data-file][aria-label="Open market-audit-saved.txt"]').count()===0};
  await second.close();
  return evidence;
}
