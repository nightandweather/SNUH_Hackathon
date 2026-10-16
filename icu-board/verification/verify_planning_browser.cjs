const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('/Users/iganghun/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const executable = fs.existsSync(chromium.executablePath()) ? chromium.executablePath() : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({headless:true,executablePath:executable});
  const context = await browser.newContext({viewport:{width:1440,height:1100},timezoneId:'UTC'});
  const page = await context.newPage();
  const errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1:8002/') && !request.url().startsWith('data:')) external.push(request.url()); });
  await page.goto('http://127.0.0.1:8002/planning');
  await page.waitForFunction(() => view.state?.scenario_id && !view.loading);
  async function click(id, status=200) {
    const [response] = await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/planning/action') && response.request().method()==='POST'),page.locator('#'+id).click()]);
    assert.equal(response.status(),status);
    const body = await response.json();
    await page.waitForFunction(() => !view.busy);
    return body;
  }
  await page.locator('#seedInput').fill('7');
  await click('resetButton');
  assert.equal(await page.evaluate(()=>view.patientId),'P003');
  assert.match(await page.locator('#clock').innerText(),/07:00/);
  assert.match(await page.locator('#calendarMeta').innerText(),/금요일/);
  assert.match(await page.locator('#modeStatus').innerText(),/모델 미호출/);
  await page.locator('#modeSelect').selectOption('live');
  await click('proposeButton',503);
  assert.match(await page.locator('#agentStatus').innerText(),/실패/);
  assert.equal(await page.evaluate(()=>view.state.plans.length),0);
  assert.equal(await page.evaluate(()=>view.state.agent_status.model_called),false);
  await page.locator('#modeSelect').selectOption('offline');
  const proposal = await click('proposeButton');
  assert.equal(proposal.plan.status,'proposed');
  assert.equal(proposal.agent.model_called,false);
  assert.match(await page.locator('#planStatus').innerText(),/승인 대기/);
  await click('conflictButton');
  await click('approveButton',409);
  assert.equal(await page.locator('#error').isVisible(),true);
  const replanned = await click('replanButton');
  assert.notEqual(replanned.plan.id,proposal.plan.id);
  await click('approveButton');
  assert.match(await page.locator('#planStatus').innerText(),/승인됨|확정/);
  assert.equal(await page.locator('#conflictButton').isDisabled(),true);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(__dirname,'..','planning-screen.png'),fullPage:true});
  await click('resetButton');
  // The browser's timezone is UTC; the simulated calendar must still jump to KST 07:00.
  async function jump(day, expected) {
    const [response] = await Promise.all([page.waitForResponse(response=>response.url().endsWith('/api/planning/action')),page.locator(`[data-weekday="${day}"]`).click()]);
    assert.equal(response.status(),200);
    const body=await response.json();
    await page.waitForFunction(()=>!view.busy);
    assert.equal(body.state.calendar.weekday,expected);
    assert.match(body.state.calendar.datetime,/T07:00\+09:00$/);
    return body;
  }
  const saturday=await jump(6,'Saturday');
  assert.equal(saturday.state.calendar.elective_surgery_open,false);
  assert.match(await page.locator('#calendarMeta').innerText(),/토요일/);
  await jump(1,'Monday');
  assert.match(await page.locator('#calendarMeta').innerText(),/월요일/);
  await click('resetButton');
  const sizing=[];
  for (const width of [390,320]) {
    await page.setViewportSize({width,height:1000});
    await page.waitForTimeout(100);
    const measurement=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert.ok(measurement.scroll<=measurement.width+1,JSON.stringify(measurement));
    sizing.push(measurement);
  }
  await page.setViewportSize({width:390,height:1100});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(__dirname,'..','planning-mobile.png'),fullPage:true});
  assert.equal(external.length,0);
  assert.equal(errors.length,0);
  const report={status:'passed',scope:'synthetic_operational_demo',real_model_call_verified:false,
    checks:['visible_patient_selection','proposal_approval_separate','conflict_reject_replan_approve',
      'weekend_calendar_and_monday','kst_jumps_in_utc_browser','responsive_390_and_320','no_external_requests','no_javascript_errors','missing_model_configuration_is_not_success'],
    widths:sizing,external_requests:external,javascript_errors:errors,verified_at:new Date().toISOString()};
  fs.writeFileSync(path.join(__dirname,'planning-browser.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
  await browser.close();
})().catch(error=>{console.error(error);process.exitCode=1;});
