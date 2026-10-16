/* The selected person, staffing slot and team timetable are separate records. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUNurseProfile=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  function derive(state,slotId){
    const nurse=state?.nurses?.find(n=>n.id===slotId);if(!nurse)return null;
    const unit=state.floors.flatMap(f=>f.units).find(u=>u.id===nurse.unit);
    if(!unit)return null;
    const beds=new Map(state.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).map(b=>[b.id,b]));
    const rows=(ids,relationship)=>[...new Set(ids||[])].map(id=>beds.get(id)).filter(Boolean).map(b=>({
      bedId:b.id,relationship,occupied:Boolean(b.patient),reserved:Boolean(b.reservation),deceased:b.flow?.kind==='icu_death',
      patient:b.patient?{pid:b.patient.pid??null,admit_t:b.patient.admit_t??null,age:b.patient.age??null,sex:b.patient.sex??null,source:b.patient.source??null}:null,
      lastAssignedDate:null,lastAssignedStatus:'not_recorded'
    }));
    const assigned=rows(nurse.beds,'assigned'),coverage=rows(nurse.cover,'coverage');
    const schedule=state.shift_schedule||[],code=nurse.shift_code??state.shift?.code??null;
    const duty=schedule.find(item=>item.code===code),next=schedule.find(item=>item.code===state.shift?.next_code);
    return {
      slotId:nurse.id,staffId:nurse.staff_id??null,role:nurse.role,unitId:unit.id,
      unitName:unit.name??unit.id,unitNameKo:unit.name_ko??null,unitNameEn:unit.name_en??unit.name??unit.id,
      hospitalId:unit.hospital_id??null,hospitalName:unit.hospital_name??null,
      clock:state.clock??null,simulationMinute:state.t??null,source:'simulation_snapshot',
      currentDuty:{code,startClock:duty?.start_clock??state.shift?.start_clock??null,endClock:duty?.end_clock??state.shift?.end_clock??null,date:null},
      previousPersonalDuty:null,nextPersonalDuty:null,
      nextTeamShift:next?{code:next.code,startClock:next.start_clock??null,endClock:next.end_clock??null}:null,
      tenure:{totalYears:null,unitYears:null},assigned,coverage,
      currentPatients:assigned.filter(row=>row.patient),
      note:'Personal dated duty, tenure and prior patient-assignment history are not supplied by this source.'
    };
  }
  return Object.freeze({derive});
});
