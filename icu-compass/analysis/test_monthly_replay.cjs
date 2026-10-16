const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path'),M=require('../static/monthly-replay.js');
const empty=()=>({status:'empty',case_id:null}),cell=(id,status,event='')=>({case_id:id,episode_id:id,status,event});
const rows=[{day:1,beds:[cell('A','red','ER'),cell('D','red','CPR'),...Array.from({length:6},empty)]},{day:2,beds:[cell('A','blue'),cell('D','red','Death'),cell('B','red','OP'),...Array.from({length:5},empty)]},{day:3,beds:[cell('A','green','GW'),empty(),cell('B','blue'),...Array.from({length:5},empty)]}];
const before=JSON.stringify(rows),model=M.build(rows);
assert.equal(M.frame(model,0).slots[0].status,'yellow');
assert.equal(M.frame(model,540).transports[0].transport,'arrival');
assert.equal(M.frame(model,540).slots[0].case_id,null);
assert.equal(M.frame(model,550).slots[0].case_id,'A');
assert.equal(M.frame(model,560).slots[0].status,'red');
assert.equal(M.frame(model,1440).day,2);assert.equal(M.frame(model,1440).slots[0].status,'blue');
assert.equal(M.frame(model,1440+960).slots[1].status,'deceased');
assert.equal(M.frame(model,1440+960).transports.length,0,'Death alone must not produce a porter move');
assert.equal(M.frame(model,2880).day,3);assert.equal(M.frame(model,2880).slots[0].status,'green');
assert.equal(M.frame(model,2880).slots[1].status,'deceased','Previous deceased patient remains until planned next-day turnover');
assert.equal(M.frame(model,2880+480).transports[0].transport,'departure');
assert.equal(M.frame(model,2880+490).slots[1].status,'turnover');assert.equal(M.frame(model,2880+500).slots[1].status,'empty');
assert.equal(M.frame(model,2880+840).slots[0].flow,'departure');
assert.equal(M.frame(model,2880+850).slots[0].case_id,null);assert.equal(M.frame(model,2880+860).slots[0].status,'empty');
assert.equal(M.frame(model,99999).day,3);assert.equal(M.frame(model,99999).minute,4319);
let minute=0,visited=[];while(minute<model.end){const next=M.next(model,minute,180);assert(next>minute);minute=next;visited.push(minute);}
assert(model.events.filter(e=>e.minute>0).every(e=>visited.includes(e.minute)),'Fast playback must land on every transport stage');
const source={initial:0,rows:[{minute:5},{minute:15},{minute:25}]},saved=JSON.stringify(source);
assert.equal(M.sourceRow(source,{admittedAt:560},550).minute,5);assert.equal(M.sourceRow(source,{admittedAt:560},570).minute,15);assert.equal(M.sourceRow(source,{admittedAt:560},4319).minute,25);assert(M.sourceRow(source,{admittedAt:560},4319).exhausted);assert.equal(JSON.stringify(source),saved);
assert.equal(JSON.stringify(rows),before,'The monthly workbook remains unchanged');
// Template aliases can repeat; episode identity drives replacement transport.
const replacements=M.build([{day:1,beds:[{...cell('SAME','red'),episode_id:'old'}]},{day:2,beds:[{...cell('SAME','red'),episode_id:'new'}]}]);
assert(replacements.events.some(e=>e.minute===1440+480&&e.kind==='departure_start'));
assert(replacements.events.some(e=>e.minute===1440+540&&e.kind==='arrival_start'));
// A full provided month retains the same early-day semantics and ends at the
// final actual dated row, never by replay-record length or a fixed three days.
const month=Array.from({length:31},(_,i)=>({day:i+1,beds:[
 cell('LONG',i===30?'green':'blue',i===30?'GW':''),
 i>=14&&i<17?cell('MID','red',i===14?'OP':''):empty(),
 i>=27&&i<30?cell('LATE','red',i===29?'Death':''):empty(),
 ...Array.from({length:5},empty)
]})),full=M.build(month);
assert.equal(full.end,31*1440-1);assert.equal(full.days.length,31);
assert.equal(M.frame(full,14*1440+560).slots[1].case_id,'MID');
assert.equal(M.frame(full,17*1440+490).slots[1].status,'turnover');
assert.equal(M.frame(full,17*1440+500).slots[1].status,'empty');
assert.equal(M.frame(full,29*1440+960).slots[2].status,'deceased');
assert.equal(M.frame(full,30*1440).slots[0].status,'green');
assert.equal(M.frame(full,30*1440+500).slots[2].status,'empty');
assert.equal(M.frame(full,30*1440+860).slots[0].status,'empty');
const last=M.frame(full,Number.MAX_SAFE_INTEGER);assert.equal(last.day,31);assert.equal(last.clockMinute,1439);assert.equal(last.minute,full.end);
assert.equal(M.next(full,full.end,1440),full.end,'End-of-month replay must not enter day32');
minute=0;visited=[];while(minute<full.end){const next=M.next(full,minute,1440);assert(next>minute);minute=next;visited.push(minute);}
assert(full.events.filter(e=>e.minute>0).every(e=>visited.includes(e.minute)),'Full-month fast speed preserves every handoff and color transition');
assert.equal(M.build(month.slice(0,28)).end,28*1440-1,'Model duration follows the actual table length');
const ctx=vm.createContext({URLSearchParams,location:{search:''},lang:'en',time:'0',data:{cases:[],monthly_plan:{by_hospital:{test:{days:month}}}},at:()=>null,t:(ko,en)=>en,esc:String,window:{MonthlyReplay:M},clearInterval:()=>{},GroundedChat:{close(){}},$:()=>({open:false})});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/shared-clinical-render.js'),'utf8'),ctx);
vm.runInContext("hospital='test';render=()=>{};seekPlanReplay(30*1440)",ctx);
assert.equal(vm.runInContext('planReplay.minute',ctx),30*1440);assert.equal(vm.runInContext('monthlyIndex',ctx),30);assert.equal(vm.runInContext('planReplay.timer',ctx),null,'Date jumps pause playback');
vm.runInContext('seekPlanReplay(999999)',ctx);assert.equal(vm.runInContext('planFrame().day',ctx),31);assert.equal(vm.runInContext('planFrame().clockMinute',ctx),1439);
vm.runInContext('seekPlanReplay(0)',ctx);assert.equal(vm.runInContext('planFrame().day',ctx),1);assert.equal(vm.runInContext('monthlyIndex',ctx),0);
console.log('Full-month and first-three-day replay boundaries, transfers, colors, date jumps and source clamping passed.');
