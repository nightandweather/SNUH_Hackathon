/* Anatomy is a route into recorded observations, never a diagnosis from a drawing. */
(() => {
  'use strict';
  const q=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let patient=null,identity='',selected='all',language='ko',current=null,connections=null;
  const t=(a,b)=>language==='ko'?a:b;
  const label=(item)=>language==='ko'?(item.labelKo||item.label):(item.labelEn||item.label);
  const kindName=kind=>({diagnosis:t('진단 관련 기록','Diagnosis-related record'),pain:t('통증 기록','Reported pain'),simulation:t('시나리오 예시','Scenario example')})[kind]||kind;
  const hints={brain:['의식·공통 기록','Consciousness'],lungs:['호흡','Respiration'],heart:['혈압·맥박','Circulation'],liver:['관련 검사','Related tests'],kidneys:['배설·신대체','Urine / renal support'],abdomen:['통증·배액','Pain / drainage']};
  const clinical=()=>SICUClinicalDetails.derive(patient,{language,demoRecord:SICUClinicalDemo.find(patient)});
  function metricHTML(metric){
    if(metric.id==='gcs'){
      const gcs=clinical().gcs;
      return '<div class="observation-record observation-gcs" data-observation-metric="gcs" data-observation-known="'+gcs.known+'" data-detail-kind="'+gcs.kind+'"><dt>GCS <span>E / V / M</span></dt><dd><strong>'+E(gcs.value)+'</strong></dd><small>'+E(gcs.note)+'</small>'+(gcs.kind==='fictional_example'?'<small class="clinical-example-label">'+t('항목별 시연 예시 · 원본 총점과 별도','Component demo example · separate from the source total')+'</small>':'')+(gcs.hasUntestable?'<small>'+t('T: 기관삽관 · 언어반응 평가 불가','T: intubated · verbal response not testable')+'</small>':'')+'</div>';
    }
    const known=metric.known===true,value=metric.type==='device'?(metric.state==='active'?t('사용 중','Active'):metric.state==='inactive'?t('없음','Not active'):t('미확인','Unknown')):known?metric.value:'—';
    return '<div class="observation-record" data-observation-metric="'+E(metric.id)+'" data-observation-known="'+known+'" data-observation-value="'+E(metric.value==null?'unknown':metric.value)+'" data-observation-source="'+E(metric.sourcePath||'')+'"><dt>'+E(label(metric))+'</dt><dd><strong>'+E(value)+'</strong>'+(metric.type==='device'?'':known&&metric.unit?'<span>'+E(metric.unit)+'</span>':!known?'<span>'+t('기록 없음','Not recorded')+'</span>':'')+'</dd>'+(metric.overridden?'<small class="observation-value-source">'+t('시나리오 설정값','Scenario value')+'</small>':'')+'</div>';
  }
  function renderConnections(){
    const list=q('.observation-connections .patient-device-list');if(!list||!connections)return;
    const clinicalDetails=clinical();
    list.innerHTML=connections.devices.map(device=>{
      const status=device.state==='active'?t('사용 중','Active'):device.state==='inactive'?t('없음','Not active'):t('미확인','Unknown');
      const detail=clinicalDetails.details[device.id];
      const rows=detail.rows.map(row=>'<span class="device-detail-row"><span>'+E(row.label)+'</span><b data-detail-known="'+row.known+'">'+E(row.value)+'</b></span>').join('');
      return '<div data-device="'+E(device.id)+'" data-device-key="'+E(device.id)+'" data-device-state="'+device.state+'" data-source-path="'+E(device.sourcePath||'')+'" data-location-known="'+device.locationKnown+'"><dt><span class="device-connection-icon">'+SICUDeviceVisuals.icon(device.id)+'</span><span>'+E(device.label)+'</span></dt><dd class="device-connection-state" data-device-state="'+device.state+'">'+status+'</dd>'+(rows?'<dd class="device-clinical-detail" data-detail-kind="'+detail.kind+'">'+rows+(detail.kind==='fictional_example'?'<small class="clinical-example-label">'+t('시연 예시','Demo example')+'</small>':'')+'</dd>':'')+'</div>';
    }).join('');
    const drain=connections.devices.find(d=>d.id==='drain'),notice=q('#deviceLocationNotice');
    if(connections.exampleSites.length){
      notice.dataset.locationKind='fictional_example';
      notice.innerHTML='<strong>'+t('가상 연결 위치 예시','Fictional placement example')+'</strong><span>'+E(connections.exampleNotice)+'</span>';
    }else if(drain.sites.length){
      notice.dataset.locationKind='record';
      notice.innerHTML='<strong>'+t('배액관 위치 기록','Recorded drain site')+'</strong><span>'+drain.sites.map(s=>E(s.label)+' · '+E(s.source)).join('<br>')+'</span>';
    }else{
      notice.dataset.locationKind='unknown';
      notice.innerHTML='<strong>'+t('연결 상태와 삽입 위치는 별도 기록입니다.','Connection state and insertion site are separate records.')+'</strong><span>'+t('삽입 위치 기록이 없는 장비는 인체 위에 실제 위치로 표시하지 않습니다.','Equipment without an insertion-site record has no recorded placement on the body.')+'</span>';
    }
    q('#deviceConnectionSummary').innerHTML=t('연결 장비','Connected equipment')+'<span class="device-connection-count">9</span><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg>';
  }
  function renderSelection(focus=false){
    if(!patient||!q('.observation-panel'))return;
    current=SICUObservationModel.derive(patient,{language,selectedRegion:selected});selected=current.selectedRegion;
    const region=current.regions.find(r=>r.id===selected),evidence=selected==='all'?current.evidence:current.evidence.filter(e=>e.region===selected);
    all('[data-observation-select]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.observationSelect===selected)));
    connections=SICUDeviceLayout.derive(patient,{language});
    q('.observation-diagram').innerHTML=SICUObservationVisuals.body({regions:current.regions,selected},{language}).replace('</svg>',SICUDeviceVisuals.overlay(connections,{language})+'</svg>');
    const diagram=q('.observation-body-svg');diagram.removeAttribute('aria-hidden');diagram.setAttribute('role','group');diagram.setAttribute('aria-label',t('인체 그림에서 관찰 부위 선택','Choose an observation site on the body'));
    all('.observation-diagram [data-observation-region]').forEach(hit=>{
      const id=hit.dataset.observationRegion,r=current.regions.find(r=>r.id===id);
      hit.dataset.observationSelect=id;hit.setAttribute('role','button');hit.setAttribute('tabindex','0');
      hit.setAttribute('aria-label',r.number+' · '+label(r)+' · '+hints[id][language==='ko'?0:1]);hit.setAttribute('aria-pressed',String(id===selected));
    });
    renderConnections();
    q('#observationFocusName').textContent=region?label(region):t('전신 · 공통 기록','Whole body · common records');
    q('#observationFocusState').textContent=evidence.length?(evidence.some(e=>e.kind!=='simulation')?t('부위 기록 연결','Location records linked'):t('시나리오 예시','Scenario example')):t('부위 기록 미연결','Location not recorded');
    q('#observationFocusState').dataset.observationEvidence=evidence.some(e=>e.kind!=='simulation')?'record':evidence.length?'simulation':'unknown';
    q('#observationEvidence').innerHTML=evidence.map(e=>'<div class="observation-evidence" data-evidence-kind="'+E(e.kind)+'" data-evidence-region="'+E(e.region)+'"><span>'+E(kindName(e.kind))+'</span><p>'+E(e.label)+'</p><small>'+E(e.source)+'</small></div>').join('');
    q('#observationRecordTitle').textContent=t('관련 관찰 기록','Related observation records');
    q('#observationRecordContext').textContent=t('선택 시점','Selected time');
    const ids=current.relatedMetricIds||[];
    q('#observationRecords').innerHTML=ids.length?'<dl>'+ids.map(id=>current.metrics[id]?metricHTML(current.metrics[id]):'').join('')+'</dl>':'<p class="observation-no-record">'+t('이 부위에 연결된 관찰·검사 기록이 없습니다.','No observation or test records are linked to this region.')+'</p>';
    q('#observationLocationNote').textContent=selected==='abdomen'?t('통증 점수와 배액관 기록은 부위가 지정되지 않은 공통 기록입니다.','Pain scores and drain records have no recorded anatomical location.'):selected==='all'?t('연결된 부위 기록이 없으면 위치를 추정하지 않습니다.','An anatomical location is not inferred when no location record is linked.'):t('관련 기록을 묶어 보여주며, 선택한 부위의 이상을 뜻하지 않습니다.','Records are grouped for reference; selecting a region does not indicate an abnormality.');
    q('#observationLegend').innerHTML='<span><i class="observation-evidence-dot"></i>'+t('연결 기록·예시','Linked record / example')+'</span><span><i class="observation-muted-dot"></i>'+t('위치 근거 없음 · 정상 판정 아님','No location evidence · not a normal finding')+'</span>';
    if(focus)all('[data-observation-select]').find(b=>b.dataset.observationSelect===selected)?.focus({preventScroll:true});
  }
  function mount(bed,lang){
    const panel=q('#publicPatientBody .anatomy-panel'),dialog=q('#publicPatient');
    dialog.classList.toggle('has-observation-panel',Boolean(bed.patient));
    if(!bed.patient||!panel){patient=null;current=null;connections=null;identity='';return;}
    const nextIdentity=[bed.id,bed.patient.pid,bed.patient.admit_t].join(':');
    const same=nextIdentity===identity;patient=bed.patient;identity=nextIdentity;language=lang==='ko'?'ko':lang==='en'?'en':I18n.language;
    const initial=SICUObservationModel.derive(patient,{language});selected=same?selected:initial.defaultRegion;
    const deviceDetails=q('#publicPatientBody .patient-device-details');
    panel.classList.add('observation-panel');panel.dataset.noTranslate='';
    panel.innerHTML='<div class="observation-titlebar"><h3>'+t('관찰 부위','Observation sites')+'</h3><button type="button" data-observation-select="all" aria-pressed="false">'+t('전체 기록','Common records')+'<span aria-hidden="true">↗</span></button></div><p class="observation-intro">'+t('부위를 선택하면 연결된 기록을 확인할 수 있습니다.','Select a region to see its related records.')+'</p><div class="observation-focus"><strong id="observationFocusName"></strong><span id="observationFocusState"></span></div><div class="observation-layout"><div class="observation-diagram"></div></div><div id="observationLegend"></div><div id="observationEvidence"></div><section class="observation-records-section" aria-labelledby="observationRecordTitle"><div class="observation-records-heading"><h4 id="observationRecordTitle"></h4><small id="observationRecordContext"></small></div><div id="observationRecords" aria-live="polite" aria-atomic="true"></div><p id="observationLocationNote"></p></section>';
    const layout=panel.querySelector('.observation-layout');
    panel.querySelector('.observation-titlebar h3').textContent=t('관찰 부위 · 연결 장비','Observation sites & equipment');
    panel.querySelector('.observation-intro').textContent=t('관찰 부위, 연결 장비와 관련 기록을 함께 확인합니다.','Review observation sites, connected equipment and related records together.');
    const figure=document.createElement('div');figure.className='device-figure';
    layout.prepend(figure);figure.append(layout.querySelector('.observation-diagram'));
    const notice=document.createElement('p');notice.id='deviceLocationNotice';notice.className='observation-intro';panel.querySelector('.observation-intro').replaceWith(notice);
    if(deviceDetails){
      const section=document.createElement('section');section.className='observation-connections';section.setAttribute('aria-labelledby','deviceConnectionSummary');
      deviceDetails.open=true;deviceDetails.querySelector('summary').id='deviceConnectionSummary';
      section.append(deviceDetails);layout.append(section);
    }
    layout.append(panel.querySelector('.observation-records-section'));
    renderSelection();
    const course=q('.patient-care-section .patient-course');
    if(initial.scenarioFindings?.length&&course){
      const notes=document.createElement('section');notes.className='observation-scenario';notes.setAttribute('aria-labelledby','observationScenarioTitle');
      notes.innerHTML='<div class="observation-scenario-heading"><h4 id="observationScenarioTitle">'+t('시나리오의 관찰 단서','Scenario observation clues')+'</h4><span>'+t('가상 예시','Fictional example')+'</span></div><ul>'+initial.scenarioFindings.map(item=>'<li data-scenario-finding="'+E(item.id)+'" data-scenario-source="'+E(item.source)+'">'+E(I18n.t(item.label))+'</li>').join('')+'</ul><p>'+t('모의 상황에 설정된 설명이며, 측정·확인된 환자 소견과 구분합니다.','These are descriptions set in the scenario, distinct from measured or verified patient findings.')+'</p>';
      course.after(notes);
    }
  }
  const nativeOpen=window.openPublicBed;
  window.openPublicBed=function(bed,lang){const result=nativeOpen.apply(this,arguments);if(bed)mount(bed,lang);return result;};
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-observation-select]'),hit=event.target.closest('.observation-diagram [data-observation-region]');
    if(button){selected=button.dataset.observationSelect;renderSelection();}
    else if(hit){selected=hit.dataset.observationRegion;renderSelection(true);}
  });
  document.addEventListener('keydown',event=>{
    const button=event.target.closest('.observation-diagram [data-observation-select]');if(!button)return;
    if(['Enter',' '].includes(event.key)){event.preventDefault();selected=button.dataset.observationSelect;renderSelection(true);return;}
    const buttons=all('.observation-diagram [data-observation-select]'),index=buttons.indexOf(button);let next;
    if(['ArrowRight','ArrowDown'].includes(event.key))next=(index+1)%buttons.length;
    else if(['ArrowLeft','ArrowUp'].includes(event.key))next=(index+buttons.length-1)%buttons.length;
    else if(event.key==='Home')next=0;else if(event.key==='End')next=buttons.length-1;else return;
    event.preventDefault();selected=buttons[next].dataset.observationSelect;renderSelection(true);
  });
  window.SICUObservations=Object.freeze({describe:()=>current,connections:()=>connections});
})();
