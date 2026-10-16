/* Connection state and explicit insertion sites are independent source facts. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUDeviceLayout=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const definitions=Object.freeze([
    ['oxygen','산소 공급','Oxygen'],['ventilator','인공호흡기','Ventilator'],
    ['iv','말초정맥관','Peripheral IV'],['central_line','중심정맥관','Central line'],
    ['arterial_line','동맥관','Arterial line'],['urinary_catheter','유치도뇨관','Urinary catheter'],
    ['drain','배액관','Drain'],['ecmo','ECMO','ECMO'],['crrt','CRRT','CRRT']
  ].map(([id,ko,en])=>Object.freeze({id,ko,en})));
  const keys=new Set(definitions.map(d=>d.id));
  const nonempty=v=>typeof v==='string'&&v.trim()!=='';
  const copy=v=>v==null?v:JSON.parse(JSON.stringify(v));
  function position(value){
    if(!value||value.view!=='anterior'||!['x','y'].every(k=>typeof value[k]==='number'&&Number.isFinite(value[k])&&value[k]>=0&&value[k]<=1))return null;
    return {x:value.x,y:value.y,view:'anterior'};
  }
  function derive(patient={},options={}){
    const p=patient||{},ko=options.language!=='en',t=(a,b)=>ko?a:b;
    const recordSites=(Array.isArray(p.device_sites)?p.device_sites:[]).filter(s=>s&&keys.has(s.device_key)&&s.source_kind==='record'&&nonempty(s.site_label)&&nonempty(s.source)).map((s,i)=>({
      id:nonempty(s.id)?s.id:'device-site-'+i,deviceKey:s.device_key,label:s.site_label,source:s.source,
      sourceKind:'record',position:position(s.position),recordedAt:copy(s.recorded_at??null)
    }));
    const exampleSites=options.examples!==false&&p.source==='synthetic'&&p.devices?.drain===true&&!recordSites.some(s=>s.deviceKey==='drain')?[{
      id:'illustrative-drain-placement',deviceKey:'drain',label:t('복부 연결 위치 예시','Illustrative abdominal connection'),
      source:t('TEAM 4 · 가상 배치 예시','TEAM 4 · fictional placement example'),sourceKind:'fictional_example',
      position:{x:.61,y:.59,view:'anterior'},recordedAt:null
    }]:[];
    const devices=definitions.map(d=>{
      const raw=p.devices?.[d.id],state=raw===true?'active':raw===false?'inactive':'unknown';
      const sites=recordSites.filter(s=>s.deviceKey===d.id);
      return {id:d.id,label:ko?d.ko:d.en,state,known:typeof raw==='boolean',rawValue:copy(raw??null),
        sourcePath:Object.prototype.hasOwnProperty.call(p.devices||{},d.id)?'devices.'+d.id:null,
        sites:copy(sites),locationKnown:sites.length>0,positionKnown:sites.some(s=>s.position!==null)};
    });
    const active=new Set(devices.filter(d=>d.state==='active').map(d=>d.id));
    const renderSites=[...recordSites,...exampleSites].filter(s=>s.position&&active.has(s.deviceKey));
    return {devices,recordSites,exampleSites,renderSites,drainLocationKnown:recordSites.some(s=>s.deviceKey==='drain'),
      exampleNotice:exampleSites.length?t('배액관 그림은 가상 연결 위치 예시입니다. 원본에 실제 삽입 위치·개수 기록은 없습니다.','The drain drawing is a fictional placement example. Actual insertion location and drain count are not recorded.'):null,
      sourceLocationsKnown:recordSites.length>0,sourceUnchanged:true};
  }
  return Object.freeze({derive,definitions,version:'device-layout-v1'});
});
