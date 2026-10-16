const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const c=vm.createContext({});vm.runInContext(fs.readFileSync('static/network.js','utf8')+fs.readFileSync('static/readiness.js','utf8')+';this.api=Readiness;this.indicators=Network.careIndicators;',c);
const clean={source:'synthetic',pid:'TEST',admit_t:0,arrest:false,pressor:0,calendar_day:0,devices:{ecmo:false,crrt:false,ventilator:false},vitals:{hr:80,map:80,spo2:98,rr:18},care_indicators:{calendar_day:0,cpr_today:false,surgery_today:true,pressor_unstable:false},transfer_review:{current:{rescue:false,postop:false},...Object.fromEntries(['window_complete','no_escalation','targets_met','trends_stable','postop_plan','ward_capacity','consultant','receiving_team','handover','followup'].map(k=>[k,true]))}};
const classify=p=>c.api.evaluate(p,[],100);
assert.equal(classify(clean).decision,'GREEN','surgery alone is not RED');
for(const key of Object.keys(clean.transfer_review).filter(k=>k!=='current')){const p=structuredClone(clean);delete p.transfer_review[key];assert.equal(classify(p).decision,'BLUE',key);}
for(const key of ['ecmo','crrt','ventilator']){const p=structuredClone(clean);p.devices[key]=true;assert.equal(classify(p).decision,'RED',key);p.devices[key]=null;assert.equal(classify(p).decision,'BLUE',key+' missing');}
let p=structuredClone(clean);p.care_indicators.cpr_today=true;assert.equal(classify(p).decision,'RED');assert.equal(classify(p).current,'GREEN','CPR today does not mean ongoing CPR');
p=structuredClone(clean);p.pressor=1;assert.equal(classify(p).decision,'RED');
p=structuredClone(clean);p.vitals.map=null;assert.equal(classify(p).decision,'BLUE');
p=structuredClone(clean);p.source='K-MIMIC';assert.equal(classify(p).decision,'BLUE','real generic ventilator or pressor defaults must not prove absence');
assert.equal(c.api.evaluate(clean,[{t:30,day:0}],100).daily,'RED');assert.equal(c.api.evaluate(clean,[{t:30,day:0}],100).current,'GREEN');assert.equal(c.api.evaluate(clean,[{t:200,day:0}],100).decision,'GREEN','no future data');assert.equal(c.api.evaluate(clean,[{t:0,day:0}],1441).decision,'GREEN','expired window');
const indicators=c.indicators({devices:{ecmo:true,crrt:false}});assert.equal(indicators.ecmo,true);assert.equal(indicators.crrt,false);assert.equal(Object.keys(indicators).length,6);
console.log('Transfer draft checks passed: all GREEN gates, each device, unknowns, CPR timing, missing vitals, source mapping, temporal boundaries and six independent icons.');
