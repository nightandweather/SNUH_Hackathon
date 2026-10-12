// Optional development DOM checks: npm install --no-save linkedom.
// App runtime itself does not need Node/npm. Uses a temporary synthetic database.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom');
const {execFileSync}=require('node:child_process'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const states=JSON.parse(execFileSync(process.env.PYTHON_BIN||'python3',['-c',`
from app.engine import Engine
from pathlib import Path
import tempfile,json
with tempfile.TemporaryDirectory() as d:
    e=Engine(Path(d)/'test.db')
    e.mutate('play',{'running':True})
    states={}
    for minute in (0,35,45,135,140):
        if minute>e.state['minute']: e.mutate('advance',{'minutes':minute-e.state['minute']})
        states[str(minute)]=e.view()
    print(json.dumps(states))
`],{cwd:root,encoding:'utf8',maxBuffer:20*1024*1024}));
const {window}=parseHTML(fs.readFileSync(root+'/static/index.html','utf8'));const document=window.document;
// Linkedom has a getter-only select.value; supply the browser's native setter.
const selectValue=Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype,'value');
if(selectValue&&!selectValue.set)Object.defineProperty(window.HTMLSelectElement.prototype,'value',{get:selectValue.get,set(value){for(const o of this.querySelectorAll('option'))o.selected=o.value===value;},configurable:true});
let clock=0,active=null,frames=new Map(),seq=0;Object.defineProperty(document,'activeElement',{get:()=>active});
window.HTMLElement.prototype.focus=function(){active=this;};
for(const proto of [window.HTMLElement.prototype,window.SVGElement.prototype]){
 proto.scrollTo=function(o){this.scrollLeft=o.left||0;this.scrollTop=o.top||0};proto.scrollBy=function(o){this.scrollLeft=(this.scrollLeft||0)+(o.left||0);this.scrollTop=(this.scrollTop||0)+(o.top||0)};
}
window.scrollTo=()=>{};window.scrollY=0;window.matchMedia=()=>({matches:false});
const store=new Map(),context={console,Intl,Date,Math,Number,String,JSON,Set,Map,Error,URL,encodeURIComponent,decodeURIComponent,
 document,window,location:{hash:''},localStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)},
 setTimeout:()=>0,clearTimeout(){},setInterval(){},fetch:async()=>({ok:true,json:async()=>JSON.parse(JSON.stringify(states[0]))}),navigator:{},FormData:class{},performance:{now:()=>clock},
 requestAnimationFrame:fn=>{const id=++seq;frames.set(id,fn);return id},cancelAnimationFrame:id=>frames.delete(id)};
vm.createContext(context);for(const file of ['app.js','hospital.js'])vm.runInContext(fs.readFileSync(root+'/static/'+file,'utf8'),context);
function run(source){return vm.runInContext(source,context)}
function snapshot(n){context.fixture=JSON.parse(JSON.stringify(states[n]));run('S=fixture;U.view="hospital";render();');}
function tick(ms){clock+=ms;const fs=[...frames.values()];frames.clear();fs.forEach(fn=>fn(clock));}
const checks=[];
snapshot(0);assert.equal(document.querySelectorAll('#map-patient-layer>g').length,60);assert.equal(document.querySelectorAll('#map-staff-layer>g').length,13);assert.equal(document.querySelectorAll('#map-bed-layer>g').length,12);checks.push('all patients staff and beds mounted');
const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);assert.equal(ids.length,new Set(ids).size);checks.push('unique IDs after SVG mount');
const patient=document.querySelector('#map-patient-layer>[data-id="DEMO-004"]');snapshot(35);assert.equal(document.querySelector('#map-patient-layer>[data-id="DEMO-004"]'),patient);checks.push('polls preserve patient DOM and focus target');
snapshot(45);run('hospitalAction("map-select",{dataset:{kind:"patient",id:"DEMO-004"}})');assert(document.querySelector('#map-detail').textContent.includes('ICU 이송'));checks.push('selected patient shows route risk and clinical detail');
const before=patient.getAttribute('transform');tick(1400);const after=patient.getAttribute('transform');assert.notEqual(before,after);checks.push('patient coordinates move between server polls');
const pair=run('(()=>{const p=MapUI.nodes.get("patient:DEMO-004");const n=[...MapUI.nodes.values()].find(e=>e.kind==="staff"&&e.item.role==="transport"&&e.item.patient_id==="DEMO-004");return [p.point,n.point]})()');assert(Math.abs(pair[1][0]-pair[0][0]-55)<.1&&Math.abs(pair[1][1]-pair[0][1]-10)<.1);checks.push('nurse follows patient with constant escort offset');
run('S.running=false;S.revision++;render();');const paused=patient.getAttribute('transform');tick(1600);run('updateMapPositions()');assert.equal(patient.getAttribute('transform'),paused);checks.push('pause freezes movement');
run('S.running=true;S.revision++;render();setHospitalConnection(false);');const offline=patient.getAttribute('transform');tick(1600);assert.equal(patient.getAttribute('transform'),offline);checks.push('connection loss stops animation');
run('setHospitalConnection(true);hospitalAction("map-motion",{dataset:{}});');assert.equal(run('MapUI.motion'),false);assert.equal(store.get('pericare-map-motion'),'off');const reduced=patient.getAttribute('transform');tick(1800);assert.equal(patient.getAttribute('transform'),reduced);checks.push('motion preference is persisted and disables animation');
run('MapUI.filter="high";applyMapFilter()');assert.equal(document.querySelector('#map-patient-layer>[data-id="DEMO-005"]').classList.contains('dimmed'),true);checks.push('risk filter dims rather than removes patients');
snapshot(135);assert(document.querySelector('#map-bed-layer>[data-id="SICU-02"]').classList.contains('bed-occupied'));snapshot(140);assert(document.querySelector('#map-bed-layer>[data-id="SICU-02"]').classList.contains('bed-cleaning'));checks.push('actual discharge changes occupied bed to cleaning');
run('hospitalAction("map-select",{dataset:{kind:"bed",id:"SICU-05"}})');assert(document.querySelector('#map-detail').textContent.includes('비수술 환자 A'));checks.push('external occupants remain visible and inspectable');
console.log(JSON.stringify({passed:checks.length,checks,scope:'DOM and animation model; no browser layout engine'},null,2));

