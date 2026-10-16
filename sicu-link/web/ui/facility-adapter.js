/* Explicit fictional capacity setting; canonical source and clinical rules stay intact. */
(() => {
  'use strict';
  const q = selector => document.querySelector(selector);
  const ko = () => I18n.language === 'ko';
  const t = (a,b) => ko() ? a : b;
  const unitName = unit => unit?.name_ko ? (ko()?unit.name_ko:unit.name_en) : I18n.t(unit?.name || '');
  const typeName = id => {const profile=FacilityProfiles.forHospital(id);return profile?(ko()?profile.typeKo:profile.typeEn):'';};
  const layoutName = id => {const profile=FacilityProfiles.forHospital(id);return profile?(ko()?profile.layoutKo:profile.layoutEn):'';};
  function geometry(state) {
    const units=state.floors.flatMap(f=>f.units);
    // A ward selection changes the viewport, never the hospital's elevator.
    const hospital=units[0]?.hospital_id || 'A';
    const elevator={A:35,B:31,C:51}[hospital] ?? Number(state.elevator_x);
    return {...state,elevator_x:elevator,floor_h:Math.max(...units.map(u=>Number(u.h))),floor_w:Math.max(...units.map(u=>Number(u.x)+Number(u.w)),elevator+3)};
  }
  const nativeProject=Transfers.project;
  Transfers.project=function(data){return nativeProject.call(this,FacilityProfiles.project(data));};
  const nativeSelect=Network.select;
  Network.select=function(data){return geometry(nativeSelect.call(this,FacilityProfiles.project(data)));};

  function decorate() {
    if(typeof S==='undefined' || !S?.facility_projection) return;
    const units=S.floors.flatMap(f=>f.units);
    const patientScope=q('.patient-board .section-heading>.tag');
    if(patientScope){patientScope.dataset.noTranslate='';const count=units.reduce((sum,u)=>sum+u.beds.length,0);patientScope.textContent=t('선택 범위 '+count+'병상',count+' beds in this view');}
    const scenarioNote=q('.scenario-description small');
    if(scenarioNote){scenarioNote.dataset.noTranslate='';scenarioNote.textContent=t('가상 사례 · 병원별 구성에 맞춰 표시 · 직원 위치와 이동은 모의 배치입니다.','Fictional cases adapted to each facility configuration. Staff positions and movement are simulated.');}
    const description=q('#profileDescription'),profile=S.profiles?.[S.hospital_profiles?.[Network.hospital] || S.demo_profile];
    if(description && profile?.description){description.dataset.noTranslate='';description.textContent=t('원본 8병상 기준 시나리오 · ','Original eight-bed reference scenario · ')+I18n.t(profile.description);}
    for(const selector of ['#wardScope','#rosterUnit']) for(const option of q(selector)?.options || []){
      const unit=units.find(u=>u.id===option.value);
      if(unit?.name_ko){option.dataset.noTranslate='';const text=unit.id+' · '+unitName(unit);if(option.textContent!==text)option.textContent=text;}
    }
    document.querySelectorAll('#networkCards .hospital-card').forEach(card=>{
      const id=card.querySelector('[data-hospital]')?.dataset.hospital,profile=FacilityProfiles.forHospital(id);
      const heading=card.querySelector('h3');if(!profile || !heading)return;
      let label=heading.querySelector('.network-facility-type');
      if(!label){label=document.createElement('small');label.className='network-facility-type';label.dataset.noTranslate='';heading.append(label);}
      const text=typeName(id)+' · '+profile.unitCount+' ICU';if(label.textContent!==text)label.textContent=text;
    });
    document.querySelectorAll('#patientCards .unit-patients').forEach(section=>{
      const id=section.querySelector('[data-patient]')?.dataset.patient?.replace(/-\d+$/,'');
      const unit=units.find(u=>u.id===id),heading=section.querySelector('h3');
      if(unit?.name_ko && heading){
        heading.dataset.noTranslate='';const text=unit.id+' · '+unitName(unit)+' ';
        if(heading.firstChild?.nodeType===Node.TEXT_NODE && heading.firstChild.textContent!==text)heading.firstChild.textContent=text;
        const button=heading.querySelector('[data-ward]');if(button)button.textContent=t('병동 보기','View ward');
      }
    });
    const planning=q('#planningView');
    if(planning){
      let note=q('#facilityPlanNote');if(!note){note=document.createElement('p');note.id='facilityPlanNote';note.dataset.noTranslate='';planning.prepend(note);}
      const text=t('아래 두 계획표는 제공된 원본 8병상 참고 자료입니다. 병원별 구성과 구분해 확인하세요.','Both planning resources below retain the supplied eight-bed reference. They are separate from each hospital configuration.');
      if(note.textContent!==text)note.textContent=text;
    }
    const table=q('#metrics');
    if(table){
      let note=q('#facilityMetricsNote');if(!note){note=document.createElement('p');note.id='facilityMetricsNote';note.className='tag';note.dataset.noTranslate='';table.before(note);}
      const text=ko()?S.facility_projection.metrics_note_ko:S.facility_projection.metrics_note_en;if(note.textContent!==text)note.textContent=text;
    }
  }
  const nativeRender=Network.render;
  Network.render=function(){const result=nativeRender.apply(this,arguments);decorate();return result;};
  document.addEventListener('icu-language',()=>queueMicrotask(decorate));
  window.FacilityRuntime=Object.freeze({unitName,typeName,layoutName,geometry,decorate});
})();
