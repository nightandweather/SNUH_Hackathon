/* Pure storyboard geometry and immutable browser-local fictional checkpoints. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUTransportModel=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const clone=x=>structuredClone(x),clamp=(n,a=0,b=1)=>Math.min(b,Math.max(a,Number(n)||0));
  const ease=value=>{const u=clamp(value);return u*u*(3-2*u);};
  const cuts=[0,.14,.24,.48,.50,.84,.94,1];
  const names={arrival:['입실','Admission'],departure:['병동 이송','Ward transfer'],icu_death:['사후 이송','Post-mortem transport']};
  const steps={
    arrival:[['환자와 함께 도착','Arriving with patient'],['ICU 문 열림','ICU doors opening'],['병상으로 이동','Moving to bed'],['환자를 침대로 인계','Patient handoff to bed'],['빈 카트 복귀','Empty cart returning'],['퇴장 · 문 닫힘','Exiting · doors closing'],['입실 완료','Admission complete']],
    departure:[['빈 카트 도착','Empty cart arriving'],['ICU 문 열림','ICU doors opening'],['병상으로 이동','Moving to bed'],['환자를 카트로 인계','Patient handoff to cart'],['환자와 함께 퇴장','Leaving with patient'],['퇴장 · 문 닫힘','Exiting · doors closing'],['병상 정리 완료','Bed turnover complete']],
    icu_death:[['빈 카트 도착','Empty cart arriving'],['ICU 문 열림','ICU doors opening'],['병상으로 이동','Moving to bed'],['사후 이송 인계','Post-mortem handoff'],['환자와 함께 퇴장','Leaving with patient'],['퇴장 · 문 닫힘','Exiting · doors closing'],['병상 정리 완료','Bed turnover complete']]
  };
  function sample(kind,progress){
    const p=clamp(progress),incoming=kind==='arrival';
    const phase=p===1?6:Math.min(6,cuts.findIndex((v,i)=>i<7&&p>=v&&p<cuts[i+1]));
    const local=clamp((p-cuts[phase])/(cuts[phase+1]-cuts[phase]));
    // A quick 280ms bedside handoff in the 14-second presentation clock.
    const handoff=clamp((p-cuts[3])/(cuts[4]-cuts[3])),handoffActive=p>=cuts[3]&&p<cuts[4],moved=p>=cuts[4];
    // Hold outside until the doors are fully open; route length varies by facility.
    const route=p<.24?0:p<.48?ease((p-.24)/.24):p<cuts[4]?1:p<.86?1-ease((p-cuts[4])/(.86-cuts[4])):0;
    const door=p<.14?0:p<.24?clamp((p-.14)/.10):p<.88?1:p<.94?1-clamp((p-.88)/.06):0;
    return {kind,progress:p,phase,local,handoff,handoffActive,moved,route,door,cartVisible:p<.90,cartOccupied:incoming?!moved:moved,bedOccupied:incoming?moved:!moved,turnover:!incoming&&moved&&p<1,complete:p===1,stage:p<.14?0:p<.24?1:p<.48?2:p<cuts[4]?3:4};
  }
  function spaces(unit,elevator){
    const e=Number.isFinite(Number(elevator))?Number(elevator):35,x=Number(unit.x),w=Number(unit.w);
    const corridorY=unit.facility_layout==='single'?6.6:7,right=Math.abs(e-(x+w))<=Math.abs(e-x);
    return {procedure:{x:e-2.3,y:.35,w:4.6,h:3.4,door:[e,3.75]},staging:[e,4.8],
      corridorY,gate:[right?x+w:x,corridorY],right};
  }
  function rounded(points,radius=.22){
    const clean=points.filter((p,i)=>!i||Math.hypot(p[0]-points[i-1][0],p[1]-points[i-1][1])>.001);
    if(clean.length<3)return clean.map(p=>[...p]);
    const output=[[...clean[0]]];
    for(let i=1;i<clean.length-1;i++){
      const a=clean[i-1],b=clean[i],c=clean[i+1],ab=Math.hypot(b[0]-a[0],b[1]-a[1]),bc=Math.hypot(c[0]-b[0],c[1]-b[1]);
      const cross=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]);
      if(Math.abs(cross)<.0001){output.push([...b]);continue;}
      const r=Math.min(radius,ab*.35,bc*.35),before=[b[0]-(b[0]-a[0])*r/ab,b[1]-(b[1]-a[1])*r/ab],after=[b[0]+(c[0]-b[0])*r/bc,b[1]+(c[1]-b[1])*r/bc];
      output.push(before);
      for(let step=1;step<=8;step++){const u=step/8,v=1-u;output.push([v*v*before[0]+2*v*u*b[0]+u*u*after[0],v*v*before[1]+2*v*u*b[1]+u*u*after[1]]);}
    }
    output.push([...clean.at(-1)]);return output;
  }
  function route(unit,bed,elevator){
    const layout=spaces(unit,elevator),upper=Number(bed.y)<Number(unit.h)/2,wallY=upper?5:9;
    const laneY=upper?(unit.facility_layout==='single'?5.65:5.6):8.45;
    const inside=layout.gate[0]+(layout.right?-1.2:1.2),roomX=Number(bed.x)+3.03;
    const near=[roomX,Number(bed.y)+(upper?2.1:-2.1)],roomDoor=[roomX,wallY];
    const waypoints=[layout.staging,[layout.staging[0],layout.corridorY],layout.gate,
      [inside,layout.corridorY],[inside,laneY],[roomX,laneY],roomDoor,near];
    return {door:layout.gate,outside:layout.staging,origin:'procedure-room',procedure:layout.procedure,
      procedureDoor:layout.procedure.door,staging:layout.staging,spaces:layout,waypoints,points:rounded(waypoints),
      bed:[Number(bed.x)+2.25,upper?2.3:Number(bed.y)],right:layout.right,
      room:{door:roomDoor,wallY,laneY,upper,near},cartScale:.6};
  }
  function point(points,progress){
    const distances=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
    const totalLength=distances.reduce((a,b)=>a+b,0),distance=clamp(progress)*totalLength;let left=distance;
    for(let i=0;i<distances.length;i++){if(left<=distances[i]||i===distances.length-1){const r=distances[i]?clamp(left/distances[i]):0,a=points[i],b=points[i+1];return {x:a[0]+(b[0]-a[0])*r,y:a[1]+(b[1]-a[1])*r,angle:Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI,distance,totalLength};}left-=distances[i];}
  }
  function example(template,kind,bed,t){
    const admission=kind==='arrival',dead=kind==='icu_death';
    const criteria=['window_complete','no_escalation','targets_met','trends_stable','postop_plan','ward_capacity','consultant','receiving_team','handover','followup'];
    return {...clone(template||{}),pid:'SIM-PORTER-'+kind.toUpperCase()+'-'+bed,source:'synthetic',dx:'Fictional transport example',admit_t:t,arrest:false,abn:[],risk:admission?30:10,vent:admission?1:0,pressor:0,simulation_override:null,devices:{iv:true,ecmo:false,crrt:false,ventilator:admission,invasive_ventilation:admission},medications:{vasoactive_support:false},extra_observations:{},care_indicators:{calendar_day:0,cpr_today:false,surgery_today:admission,pressor_unstable:false},vitals:dead?{hr:null,sbp:null,map:null,spo2:null,rr:null}:{hr:82,sbp:118,map:82,spo2:98,rr:18},transfer_review:admission||dead?{}:{...Object.fromEntries(criteria.map(k=>[k,true])),current:{cpr:false,ecmo:false,crrt:false,vent:false,pressor:false,rescue:false,postop:false}}};
  }
  function project(data,scene,progress,language='ko'){
    const out=clone(data),state=sample(scene.kind,progress),bed=out.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).find(b=>b.id===scene.bed);
    if(!bed)return out;
    const ko=language==='ko',w=a=>a[ko?0:1],incoming=scene.kind==='arrival',departed=!incoming&&!state.bedOccupied;
    bed.patient=state.bedOccupied?clone(scene.patient):null;bed.reservation=null;bed.unavailable=state.turnover;
    let status;
    if(state.bedOccupied){const red=incoming||scene.kind==='icu_death';status={key:red?'critical':'stable',label:red?'RED':'GREEN',color:red?'#af3540':'#246b4b',ink:'#fff'};}
    else if(state.turnover)status={key:'turnover',label:w(['정리 중','TURNOVER']),color:'#dce6f1',ink:'#294964'};
    else status={key:'empty',label:w(['빈 병상','EMPTY']),color:'#ffffff',ink:'#637b91'};
    if(!incoming&&state.complete&&scene.nextReservation){bed.reservation={source:'simulation_schedule',label:w(['다음 입실 예약','Next admission reserved'])};status={key:'reserved',label:w(['다음 입실 예약','NEXT RESERVED']),color:'#fff1b8',ink:'#67521c'};}
    bed.flow={scene:'porter-story',kind:scene.kind,bed:bed.id,unit:scene.unit,stage:state.stage,scenePhase:state.phase,sceneProgress:state.progress,title:w(names[scene.kind]),label:w(steps[scene.kind][state.phase]),route:w(incoming?['입구 → 병상 → 빈 카트 퇴장','Entrance → bed → empty cart exits']:['빈 카트 입장 → 병상 → 환자 이송','Empty cart enters → bed → patient exits']),suppressVitals:scene.kind==='icu_death'||!state.bedOccupied,status,ink:status.ink};
    // These are independent fictional examples; retain the canonical source frame.
    out.incidents=(out.incidents||[]).filter(i=>i.bed!==bed.id);
    const incidentIds=new Set(out.incidents.map(i=>i.id));
    const nurseIds=new Set((out.nurses||[]).map(n=>n.id));
    for(const person of [...(out.nurses||[]),...(out.doctors||[])]){
      if(person.incident&&!incidentIds.has(person.incident)){person.incident=null;if(['moving','called','responding','incident'].includes(person.status))person.status=nurseIds.has(person.id)?'care':'available';}
      if(departed){if(person.beds)person.beds=person.beds.filter(id=>id!==bed.id);if(person.cover)person.cover=person.cover.filter(id=>id!==bed.id);}
    }
    return out;
  }
  return Object.freeze({sample,spaces,route,point,ease,example,project,names,steps,cuts});
});
