// Selected-time movement history, with monthly plans kept separate from source events.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const ctx=vm.createContext({URLSearchParams,location:{search:''},lang:'en',time:'0',data:null,
 t:(ko,en)=>en,esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),at:c=>c.rows[c.initial]});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/shared-clinical-render.js'),'utf8'),ctx);
ctx.source={id:'SOURCE',source:'K-MIMIC',dataset:'test',initial:0,rows:[{minute:0},{minute:20},{minute:40}],los_min:40,gs_selection:{scenario_events:[
 {kind:'ed_within_24h_before_icu',table:'ADMISSIONS',minute:-60,evidence_status:'confirmed'},
 {kind:'next_unit_unclassified',table:'TRANSFERS',minute:30,evidence_status:'confirmed'},
 {kind:'next_unit_unclassified',table:'TRANSFERS',minute:30,evidence_status:'confirmed'},
 {kind:'death_during_icu',table:'ADMISSIONS',minute:35,evidence_status:'confirmed'},
 {kind:'next_unit_unclassified',table:'WRONG_TABLE',minute:10,evidence_status:'confirmed'},
 {kind:'next_unit_unclassified',table:'TRANSFERS',minute:10,evidence_status:'unconfirmed'},
 {kind:'surgery_record_during_icu',table:'PROCEDUREEVENTS',minute:15,evidence_status:'confirmed'}]}};
ctx.data={cases:[ctx.source],scenario_cases:[{id:'REPLAY',source:'ScenarioReplay',source_case_id:'SOURCE',dataset:'test',initial:0,scenario_replay:{episode_id:'E01'}}],monthly_plan:{by_hospital:{test:{days:[
 {day:1,beds:[{case_id:'REPLAY',episode_id:'E01',event:'ER'}]},
 {day:2,beds:[{case_id:'REPLAY',episode_id:'E01',event:''}]},
 {day:3,beds:[{case_id:'REPLAY',episode_id:'E01',event:'GW'}]},
 {day:4,beds:[{case_id:'REPLAY',episode_id:'E02',event:'DEATH'}]}
]}}}};
const before=JSON.stringify(ctx.data);
const read=code=>vm.runInContext(code,ctx);
assert.deepEqual(JSON.parse(JSON.stringify(read('sourceMovementRecords(source,{minute:20})'))).map(e=>e.kind),['ed_within_24h_before_icu','icu_admission']);
assert.equal(read('sourceMovementRecords(source,{minute:30}).length'),3,'Duplicate source events are rendered once');
assert.equal(read('sourceMovementRecords(source,{minute:NaN}).length'),0,'Invalid checkpoints cannot reveal future records');
assert.equal(read('sourceMovementRecords(source,{minute:40}).length'),4,'Replay end must not invent a discharge event');
assert.equal(read('sourceMovementRecords(displayCases()[1],{minute:30}).length'),3,'Replay assignments retain the source movement history');
read("hospital='test';viewPhase='monthly';monthlyIndex=1");
let html=read('transferDetails(displayCases()[1],{minute:20})');
assert(html.includes('ICU admission')&&html.includes('Emergency department exit'));
assert(!html.includes('Transfer after ICU')&&!html.includes('Death recorded'),'Later source events remain hidden');
assert(!html.includes('Transfer to general ward')&&!html.includes('ICU death'),'Future monthly-plan outcomes remain hidden');
assert(html.includes('planned-transfer-history')&&html.includes('separate from the source movement records'));
read('monthlyIndex=2');html=read('transferDetails(displayCases()[1],{minute:30})');
assert(html.includes('Transfer after ICU · Destination unit type unknown'),'Unknown destination is not relabelled as ward transfer');
assert(html.includes('Transfer to general ward')&&html.includes('3 day'));
assert(!html.includes('ICU death'),'An adjacent reused episode must not leak into this episode');
assert.equal(JSON.stringify(ctx.data),before,'Rendering does not change source records, plan colors, or patient assignments');
const events=fs.readFileSync(path.join(__dirname,'../static/shared-clinical-events.js'),'utf8');
assert(events.includes('transferDetails(c,r)+equipmentDetails(c,r)'),'Movement history must be mounted in the real detail view');
console.log('Transfer detail selected-time, replay-reference and plan separation checks passed.');
