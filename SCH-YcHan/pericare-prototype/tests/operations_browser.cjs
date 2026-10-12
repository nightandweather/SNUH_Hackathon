// Optional real Chromium checks for multi-day turnover and recorded-data UI.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const playwright=require('playwright'),root=path.resolve(__dirname,'..');
const runtime=fs.mkdtempSync(path.join(os.tmpdir(),'pericare-v6_1-operations-'));
const qa=process.env.PERICARE_SCREENSHOT_DIR||runtime;
fs.mkdirSync(qa,{recursive:true});
(async()=>{
 const server=spawn(process.env.PYTHON_BIN||'python3',['server.py'],{cwd:root,env:{...process.env,HOST:'127.0.0.1',PORT:'8096',DATA_DIR:runtime},stdio:['ignore','ignore','pipe']});let browser;
 try{
  const url='http://127.0.0.1:8096';let ready=false;
  for(let i=0;i<40;i++){try{if((await fetch(url+'/health')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,100));}assert(ready);
  browser=await playwright.chromium.launch({executablePath:process.env.PERICARE_CHROMIUM_BINARY,args:process.env.PERICARE_CHROMIUM_ARGS?JSON.parse(process.env.PERICARE_CHROMIUM_ARGS):['--no-sandbox','--disable-dev-shm-usage'],headless:true});
  const page=await browser.newPage({viewport:{width:1680,height:1100}}),errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForSelector('#hospital-svg');
  let fontDir;try{fontDir=path.dirname(require.resolve('@fontsource/noto-sans-kr/400.css'));}catch{}
  if(fontDir){await page.route('**/qa-font/*',r=>r.fulfill({body:fs.readFileSync(path.join(fontDir,'files',new URL(r.request().url()).pathname.split('/').at(-1))),contentType:'font/woff2'}));await page.addStyleTag({content:fs.readFileSync(fontDir+'/400.css','utf8').replace(/url\(([^)]+)\)/g,(_,s)=>`url('/qa-font/${s.replace(/["']/g,'').split('/').at(-1)}')`)+'body,.hospital-svg{font-family:"Noto Sans KR",sans-serif !important}'});await page.evaluate(()=>document.fonts.ready);}
  assert.equal(await page.locator('#map-patient-layer>g').count(),60);assert((await page.locator('#operation-day').textContent()).includes('7일'));checks.push('60-patient initial census and seven-day period');
  // Explicit refresh after the API write; polling can be in flight, so wait on
  // the intended final clock value rather than assuming DOM work is immediate.
  let r=await page.request.post(url+'/api/actions/advance',{data:{minutes:20}});assert(r.ok());await page.evaluate(()=>refresh(true));await page.waitForFunction(()=>S.minute===20);
  assert(await page.evaluate(()=>S.scene.patients.some(p=>p.motion?.destination==='EXIT')));checks.push('observed recovery leads to nursing handoff and an exit route');
  assert(await page.locator('#map-patient-picker option[value="DEMO-061"]').count());assert.equal(await page.locator('#map-patient-picker option[value="DEMO-062"]').count(),0);checks.push('arrivals enter the picker only after admission');
  await page.locator('#map-options summary').click();await page.selectOption('#map-zone-picker','EXIT');await page.waitForFunction(()=>document.querySelector('#map-viewport').scrollTop>0);assert(await page.locator('#map-viewport').evaluate(n=>n.scrollTop>0));checks.push('exit zone can be reached without reading logs');
  r=await page.request.post(url+'/api/actions/advance',{data:{minutes:60}});assert(r.ok());await page.evaluate(()=>refresh(true));await page.waitForFunction(()=>S.minute===80);
  assert(await page.evaluate(()=>S.hospital.discharges>0&&S.hospital.admissions>0&&S.hospital.current_census===60+S.hospital.admissions-S.hospital.exits));checks.push('actual turnover and census conservation on the dashboard');
  await page.screenshot({path:path.join(qa,'v6_1-turnover.png'),fullPage:true});
  await page.locator('#navigation [data-view="patients"]').click();await page.waitForSelector('#phase-filter');await page.selectOption('#phase-filter','DISCHARGED');
  await page.locator('.patient-directory-list button').first().click();assert((await page.locator('.patient-main').textContent()).includes('관측된 병원 체류'));checks.push('discharged patients retain observed history and no current forecast');
  await page.locator('[data-action="advance"][data-minutes="1440"]').click();await page.waitForFunction(()=>S.minute===1520,{},{timeout:60000});assert((await page.locator('#operation-day').textContent()).includes('2일차'));checks.push('one-day control processes all intermediate events');
  await page.locator('#navigation [data-view="hospital"]').click();await page.screenshot({path:path.join(qa,'v6_1-day2.png'),fullPage:true});
  await page.locator('#app-options summary').click();await page.locator('[data-action="data"]').click();await page.locator('#dataset-file').setInputFiles(root+'/examples/recorded-replay.json');await page.locator('[data-action="import-data"]').click();await page.waitForFunction(()=>S.source==='import');
  assert.equal(await page.evaluate(()=>S.clock_kind),'hospital_shared');assert.equal(await page.evaluate(()=>S.patients.length),1);assert.equal(await page.locator('#map-staff-layer>g').count(),0);assert((await page.locator('#care-mode').textContent()).includes('실제 기록'));checks.push('data UI loads a valid shared clock and does not invent staff or future arrivals');
  r=await page.request.post(url+'/api/actions/advance',{data:{minutes:17}});assert(r.ok());await page.evaluate(()=>refresh(true));await page.waitForFunction(()=>S.minute===17);assert.equal(await page.evaluate(()=>S.patients[0].prediction.features.latest.minute),17);checks.push('off-grid recorded observation appears at its exact release time');
  r=await page.request.post(url+'/api/actions/advance',{data:{minutes:133}});assert(r.ok());await page.evaluate(()=>refresh(true));await page.waitForFunction(()=>S.minute===150);assert.equal(await page.evaluate(()=>S.hospital.discharges),1);checks.push('recorded discharge uses the observed event, not predicted LOS');
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));await page.screenshot({path:path.join(qa,'v6_1-recorded-mobile.png'),fullPage:true});checks.push('recorded data and new controls preserve mobile layout');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:checks.length,checks,pageErrors:errors},null,2));
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
