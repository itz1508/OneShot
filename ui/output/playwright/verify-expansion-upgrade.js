async(page)=>{
  if(page.url()!=='http://127.0.0.1:4173/')await page.goto('http://127.0.0.1:4173/');
  const read=()=>page.evaluate(async()=>{const {loadWorkspace}=await import('./lib/storage.js');return loadWorkspace();});
  const before=await read();if(before.activeRun)throw new Error('Existing preview has an active operation; do not reload it.');
  await page.reload();await page.waitForFunction(()=>document.querySelector('#save-status')?.textContent==='Workspace saved in this browser');
  const after=await read();
  for(const source of before.sources){const retained=after.sources.find(f=>f.id===source.id);if(!retained||retained.saved!==source.saved||retained.draft!==source.draft||retained.original!==source.original||retained.path!==source.path)throw new Error(`Source changed during upgrade: ${source.name}`);}
  if(before.selectedFile!==after.selectedFile||before.agentDraft!==after.agentDraft||before.systemDraft!==after.systemDraft)throw new Error('Review or chat context changed during upgrade');
  if(after.sources.filter(f=>f.referenceKey).length!==2)throw new Error('Expected exactly two new diagram references');
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:1536,height:960});
  await page.getByRole('button',{name:'Open mermaid-diagram (3).png',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#source-image')?.naturalWidth>0);await page.screenshot({path:'output/playwright/expansion-upgraded-preview.png'});
  return {before:before.sources.length,after:after.sources.length,retainedSources:before.sources.length,preserved:'source IDs, originals, saved revisions, drafts, review selection, both chat drafts',diagramCopies:2};
}
