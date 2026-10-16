/* Monthly-table demonstration clock. Source records and clinical states are never modified. */
const MonthlyReplay=(()=>{
 const DAY=1440,occupied=c=>['red','blue','green'].includes(c?.status),identity=c=>c?.episode_id||c?.case_id||null;
 const empty=()=>({status:'empty',case_id:null,episode_id:null,event:''});
 function build(rows){
  const days=rows.filter(r=>Number.isInteger(r.day)&&r.day>=1).sort((a,b)=>a.day-b.day),end=Math.max(1,...days.map(r=>r.day))*DAY-1,events=[],last=Array.from({length:8},empty);let order=0;
  const add=(minute,bed,kind,cell,extra={})=>events.push({minute,bed,kind,cell:{...cell},order:order++,...extra});
  for(const row of days)for(let bed=0;bed<8;bed++){
   const base=(row.day-1)*DAY,target={...empty(),...row.beds[bed]},previous=last[bed],same=occupied(target)&&identity(target)&&identity(target)===identity(previous)&&previous.status!=='empty';
   if(same){add(base,bed,'daily_status',{...target,admittedAt:previous.admittedAt});}
   else{
    if(previous.case_id){
     add(base+480,bed,'departure_start',{...previous,flow:'departure'},{transport:'departure',end:base+500});
     add(base+490,bed,'departure_exit',{...empty(),status:'turnover'});
     add(base+500,bed,'departure_end',occupied(target)?{...empty(),status:'yellow'}:target);
    }else add(base,bed,'daily_status',occupied(target)?{...empty(),status:'yellow'}:target);
    if(occupied(target)){
     add(base+540,bed,'arrival_start',{...empty(),status:'yellow',flow:'arrival'},{transport:'arrival',end:base+560});
     add(base+550,bed,'arrival_handoff',{...target,admittedAt:base+560,flow:'handoff'});
     add(base+560,bed,'arrival_end',{...target,admittedAt:base+560});
    }
   }
   let final=occupied(target)?{...target,admittedAt:same?previous.admittedAt:base+560}:target;
   if(occupied(target)&&String(target.event).toUpperCase()==='GW'){
    add(base+840,bed,'departure_start',{...final,flow:'departure'},{transport:'departure',end:base+860});
    add(base+850,bed,'departure_exit',{...empty(),status:'turnover'});add(base+860,bed,'departure_end',empty());final=empty();
   }else if(occupied(target)&&String(target.event).toUpperCase()==='DEATH'){
    final={...final,status:'deceased'};add(base+960,bed,'planned_death',final);
   }
   last[bed]=final;
  }
  events.sort((a,b)=>a.minute-b.minute||a.order-b.order);return {events,end,days:days.map(r=>r.day)};
 }
 function frame(model,minute){
  minute=Math.max(0,Math.min(model.end,Number(minute)||0));const slots=Array.from({length:8},empty),history=[];
  for(const e of model.events){if(e.minute>minute)break;slots[e.bed]={...e.cell};if(e.kind!=='daily_status')history.push(e);}
  const transports=model.events.filter(e=>e.transport&&e.minute<=minute&&minute<e.end).map(e=>({...e,progress:(minute-e.minute)/(e.end-e.minute)}));
  return {minute,day:Math.floor(minute/DAY)+1,clockMinute:minute%DAY,slots,transports,history};
 }
 function next(model,minute,step=60){const event=model.events.find(e=>e.minute>minute);return Math.min(model.end,minute+step,event?.minute??Infinity);}
 function sourceRow(c,slot,minute){if(!c?.rows?.length)return null;const base=c.rows[c.initial||0]?.minute??c.rows[0].minute,target=base+Math.max(0,minute-(slot?.admittedAt??minute));let index=0;for(let i=0;i<c.rows.length;i++){if(c.rows[i].minute<=target)index=i;else break;}return {index,minute:c.rows[index].minute,exhausted:target>c.rows.at(-1).minute};}
 function staffAssignment(frame){
  const move=frame.transports.find(m=>frame.slots[m.bed]?.case_id&&frame.slots[m.bed]?.status!=='deceased');
  if(move)return {bedIndex:move.bed,phase:'handoff',reason_ko:'이송 중인 병상 인계 · 모의',reason_en:'Transport bedside handoff · simulated'};
  const beds=frame.slots.map((s,i)=>occupied(s)&&s.case_id?i:null).filter(i=>i!==null);
  if(!beds.length)return {bedIndex:null,phase:'idle',reason_ko:'입실 환자 없음 · 대기',reason_en:'No admitted patients · Standby'};
  return {bedIndex:beds[Math.floor(frame.minute/20)%beds.length],phase:Math.floor(frame.minute/10)%2?'doctor':'nurse',reason_ko:'월간표 일정에 따른 모의 라운딩',reason_en:'Scheduled monthly-plan rounds'};
 }
 return {build,frame,next,sourceRow,staffAssignment};
})();
if(typeof window!=='undefined')window.MonthlyReplay=MonthlyReplay;
if(typeof module!=='undefined'&&module.exports)module.exports=MonthlyReplay;
