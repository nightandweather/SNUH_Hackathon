// Pure state/translation contracts; browser interactions are verified separately.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const raw=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const ctx=vm.createContext({URLSearchParams,location:{search:''},localStorage:{getItem:()=>null},MutationObserver:class{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/network.js'),'utf8')+';this.network=Network;',ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'static/i18n.js'),'utf8')+';this.i18n=I18n;',ctx);
const original=JSON.stringify(raw);
for(const id of ['A','B','C']){
 const state=ctx.network.scopeState(raw,id);
 assert.equal(state.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).length,32);
 assert.equal(state.nurses.length,20);
 assert.equal(state.shift.on_duty,20);
 assert.ok(state.floors.every(f=>f.units.every(u=>u.hospital_id===id)));
 const unit=id==='A'?'SICU':`${id}-SICU`,single=ctx.network.scopeState(raw,id,unit);
 assert.equal(single.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).length,8);
 for(const key of ['nurses','doctors','roster'])assert.ok(single[key].every(x=>x.unit===unit));
 assert.ok(single.incidents.every(i=>i.unit===unit));
 assert.equal(single.shift.on_duty,5);
}
assert.equal(JSON.stringify(raw),original);
const care=p=>JSON.parse(JSON.stringify(ctx.network.careIndicators(p)));
assert.ok(Object.values(care({})).every(x=>x===null));
assert.equal(care({devices:{ecmo:true,crrt:null}}).ecmo,true);
assert.equal(care({devices:{ecmo:false,crrt:false}}).crrt,false);
assert.equal(care({devices:{ecmo:false,crrt:null}}).crrt,null);
assert.equal(care({arrest:true,pressor:1}).cpr_today,null);
assert.equal(care({arrest:true,pressor:1}).pressor_unstable,null);
const indicators={calendar_day:0,cpr_today:true,surgery_today:true,pressor_unstable:true};
assert.equal(care({calendar_day:1,care_indicators:indicators}).cpr_today,null);
assert.equal(care({calendar_day:1,care_indicators:indicators}).surgery_today,null);
assert.ok(Object.values(care({calendar_day:0,care_indicators:indicators,devices:{ventilator:true,crrt:true,ecmo:true}})).every(x=>x===true));
assert.ok(ctx.network.findings({vitals:{},extra_observations:{}}).every(row=>row[2]===null));
assert.equal(ctx.i18n.t('Demo Hospital B · B-SICU · 8 Beds'),'가상 병원 B · B-SICU · 8 병상');
assert.equal(ctx.i18n.t('Patient SIM-B-SICU-01 · HR 128 mmHg'),'환자 SIM-B-SICU-01 · HR 128 mmHg');
assert.equal(ctx.i18n.t('Critical · active emergency'),'위급 · 응급 이벤트 진행');
console.log('PASS: 3 hospital scopes, ward/staff/event isolation, immutable source state, unknown findings, translations and IDs');

for(const a of [true,false,null])for(const b of [true,false,null]){
 const p={devices:{ecmo:a,crrt:b}},d=ctx.network.careDisplayIndicators(p);
 assert.equal(Object.keys(d).length,5);
 assert.equal(d.ecmo_crrt,a===true||b===true?true:a===false&&b===false?false:null);
 assert.equal((ctx.network.careMapIcons(p).match(/role="img"/g)||[]).length,5);
}
console.log('PASS: combined ECMO/CRRT preserves positive, negative and unknown evidence');
