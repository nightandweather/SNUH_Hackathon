const assert=require('node:assert/strict'),labs=require('../static/eight-bed-labs.js');
const c=labs.contextFor({case:{id:'SCN-1',source_case_id:'CASE-1',rows:[{minute:0},{minute:10}]},minute:12});
assert.deepEqual(c,{id:'CASE-1',index:1,minute:12,rowMinute:10});
assert.equal(labs.contextFor({case:{id:'C',rows:[{minute:5}]},minute:4}),null);
const d={case_id:'CASE-1',row_index:1,as_of_minute:10,labs:[{name:'Hb(Hemoglobin)',value:10,chart_minute:9,available_minute:12},{name:'Hb(Hemoglobin)',value:11,chart_minute:5,available_minute:6},{name:'Glucose',value:120,chart_minute:8,available_minute:9}]};
assert.equal(labs.latestEligible(d,c).value,120);
assert.equal(labs.latestEligible(d,c,'Hb(').value,11);
assert.equal(labs.latestEligible({...d,case_id:'CASE-2'},c),null);
assert.equal(labs.latestEligible({...d,row_index:0},c),null);
assert.equal(labs.latestEligible({...d,as_of_minute:20},c),null);
assert.equal(labs.latestEligible({...d,as_of_minute:9},c),null);
assert.equal(labs.latestEligible(d,c,'lactate'),null);
assert.match(labs.cellHTML(d.labs[1],c,'ko'),/7분 전 관측/);
assert.doesNotMatch(labs.cellHTML({...d.labs[1],name:'<script>alert(1)</script>'},c,'en'),/<script>/);
console.log('PASS: scenario source resolution, row/time response identity, no future lab values, query isolation, actual age and escaping.');
const variantData={...d,labs:[
 {name:'Hb(Hemoblobin)[Spectrophotometry]:응급검사실',value:'11.1',unit:'g/dL',chart_minute:3,available_minute:3},
 {name:'[처방불가]Hb (em)',value:'10.8',unit:'g/dL',chart_minute:5,available_minute:5},
 {name:'HBsAg',value:'0',unit:'COI',chart_minute:8,available_minute:8},
 {name:'AntiHBs',value:'120',unit:'IU/L',chart_minute:9,available_minute:9},
 {name:'Glucose(정량)(현장검사)',value:'128',unit:'mg/dL',chart_minute:6,available_minute:6},
 {name:'Glucose(urine)',value:'0',unit:'',chart_minute:9,available_minute:9},
 {name:'Glucose(urine)',value:'1',unit:'mg/dL',chart_minute:8,available_minute:8},
 {name:'Glucose',value:0,unit:'',chart_minute:10,available_minute:10}
]};
assert.equal(labs.latestEligible(variantData,c,'Hb').value,'10.8','Hb whitespace and prefix variant included without hepatitis assays');
assert.equal(labs.latestEligible(variantData,c,'Glucose').value,'128','blood quantitative glucose chosen over urine or unitless code');
assert.equal(labs.latestEligible(variantData,c).value,0,'latest-any can retain a raw coded result');
assert.match(labs.cellHTML(labs.latestEligible(variantData,c),c,'ko'),/원문 값 · 단위 미기재/);
for(const query of ['Creatinine','Potassium','Lactate']){
 const base={name:query,value:'3.5',unit:'mmol/L',chart_minute:5,available_minute:5};
 const choices={...d,labs:[base,{...base,name:query+' (urine)',chart_minute:8,available_minute:8},{...base,unit:' ',value:0,chart_minute:9,available_minute:9}]};
 assert.equal(labs.latestEligible(choices,c,query).chart_minute,5,query+' rejects urine and unitless numeric codes');
 assert.equal(labs.latestEligible({...d,labs:[{...base,value:'negative'}]},c,query),null,query+' requires a finite number');
}
console.log('PASS: Hb source-name variants, exclusion of hepatitis assays and urine values, numeric unit-bearing lab choices, unitless raw-value label.');


const pending=[];global.fetch=(url)=>new Promise(resolve=>pending.push({url,resolve}));
class Element {
 constructor(){this.dataset={};this.children=[];this.isConnected=true;this.events={};this.innerHTML='';}
 append(node){this.children.push(node);node.parent=this;}
 remove(){this.isConnected=false;}
 before(){}
 addEventListener(k,fn){this.events[k]=fn;}
 querySelector(sel){if(sel==='[data-eight-lab-query]')return this.select||(this.select=new Element());return null;}
 querySelectorAll(){return [];}
 matches(){return false;}
}
global.document={createElement:()=>new Element()};
function section(){
 const s=new Element(),table=new Element(),head=new Element(),rows=Array.from({length:8},()=>new Element()),scroll=new Element();
 s.table=table;s.rows=rows;table.querySelector=()=>head;table.querySelectorAll=()=>rows;
 s.querySelector=sel=>sel==='table'?s.table:sel==='.replay-table-scroll'?scroll:null;
 s.contains=cell=>s.rows.some(row=>row.children.includes(cell));return s;
}
const host=new Element();host.section=section();host.querySelector=()=>host.section;
const slot=id=>({case:{id,rows:[{minute:10}]},minute:10});
labs.mount(host,{slots:[slot('CASE-1')],lang:'ko'});const oldCell=host.section.rows[0].children[0];
host.section=section();labs.mount(host,{slots:[slot('CASE-2')],lang:'ko'});const newCell=host.section.rows[0].children[0];
function response(id,value){return {ok:true,json:async()=>({case_id:id,row_index:0,as_of_minute:10,labs:[{name:'Hb',value,chart_minute:5,available_minute:6}]})};}
(async()=>{
 pending[1].resolve(response('CASE-2',11));await new Promise(resolve=>setTimeout(resolve,0));assert.match(newCell.innerHTML,/>11</);
 pending[0].resolve(response('CASE-1',99));await new Promise(resolve=>setTimeout(resolve,0));assert.doesNotMatch(newCell.innerHTML,/>99</);assert.match(oldCell.innerHTML,/불러오는 중/);
 console.log('PASS: late earlier-patient response cannot mutate newly mounted table or detached prior cell.');
})().catch(error=>{console.error(error);process.exitCode=1;});
