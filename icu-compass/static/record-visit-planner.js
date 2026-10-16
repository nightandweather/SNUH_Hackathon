/* Source-record visit ranking only; no severity score or treatment inference. */
const RecordVisitPlanner=(()=>{
 'use strict';
 const variables=['hr','map','spo2','rr','sbp'];
 const names={hr:'HR',map:'MAP',spo2:'SpO₂',rr:'RR',sbp:'SBP'};
 const finite=value=>typeof value==='number'&&Number.isFinite(value);
 function observations(row){
  const result={};if(!row||!finite(row.minute)||row.minute<0)return result;
  for(const key of variables){const value=row.vitals?.[key],age=row.age?.[key];
   // The thirty-minute bound is the existing source-replay validity contract,
   // not a new clinical alert cutoff. Missing values never become zero.
   if(finite(value)&&finite(age)&&age>=0&&age<=30&&row.minute-age>=0)
    result[key]={value,minute:row.minute-age};
  }return result;
 }
 function describe(bed){
  const current=observations(bed.current),previous=observations(bed.previous),fresh=[],changed=[];
  let magnitude=0;
  for(const key of variables){const now=current[key],before=previous[key];if(!now)continue;
   if(!before||now.minute>before.minute)fresh.push(key);
   if(before&&now.minute>=before.minute&&now.value!==before.value){changed.push(key);
    // Unit-independent relative difference is only a deterministic tie-breaker.
    // It is never interpreted as clinical severity or a reason to treat.
    magnitude+=Math.abs(now.value-before.value)/Math.max(Math.abs(now.value),Math.abs(before.value),1);
   }
  }
  return {index:bed.index,newKeys:fresh,changedKeys:changed,magnitude,
          existingAlert:bed.hasExistingAlert===true};
 }
 function plan({beds=[],fallbackIndex=0,phase='nurse',minute=0}={}){
  const candidates=beds.filter(b=>Number.isInteger(b.index)&&b.index>=0&&b.index<8).map(describe);
  if(!candidates.length)return {bedIndex:null,method:'none',reason_ko:'표시할 환자 기록 없음',reason_en:'No displayed patient record',newObservationCount:0,changedVariableCount:0};
  const fallback=Number.isInteger(fallbackIndex)&&fallbackIndex>=0&&fallbackIndex<8?fallbackIndex:0;
  const distance=i=>(i-fallback+8)%8;
  candidates.sort((a,b)=>Number(b.existingAlert)-Number(a.existingAlert)||b.changedKeys.length-a.changedKeys.length||b.magnitude-a.magnitude||b.newKeys.length-a.newKeys.length||distance(a.index)-distance(b.index)||a.index-b.index);
  const selected=candidates[0],newNames=selected.newKeys.map(k=>names[k]).join('·'),changedNames=selected.changedKeys.map(k=>names[k]).join('·');
  const method=selected.existingAlert?'existing-alert':selected.changedKeys.length?'changed-observation':selected.newKeys.length?'new-observation':'scheduled';
  const ko=selected.existingAlert?'화면에 이미 표시된 알림 확인':selected.newKeys.length?`새 관측 ${newNames}${changedNames?' · 값 변화 '+changedNames:''}`:selected.changedKeys.length?'원본 기록 값 변경 '+changedNames:'새 관측 없는 구간 · 순서에 따른 라운딩';
  const en=selected.existingAlert?'Review an alert already shown on the board':selected.newKeys.length?`New observations ${newNames}${changedNames?' · Changed values '+changedNames:''}`:selected.changedKeys.length?'Source-record values changed '+changedNames:'No new observations · Scheduled rounding';
  return {bedIndex:selected.index,method,reason_ko:(phase==='doctor'?'Dr. 기록 검토 · ':'N 기록 확인 · ')+ko,
          reason_en:(phase==='doctor'?'Dr. record review · ':'N record check · ')+en,
          newObservationCount:selected.newKeys.length,changedVariableCount:selected.changedKeys.length,
          newObservationKeys:[...selected.newKeys],changedVariableKeys:[...selected.changedKeys],
          existingAlert:selected.existingAlert,minute:finite(minute)?minute:null,
          clinicalSeverityAssessed:false,staffMovementSimulated:true};
 }
 return {plan,observations};
})();
if(typeof window!=='undefined')window.RecordVisitPlanner=RecordVisitPlanner;
if(typeof module!=='undefined'&&module.exports)module.exports=RecordVisitPlanner;
