/* Source-labelled anatomy evidence and related records; no clinical inference. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUObservationModel=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const clone=value=>value==null?value:typeof structuredClone==='function'?structuredClone(value):JSON.parse(JSON.stringify(value));
  const freeze=value=>{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
  const own=(object,key)=>object!=null&&Object.prototype.hasOwnProperty.call(object,key);
  const numberKnown=value=>(typeof value==='number'&&Number.isFinite(value))||(typeof value==='string'&&value.trim()!==''&&Number.isFinite(Number(value)));
  const definitions=freeze([
    {id:'brain',number:1,labelKo:'뇌',labelEn:'Brain',anchor:[150,44],relatedMetricIds:['gcs','pain','temperature'],relatedHint:{labelKo:'의식·통증',labelEn:'Consciousness and pain'}},
    {id:'lungs',number:2,labelKo:'폐',labelEn:'Lungs',anchor:[176,135],relatedMetricIds:['spo2','rr','oxygen','ventilator'],relatedHint:{labelKo:'호흡',labelEn:'Respiration'}},
    {id:'heart',number:3,labelKo:'심장',labelEn:'Heart',anchor:[155,158],relatedMetricIds:['sbp','map','hr'],relatedHint:{labelKo:'혈압·맥박',labelEn:'Blood pressure and pulse'}},
    {id:'liver',number:4,labelKo:'간',labelEn:'Liver',anchor:[139,198],relatedMetricIds:[],relatedHint:{labelKo:'관련 검사',labelEn:'Related tests'}},
    {id:'kidneys',number:5,labelKo:'신장',labelEn:'Kidneys',anchor:[175,230],relatedMetricIds:['urinary_catheter','urine_volume','crrt'],relatedHint:{labelKo:'배설·신대체',labelEn:'Output and renal support'}},
    {id:'abdomen',number:6,labelKo:'복부·장',labelEn:'Abdomen / bowel',anchor:[150,249],relatedMetricIds:['pain','drain','drain_volume'],relatedHint:{labelKo:'통증·배액',labelEn:'Pain and drainage'}}
  ]);
  const validRegions=new Set(definitions.map(region=>region.id));
  const metricDefinitions=freeze([
    {id:'sbp',labelKo:'수축기 혈압',labelEn:'Systolic blood pressure',unit:'mmHg',path:['vitals','sbp']},
    {id:'map',labelKo:'평균 동맥압',labelEn:'Mean arterial pressure',unit:'mmHg',path:['vitals','map']},
    {id:'hr',labelKo:'심박수',labelEn:'Heart rate',unit:'bpm',path:['vitals','hr']},
    {id:'spo2',labelKo:'산소포화도',labelEn:'Oxygen saturation',unit:'%',path:['vitals','spo2']},
    {id:'rr',labelKo:'호흡수',labelEn:'Respiratory rate',unit:'/min',path:['vitals','rr']},
    {id:'gcs',labelKo:'의식 점수 · GCS',labelEn:'Consciousness score · GCS',unit:'/15',path:['extra_observations','gcs']},
    {id:'pain',labelKo:'통증 점수 · 부위 미지정',labelEn:'Pain score · location unspecified',unit:'',path:['extra_observations','pain'],noteKo:'통증 점수와 통증 부위의 기록은 별개입니다.',noteEn:'The pain score and the recorded pain location are separate.'},
    {id:'temperature',labelKo:'체온',labelEn:'Temperature',unit:'°C',path:['extra_observations','temperature']},
    {id:'urine_volume',labelKo:'소변량',labelEn:'Urine volume',unit:'mL',path:null,noteKo:'정량 소변 기록이 제공되지 않았습니다.',noteEn:'A quantitative urine record was not supplied.'},
    {id:'drain_volume',labelKo:'배액량 · 부위 미지정',labelEn:'Drain volume · location unspecified',unit:'mL',path:null,noteKo:'정량 배액 기록이 제공되지 않았습니다.',noteEn:'A quantitative drain-output record was not supplied.'},
    {id:'urinary_catheter',labelKo:'유치도뇨관 연결 상태',labelEn:'Urinary catheter connection',device:true},
    {id:'drain',labelKo:'배액관 연결 상태 · 부위 미지정',labelEn:'Drain connection · location unspecified',device:true,noteKo:'배액관 유무는 배액 부위나 배액량을 뜻하지 않습니다.',noteEn:'Drain presence does not specify its location or output volume.'},
    {id:'oxygen',labelKo:'산소 공급 상태',labelEn:'Oxygen support state',device:true},
    {id:'ventilator',labelKo:'인공호흡기 연결 상태',labelEn:'Ventilator connection',device:true},
    {id:'iv',labelKo:'정맥주입 연결 상태',labelEn:'IV cannula connection',device:true},
    {id:'central_line',labelKo:'중심정맥관 연결 상태',labelEn:'Central-line connection',device:true},
    {id:'arterial_line',labelKo:'동맥관 연결 상태',labelEn:'Arterial-line connection',device:true},
    {id:'ecmo',labelKo:'ECMO 연결 상태',labelEn:'ECMO connection',device:true},
    {id:'crrt',labelKo:'CRRT 연결 상태',labelEn:'CRRT connection',device:true}
  ]);
  const groupDefinitions=freeze([
    {id:'circulation',labelKo:'혈압·심박 기록',labelEn:'Blood pressure and pulse records',metricIds:['sbp','map','hr']},
    {id:'respiration',labelKo:'호흡 기록',labelEn:'Respiratory records',metricIds:['spo2','rr']},
    {id:'awareness',labelKo:'의식·통증·체온 기록',labelEn:'Consciousness, pain and temperature records',metricIds:['gcs','pain','temperature']},
    {id:'outputs',labelKo:'배설·배액 기록',labelEn:'Output and drainage records',metricIds:['urinary_catheter','urine_volume','drain','drain_volume']},
    {id:'devices',labelKo:'장비 연결 기록',labelEn:'Device connection records',metricIds:['oxygen','ventilator','iv','central_line','arterial_line','urinary_catheter','drain','ecmo','crrt']}
  ]);
  function derive(patient={},options={}){
    const p=patient||{},language=options.language==='en'?'en':'ko',ko=language==='ko',text=(a,b)=>ko?a:b;
    const records=(Array.isArray(p.anatomy_findings)?p.anatomy_findings:[]).map((finding,index)=>({finding,index})).filter(({finding:f})=>
      f&&validRegions.has(f.region)&&['diagnosis','pain'].includes(f.kind)&&f.source&&f.label).map(({finding,index})=>
      ({...clone(finding),id:finding.id??'anatomy-'+index,sourceKind:'record',simulation:false,
        kindLabel:text(finding.kind==='pain'?'통증 부위 기록':'진단 관련 부위 기록',finding.kind==='pain'?'Pain-location record':'Diagnosis-related location record')}));
    const simulation=p.source==='synthetic'&&p.simulation_override?.scenario==='bleeding';
    const examples=simulation?[{id:'simulation-bleeding-abdomen',region:'abdomen',kind:'simulation',source:'Fictional scenario',
      sourceKind:'simulation',simulation:true,kindLabel:text('시뮬레이션 예시','Simulation example'),
      label:text('복부 출혈 의심을 설명하기 위한 예시 위치','Illustrative abdominal site for the bleeding scenario')}]:[];
    const scenarioFindings=(Array.isArray(p.simulation_override?.findings)?p.simulation_override.findings:[])
      .map((label,index)=>({label,index})).filter(row=>typeof row.label==='string'&&row.label.trim()!=='')
      .map(row=>({id:'scenario-finding-'+row.index,label:row.label,source:p.simulation_override.source,kind:'simulation'}));
    const evidence=[...records,...examples],activeRegions=[...new Set(evidence.map(row=>row.region))];
    const defaultRegion=records[0]?.region||examples[0]?.region||'all';
    const selectedRegion=options.selectedRegion==='all'||validRegions.has(options.selectedRegion)?options.selectedRegion:defaultRegion;
    const metrics={};
    for(const definition of metricDefinitions){
      const path=definition.device?['devices',definition.id]:definition.path;
      const object=path?p[path[0]]:null,present=Boolean(path&&own(object,path[1])),raw=present?object[path[1]]:null;
      const known=definition.device?typeof raw==='boolean':numberKnown(raw),value=known?clone(raw):null;
      const overridden=Boolean(path?.[0]==='vitals'&&own(p.simulation_override?.values,definition.id));
      const sourceKind=overridden?'simulation':known?(p.source==='synthetic'?'fictional_record':'record'):'unknown';
      const observedPresent=Boolean(path?.[0]==='vitals'&&own(p.observed_vitals,definition.id));
      const observedRaw=observedPresent?p.observed_vitals[definition.id]:null,observedKnown=numberKnown(observedRaw);
      const state=definition.device?(value===true?'active':value===false?'inactive':'unknown'):known?'recorded':'unknown';
      metrics[definition.id]={id:definition.id,type:definition.device?'device':'number',label:text(definition.labelKo,definition.labelEn),
        labelKo:definition.labelKo,labelEn:definition.labelEn,unit:definition.unit||'',value,rawValue:clone(raw),known,present,state,
        displayValue:known?(definition.device?text(value?'사용 중':'없음',value?'Active':'Not active'):String(value)):text('미확인','Unknown'),
        sourcePath:present?path.join('.'):null,sourceKind,source:overridden?(p.simulation_override.source||'simulation_injected'):(p.source||null),
        sourceLabel:text(sourceKind==='simulation'?'모의 상황 값':sourceKind==='fictional_record'?'가상 기록':sourceKind==='record'?'기록':'기록 미확인',sourceKind==='simulation'?'Injected simulation':sourceKind==='fictional_record'?'Fictional record':sourceKind==='record'?'Recorded value':'Record unknown'),
        overridden,observedValue:observedKnown?clone(observedRaw):null,observedKnown,
        observedSourcePath:observedPresent?'observed_vitals.'+definition.id:null,
        note:definition.noteKo?text(definition.noteKo,definition.noteEn):null,
        locationLinked:false};
    }
    const regions=definitions.map(definition=>{
      const rows=evidence.filter(row=>row.region===definition.id),recordRows=records.filter(row=>row.region===definition.id);
      return {...clone(definition),label:text(definition.labelKo,definition.labelEn),hasEvidence:rows.length>0,
        hasRecordEvidence:recordRows.length>0,hasSimulationExample:rows.some(row=>row.simulation),evidence:clone(rows),
        hint:text(definition.relatedHint.labelKo,definition.relatedHint.labelEn)};
    });
    const relatedMetricIds=selectedRegion==='all'?['gcs','pain','temperature']:[...definitions.find(region=>region.id===selectedRegion).relatedMetricIds];
    return {language,regions,evidence:clone(evidence),recordEvidence:clone(records),examples:clone(examples),
      simulationEvidence:clone(examples),scenarioFindings,activeRegions,defaultRegion,selectedRegion,simulation,
      locationKnown:records.length>0,hasLocationEvidence:evidence.length>0,
      groups:groupDefinitions.map(group=>({...clone(group),label:text(group.labelKo,group.labelEn),metrics:group.metricIds.map(id=>clone(metrics[id]))})),
      metrics,relatedMetricIds,relatedMetrics:relatedMetricIds.map(id=>clone(metrics[id])),
      relatedLabel:text('관련 관찰 기록','Related observation records'),
      relatedNote:text('부위 선택에 따라 기존 기록을 모아 보여줍니다. 수치나 장비에서 부위·진단을 추정하지 않습니다.','Region selection groups existing records for navigation. Values and devices do not establish anatomy or a diagnosis.'),
      locationNote:text('위치 근거가 없다는 표시는 정상 소견을 뜻하지 않습니다.','Missing location evidence does not indicate a normal finding.'),
      simulationNote:simulation?text('복부 표시는 출혈 시나리오의 예시 위치이며 실제 통증·출혈 부위를 확인한 기록이 아닙니다.','The abdominal marker illustrates the bleeding scenario; it does not verify a pain or bleeding location.'):null};
  }
  return Object.freeze({derive,regions:definitions,groups:groupDefinitions,version:'source-observations-v1'});
});
