const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/shared-staff.js'),'utf8');
const simulation=require('../static/shared-staff.js');

for(const kind of ['calm','busy','help','arrival','departure'])for(let bed=0;bed<8;bed++)for(let stage=0;stage<5;stage++){
 const frame=simulation.frame(kind,stage,bed);
 assert.deepEqual(frame,simulation.frame(kind,stage,bed),'deterministic scene');
 assert.equal(frame.simulation,true);
 assert.equal(frame.people.length,6);
 assert.equal(frame.people.find(p=>p.role==='doctor').gender,'male');
 assert.deepEqual(new Set(frame.people.filter(p=>p.role==='nurse').map(p=>p.gender)),new Set(['female','male']));
 for(let i=0;i<frame.people.length;i++)for(let j=i+1;j<frame.people.length;j++){
  const a=frame.people[i],b=frame.people[j];assert.ok(Math.hypot(a.x-b.x,a.y-b.y)>=2.25,'staff do not overlap');
 }
 assert.ok(frame.people.every(p=>p.x>0&&p.x<32&&p.y>=6.2&&p.y<=16.3));
 assert.ok(frame.people.every(p=>Number.isInteger(p.tasks)&&p.tasks>=0));
}
const before=simulation.frame('calm');before.people[0].home[0]=-1;
assert.equal(simulation.frame('calm').people[0].home[0],1.8,'frame owns its position arrays');
assert.equal(simulation.frame('help',1).people.find(p=>p.id==='NC').state,'called');
assert.equal(simulation.frame('help',3).people.find(p=>p.id==='Dr.').state,'responding');
assert.ok(simulation.avatar({id:'N1',role:'nurse',gender:'female'}).includes('>N1</text>'));
assert.ok(simulation.avatar({id:'Dr.',role:'doctor',gender:'female'}).includes('data-character="male"'));
assert.ok(simulation.frame('arrival',0).porter.y>simulation.frame('arrival',3).porter.y);
assert.ok(simulation.frame('departure',0).porter.y<simulation.frame('departure',3).porter.y);
for(let bed=0;bed<8;bed++)for(const phase of ['nurse','doctor','hold']){
 const input={minute:20,bedIndex:bed,phase,running:true},current=simulation.replayFrame(input);
 assert.deepEqual(current,simulation.replayFrame(input),'record-linked movement is deterministic');
 assert.equal(current.porter,null,'record replay does not invent admission or discharge');
 assert.ok(current.people.every(p=>p.tasks===null),'record replay never claims completed care counts');
 assert.equal(current.people[bed%4].state,'checking');
 for(let i=0;i<current.people.length;i++)for(let j=i+1;j<current.people.length;j++){
  const a=current.people[i],b=current.people[j];assert.ok(Math.hypot(a.x-b.x,a.y-b.y)>=2.25,'replay people do not overlap');
 }
}
assert.equal(simulation.replayFrame({minute:0}).phase,'nurse');
assert.equal(simulation.replayFrame({minute:10}).phase,'doctor');
assert.equal(simulation.replayFrame({minute:20}).phase,'nurse');
assert.equal(simulation.replayFrame({minute:Infinity}).minute,0);
assert.equal(simulation.replayFrame({bedIndex:-3}).bed,0);
assert.equal(simulation.replayFrame({bedIndex:99}).bed,7);

// A bounded component DOM double verifies actual handlers/timers, without a
// browser or any patient records. It retains handler objects across redraws.
class Element {
 constructor(name='div'){this.name=name;this.attributes={};this.dataset={};this.children=[];this.style={};this.isConnected=true;this.queries=new Map();this.classList={toggle(){}};}
 setAttribute(k,v){this.attributes[k]=String(v);}
 appendChild(child){if(child.parent)child.parent.children=child.parent.children.filter(c=>c!==child);child.parent=this;child.isConnected=this.isConnected;child.ownerSVGElement=this.name==='svg'?this:this.ownerSVGElement;this.children.push(child);return child;}
 before(child){document.elements.set(child.id,child);}
 remove(){this.isConnected=false;}
 addEventListener(name,fn){this['on'+name]=fn;}
 closest(){return {setAttribute(){}};}
 set innerHTML(value){this.html=value;}
 get innerHTML(){return this.html||'';}
 querySelector(selector){
  const staffId=selector.match(/^\[data-sim-staff="(.+)"\]$/)?.[1];
  const walk=node=>{for(const child of node.children){if(staffId&&child.attributes['data-sim-staff']===staffId)return child;if(selector==='[data-route]'&&Object.hasOwn(child.dataset,'route'))return child;if(selector.startsWith('.')&&child.attributes.class?.split(' ').includes(selector.slice(1)))return child;if(selector==='title'&&child.name==='title')return child;const deep=walk(child);if(deep)return deep;}return null;};
  const match=walk(this);if(match)return match;
  if(!this.queries.has(selector))this.queries.set(selector,new Element());
  return this.queries.get(selector);
 }
}
const document={elements:new Map(),createElement:name=>new Element(name),createElementNS:(_,name)=>new Element(name),getElementById(id){return this.elements.get(id)||null;}};
for(const id of ['floors','staffNote','rosterSummary'])document.elements.set(id,new Element());
let nextTimer=0;const timers=new Map(),moduleContext={exports:{}},events=[];
const context={module:moduleContext,document,window:{addEventListener(){},dispatchEvent:event=>events.push(event.type)},CustomEvent:class{constructor(type){this.type=type;}},setInterval:fn=>{const id=++nextTimer;timers.set(id,fn);return id;},clearInterval:id=>timers.delete(id)};
vm.runInNewContext(source,context);const component=moduleContext.exports;
const svg=new Element('svg'),input={svg,hospital:'H1',unit:'SICU',lang:'en',planDay:1,beds:[{index:0,hasLinkedRecord:true}]};
component.mount(input);const panel=document.elements.get('staffSimulationPanel');
assert.ok(panel);panel.querySelector('[data-staff-play]').onclick();assert.equal(timers.size,1);
component.mount({...input,svg:new Element('svg')});assert.equal(timers.size,1,'same scope does not add timer');
panel.querySelector('[data-staff-play]').onclick();assert.equal(timers.size,0,'pause stops timer');
panel.querySelector('[data-staff-play]').onclick();panel.querySelector('[data-staff-reset]').onclick();assert.equal(timers.size,0,'reset stops timer');
panel.querySelector('[data-staff-play]').onclick();component.mount({...input,hospital:'H2'});assert.equal(timers.size,0,'scope change stops timer');
panel.querySelector('[data-staff-play]').onclick();for(let i=0;i<5;i++)for(const tick of [...timers.values()])tick();assert.equal(timers.size,0,'playback stops at final stage');
panel.querySelector('[data-staff-play]').onclick();assert.equal(timers.size,1);
component.setReplayFrame({minute:0,bedIndex:2,phase:'nurse',running:true});assert.equal(timers.size,0,'main record replay cancels independent manual timer');
assert.match(panel.querySelector('[data-staff-status]').textContent,/N bedside record check/);
const previousSvg=svg,oldLayer=previousSvg.querySelector('.staff-simulation-layer'),oldNurse=oldLayer.querySelector('[data-sim-staff="N3"]');
const replacementSvg=new Element('svg');component.mount({...input,hospital:'H2',svg:replacementSvg});
assert.equal(replacementSvg.querySelector('.staff-simulation-layer'),oldLayer,'same-scope redraw transplants existing layer');
assert.equal(replacementSvg.querySelector('[data-sim-staff="N3"]'),oldNurse,'staff DOM identity persists for smooth transforms');
component.setReplayFrame({minute:10,bedIndex:2,phase:'doctor',running:true});assert.equal(timers.size,0,'record update has no staff interval');
assert.match(panel.querySelector('[data-staff-status]').textContent,/Dr\. bedside review/);
const transform=replacementSvg.querySelector('[data-sim-staff="Dr."]').style.transform;
component.setReplayFrame({minute:10,bedIndex:2,phase:'doctor',running:false});
assert.equal(replacementSvg.querySelector('[data-sim-staff="Dr."]').style.transform,transform,'pause keeps current positions');
assert.match(panel.querySelector('[data-staff-status]').textContent,/Paused/);
panel.querySelector('[data-staff-scene]').onchange({target:{value:'busy'}});
assert.deepEqual(events,['staff-simulation-manual'],'manual scene tells main replay to pause once');
component.setReplayFrame({minute:30,bedIndex:3,running:true});component.mount({...input,hospital:'H2',planDay:2,svg:new Element('svg')});
assert.doesNotMatch(panel.querySelector('[data-staff-status]').textContent,/Replay elapsed/,'day change clears record frame');
component.setReplayFrame({minute:40,bedIndex:3,running:true});component.setReplayFrame(null);
assert.doesNotMatch(panel.querySelector('[data-staff-status]').textContent,/Replay elapsed/,'null exits record mode');
assert.equal(timers.size,0);
panel.querySelector('[data-staff-play]').onclick();component.dispose();assert.equal(timers.size,0,'dispose stops timer');
assert.deepEqual(input.beds,[{index:0,hasLinkedRecord:true}],'staff mount does not mutate patient slots');
console.log('PASS: 200 manual and 24 record-linked frames, non-overlap, source-independent movement, no competing replay timer, DOM continuity, pause/reset/scope/disposal cleanup; no patient mutation.');
