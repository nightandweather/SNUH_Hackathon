const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const context=vm.createContext({structuredClone,I18n:{language:'en'}});
vm.runInContext(fs.readFileSync('static/transfers.js','utf8')+';this.projectEvent=Transfers.projectEvent;',context);
const data=JSON.parse(fs.readFileSync('../public-icu-preview/dist/snapshot.json','utf8'));
const beds=d=>d.floors.flatMap(f=>f.units.flatMap(u=>u.beds)),unit=data.floors.flatMap(f=>f.units).find(u=>u.id==='B-SICU');
const patient=unit.beds.find(b=>b.patient).patient,original=JSON.stringify(data);
for(const kind of ['arrival','departure','or_death','icu_death']){
 const target=unit.beds.find(b=>['arrival','or_death'].includes(kind)?!b.patient&&b.reservation:b.patient);
 for(let stage=0;stage<5;stage++){
  const out=context.projectEvent(data,{kind,stage,bed:target.id,patient,unit:unit.id});
  const bed=beds(out).find(b=>b.id===target.id),available=!bed.patient&&!bed.reservation&&!bed.unavailable;
  assert.equal(available,kind!=='arrival'&&stage===4,`${kind}/${stage}: availability`);
  if(kind==='icu_death'&&stage<2)assert.equal(bed.patient.vitals.hr,null);
  if(kind==='or_death')assert.equal(bed.patient,null);
  if(stage===4&&kind==='arrival')assert.equal(bed.patient.source,'synthetic');
  assert.equal(JSON.stringify(beds(out).filter(b=>b.id!==target.id)),JSON.stringify(beds(data).filter(b=>b.id!==target.id)));
  assert.equal(JSON.stringify(data),original,'input must remain untouched');
 }
}
const html=fs.readFileSync('static/index.html','utf8');for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
console.log('20 transport/death transitions passed: availability, explicit death, input isolation, unaffected beds; inline JS parses.');
for(const kind of ['departure','icu_death','or_death']){
 const target=unit.beds.find(b=>kind==='or_death'?!b.patient&&b.reservation:b.patient);
 const out=context.projectEvent(data,{kind,stage:4,bed:target.id,patient,unit:unit.id,nextReservation:true});
 const b=beds(out).find(x=>x.id===target.id);assert.equal(b.patient,null);assert.ok(b.reservation);assert.equal(b.flow.status.key,'reserved');assert.equal(b.flow.status.color,'#fff1b8');assert.equal(b.unavailable,false);
}
const avatar=html.slice(html.indexOf('function staffAvatar('),html.indexOf('function build(){'));
vm.runInContext(avatar+';this.staffAvatar=staffAvatar;',context);
for(const id of ['MD-B-SICU','MD-C-SICU']){assert.match(context.staffAvatar({id},true),/data-character="male"/);assert.match(context.staffAvatar({id},true),/>Dr\.</);}
assert.match(context.staffAvatar({id:'N-1'},false),/>N</);
console.log('Next reservation stays yellow; all doctors male; nurse badges use capital N.');
vm.runInContext('this.automaticProjection=Transfers.automaticProjection;',context);
const oldBed=unit.beds.find(b=>b.patient),newBed=structuredClone(oldBed);newBed.patient.pid='NEW-SIM-CASE';
const finalData=structuredClone(data);Object.assign(beds(finalData).find(b=>b.id===oldBed.id),newBed);
const ev={oldBed,newBed,unit:unit.id,started:0,clock:'07:00'};
for(const [ms,expected] of [[0,'departure'],[3000,'departure'],[4000,'arrival'],[7000,'arrival']]){
 const p=context.automaticProjection(finalData,ev,ms);assert.equal(p.event.kind,expected);assert.equal(p.done,false);
 const b=beds(p.data).find(b=>b.id===oldBed.id);if(ms>=3000)assert.equal(b.patient,null);else assert.equal(b.patient.pid,oldBed.patient.pid);
}
const done=context.automaticProjection(finalData,ev,8000);assert.equal(done.done,true);assert.equal(beds(done.data).find(b=>b.id===oldBed.id).patient.pid,'NEW-SIM-CASE');
assert.match(fs.readFileSync('../public-icu-preview/dist/index.html','utf8'),/id="flowDetails" open/);
assert.ok(!fs.readFileSync('../public-icu-preview/dist/static/app-shell.css','utf8').includes('#bleedingCase,#flowDetails'));
console.log('Automatic replacement: departure → turnover → arrival → exact target patient; 30-day table visible.');
