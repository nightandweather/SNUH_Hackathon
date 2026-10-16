/* Keep reference material below work, and describe the actual replay clock. */
(() => {
  'use strict';
  const q=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const t=(a,b)=>I18n.language==='ko'?a:b,E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let initialized=false;
  const descriptions=()=>[
    t('활력징후와 간호 상태는 선택한 시뮬레이션 시각의 가상 기록입니다. 처음에는 저장된 07:00 초기 스냅샷을 표시합니다.','Vitals and care indicators are fictional records at the selected simulation time. The initial view displays a stored 07:00 snapshot.'),
    t('시나리오는 07:00–07:30의 7개 시점으로 준비되어 있으며, 시점 간격은 시뮬레이션 5분입니다. 개별 활력징후의 실제 측정 시각·측정 주기는 제공되지 않습니다.','Scenarios contain seven stored states from 07:00 to 07:30, five simulated minutes apart. Individual vital measurement times and measurement intervals are not supplied.'),
    t('통합 재생은 약 14초 동안 7개 기록과 선택한 이송 예시를 함께 보여줍니다. 일시정지·시간 이동·초기화는 두 장면에 함께 적용됩니다.','Unified replay shows the seven stored states together with the selected porter example in about 14 seconds. Pause, seek and reset apply to both.'),
    t('환자 상세는 창을 열었을 때의 시점을 보여줍니다. 재생 시점이 바뀌면 상세창이 닫히며, 다시 환자를 선택해 해당 시점의 값을 확인합니다.','Patient details show the state when the dialog was opened. Changing the replay state closes the dialog; select the patient again to inspect that state.'),
    t('이송은 동선을 설명하는 가상 예시로, 해당 기록에서 실제 이송이 발생했다는 뜻은 아닙니다. 빈 병상이 없으면 입실 장면 없이 기록만 재생합니다.','Transport illustrates a fictional route; it does not mean a transfer occurred in the stored records. If no bed is available, arrival replay shows the records without an admission scene.')
  ];
  function removeEmptySection(parent){if(parent?.matches('.side>section')&&!parent.children.length&&!parent.textContent.trim())parent.remove();}
  function moveOriginal(node,destination,id){
    if(!node)return;const parent=node.parentElement;if(id)node.id=id;destination.append(node);removeEmptySection(parent);
  }
  function translate(){
    if(!initialized)return;
    q('#contextReferenceTitle').textContent=t('화면 안내·참고 자료','Display guide and references');
    q('#contextReferenceCaption').textContent=t('자료 시점 · 범례 · 시연 기준','Data timing · legend · simulation notes');
    q('#contextTimeTitle').textContent=t('자료 시점과 재생 방식','Data timing and replay');
    q('#contextTimeBody').innerHTML=descriptions().map(text=>'<p>'+E(text)+'</p>').join('');
    q('#contextCareTitle').textContent=t('간호 상태 표시 안내','Care indicator display guide');
  }
  function setup(){
    if(initialized||!q('#workspaceFooter'))return;
    const root=document.createElement('details');root.id='contextReferences';root.dataset.noTranslate='';
    root.innerHTML='<summary><span id="contextReferenceTitle"></span><small id="contextReferenceCaption"></small><span class="context-reference-chevron" aria-hidden="true">⌄</span></summary><div id="contextReferenceBody"><details id="contextTimeGuide"><summary id="contextTimeTitle"></summary><div id="contextTimeBody"></div></details><details id="contextCareGuide"><summary id="contextCareTitle"></summary><div id="contextCareBody"></div></details></div>';
    q('#workspaceFooter').before(root);
    const content=q('#contextReferenceBody'),care=q('#contextCareBody');
    const legend=q('.side .legend')?.closest('details');moveOriginal(legend,content,'contextLegend');
    // These are existing nodes, including their controllers, not copied tables.
    moveOriginal(q('#metrics')?.closest('details'),content,'contextMetrics');
    moveOriginal(q('#log')?.closest('details'),content,'contextSimulationLog');
    for(const selector of ['.patient-board>.tag','.patient-board>.icon-rules','#careIconLegend','.care-key-note','.floor-plan>.map-caption']){
      const node=q(selector);if(node)care.append(node);
    }
    initialized=true;translate();
  }
  function basis(bed,language){
    if(!bed?.patient)return;
    const t=(a,b)=>(language==='ko'||language==='en'?language:I18n.language)==='ko'?a:b;
    const model=typeof S!=='undefined'?S:null,clock=model?.clock||'—';
    const replay=Boolean(q('#sandboxReset')&&!q('#sandboxReset').disabled);
    const story=bed.flow?.scene==='porter-story';
    const mode=story?'porter':replay?'replay':'snapshot';
    const node=document.createElement('section');node.id='patientDataBasis';node.dataset.noTranslate='';node.dataset.referenceClock=clock;node.dataset.dataMode=mode;
    const modeName=story?t('이송 예시 시점','Porter example state'):replay?t('선택한 재생 시점','Selected replay state'):t('저장된 초기 스냅샷','Stored initial snapshot');
    node.innerHTML='<div class="patient-basis-clock"><small>'+t('표시 기준','Display reference')+'</small><strong>'+E(clock)+'</strong></div><p><b>'+modeName+'</b><span>'+t('실시간 측정이 아닌 가상 기록입니다.','Fictional records, not live measurements.')+'</span></p><details class="patient-basis-help"><summary>'+t('자료 기준','About this data')+'</summary><p>'+t('상세창을 열었을 때의 값입니다. 재생 자료는 시뮬레이션 5분 간격으로 준비되어 있으며, 개별 항목의 실제 측정 시각·측정 주기는 제공되지 않습니다.','These values are from the state when this dialog was opened. Replay states are five simulated minutes apart; individual measurement times and measurement intervals are not supplied.')+'</p></details>';
    const vitals=q('#publicPatientBody .patient-vitals');if(vitals)vitals.after(node);
    const asof=q('#publicPatientBody .patient-sheet-asof>small');
    if(asof)asof.textContent=clock+' · '+t('조회 시점 고정','Fixed at opening');
    const body=q('#publicPatientBody');
    const described=q('#publicPatient').getAttribute('aria-describedby')||'';
    q('#publicPatient').setAttribute('aria-describedby',[...new Set([...described.split(/\s+/).filter(Boolean),'patientDataBasis'])].join(' '));
    body.dataset.referenceClock=clock;
  }
  const nativeOpen=window.openPublicBed;
  window.openPublicBed=function(bed,...args){const result=nativeOpen.call(this,bed,...args);if(bed?.patient)basis(bed,args[0]);return result;};
  const nativeDraw=window.draw;window.draw=function(...args){const result=nativeDraw.apply(this,args);setup();return result;};
  document.addEventListener('icu-language',()=>queueMicrotask(translate));
  window.SICUContextDetails=Object.freeze({describe:()=>({cadenceMinutes:5,unifiedDurationMilliseconds:14000,storedStates:7,liveMeasurements:false,patientDetail:'opening-state',referenceSection:'contextReferences'}),setup});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
