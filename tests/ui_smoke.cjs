// HTML generation and application handlers in a minimal DOM harness.
// This does not test browser layout or replace screen-reader/device testing.
// Node 18+, no npm installation. Start the Python server first.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
async function main(){
  const url=(process.argv[2]||'http://localhost:8000').replace(/\/$/,'');
  const response=await fetch(url+'/api/state');assert(response.ok);const state=await response.json();
  const nodes=new Map(),listeners=new Map(),storage=new Map();let dialogsOpened=0,focusCount=0,scrollCount=0;
  function node(key){
    if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',className:'',dataset:{},value:'',id:key.slice(1),
      querySelector:()=>null,querySelectorAll:()=>[],contains:()=>false,setAttribute(k,v){this[k]=v},
      close(){this.open=false},showModal(){this.open=true;dialogsOpened++},focus(){focusCount++},open:false});
    return nodes.get(key);
  }
  const document={documentElement:{dataset:{}},activeElement:null,querySelector:node,getElementById:id=>node('#'+id),
    addEventListener(event,fn){if(!listeners.has(event))listeners.set(event,[]);listeners.get(event).push(fn)}};
  const context={console,Intl,Date,Math,Number,String,JSON,Set,Map,Error,URL,encodeURIComponent,decodeURIComponent,
    document,window:{addEventListener(){},scrollY:240,scrollTo(){scrollCount++}},location:{hash:''},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
    setInterval(){},setTimeout(){},clearTimeout(){},fetch:async()=>({ok:true,json:async()=>state}),navigator:{},FormData:class{}};
  vm.createContext(context);
  for(const name of ['app.js','hospital.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',name),'utf8'),context);
  context.fixture=state;vm.runInContext('S=fixture;U.selected=S.patients[0].id;',context);
  const checks=[];
  assert(listeners.has('DOMContentLoaded'));checks.push('deferred scripts initialize');
  assert.equal(vm.runInContext('nav.length',context),3);checks.push('three focused navigation views');
  for(const fn of ['hospitalView','patientView','bedView']){
    const html=vm.runInContext(fn+'()',context);
    assert(html.length>300,fn+' empty');assert(!html.includes('undefined'));assert(!html.includes('NaN'));
    const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size);
    assert(!/data-action="(approve|admit|discharge|manual-reservation|compare|scenario)"/.test(html));
    checks.push(fn+' valid core HTML without admission questions');
  }
  for(const chart of ['risk','vitals','oxygen']){
    assert(vm.runInContext(`U.chart='${chart}';trajectoryChart(patient())`,context).includes('<svg'));
    checks.push(chart+' observed-series SVG generated');
  }
  const detail=vm.runInContext('patientView()',context);
  for(const label of ['집중관리 지속 예측','ICU 재실 예측','잔여 입원기간','집중관리 필요 예측','ICU 이용 예측','예약·준비·입실'])assert(detail.includes(label));
  checks.push('need, utilization, durations and booking journey visible together');
  vm.runInContext('S.reservations.push({patient_id:S.patients[0].id,status:"confirmed",created_minute:3,start:50,bed_id:"SICU-03",initial_booking_forecast:{recommended_due_minute:2,as_of_minute:1}});S.patients[0].recommendation.due=7',context);
  const originalPlan=vm.runInContext('bookingSteps(S.patients[0])',context);assert(originalPlan.includes('08:32'));assert(!originalPlan.includes('08:37'));assert(originalPlan.includes('08:33'));
  checks.push('booking comparison uses original forecast and actual confirmation, not a later prediction');
  vm.runInContext('S.reservations.pop()',context);
  assert(vm.runInContext('hospitalView()',context).includes('map-patient-picker'));checks.push('native accessible patient picker');
  vm.runInContext("U.view='patients'",context);
  await vm.runInContext("clickAction('text-size',{dataset:{}})",context);
  assert.equal(document.documentElement.dataset.text,'large');assert.equal(storage.get('pericare-text'),'large');
  assert.equal(node('#text-size')['aria-pressed'],'true');checks.push('large type preference persisted');
  const active=node('#patient-search');document.activeElement=active;node('#content').contains=()=>true;
  vm.runInContext("U.view='patients';render()",context);assert(focusCount>0&&scrollCount>0);checks.push('refresh restores focus and scroll');
  document.activeElement=null;node('#content').contains=()=>false;
  vm.runInContext("U.inputsOpen=true",context);assert(vm.runInContext('patientView()',context).includes('clinical-inputs" open'));checks.push('expanded clinical input history survives polling');
  // A discharge forecast does not clear actual occupancy, even when overdue.
  vm.runInContext('S.beds[0].occupant_id="external-patient";S.beds[0].available_minute=S.minute-10;S.beds[0].enabled=true',context);
  const timeline=vm.runInContext('gantt()',context);assert(timeline.includes('external-patient · 실제 퇴실 전까지 점유'));assert(timeline.includes('가용 예상 경과 · 재실 유지'));
  checks.push('overdue forecast retains actual occupant in horizon');
  vm.runInContext('S.beds[0].reservations=[{status:"occupied",start:S.minute,end:S.minute+60,patient_id:"same-occupant"}]',context);
  assert(!vm.runInContext('gantt()',context).includes('same-occupant'));checks.push('occupied reservation does not duplicate actual occupancy');
  vm.runInContext("S.patients[0].surgery='<script>alert(1)</script>';U.selected=S.patients[0].id",context);
  const escaped=vm.runInContext('hospitalView()+patientView()+bedView()',context);
  assert(!escaped.includes('<script>alert(1)'));assert(escaped.includes('&lt;script&gt;'));checks.push('user text escaped in map, patient and bed views');
  vm.runInContext("S.patients[0].prediction.mode='unavailable';S.patients[0].prediction.need_score=null;S.patients[0].prediction.need_probability=null;S.patients[0].prediction.icu_probability=null;S.patients[0].prediction.icu_los_upper=null",context);
  const unavailable=vm.runInContext('patientView()',context);assert(!unavailable.includes('NaN'));assert(unavailable.includes('—'));assert(unavailable.includes('자동 예약 보류'));assert.equal(vm.runInContext('riskClass(null)',context),'unavailable');
  checks.push('unavailable model masked and flagged, not classified as low risk');
  // Clock controls may retry a rejected tick race, while reviewed clinical
  // changes must remain bound to the revision the operator reviewed.
  const originalFetch=context.fetch;let attempts=0;
  const fresh=JSON.parse(JSON.stringify(state));fresh.revision+=10;
  context.fetch=async(path,options={})=>{
    if(options.method==='POST'){
      attempts++;
      if(attempts===1)return {ok:false,status:409,json:async()=>({error:'stale revision'})};
      const body=JSON.parse(options.body);assert.equal(body.expected_revision,fresh.revision);assert.equal(body.running,false);
      return {ok:true,json:async()=>({ok:true})};
    }
    return {ok:true,json:async()=>fresh};
  };
  assert(await vm.runInContext("act('play',{running:false},'')",context));assert.equal(attempts,2);
  checks.push('pause intent retries a rejected clock tick race once');
  attempts=0;
  context.fetch=async(path,options={})=>{
    if(options.method==='POST'){attempts++;return {ok:false,status:409,json:async()=>({error:'stale revision'})};}
    return {ok:true,json:async()=>fresh};
  };
  assert.equal(await vm.runInContext("act('cancel',{reservation_id:'test'},'')",context),null);assert.equal(attempts,1);
  checks.push('reviewed clinical changes never retry stale revisions');context.fetch=originalFetch;
  console.log(JSON.stringify({passed:checks.length,checks,scope:'HTML/SVG generation and handler harness; browser rendering not tested'},null,2));
}
main().catch(e=>{console.error(e);process.exit(1)});
