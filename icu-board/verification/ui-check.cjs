// Offline VM and lightweight DOM checks. This does not launch a browser or use HTTP.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.style = {};
    this.value = '';
    this.textContent = '';
    this.disabled = false;
    this.listeners = {};
    this._html = '';
    this.classList = {
      contains: value => (this.attributes.class || '').split(' ').includes(value),
      add: value => this.attributes.class = `${this.attributes.class || ''} ${value}`,
      remove: value => this.attributes.class = (this.attributes.class || '').split(' ').filter(item => item !== value).join(' '),
      toggle: (value, enabled) => enabled ? this.classList.add(value) : this.classList.remove(value),
    };
  }
  set innerHTML(value) {
    this._html = value;
    this.children = [];
    // Model the placeholders used to insert handover activity text with DOM nodes.
    for (const match of value.matchAll(/<div class="handover-sim-activities" data-bed="([^"]+)"/g)) {
      const placeholder = new Element();
      placeholder.setAttribute('class', 'handover-sim-activities');
      placeholder.dataset.bed = match[1];
      this.appendChild(placeholder);
    }
  }
  get innerHTML() { return this._html; }
  set className(value) { this.attributes.class = value; }
  get className() { return this.attributes.class || ''; }
  get firstChild() { return this.children[0]; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  removeAttribute(key) { delete this.attributes[key]; }
  appendChild(child) {
    if (child.parentNode && child.parentNode !== this) {
      child.parentNode.children = child.parentNode.children.filter(item => item !== child);
    }
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelector(selector) {
    return this.children.find(child => selector.startsWith('.')
      ? (child.attributes.class || '').split(' ').includes(selector.slice(1))
      : child.tagName === selector) || null;
  }
}

const elements = new Map();
const get = selector => {
  if (!elements.has(selector)) elements.set(selector, new Element());
  return elements.get(selector);
};
const document = {
  querySelector: get,
  querySelectorAll(selector) {
    if (selector === '#handoverPatients .handover-sim-activities') {
      return get('#handoverPatients').children.filter(child => child.classList.contains('handover-sim-activities'));
    }
    return [];
  },
  createElement: tag => new Element(tag),
  createElementNS: (_namespace, tag) => new Element(tag),
  createTextNode: text => Object.assign(new Element('#text'), {textContent: text}),
};
const htmlPath = path.join(__dirname, '..', 'static', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const source = html.split('<script>')[1].split('</script>')[0].replace(/\npoll\(\);\s*$/, '\n');
const ids = [...html.split('<script>')[0].matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
assert.equal(ids.length, new Set(ids).size, 'Static HTML IDs must be unique');
const context = vm.createContext({
  assert, console, document, Element, get, URL, URLSearchParams,
  location: {search: ''}, history: {replaceState() {}},
  requestAnimationFrame: callback => callback(), setTimeout: () => 0,
  fetch() { throw new Error('Unexpected HTTP request during offline verification'); },
});
new vm.Script(source, {filename: htmlPath}).runInContext(context);

new vm.Script(`
const units=['PICU','NICU','MICU','CCU','CSICU','SICU2','SICU1','EICU'];
const userAction={t:460,clock:'14:40',nurse_id:'MICU-1',staff_id:'D-MICU-1',shift_code:'D',cycle:0,bed:'MICU-1',pid:'P1',admit_t:0,text:'<img src=x onerror=example()> 사용자 입력',source:'user_entered'};
const activity={t:470,clock:'14:50',nurse_id:'MICU-1',staff_id:'D-MICU-1',shift_code:'D',cycle:0,bed:'MICU-1',pid:'P1',admit_t:0,type:'arrival',text:'<script>출동 도착 시연</script>',source:'simulation_activity',incident_id:1};
const patient={pid:'P1',admit_t:0,dx:'검증 환자',source:'synthetic',risk:45,vitals:{hr:90,map:65,spo2:94,rr:22},abn:[],hours:2};
const floors=Array.from({length:4},(_,index)=>({floor:7-index,units:units.slice(index*2,index*2+2).map((unit,column)=>({id:unit,name:unit,x:column*42,w:40,h:20,beds:Array.from({length:8},(_,bedIndex)=>({id:unit+'-'+(bedIndex+1),x:column*42+4+bedIndex*4,y:bedIndex%2?16:4,nurse:unit+'-'+(Math.floor(bedIndex/2)+1),patient:unit==='MICU'&&bedIndex===0?patient:null}))}))}));
const nurses=units.flatMap((unit,index)=>Array.from({length:5},(_,slot)=>({id:unit+'-'+(slot+1),staff_id:'D-'+unit+'-'+(slot+1),shift_code:'D',shift_label:'Day',role:slot===4?'charge':'bedside',unit,floor:7-Math.floor(index/2),x:index%2*42+5+slot*5,y:10,beds:slot===4?[]:[unit+'-'+(2*slot+1),unit+'-'+(2*slot+2)],cover:[],status:'care',on_break:false,incident:null,fatigue:20,work:30,breaks:0,activities:unit==='MICU'&&slot===0?[activity]:[]})));
const doctors=units.map((unit,index)=>({id:'MD-'+unit,unit,role:'전담/당직 MD(시연)',floor:7-Math.floor(index/2),x:index%2*42+20,y:10,status:'available',incident:null}));
const roster=['D','E','N'].flatMap((code,index)=>nurses.map(nurse=>({staff_id:code+'-'+nurse.id,slot_id:nurse.id,unit:nurse.unit,role:nurse.role,shift_code:code,shift_label:['Day','Evening','Night'][index],on_duty:code==='D'})));
S={floors,nurses,doctors,roster,shift:{code:'D',label:'Day',start_clock:'07:00',end_clock:'15:00',remaining_min:10,in_handover:true,next_code:'E',next_label:'Evening',on_duty:40,total_staff:120},shift_schedule:[],clock:'14:50',running:false,speed:2,source:['synthetic'],seed:1,t:470,policy:'auto',metrics:{arrest:{n:0,first_resp:null,full_team:null,helpers:0},det:{n:0,first_resp:null,helpers:0},focus:{n:0},fatigue_mean_label:'현재 Day 근무조 평균 피로도'},log:[],incidents:[],floor_h:20,floor_w:84,elevator_x:42,fatigue_high:75,fatigue_warn:60,care_actions:[userAction],activities:[activity],last_handover:null,handover_history:[]};
draw();
assert.equal(Object.keys(floorSvg).length,4);
assert.equal(Object.keys(bedEl).length,64);
assert.equal(Object.keys(nurseEl).length,40);
assert.equal(Object.keys(doctorEl).length,8);
assert.equal(roster.length,120);
assert.equal(get('#nextShift').disabled,false);
assert.equal(get('#shiftPrep').style.display,'block');

Object.assign(C,{bed:'MICU-1',nurse_id:'MICU-1',staff_id:'D-MICU-1',shift_label:'Day',patient_key:{pid:'P1',admit_t:0},actions:[],activities:[],stale:''});
renderCareActions([userAction,activity]);
assert.equal(C.actions.length,1);
assert.equal(get('#cCareActions').children[0].children[1].textContent,userAction.text);
assert.equal(get('#cCareActions').children[0].children[1].innerHTML,'');
renderPatientActivities([userAction,activity,{...activity,pid:'other-patient'},{...activity,admit_t:480}]);
assert.equal(C.activities.length,1);
assert.equal(get('#cActivities').children[0].children[1].textContent,activity.text);
assert.equal(get('#cActivities').children[0].children[1].innerHTML,'');
assert.match(get('#cActivities').children[0].children[0].textContent,/14:50.*D-MICU-1.*도착/);

picked='N:MICU-1';detail();
const nurseActivityBlock=get('#detail').children.at(-1);
assert.equal(nurseActivityBlock.children[0].textContent,'이번 근무 시뮬레이션 활동');
assert.match(nurseActivityBlock.children[1].textContent,/실제 환자 처치 기록 아님/);
assert.equal(nurseActivityBlock.children[2].children[0].children[1].textContent,activity.text);

rosterUnit='MICU';
S.last_handover={t:480,clock:'15:00',from_code:'D',to_code:'E',from_label:'Day',to_label:'Evening',patients:[{bed:'MICU-1',pid:'P1',dx:'검증 환자',risk:45,vitals:patient.vitals,abn:[],open_events:[],from_staff_id:'D-MICU-1',to_staff_id:'E-MICU-1',actions:[userAction],activities:[activity]}]};
drawHandover();
assert.match(get('#handoverPatients').innerHTML,/사용자 입력 수행 기록 1건/);
assert.match(get('#handoverPatients').innerHTML,/시뮬레이션 활동 1건 · 실제 처치 기록 아님/);
assert(get('#handoverPatients').innerHTML.includes('&lt;img src=x onerror=example()&gt;'));
const handoverActivity=get('#handoverPatients').children.find(child=>child.classList.contains('handover-sim-activities'));
assert.equal(handoverActivity.children[0].children[1].textContent,activity.text);
assert.equal(handoverActivity.children[0].children[1].innerHTML,'');

S.t=1440;S.clock='07:00';drawShifts();
assert.equal(get('#nextShift').disabled,true);
assert.equal(get('#shiftCurrent').textContent,'24시간 시연 완료');
assert.match(get('#shiftMessage').textContent,/24시간 시연 완료/);
assert.equal(get('#shiftPrep').style.display,'none');
get('#nextShift').onclick(); // Must return before trying HTTP after completion.
`, {filename: 'ui-verification-fixtures'}).runInContext(context);

(async () => {
  await new vm.Script(`(async()=>{
const descendants=node=>[node,...node.children.flatMap(descendants)];
const fakeResponse=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const settle=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();await Promise.resolve();};
const requests=[];
S.t=120;S.clock='09:00';picked='MICU-1';me='';
const currentPatient=findBed(picked).patient;
const historyResult={bed:picked,patient_key:{pid:'P1',admit_t:0},as_of:'09:00',t:120,source:'MIMIC-IV',points:[
  {t:-1,clock:'06:59',hr:999,simulated:false},
  {t:0,clock:'07:00',hr:80,map:65,spo2:94,rr:null,simulated:false},
  {t:30,clock:'07:30',hr:777,observed_vitals:{hr:null},map:null,spo2:null,rr:null,simulated:false},
  {t:60,clock:'08:00',hr:200,map:45,spo2:75,rr:null,observed_vitals:{hr:90,map:70,spo2:96,rr:null},simulated:true},
  {t:121,clock:'09:01',hr:888,simulated:false},
]};
let resolveHistory;
fetch=(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return new Promise(resolve=>resolveHistory=resolve);};
detail();detail();
assert.equal(requests.length,1,'Only selected patient is loaded; no overlapping history poll');
assert.equal(requests[0].url,'/api/patient');
assert.equal(requests[0].body.staff_id,'D-MICU-1');
assert.equal(requests[0].body.patient_key.admit_t,0);
resolveHistory(fakeResponse({history:historyResult,patient_key:historyResult.patient_key,diagnostics:[]}));
await settle();
assert.equal(P.history.t,120);
assert.equal(trendPoints(P.history).length,3,'Past two hours only, never future values');
assert.equal(recordedVital(historyResult.points[2],'hr'),null,'Explicit missing observation is not filled from an effective value');
assert.match(get('#patientAsOf').textContent,/MIMIC-IV.*09:00/);
const cards=get('#patientTrends').children;
assert.equal(cards.length,4);
assert.equal(cards[0].children[1].textContent,'90');
assert.match(cards[0].children[2].textContent,/마지막 재생 시점 08:00/);
assert.match(get('#patientHistorySource').textContent,/원본 측정 시각과 다를 수 있음/);
const hrPaths=descendants(cards[0]).filter(node=>node.tagName==='path');
assert.equal(hrPaths.length,2,'Recorded values and injected demo values use separate traces');
assert.equal(hrPaths[0].attributes.stroke,'var(--care)');
assert.equal(hrPaths[1].attributes.stroke,'var(--mid)');
assert(!hrPaths[0].attributes.d.includes('L'),'Do not connect over a missing observation');
const hrTitles=descendants(cards[0]).filter(node=>node.tagName==='title').map(node=>node.textContent);
assert(hrTitles.some(text=>text.includes('기록')&&text.includes('90')));
assert(hrTitles.some(text=>text.includes('응급 시연 주입')&&text.includes('200')));
assert(!hrTitles.some(text=>text.includes('999')||text.includes('777')||text.includes('888')));
assert.match(descendants(cards[3]).map(node=>node.textContent).join(' '),/관측 기록 없음.*표시할 관측값 없음/);
const realNow=Date.now;let mockNow=100000;Date.now=()=>mockNow;P.lastRequested=mockNow;
const intervalRequests=requests.length;
fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return fakeResponse({patient_key:historyResult.patient_key,history:{...historyResult,source_description:'원본 기록을 이월해 재생할 수 있습니다.'},diagnostics:[]});};
mockNow+=2999;syncPatientPanel();assert.equal(requests.length,intervalRequests);
mockNow+=1;syncPatientPanel();await settle();assert.equal(requests.length,intervalRequests+1,'The lazy selected-patient poll runs every three seconds');
assert.match(get('#patientHistorySource').textContent,/원본 기록을 이월/);
Date.now=realNow;

const portable={id:'DX-1',kind:'portable_xray',bed:'MICU-1',pid:'P1',admit_t:0,unit:'MICU',nurse_id:'MICU-1',requested_by_staff_id:'D-MICU-1',requested_t:100,requested_clock:'08:40',status:'image_available',source:'simulation_workflow',simulated:true,events:[{t:110,clock:'08:50',status:'image_available',text:'<img src=x onerror=bad()> 촬영 시연',staff_id:'D-MICU-1',source:'simulation_activity'}],image_source:'public_nih_example',patient_linked:false,image_url:'/static/cxr/example.png',image_id:'example',review:null};
P.diagnostics=[portable];renderDiagnostics();
let dxNodes=descendants(get('#patientDiagnostics'));
assert(dxNodes.some(node=>node.tagName==='img'&&node.src==='/static/cxr/example.png'));
assert(dxNodes.some(node=>node.textContent.includes('이 환자의 영상이 아니며')));
const dxEvent=dxNodes.find(node=>node.tagName==='li');
assert(dxEvent.textContent.includes('<img src=x onerror=bad()>'));
assert.equal(dxEvent.innerHTML,'','Event text cannot execute HTML');
assert(dxNodes.some(node=>node.tagName==='button'&&node.dataset.imageReview==='DX-1'));
const stateTask={...portable};delete stateTask.image_url;delete stateTask.image_id;
assert.equal(mergeDiagnostics([stateTask])[0].image_url,portable.image_url,'State poll preserves API preview metadata');
assert.equal(mergeDiagnostics([{...stateTask,status:'cancelled'}])[0].image_url,undefined,'Cancelled task does not retain a preview');

fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return fakeResponse({task_id:'DX-1',patient_key:{pid:'P1',admit_t:0},mode:'unavailable',model:null,text:'VL 모델 미연결',source:'public_nih_example',diagnostics:[portable]});};
await reviewDiagnostic('DX-1');
assert.equal(requests.at(-1).url,'/api/image-review');
assert.equal(requests.at(-1).body.task_id,'DX-1');
assert.equal(requests.at(-1).body.staff_id,'D-MICU-1');
assert.match(get('#diagnosticMessage').textContent,/검토를 실행하지 않았습니다/);
assert(descendants(get('#patientDiagnostics')).some(node=>node.textContent==='영상 모델 검토 미실행'));
assert(!P.reviewBusy);

fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return fakeResponse({error:'현재 담당자가 변경되었습니다'},409);};
await requestDiagnostic('blood_draw');
assert.equal(requests.at(-1).body.kind,'blood_draw');
assert.match(P.message,/담당자.*다시 선택/);
assert.equal(P.diagnostics.length,1,'A failed request does not fabricate a completed diagnostic');

// An in-flight history/model response must never attach to a different admission.
let resolveStaleHistory;
P.lastRequested=0;fetch=(url,options)=>new Promise(resolve=>resolveStaleHistory=resolve);
const oldHistoryLoad=loadPatientHistory();
currentPatient.admit_t=40;
fetch=async(url,options)=>{const selection=JSON.parse(options.body);return fakeResponse({patient_key:selection.patient_key,history:{...historyResult,patient_key:selection.patient_key,points:[]},diagnostics:[]});};
syncPatientPanel();await settle();
assert.equal(P.selection.patient_key.admit_t,40);
resolveStaleHistory(fakeResponse({patient_key:{pid:'P1',admit_t:0},history:historyResult,diagnostics:[portable]}));await oldHistoryLoad;
assert.equal(P.history.patient_key.admit_t,40);
assert.equal(P.diagnostics.length,0);

currentPatient.admit_t=0;syncPatientPanel();await settle();P.diagnostics=[portable];
let resolveStaleModel;
fetch=(url,options)=>new Promise(resolve=>resolveStaleModel=resolve);
const staleReview=reviewDiagnostic('DX-1');
assert(P.reviewBusy);
currentPatient.admit_t=50;
fetch=async(url,options)=>{const selection=JSON.parse(options.body);return fakeResponse({patient_key:selection.patient_key,history:{...historyResult,patient_key:selection.patient_key,points:[]},diagnostics:[]});};
syncPatientPanel();await settle();
resolveStaleModel(fakeResponse({patient_key:{pid:'P1',admit_t:0},task_id:'DX-1',text:'오래된 환자에 대한 영상 응답',mode:'model',model:'VL-test',diagnostics:[portable]}));await staleReview;
assert.equal(P.selection.patient_key.admit_t,50);
assert.equal(P.diagnostics.length,0);
assert(!P.message.includes('오래된 환자'));

// The completed handover keeps fixed snapshot/admission/staff identity.
currentPatient.admit_t=0;S.t=480;S.clock='15:00';me='MICU-1';
for(const nurse of S.nurses){nurse.staff_id='E-'+nurse.id;nurse.shift_code='E';nurse.shift_label='Evening';}
const handoverPatient={bed:'MICU-1',pid:'P1',admit_t:0,dx:'검증 환자',risk:45,vitals:currentPatient.vitals,abn:[],open_events:[],from_staff_id:'D-MICU-1',to_staff_id:'E-MICU-1',actions:[],activities:[],diagnostics:[{...portable,status:'requested',paused:true,pause_reason:'응급 대응 우선'},{...portable,id:'DX-2',kind:'blood_draw',status:'specimen_sent'}],receipt:{status:'pending',questions:[]}};
S.last_handover={t:480,clock:'15:00',from_code:'D',to_code:'E',from_label:'Day',to_label:'Evening',patients:[handoverPatient]};
rosterUnit='MICU';H.signature='';drawHandover();
const handoverKey=[...H.rows.keys()][0];
assert(H.rows.get(handoverKey).eligible);
assert.equal(H.rows.get(handoverKey).staff_id,'E-MICU-1');
assert.equal(H.rows.get(handoverKey).handover_t,480);
assert.match(get('#handoverPatients').innerHTML,/수신 확인 대기/);
assert.match(get('#handoverPatients').innerHTML,/검체 전달 시연 완료/);
assert.match(get('#handoverPatients').innerHTML,/응급 대응 우선/);
const sameChildren=get('#handoverPatients').children;drawHandover();
assert.equal(get('#handoverPatients').children,sameChildren,'An unchanged snapshot is not rebuilt while a question is being typed');

H.drafts.set(handoverKey,'<script>저장할 질문</script>');
fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return fakeResponse({error:'교대 자료가 변경되었습니다'},409);};
await sendHandoverAction(handoverKey,'question');
assert.equal(requests.at(-1).url,'/api/handover');
assert.equal(requests.at(-1).body.action,'question');
assert.equal(requests.at(-1).body.handover_t,480);
assert.equal(requests.at(-1).body.patient_key.admit_t,0);
assert.equal(requests.at(-1).body.staff_id,'E-MICU-1');
assert(!Object.hasOwn(requests.at(-1).body,'eligible'),'Private UI fields are not sent as API identity');
assert.equal(H.drafts.get(handoverKey),'<script>저장할 질문</script>','A rejected question keeps the draft');
assert.match(H.messages.get(handoverKey),/교대 자료가 변경/);
assert(get('#handoverPatients').innerHTML.includes('&lt;script&gt;저장할 질문&lt;/script&gt;'));

fetch=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});return fakeResponse({ok:true,receipt:{status:body.action==='ack'?'received':'question_open',received_by:'E-MICU-1',received_t:480,received_clock:'15:00',questions:body.action==='question'?[{t:480,clock:'15:00',staff_id:'E-MICU-1',text:body.text,source:'user_entered'}]:[]}});};
await sendHandoverAction(handoverKey,'question');
assert.equal(H.drafts.has(handoverKey),false);
assert.equal(S.last_handover.patients[0].receipt.status,'question_open');
assert.match(H.messages.get(handoverKey),/질문 저장됨.*답변 대기.*실제 메시지/);
assert(get('#handoverPatients').innerHTML.includes('&lt;script&gt;저장할 질문&lt;/script&gt;'));
await sendHandoverAction(handoverKey,'ack');
assert.equal(S.last_handover.patients[0].receipt.status,'received');
assert.match(get('#handoverPatients').innerHTML,/인계 수신 확인됨/);

me='MICU-2';H.signature='';drawHandover();
assert.equal(H.rows.get(handoverKey).eligible,false,'A different current nurse cannot receive this handover');
const beforeRequests=requests.length;await sendHandoverAction(handoverKey,'ack');assert.equal(requests.length,beforeRequests);
me='';H.signature='';drawHandover();
assert.match(get('#handoverPatients').innerHTML,/받는 담당자 역할 시연.*실제 로그인 아님/);
assert(H.rows.get(handoverKey).eligible);
currentPatient.admit_t=70;H.signature='';drawHandover();
assert.equal(H.rows.get(handoverKey).eligible,false,'A new patient admission cannot receive an old handover');
})()`, {filename: 'patient-workflow-fixtures'}).runInContext(context);

  console.log(`PASS: JavaScript syntax and ${ids.length} unique static IDs.`);
  console.log('PASS: Offline DOM preserves 4 floors, 8 ICUs, 64 beds, 40 nurse markers and 8 distinct MD markers.');
  console.log('PASS: User-entered care records and simulation activities remain separate and use textContent for activity text.');
  console.log('PASS: Patient/admission filtering, modal activities, current-nurse activities and completed-handover activity blocks.');
  console.log('PASS: After 24 hours, next-shift control is disabled, completion is visible and no request is sent.');
  console.log('PASS: Selected-patient history uses actual past observations only, keeps missing values and separates demo overlays.');
  console.log('PASS: Diagnostic API identity, safe event text, public-example image metadata, unavailable VL status and failed requests.');
  console.log('PASS: Late history/model responses are discarded after a patient admission changes.');
  console.log('PASS: Handover receiving staff/admission/snapshot checks, unchanged input rendering, question drafts on 409 and safe receipt text.');
  console.log('LIMITATION: VM/lightweight DOM and mocked fetch verification only; no browser rendering, HTTP integration or live model call was tested here.');
})().catch(error => { console.error(error); process.exitCode = 1; });
