// Optional browser QA: npm install --no-save playwright; npx playwright install chromium.
// Uses a temporary DB. App runtime itself requires neither Node nor npm.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawn}=require('node:child_process'),os=require('node:os');
const playwright=require('playwright');
const qa=process.env.PERICARE_SCREENSHOT_DIR||fs.mkdtempSync(path.join(os.tmpdir(),'pericare-v6_1-browser-'));
fs.mkdirSync(qa,{recursive:true});const runtime=fs.mkdtempSync(path.join(os.tmpdir(),'pericare-v6_1-data-')),root=path.resolve(__dirname,'..');
(async()=>{
  const server=spawn(process.env.PYTHON_BIN||'python3',['server.py'],{cwd:root,env:{...process.env,HOST:'127.0.0.1',PORT:'8094',DATA_DIR:runtime},stdio:['ignore','ignore','pipe']});let browser;
  try{
    let healthy=false;for(let i=0;i<40;i++){try{if((await fetch('http://127.0.0.1:8094/health')).ok){healthy=true;break}}catch{}await new Promise(r=>setTimeout(r,100));}assert(healthy,'isolated test server failed to start');
    const executablePath=process.env.PERICARE_CHROMIUM_BINARY,args=process.env.PERICARE_CHROMIUM_ARGS?JSON.parse(process.env.PERICARE_CHROMIUM_ARGS):executablePath?['--no-sandbox','--disable-dev-shm-usage']:[];
    assert(Array.isArray(args)&&args.every(a=>typeof a==='string'));
    browser=await playwright.chromium.launch({executablePath,args,headless:true});
    const page=await browser.newPage({viewport:{width:1680,height:1100},reducedMotion:'no-preference'}),errors=[],checks=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:8094');await page.waitForSelector('#map-patient-layer>g');
    let fontDir;try{fontDir=path.dirname(require.resolve('@fontsource/noto-sans-kr/400.css'));}catch{}
    if(fontDir){
      await page.route('**/qa-font/*',r=>r.fulfill({body:fs.readFileSync(path.join(fontDir,'files',new URL(r.request().url()).pathname.split('/').at(-1))),contentType:'font/woff2'}));
      const css=fs.readFileSync(fontDir+'/400.css','utf8').replace(/url\(([^)]+)\)/g,(_,s)=>`url('/qa-font/${s.replace(/["']/g,'').split('/').at(-1)}')`);
      await page.addStyleTag({content:css+'body,.hospital-svg{font-family:"Noto Sans KR",sans-serif!important}'});await page.evaluate(()=>document.fonts.ready);
    }
    assert.equal(await page.locator('#navigation .nav-item').count(),3);
    assert.equal(await page.locator('#map-patient-layer>g').count(),60);assert.equal(await page.locator('#map-staff-layer>g').count(),13);assert.equal(await page.locator('#map-bed-layer>g').count(),12);
    assert.equal(await page.locator('#map-status-bar .map-stat').count(),4);
    assert.equal(await page.locator('.sidebar,.map-side,#map-events,.map-status-bar .map-stat p').count(),0);
    assert.equal(await page.locator('#map-drawer').isVisible(),false);
    assert((await page.locator('#map-bed-mix').textContent()).includes('128'));
    const originalSize=await page.locator('#map-viewport').boundingBox();assert(originalSize.width>1500&&originalSize.height>760,JSON.stringify(originalSize));
    await page.locator('#map-fullscreen').click();await page.waitForFunction(()=>document.querySelector('#map-fullscreen').getAttribute('aria-pressed')==='true');
    assert(await page.locator('#play').isVisible());assert((await page.locator('#map-viewport').boundingBox()).height>originalSize.height+30);
    await page.screenshot({path:qa+'/v6_1-fullscreen.png',fullPage:true});
    await page.locator('#map-fullscreen').click();await page.waitForFunction(()=>document.querySelector('#map-fullscreen').getAttribute('aria-pressed')==='false');
    checks.push('full-width map, four compact metrics, hidden detail, fullscreen preserves clock controls');
    await page.evaluate(()=>{document.querySelector('.workspace').requestFullscreen=undefined;});
    await page.locator('#map-fullscreen').click();await page.waitForFunction(()=>document.querySelector('.workspace').classList.contains('map-expanded'));
    assert(await page.locator('#play').isVisible());await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('.workspace').classList.contains('map-expanded'));
    checks.push('browser fallback expands the workspace and Escape restores it');
    await page.locator('[data-action="map-fit"]').click();assert(await page.locator('#map-viewport').evaluate(n=>n.scrollWidth<=n.clientWidth+1&&n.scrollHeight<=n.clientHeight+1));
    await page.screenshot({path:qa+'/v6_1-hospital.png',fullPage:true});checks.push('three views, all actors and beds, full map fit');
    await page.selectOption('#map-patient-picker','DEMO-004');await page.waitForFunction(()=>document.querySelector('#map-detail')?.textContent.includes('DEMO-004'));
    assert((await page.locator('#map-detail').textContent()).includes('집중관리 지속 예측'));checks.push('native patient picker and core duration detail');
    await page.locator('[data-action="map-close-detail"]').click();assert.equal(await page.locator('#map-drawer').isVisible(),false);
    await page.evaluate(()=>refresh(true));assert.equal(await page.locator('#map-drawer').isVisible(),false);
    assert.equal(await page.locator('#map-patient-picker').inputValue(),'');await page.selectOption('#map-patient-picker','DEMO-004');assert(await page.locator('#map-drawer').isVisible());checks.push('same patient can be reopened immediately after closing detail');
    await page.keyboard.press('Escape');assert.equal(await page.locator('#map-drawer').isVisible(),false);
    checks.push('on-demand detail closes with button or Escape and stays closed after polling');
    await page.locator('#map-options summary').click();
    await page.locator('#map-motion').click();assert.equal(await page.locator('#map-motion').getAttribute('aria-pressed'),'false');await page.locator('#map-motion').click();checks.push('persistent motion preference');await page.locator('#map-options summary').click();
    await page.selectOption('#speed','1');await page.waitForFunction(()=>S.speed===1);await page.locator('#play').click();await page.waitForFunction(()=>S.running);
    const step=await page.request.post('http://127.0.0.1:8094/api/actions/advance',{data:{minutes:45}});assert(step.ok());
    await page.waitForFunction(()=>document.querySelector('g.map-patient[data-id="DEMO-004"]')?.classList.contains('in-motion'));
    const before=await page.locator('g.map-patient[data-id="DEMO-004"]').getAttribute('transform');
    await page.waitForFunction(previous=>document.querySelector('g.map-patient[data-id="DEMO-004"]')?.getAttribute('transform')!==previous,before,{timeout:8000});
    assert.equal(await page.locator('dialog[open]').count(),0);checks.push('real animated escort and no admission question');
    await page.locator('.hospital-map-panel').screenshot({path:qa+'/v6_1-transfer.png'});
    await page.locator('#play').click();await page.waitForFunction(()=>!S.running);await page.waitForTimeout(300);
    const paused=await page.locator('g.map-patient[data-id="DEMO-004"]').getAttribute('transform');await page.waitForTimeout(500);assert.equal(await page.locator('g.map-patient[data-id="DEMO-004"]').getAttribute('transform'),paused);checks.push('pause freezes movement');
    await page.locator('g.map-patient[data-id="DEMO-004"]').focus();await page.keyboard.press('Enter');assert.equal(await page.locator('g.map-patient[data-id="DEMO-004"]').getAttribute('aria-pressed'),'true');
    await page.locator('#map-options summary').click();await page.selectOption('#map-filter','high');assert(await page.locator('g.map-patient[data-id="DEMO-005"]').evaluate(n=>n.classList.contains('dimmed')));await page.selectOption('#map-filter','all');await page.locator('#map-options summary').click();checks.push('keyboard selection and risk emphasis');
    await page.locator('#navigation [data-view="patients"]').click();await page.waitForSelector('.duration-grid');
    assert((await page.locator('.patient-hero').textContent()).includes('DEMO-004'));assert.equal(await page.locator('.duration-card').count(),3);assert(await page.evaluate(()=>window.scrollY<5));assert.equal(await page.locator('.booking-steps>li').count(),4);
    await page.locator('.clinical-inputs summary').click();await page.evaluate(()=>refresh(true));assert(await page.locator('.clinical-inputs').evaluate(n=>n.open));
    await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:qa+'/v6_1-patient.png',fullPage:true});checks.push('same selected patient, three durations, four booking steps, persistent input expansion');
    await page.locator('#navigation [data-view="beds"]').click();await page.waitForSelector('.core-bed');assert.equal(await page.locator('.core-bed').count(),12);assert(await page.evaluate(()=>window.scrollY<5));
    assert.equal(await page.locator('[data-action="approve"],[data-action="admit"],[data-action="discharge"]').count(),0);
    await page.screenshot({path:qa+'/v6_1-beds.png',fullPage:true});checks.push('bed planning with actual occupancy and no manual admission controls');
    await page.locator('.core-bed[data-bed="SICU-05"]').click();await page.waitForSelector('#hospital-svg');assert((await page.locator('#map-detail').textContent()).includes('비수술 환자 A'));checks.push('bed navigation preserves external occupant');
    await page.locator('#app-options summary').click();await page.locator('[data-action="theme"]').click();await page.screenshot({path:qa+'/v6_1-dark.png',fullPage:true});checks.push('dark theme');
    await page.locator('[data-action="text-size"]').click();assert.equal(await page.locator('#text-size').getAttribute('aria-pressed'),'true');checks.push('large type');await page.locator('#app-options summary').click();
    await page.setViewportSize({width:390,height:844});
    for(const view of ['hospital','patients','beds']){
      await page.locator(`#navigation [data-view="${view}"]`).click();await page.waitForTimeout(150);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),view+' causes document overflow');
      assert(await page.locator('#navigation').isVisible());if(view==='hospital')assert(await page.locator('#hospital-svg').evaluate(n=>n.clientWidth/Number(n.getAttribute('viewBox').split(' ')[2])>=.5),'mobile map should open at a readable scale with internal panning');if(view==='patients')assert((await page.locator('.chart-wrap svg').getAttribute('viewBox')).includes('380'));
      await page.screenshot({path:qa+`/v6_1-mobile-${view}.png`,fullPage:true});
    }
    checks.push('all three views at mobile width without document overflow; visible navigation');checks.push('resizing to mobile restores readable map scale and internal panning');
    await page.locator('#navigation [data-view="patients"]').click();await page.locator('#patient-search').fill('DEMO-007');await page.waitForSelector('.patient-directory-list button[data-patient="DEMO-007"]');
    await page.locator('.patient-directory-list button[data-patient="DEMO-007"]').click();assert((await page.locator('.patient-hero').textContent()).includes('DEMO-007'));checks.push('mobile search and patient selection');
    assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:checks.length,checks,pageErrors:errors,screenshots:qa},null,2));
  }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
