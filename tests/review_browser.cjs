// Real Chromium regressions for reviewed data and selection paths.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require('playwright'),root=path.resolve(__dirname,'..');
const runtime=fs.mkdtempSync(path.join(os.tmpdir(),'pericare-v6_1-review-'));
(async()=>{
 const url='http://127.0.0.1:8097';
 const server=spawn(process.env.PYTHON_BIN||'python3',['server.py'],{cwd:root,env:{...process.env,HOST:'127.0.0.1',PORT:'8097',DATA_DIR:runtime},stdio:['ignore','ignore','pipe']});let browser;
 try{
  let ready=false;for(let i=0;i<40;i++){try{if((await fetch(url+'/health')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,100));}assert(ready);
  browser=await chromium.launch({executablePath:process.env.PERICARE_CHROMIUM_BINARY,args:process.env.PERICARE_CHROMIUM_ARGS?JSON.parse(process.env.PERICARE_CHROMIUM_ARGS):['--no-sandbox','--disable-dev-shm-usage'],headless:true});
  const page=await browser.newPage({viewport:{width:1680,height:1100}}),errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForSelector('#hospital-svg');
  await page.selectOption('#map-patient-picker','DEMO-017');
  assert(await page.locator('#map-drawer').isVisible());
  let response=await page.request.post(url+'/api/actions/advance',{data:{minutes:100}});assert(response.ok());
  await page.evaluate(()=>refresh(true));await page.waitForFunction(()=>S.minute===100);
  assert.equal(await page.locator('#map-patient-layer [data-id="DEMO-017"]').count(),0);
  assert((await page.locator('#map-detail').textContent()).includes('병원 퇴원'));
  assert(!(await page.locator('#map-detail').textContent()).includes('현재 데이터에 없습니다'));
  await page.locator('#map-detail [data-action="inspect"]').click();await page.waitForSelector('#phase-filter');
  assert((await page.locator('.patient-main').textContent()).includes('관측된 병원 체류'));
  checks.push('selected discharge history remains available after the exit icon disappears');
  await page.selectOption('#phase-filter','DISCHARGED');await page.locator('#navigation [data-view="hospital"]').click();
  await page.locator('#map-options summary').click();await page.selectOption('#map-filter','high');await page.locator('#map-options summary').click();
  function fixture(){const d=JSON.parse(fs.readFileSync(root+'/examples/canonical-data.json','utf8'));d.schema_version='1.1';d.horizon_minutes=1440;d.clock_kind='hospital_shared';d.patients=d.patients.filter(p=>['DEMO-011','DEMO-014'].includes(p.id));d.beds=d.beds.filter(b=>['SICU-01','SICU-02'].includes(b.id));return d;}
  async function load(d){const file=path.join(runtime,'incoming.json');fs.writeFileSync(file,JSON.stringify(d));await page.locator('#app-options summary').click();await page.locator('[data-action="data"]').click();await page.locator('#dataset-file').setInputFiles(file);await page.locator('[data-action="import-data"]').click();await page.waitForFunction(()=>S.source==='import'&&S.minute===0);await page.waitForFunction(()=>!document.querySelector('#modal').open);}
  let d=fixture();delete d.beds[0].available_minute;await load(d);
  assert.equal(await page.evaluate(()=>MapUI.filter),'all');assert.equal(await page.locator('#map-filter').inputValue(),'all');assert.equal(await page.locator('#map-drawer').isVisible(),false);
  await page.locator('#navigation [data-view="patients"]').click();assert.equal(await page.locator('#phase-filter').inputValue(),'active');assert.equal(await page.locator('.patient-directory-list button').count(),2);
  checks.push('replacing data clears old map emphasis and discharged-patient filters');
  await page.locator('#navigation [data-view="beds"]').click();assert((await page.locator('.gantt').textContent()).includes('퇴실 시각 미확인'));
  await page.locator('.core-bed[data-bed="SICU-01"]').click();assert((await page.locator('#map-detail').textContent()).includes('퇴실 시각 미확인'));
  checks.push('missing ICU exit forecast is labelled unknown on the map and planning timeline');
  d=fixture();d.patients[0].operation_start_minute=60;d.patients[0].estimated_end_minute=180;d.patients[0].actual_end_minute=null;d.patients[0].location='BED-A01';d.beds[0].id='BED-A01';await load(d);
  assert.equal(await page.evaluate(()=>S.patients.find(p=>p.id==='DEMO-011').phase),'ICU');assert.equal(await page.locator('#map-staff-layer>g').count(),0);
  assert.equal(await page.locator('#map-patient-layer [data-id="DEMO-011"]').count(),1);
  checks.push('supplied custom ICU bed IDs and preoperative ICU patients remain correctly placed');
  const before=await page.request.get(url+'/api/state'),state=await before.json();d.beds[0].occupant_id=null;
  response=await page.request.post(url+'/api/actions/import',{data:{dataset:d,expected_revision:state.revision}});assert.equal(response.status(),400);
  const after=await (await page.request.get(url+'/api/state')).json();assert.equal(after.revision,state.revision);assert.equal(after.hospital.current_census,state.hospital.current_census);
  checks.push('inconsistent location and occupancy fail import without replacing current data');
  d=fixture();d.replay_events=[{minute:10,patient_id:'DEMO-011',kind:'location',location:'SICU-02'},{minute:10,patient_id:'DEMO-014',kind:'location',location:'WARD'}];await load(d);
  response=await page.request.post(url+'/api/actions/advance',{data:{minutes:10}});assert(response.ok());await page.evaluate(()=>refresh(true));await page.waitForFunction(()=>S.minute===10);
  assert.equal(await page.evaluate(()=>S.beds.find(b=>b.id==='SICU-02').occupant_id),'DEMO-011');assert.equal(await page.locator('#map-patient-layer>g').count(),2);assert.equal(await page.locator('#map-staff-layer>g').count(),0);
  checks.push('same-timestamp observed transfer updates physical occupancy and the map');
  d=fixture();const longPatient='CASE-VERY-LONG-ANONYMOUS-PATIENT-OPERATION-001',longBed='SURGICAL-INTENSIVE-CARE-BUILDING-A-BED-001';
  d.patients[0].id=longPatient;d.patients[0].location=longBed;d.beds[0].id=longBed;d.beds[0].occupant_id=longPatient;await load(d);
  const patientNode=page.locator('#map-patient-layer>g').filter({has:page.locator('title',{hasText:longPatient})});
  const alias=await patientNode.locator('.map-entity-caption text').textContent();assert(alias.length<=5);
  assert((await page.locator('#map-patient-picker').textContent()).includes(longPatient));
  await page.selectOption('#map-patient-picker',longPatient);assert((await page.locator('#map-detail').textContent()).includes(longPatient));
  await page.evaluate(()=>refresh(true));assert.equal(await patientNode.locator('.map-entity-caption text').textContent(),alias);
  assert((await page.locator('#map-bed-layer>g').filter({has:page.locator('title',{hasText:longBed})}).locator('.map-bed-id').textContent()).length<=5);
  await page.locator('#navigation [data-view="beds"]').click();const timelineButton=page.locator('.gantt-row>button[title="'+longBed+'"]');assert((await timelineButton.textContent()).length<=5);
  checks.push('long source IDs get stable compact map labels while original keys remain in detail');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:checks.length,checks,pageErrors:errors},null,2));
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
