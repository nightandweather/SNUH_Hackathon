/* Observed operational records only. No clinical clearance or capacity inference. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUOperationsModel=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const finite=n=>typeof n==='number'&&Number.isFinite(n),bool=v=>v===true?true:v===false?false:null;
  function derive(state){
    const now=finite(state?.t)?state.t:0,horizon=360;
    const units=state?.floors?.flatMap(f=>f.units)||[],rawBeds=units.flatMap(u=>u.beds);
    const beds=units.flatMap(unit=>unit.beds.map(b=>{
      const record=b.operational_readiness||{},requirements={staff:bool(record.staff),equipment:bool(record.equipment),cleaning:bool(record.cleaning)};
      const kind=b.patient?'occupied':b.unavailable?'turnover':b.reservation?'reserved':'vacant';
      const missing=Object.keys(requirements).filter(key=>requirements[key]===null),pending=Object.keys(requirements).filter(key=>requirements[key]===false);
      const prep=kind==='occupied'?'occupied':kind==='turnover'?'turnover':pending.length?'pending':missing.length?'unknown':'confirmed';
      const nurse=(state.nurses||[]).find(n=>n.id===b.nurse);
      return {id:b.id,unit:unit.id,kind,prep,requirements,missing,pending,owner:nurse?.id||null,expected_t:finite(b.reservation?.expected_t)?b.reservation.expected_t:null,reservation:b.reservation||null,flow:b.flow||null};
    }));
    const ids=new Set(beds.map(b=>b.id));
    const reservations6h=beds.filter(b=>b.kind==='reserved'&&finite(b.expected_t)&&b.expected_t>=now&&b.expected_t<=now+horizon).map(b=>({bed:b.id,unit:b.unit,expected_t:b.expected_t,confirmed:false,source:b.reservation.source||null}));
    const support=(state?.incidents||[]).filter(i=>ids.has(i.bed)&&i.type!=='focus').map(i=>{
      const need=finite(i.need)?Math.max(0,i.need):null,responders=[...new Set(i.responders||[])],arrived=[...new Set(i.arrived||[])];
      return {incidentId:i.id,bed:i.bed,unit:i.unit,need,responders,arrived,arrivedCount:arrived.length,pending:responders.filter(id=>!arrived.includes(id)),shortage:need===null?null:Math.max(0,need-responders.length),start:finite(i.start)?i.start:null,label:i.label||'',source:i.simulated?'simulation':'record'};
    });
    const timeline=[...reservations6h.map(r=>({...r,key:'reservation:'+r.bed,kind:'reservation',at:r.expected_t})),...beds.filter(b=>b.flow).map(b=>({key:'flow:'+b.id,bed:b.id,unit:b.unit,kind:b.flow.kind,at:now,label:b.flow.label,stage:b.flow.stage,confirmed:false}))].sort((a,b)=>a.at-b.at||a.bed.localeCompare(b.bed));
    const groupedReservations=new Map();
    for(const event of timeline.filter(row=>row.key.startsWith('reservation:'))){
      if(!groupedReservations.has(event.at))groupedReservations.set(event.at,{at:event.at,events:[]});
      groupedReservations.get(event.at).events.push(event);
    }
    const scheduleGroups=[...groupedReservations.values()];
    const currentFlows=timeline.filter(row=>row.key.startsWith('flow:')&&finite(row.stage)&&row.stage>=0&&row.stage<4);
    const nurseContext=(state?.nurses||[]).map(n=>({id:n.id,unit:n.unit,role:n.role,assigned:(n.beds||[]).filter(id=>ids.has(id)),cover:(n.cover||[]).filter(id=>ids.has(id)),onBreak:!!n.on_break,incident:n.incident??null,status:n.status,events:support.filter(i=>i.responders.includes(n.id)),devices:(n.beds||[]).flatMap(id=>{
      const patient=rawBeds.find(b=>b.id===id)?.patient;if(!patient)return [];
      return ['ecmo','crrt','ventilator'].filter(k=>patient.devices?.[k]===true).map(k=>({bed:id,key:k}));
    })}));
    return {scope:units.map(u=>u.id),clock:state?.clock||'',now,horizon,beds,vacantCount:beds.filter(b=>b.kind==='vacant').length,readyCount:beds.filter(b=>b.kind==='vacant'&&b.prep==='confirmed').length,unknownPrepCount:beds.filter(b=>b.kind!=='occupied'&&b.kind!=='turnover'&&b.prep==='unknown').length,pendingPrepCount:beds.filter(b=>b.prep==='pending').length,reservations6h,support,timeline,scheduleGroups,currentFlows,nurseContext,metrics:{occupied:beds.filter(b=>b.kind==='occupied').length,total:beds.length,turnover:beds.filter(b=>b.kind==='turnover').length,activeTransport:beds.filter(b=>b.flow&&b.flow.stage<4).length,completedTransport:beds.filter(b=>b.flow&&b.flow.stage===4).length,admissionWaitMinutes:null,turnoverMinutes:null,overtimeMinutes:null}};
  }
  function clockAt(state,at){if(!finite(at))return null;const parts=String(state.clock||'07:00').split(':').map(Number);const minute=((parts[0]*60+parts[1]-Number(state.t||0)+at)%1440+1440)%1440;return String(Math.floor(minute/60)).padStart(2,'0')+':'+String(Math.floor(minute%60)).padStart(2,'0');}
  return Object.freeze({derive,clockAt});
});
