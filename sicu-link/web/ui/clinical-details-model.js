/* Read-only detail formatting. Authored demo supplements never alter source records. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.SICUClinicalDetails=api;
})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const copy=v=>v==null?v:JSON.parse(JSON.stringify(v));
  const text=v=>typeof v==='string'&&v.trim()?v.trim():null;
  const number=(v,min,max)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max?v:null;
  const localized=(value,language)=>text(value)||text(value?.[language])||text(value?.en)||text(value?.ko);
  const supplied=value=>value&&value.source_kind==='record'&&text(value.source)?value:null;
  const display=(v,language)=>localized(v,language);
  function components(value){
    if(!value||typeof value!=='object')return null;
    const component=(v,max,intubated=false)=>v==='NT'||intubated&&v==='T'?v:Number.isInteger(v)&&v>=1&&v<=max?v:null;
    const result={eye:component(value.eye,4),verbal:component(value.verbal,5,true),motor:component(value.motor,6)};
    return Object.values(result).some(v=>v!==null)?result:null;
  }
  function derive(patient={},options={}){
    const p=patient||{},language=options.language==='en'?'en':'ko',t=(a,b)=>language==='ko'?a:b;
    const candidate=options.demoRecord;
    // Match the patient and admission, never the current bed or a guessed diagnosis.
    const example=p.source==='synthetic'&&candidate?.pid===p.pid&&candidate?.admit_t===p.admit_t?candidate:null;
    const summary=supplied(p.clinical_summary),unknown=t('미기록','Not recorded');
    const primary=(key,fallback)=>{
      const actual=display(summary?.[key],language)||display(p[key],language)||fallback;
      if(actual)return {value:actual,kind:'record',source:summary?.source||key};
      const value=display(example?.[key],language);
      return {value:value||unknown,kind:value?'fictional_example':'unknown',source:value?'TEAM 4 · v25 demo supplement':null};
    };
    const genericDx=['Fictional postoperative monitoring case','Fictional postoperative admission'];
    const originalDx=text(p.dx);
    const diagnosis=primary('primary_diagnosis',originalDx&&!genericDx.includes(originalDx)?originalDx:null);
    if(diagnosis.kind==='unknown'&&originalDx)diagnosis.value=t('수술 후 ICU 관찰 · 세부 진단 미기록','Postoperative ICU observation · diagnosis not specified');
    const procedure=primary('primary_procedure',null);
    const details={};
    for(const id of ['oxygen','ventilator','iv','central_line','arterial_line','urinary_catheter','drain','ecmo','crrt']){
      const raw=p.devices?.[id],state=raw===true?'active':raw===false?'inactive':'unknown';
      const record=supplied(p.device_details?.[id]);
      const sites=(Array.isArray(p.device_sites)?p.device_sites:[]).filter(s=>s?.device_key===id&&s.source_kind==='record'&&text(s.source)&&text(s.site_label));
      // A supplied partial record remains partial; do not mix in invented missing fields.
      const value=record||(!sites.length?example?.device_details?.[id]:null)||{};
      const kind=record||sites.length?'record':example?.device_details?.[id]?'fictional_example':'unknown';
      const rows=[];
      const add=(label,content)=>rows.push({label,value:content||unknown,known:!!content});
      if(state!=='inactive'){
        if(id==='oxygen'){
          add(t('공급 종류','Delivery'),display(value.type,language));
          const flow=number(value.flow_l_min,0,200),fio2=number(value.fio2_percent,21,100);
          add(t('유량 · FiO₂','Flow · FiO₂'),[flow===null?null:flow+' L/min',fio2===null?null:'FiO₂ '+fio2+'%'].filter(Boolean).join(' · '));
        }else if(id==='ventilator'){
          add(t('모드','Mode'),text(value.mode));
          const fio2=number(value.fio2_percent,21,100);add('FiO₂',fio2===null?null:fio2+'%');
        }else if(id==='iv'){
          const count=number(value.count,0,20);add(t('개수','Count'),Number.isInteger(count)?count+t('개',' lines'):null);
        }else if(id==='drain'){
          add(t('종류','Type'),display(value.type,language));
          add(t('위치','Site'),sites.length?sites.map(s=>s.site_label).join(' · '):display(value.site,language));
        }else if(['central_line','arterial_line','ecmo','crrt'].includes(id)){
          add(t(id==='ecmo'||id==='crrt'?'카테터 위치':'삽입 위치','Catheter site'),sites.length?sites.map(s=>s.site_label).join(' · '):display(value.site,language));
        }
      }
      // An unknown connection cannot acquire an apparently current example setting.
      const usable=state==='active';
      details[id]={state,kind:usable?kind:'unknown',source:record?.source||sites[0]?.source||(usable&&kind==='fictional_example'?'TEAM 4 · v25 demo supplement':null),
        rows:rows.map(row=>usable?row:{...row,value:unknown,known:false})};
    }
    const originalComponents=p.extra_observations?.gcs_components;
    const actual=components(originalComponents);
    const matches=example&&example.gcs_baseline_total===p.extra_observations?.gcs&&example.gcs_baseline_ventilator===p.devices?.ventilator;
    const sample=matches?components(example.gcs_components):null,c=actual||sample;
    const gcs={components:copy(c),value:c?[c.eye,c.verbal,c.motor].map(v=>v??'—').join('/'):'—/—/—',
      kind:actual?'record':sample?'fictional_example':'unknown',known:!!c,
      note:c?t('E / V / M · 눈 / 언어 / 운동','E / V / M · Eye / Verbal / Motor'):t('항목별 기록 미제공 · 총점에서 환산하지 않음','Components not supplied · not inferred from the total'),
      hasUntestable:!!c&&Object.values(c).some(v=>v==='T'||v==='NT'),originalTotal:copy(p.extra_observations?.gcs??null)};
    return {diagnosis,procedure,details,gcs,hasExamples:diagnosis.kind==='fictional_example'||procedure.kind==='fictional_example'||gcs.kind==='fictional_example'||Object.values(details).some(d=>d.kind==='fictional_example')};
  }
  return Object.freeze({derive,components,version:'v25'});
});
