const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const M=require('../static/monthly-replay.js'),S=require('../static/shared-staff.js');
const rows=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../verification/ui-monthly-31-days.json'))),m=M.build(rows);
const checkpoints=new Set([0,m.end,...m.events.flatMap(e=>[e.minute-1,e.minute,e.minute+1]).filter(t=>t>=0&&t<=m.end)]);
for(let t=0;t<=m.end;t+=10)checkpoints.add(t);
const rect=(x,y,w,h)=>({x,y,w,h}),overlap=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
let count=0,moves=0,maxConcurrent=0;const colors=new Set();
for(const t of [...checkpoints].sort((a,b)=>a-b)){
 const f=M.frame(m,t),assignment=M.staffAssignment(f),staff=S.replayFrame({...assignment,minute:t,running:true});
 assert.equal(f.slots.length,8);assert.equal(f.day,Math.floor(t/1440)+1);assert(f.day<=31);
 if(assignment.phase==='idle')assert(f.slots.every(s=>!['red','blue','green'].includes(s.status)||!s.case_id));
 else assert(f.slots[assignment.bedIndex].case_id&&f.slots[assignment.bedIndex].status!=='deceased','Staff target must be an admitted living patient');
 if(assignment.phase==='handoff')assert(f.transports.some(e=>e.bed===assignment.bedIndex),'Handoff follows an active transport');
 const boxes=staff.people.map(p=>rect(p.x-.84,p.y-1.34,1.68,2.65));
 const beds=Array.from({length:8},(_,i)=>rect(.5+i%4*8,i<4?.4:18,7,3.6));
 for(let i=0;i<boxes.length;i++){
  assert(beds.every(b=>!overlap(boxes[i],b)),`Staff/bed overlap at ${t}`);
  for(let j=i+1;j<boxes.length;j++)assert(!overlap(boxes[i],boxes[j]),`Staff/label overlap at ${t}`);
 }
 const porters=f.transports.map(e=>{const top=e.bed<4,p=e.transport==='arrival'?e.progress:1-e.progress,x=4+e.bed%4*8,y=(top?11:13)+((top?5.5:17)-(top?11:13))*p;return rect(x-1.3,y-.9,2.6,1.55);});
 for(let i=0;i<porters.length;i++){
  assert(boxes.every(b=>!overlap(porters[i],b)),`Porter/staff overlap at ${t}`);
  assert(beds.every(b=>!overlap(porters[i],b)),`Porter/bed overlap at ${t}`);
  for(let j=i+1;j<porters.length;j++)assert(!overlap(porters[i],porters[j]),`Porter/porter overlap at ${t}`);
 }
 for(const slot of f.slots)colors.add(slot.status);
 maxConcurrent=Math.max(maxConcurrent,porters.length);moves+=porters.length;count++;
}
for(const e of m.events){
 const slot=M.frame(m,e.minute).slots[e.bed];
 if(e.kind==='arrival_start')assert.equal(slot.status,'yellow');
 if(e.kind==='arrival_handoff')assert(slot.case_id);
 if(e.kind==='arrival_end')assert(['red','blue','green'].includes(slot.status));
 if(e.kind==='departure_exit'){assert.equal(slot.status,'turnover');assert.equal(slot.case_id,null);}
 if(e.kind==='planned_death')assert.equal(slot.status,'deceased');
}
let time=0,visited=new Set([0]);while(time<m.end){time=M.next(m,time,1440);visited.add(time);}
assert(m.events.every(e=>visited.has(e.minute)),'Full-month playback visits every transition');
const result={days:31,beds:8,frames:count,eventRows:m.events.length,transportFrameOccurrences:moves,maxConcurrentTransports:maxConcurrent,statuses:[...colors],allTransitionTimesVisited:true,staffTargetsValidated:true,endpointGeometryOverlapCount:0};
fs.writeFileSync(path.resolve(__dirname,'../../verification/monthly-replay-audit.json'),JSON.stringify(result,null,2));console.log(result);
