async (page) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:1536,height:960});
  await page.waitForFunction(()=>document.querySelector('#source-image')?.naturalWidth>0);
  await page.waitForFunction(()=>document.querySelector('#save-status')?.textContent==='Workspace saved in this browser');
  await page.screenshot({path:'output/playwright/desktop-final.png'});
  await page.getByRole('button',{name:'Switch color theme',exact:true}).click();
  await page.screenshot({path:'output/playwright/dark-final.png'});
  await page.getByRole('button',{name:'Switch color theme',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Sources',exact:false}).first().click();
  await page.screenshot({path:'output/playwright/mobile-sources-final.png'});
  await page.getByRole('button',{name:'Open state-driven-transition.png',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#source-image')?.naturalWidth>0);
  await page.screenshot({path:'output/playwright/mobile-review-final.png'});
  await page.getByRole('button',{name:'Sources',exact:false}).first().click();
  await page.getByRole('button',{name:'Start preparation',exact:true}).click();
  await page.getByRole('button',{name:'Return to review',exact:true}).waitFor();
  if(await page.locator('#process-state').textContent()!=='partial')throw new Error('Default reference set must report partial');
  if(await page.locator('#coverage-stats').innerText().then(text=>text.includes('3'))===false)throw new Error('Default source coverage missing');
  await page.screenshot({path:'output/playwright/mobile-processing-final.png'});
  await page.getByRole('button',{name:'Return to review',exact:true}).click();
  await page.setViewportSize({width:1536,height:960});
  await page.getByRole('button',{name:'Open workflow-diagram.png',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#source-image')?.naturalWidth>0);
  return {preview:'http://127.0.0.1:4173',screenshots:5,sources:await page.locator('#source-count').textContent(),defaultPreparation:'partial with actual text and image reads'};
}
