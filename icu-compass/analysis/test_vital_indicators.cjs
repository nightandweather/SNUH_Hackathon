const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const v=require('../static/vital-indicators.js');
v.reset();
for(const [key,inside,outside,direction] of [['hr',40,39,'low'],['hr',140,141,'high'],['map',60,59,'low'],['spo2',88,87,'low'],['spo2',100,101,'high'],['rr',35,36,'high'],['sbp',90,89,'low']]){
 assert.equal(v.classify(key,inside).out,false,key+' inclusive display boundary');
 assert.equal(v.classify(key,outside).direction,direction,key+' out of range direction');
}
for(const value of [null,undefined,NaN,Infinity,'88',false,{value:90,conflict:true},-1]){
 assert.equal(v.classify('spo2',value).out,false,'invalid or conflicted value not colored red');
 assert.match(v.valueMarkup('spo2',value),/vital-display-missing/);
}
assert.match(v.valueMarkup('hr',141,'ko'),/vital-display-out/);
assert.match(v.valueMarkup('hr',141,'ko'),/↑/);
assert.match(v.valueMarkup('map',59,'en'),/↓/);
assert.doesNotMatch(v.valueMarkup('hr',80),/vital-display-out/);
assert.match(v.valueMarkup('hr',39.999),/39\.999/,'value not rounded across display boundary');
const before=JSON.stringify(v.getRanges());
for(const input of [{hr:{min:-1}},{hr:{min:'abc'}},{hr:{max:Infinity}},{hr:{min:150,max:50}},{bad:{min:1}},{hr:{max:true}},{hr:{min:'0x10'}}])assert.throws(()=>v.configure(input));
assert.equal(JSON.stringify(v.getRanges()),before,'invalid settings transaction does not partially apply');
v.configure({hr:{min:'',max:'150'},map:{min:'60.5'}});
assert.equal(v.classify('hr',20).out,false,'blank endpoint removes only that bound');
assert.equal(v.classify('hr',151).out,true);
assert.equal(v.classify('map',60.4).out,true);
assert.equal(v.classify('map',60.5).out,false);
const copied=v.getRanges();copied.hr.max=1;assert.equal(v.getRanges().hr.max,150,'returned configuration is independent copy');
v.reset();assert.equal(v.getRanges().hr.min,40);
const setting=v.settings('ko');assert.match(setting,/임상 정상범위 아님/);assert.match(setting,/aria-label="HR 표시 하한"/);assert.match(setting,/data-vital-reset/);assert.doesNotMatch(setting,/data-vital-key="(?:dbp|temp)"/);
const calc={name:'qSOFA',formula:'RR ≥ 22 + SBP ≤ 100 + altered mentation',components:[{name:'RR',value:22,unit:'/min',rule:'≥22',points:1},{name:'SBP',value:110,unit:'mmHg',rule:'≤100',points:0},{name:'GCS',value:15,rule:'<15',points:0}],missing:[],score:1,range:[0,3],source_url:'https://jamanetwork.com/journals/jama/fullarticle/2492881',method_url:'https://www.nature.com/articles/s41467-025-64430-x'};
const complete=v.referencePanel({calculator:calc},'ko');assert.match(complete,/총점: 1/);assert.doesNotMatch(complete,/1 \/ 0–3/);assert.match(complete,/rel="noopener noreferrer"/);
const incomplete=v.referencePanel({calculator:{...calc,missing:['GCS'],score:2}},'ko');assert.match(incomplete,/입력 부족 · 총점 미산출/);assert.doesNotMatch(incomplete,/총점: 2/);
for(const component of [{...calc.components[0],value:null},{...calc.components[0],same_time_conflict:true},{...calc.components[0],value:NaN}]){
 const html=v.referencePanel({calculator:{...calc,components:[component],score:1}},'en');assert.match(html,/Total not calculated/);assert.doesNotMatch(html,/Total: 1/);
}
assert.match(v.referencePanel({qsofa:{...calc,score:0}},'en'),/Total: 0/,'zero is a valid computed score');
const malicious=v.referencePanel({calculator:{...calc,name:'<script>evil</script>',source_url:'javascript:alert(1)',method_url:'https://attacker.test/?evil=1'}},'en');assert.doesNotMatch(malicious,/<script>|javascript:|attacker\.test/);assert.match(malicious,/&lt;script&gt;/);
const memory=new Map(),source=fs.readFileSync(require.resolve('../static/vital-indicators.js'),'utf8');
function moduleWithStorage(){const context={module:{exports:{}},URL,localStorage:{getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value)}};vm.runInNewContext(source,context);return context.module.exports;}
const stored=moduleWithStorage();stored.configure({hr:{min:50,max:120}});assert.equal(moduleWithStorage().getRanges().hr.min,50,'configuration survives module reload');
memory.set(stored.storageKey,'{"hr":{"min":200,"max":10}}');assert.equal(moduleWithStorage().getRanges().hr.min,40,'invalid persisted config falls back to demo defaults');
console.log('PASS: inclusive thresholds, direction/missing/conflict handling, atomic settings validation, local persistence, formula visibility, incomplete-score suppression and safe reference links.');
