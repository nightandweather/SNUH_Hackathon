/* Connect the project's purpose to observed bed preparation and team work. */
(() => {
  'use strict';
  const M=window.SICUOperationsModel,q=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const ko=()=>I18n.language==='ko',t=(a,b)=>ko()?a:b,E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state=()=>typeof S==='undefined'?null:S,model=()=>M.derive(state());
  const clock=at=>M.clockAt(state()||{},at)||t('시각 미확인','Time unknown');
  let ready=false,tab='timeline',detailKind='capacity',selectedBed=null,selectedNurse=null,opener=null,lastPlan='',lastDialog='';
  const names={staff:()=>t('간호 인력','Nursing staff'),equipment:()=>t('필요 장비','Required equipment'),cleaning:()=>t('청소·정리','Cleaning / turnover')};
  const status=value=>value===true?t('준비 확인','Confirmed'):value===false?t('준비 중','Pending'):t('확인 대기','Not confirmed');
  const kindName=b=>({occupied:t('입실 중','Occupied'),reserved:t('입실 예약','Reserved'),turnover:t('정리 중','Turnover'),vacant:t('빈 병상','Vacant')})[b.kind];
  const scope=()=>{const s=state();return s?s.floors.flatMap(f=>f.units).map(u=>u.id).join(' · '):'';};
  const nurseName=id=>{const n=state()?.nurses.find(n=>n.id===id);return n?staffId(n):t('담당 미확인','Unassigned');};
  function sectionTitle(title,caption=''){return '<div class="ops-section-heading"><h3>'+title+'</h3>'+(caption?'<span>'+caption+'</span>':'')+'</div>';}
  function requirements(b){return '<dl class="ops-requirements">'+Object.entries(b.requirements).map(([key,value])=>'<div data-prep-key="'+key+'" data-prep-state="'+(value===true?'confirmed':value===false?'pending':'unknown')+'"><dt>'+names[key]()+'</dt><dd>'+status(value)+'</dd></div>').join('')+'</dl>';}
  function bedRows(beds){return beds.map(b=>'<button type="button" class="ops-list-row" data-operations-bed="'+E(b.id)+'"><span class="ops-bed-number">'+E(b.id.split('-').pop())+'</span><span><b>'+E(b.id)+'</b><small>'+kindName(b)+' · '+(b.kind==='occupied'?t('담당 ','Assigned ')+E(nurseName(b.owner)):b.prep==='confirmed'?t('준비 조건 확인','Preparation confirmed'):t('인력·장비·정리 확인','Staff, equipment and turnover checks'))+'</small></span><span aria-hidden="true">↗</span></button>').join('');}
  function summary(d){
    const prep=q('[data-operations-kind=capacity]'),arrival=q('[data-operations-kind=arrivals]'),support=q('[data-operations-kind=support]');
    prep.querySelector('small').textContent=t('수용 준비','Bed preparation');
    prep.querySelector('strong').textContent=d.unknownPrepCount||d.pendingPrepCount?t('확인 대기','Check pending'):d.vacantCount?d.readyCount+t('병상',' beds'):t('빈 병상 없음','No vacant beds');
    prep.querySelector('.ops-summary-note').textContent=t('빈 병상 ','Vacant ')+d.vacantCount+' · '+t('예약 ','Reserved ')+d.beds.filter(b=>b.kind==='reserved').length;
    arrival.querySelector('small').textContent=t('예정 입실 · 6시간','Expected arrivals · 6h');arrival.querySelector('strong').textContent=d.reservations6h.length+t('건',' scheduled');
    arrival.querySelector('.ops-summary-note').textContent=d.reservations6h.length?clock(d.reservations6h[0].expected_t)+' · '+t('입실 예약','Admission reserved'):t('기록된 예약 없음','No recorded reservations');
    support.querySelector('small').textContent=t('지원 대응','Team response');support.querySelector('strong').textContent=d.support.length+t('건',' active');
    const moving=d.support.reduce((n,i)=>n+i.pending.length,0),short=d.support.reduce((n,i)=>n+(i.shortage||0),0);
    support.querySelector('.ops-summary-note').textContent=short?t('추가 배정 필요 ','Additional assignment needed ')+short:moving?t('배정 인력 이동 중 ','Assigned staff en route ')+moving:t('진행 중인 대응 기록','Current response records');
  }
  function detailBody(d){
    if(selectedBed){
      const b=d.beds.find(b=>b.id===selectedBed);if(!b)return '<p>'+t('현재 범위에 없는 병상입니다.','This bed is outside the current scope.')+'</p>';
      const tasks=d.support.filter(i=>i.bed===b.id),reservation=b.reservation&&b.expected_t!==null?b:null;
      return '<div class="ops-bed-context"><span class="ops-kicker">'+E(b.unit)+'</span><h3>'+E(b.id)+'</h3><span class="ops-operational-state">'+kindName(b)+'</span></div>'+sectionTitle(t('다음 업무','Next work'))+'<dl class="ops-work-facts"><div><dt>'+t('담당','Assigned')+'</dt><dd>'+E(nurseName(b.owner))+'</dd></div><div><dt>'+t('현재 준비','Preparation')+'</dt><dd>'+E(b.flow?.label||(b.kind==='occupied'?t('환자 간호 중','Patient care ongoing'):b.prep==='confirmed'?t('기록된 준비 조건 확인','Recorded preparation confirmed'):t('인력·장비·청소 상태 확인','Confirm staff, equipment and cleaning')))+'</dd></div><div><dt>'+t('예정 시각','Expected time')+'</dt><dd>'+E(reservation?clock(reservation.expected_t)+' · '+t('예약','Reserved'):t('기록 없음','Not recorded'))+'</dd></div></dl>'+(b.kind!=='occupied'?requirements(b):'')+(tasks.length?'<p class="ops-record-note">'+t('연결된 대응 기록 ','Linked response records ')+tasks.length+t('건','')+'</p>':'')+'<button class="ops-locate" type="button" data-operations-locate="'+E(b.id)+'">'+t('지도에서 보기','Locate on map')+' ↗</button>';
    }
    if(selectedNurse){
      const n=d.nurseContext.find(n=>n.id===selectedNurse);if(!n)return '';
      return sectionTitle(E(nurseName(n.id)),E(n.unit))+'<div class="ops-team-summary"><span>'+t('담당 병상','Assigned beds')+'<b>'+n.assigned.length+'</b></span><span>'+t('지원 병상','Coverage beds')+'<b>'+n.cover.length+'</b></span><span>'+t('대응 업무','Response tasks')+'<b>'+n.events.length+'</b></span></div>'+bedRows(d.beds.filter(b=>n.assigned.includes(b.id)||n.cover.includes(b.id)))+'<p class="ops-record-note">'+t('예정 처치·신규 입실의 담당 배정과 숙련 정보는 확인 대기입니다.','Planned procedures, new admission assignments and competency availability are not confirmed.')+'</p>';
    }
    if(detailKind==='capacity')return '<p class="ops-detail-intro">'+t('빈 병상과 입실 예약의 준비 조건을 함께 확인합니다.','Review preparation requirements for vacant and reserved beds.')+'</p>'+bedRows(d.beds.filter(b=>b.kind!=='occupied'))+(!d.beds.some(b=>b.kind!=='occupied')?'<div class="ops-empty-state">'+t('현재 선택 병동의 모든 병상에 환자가 입실해 있습니다.','All beds in this view are occupied.')+'</div>':'')+'<p class="ops-record-note">'+t('수용 준비는 인력·필요 장비·청소 확인 기록을 기준으로 표시합니다.','Preparation uses recorded confirmation of staff, required equipment and cleaning.')+'</p>';
    if(detailKind==='arrivals')return '<p class="ops-detail-intro">'+t('현재 시각부터 6시간 안에 기록된 입실 예약입니다.','Recorded admission reservations within the next six hours.')+'</p>'+d.reservations6h.map(r=>'<button type="button" class="ops-list-row" data-operations-bed="'+E(r.bed)+'"><time>'+clock(r.expected_t)+'</time><span><b>'+E(r.bed)+'</b><small>'+t('입실 예약 · 수용 확정 확인 대기','Reserved admission · acceptance not confirmed')+'</small></span><span>↗</span></button>').join('')+(!d.reservations6h.length?'<div class="ops-empty-state">'+t('이 시간대에 기록된 입실 예약이 없습니다.','No admission reservations are recorded in this window.')+'</div>':'');
    return '<p class="ops-detail-intro">'+t('현재 대응 기록에 연결된 배정·도착 현황입니다.','Assignments and arrivals linked to current response records.')+'</p>'+d.support.map(i=>'<article class="ops-response-row" data-operations-incident="'+E(i.incidentId)+'"><button type="button" data-operations-bed="'+E(i.bed)+'">'+E(i.bed)+' ↗</button><p>'+t('필요 ','Needed ')+(i.need??'—')+' · '+t('배정 ','Assigned ')+i.responders.length+' · '+t('도착 ','Arrived ')+i.arrivedCount+'</p><small>'+t('이동 중 ','En route ')+i.pending.length+' · '+t('추가 배정 필요 ','Additional assignment needed ')+(i.shortage??'—')+'</small></article>').join('')+(!d.support.length?'<div class="ops-empty-state">'+t('현재 범위에 진행 중인 대응 기록이 없습니다.','There are no active response records in this view.')+'</div>':'');
  }
  function renderDialog(d,force=false){
    const dialog=q('#operationsDetail');if(!dialog?.open&&!force)return;
    const signature=JSON.stringify([I18n.language,d.scope,d.now,detailKind,selectedBed,selectedNurse,d.beds.map(b=>[b.id,b.kind,b.prep,b.requirements,b.owner,b.flow?.label]),d.reservations6h,d.support]);if(!force&&lastDialog===signature)return;lastDialog=signature;
    const content=q('#operationsDetailBody'),scroll=content.scrollTop;
    q('#operationsDetailTitle').textContent=selectedNurse?t('간호팀 업무','Nursing team work'):selectedBed?t('병상 준비·다음 업무','Bed preparation and next work'):({capacity:t('수용 준비','Bed preparation'),arrivals:t('예정 입실','Expected arrivals'),support:t('지원 대응','Team response')})[detailKind];
    q('#operationsDetailScope').textContent=scope()+' · '+d.clock+' · '+t('시뮬레이션','Simulation');
    q('#operationsDetailBack').hidden=!selectedBed&&!selectedNurse;q('#operationsDetailBack').textContent=t('← 목록','← Back');q('#operationsDetailClose').setAttribute('aria-label',t('운영 정보 닫기','Close operational details'));
    content.innerHTML=detailBody(d);content.scrollTop=scroll;
  }
  function open(kind,bed=null,nurse=null){
    if(!state())return;detailKind=kind;selectedBed=bed;selectedNurse=nurse;lastDialog='';const dialog=q('#operationsDetail');if(!dialog.open)opener=document.activeElement;
    renderDialog(model(),true);if(!dialog.open)dialog.showModal();q('#operationsDetailClose').focus({preventScroll:true});
  }
  function tabSelect(key,focus=false){
    tab=key;all('[data-operations-tab]').forEach(b=>{const chosen=b.dataset.operationsTab===key;b.setAttribute('aria-selected',String(chosen));b.tabIndex=chosen?0:-1;if(chosen&&focus)b.focus();});
    all('[data-operations-panel]').forEach(panel=>panel.hidden=panel.dataset.operationsPanel!==key);
  }
  function planEvent(row){
    const reservation=row.kind==='reservation';
    const label=reservation?t('인력·장비·정리 확인','Check staff, equipment and turnover'):I18n.t(row.label||'');
    return '<button type="button" class="ops-timeline-row" data-operations-bed="'+E(row.bed)+'" data-operations-event="'+E(row.kind)+'"><time class="ops-sr-only">'+clock(row.at)+'</time><span><b>'+E(row.bed)+'</b><small>'+E(label)+'</small></span><span aria-hidden="true">↗</span></button>';
  }
  function planCurrent(d,expanded=false){
    const flows=d.currentFlows.map(planEvent).join('');
    const support=d.support.map(i=>'<button type="button" class="ops-timeline-row ops-support-record" data-operations-bed="'+E(i.bed)+'"><span><b>'+E(i.bed)+' · '+E(I18n.t(i.label||t('지원 대응','Team response')))+'</b><small>'+t('지원 배정 ','Assigned ')+i.responders.length+' · '+t('도착 ','Arrived ')+i.arrivedCount+(i.shortage===null?' · '+t('필요 인력 확인','Required staffing unknown'):i.shortage?' · '+t('추가 필요 ','Additional staff needed ')+i.shortage:'')+'</small></span><span aria-hidden="true">↗</span></button>');
    const extra=support.length>3?'<details class="ops-support-more"'+(expanded?' open':'')+'><summary>'+t('나머지 ','Show remaining ')+(support.length-3)+t('건 보기',' responses')+'</summary><div class="ops-current-support">'+support.slice(3).join('')+'</div></details>':'';
    const preview=support.length?'<div class="ops-current-support">'+support.slice(0,3).join('')+'</div>'+extra:'';
    return '<section id="operationsCurrentFlows"><div class="ops-current-heading"><h4>'+t('지금 확인할 업무','Work at this time')+'</h4><small>'+E(d.clock)+' · '+(extra?t('기록순 3건 미리보기','First 3 recorded responses'):t('선택 범위','Selected scope'))+'</small></div>'+(flows+preview||'<p class="ops-current-empty">'+t('진행 중인 이송·지원 대응 기록이 없습니다.','No active transport or team responses are recorded.')+'</p>')+'</section>';
  }
  function renderPlan(d){
    const signature=JSON.stringify([I18n.language,d.scope,d.now,d.clock,d.timeline,d.support,d.metrics,d.unknownPrepCount]);if(signature===lastPlan)return;lastPlan=signature;
    all('[data-operations-tab]').forEach(b=>b.textContent=({timeline:t('다음 6시간','Next six hours'),performance:t('운영 지표','Operational measures'),references:t('참고 자료','Reference material')})[b.dataset.operationsTab]);
    const body=q('#operationsTimeline'),focused=body.contains(document.activeElement)?document.activeElement.closest('[data-operations-bed]')?.dataset.operationsBed:null,returnBed=body.contains(opener)?opener.closest('[data-operations-bed]')?.dataset.operationsBed:null,supportExpanded=!!body.querySelector('.ops-support-more')?.open,focusedSummary=document.activeElement===body.querySelector('.ops-support-more>summary');
    body.innerHTML=planCurrent(d,supportExpanded)+sectionTitle(t('다음 6시간의 기록된 일정','Recorded schedule · next six hours'),E(d.clock)+' — '+clock(d.now+d.horizon))+'<p class="ops-plan-intro">'+t('같은 시각의 입실 예약을 묶었습니다. 병상을 선택해 준비할 업무를 확인하세요.','Reservations at the same time are grouped. Select a bed to review its preparation work.')+'</p><div class="ops-time-axis" aria-hidden="true">'+Array.from({length:7},(_,i)=>'<time>'+clock(d.now+i*60)+'</time>').join('')+'</div><div class="ops-time-rows">'+d.scheduleGroups.map(group=>'<section class="ops-schedule-group" data-schedule-at="'+group.at+'" data-schedule-count="'+group.events.length+'"><div class="ops-schedule-time"><time>'+clock(group.at)+'</time><span>'+t('입실 예약 ','Reserved arrivals ')+group.events.length+t('건','')+'</span></div><div class="ops-schedule-beds">'+group.events.map(planEvent).join('')+'</div></section>').join('')+(!d.scheduleGroups.length?'<div class="ops-empty-state">'+t('이 범위의 다음 6시간에는 기록된 입실 예약이 없습니다.','No admission reservations are recorded for the next six hours in this scope.')+'</div>':'')+'</div><p class="ops-record-note">'+t('예약 시각이며 수용 확정은 아닙니다. 퇴실 예정이 없으면 새로 만들지 않습니다.','These are reserved times, not confirmed acceptance. No unrecorded departures are added.')+'</p>';
    const findBed=id=>[...body.querySelectorAll('[data-operations-bed]')].find(node=>node.dataset.operationsBed===id);
    if(returnBed)opener=findBed(returnBed)||q('#ops-tab-timeline');
    if(focused)(findBed(focused)||q('#ops-tab-timeline')).focus({preventScroll:true});
    if(focusedSummary)(body.querySelector('.ops-support-more>summary')||q('#ops-tab-timeline')).focus({preventScroll:true});
    q('#operationsPerformance').innerHTML=sectionTitle(t('운영의 변화를 확인하는 지표','Measures of operational change'),E(scope()))+'<div class="ops-performance-census">'+[[t('현재 재실','Currently occupied'),d.metrics.occupied+'/'+d.metrics.total],[t('진행 이송','Active transport'),d.metrics.activeTransport],[t('병상 정리','Bed turnover'),d.metrics.turnover]].map(([label,value])=>'<div><small>'+label+'</small><strong>'+value+'</strong></div>').join('')+'</div><div class="ops-measure-list">'+[[t('입실 대기시간','Admission waiting time'),t('입실 요청과 실제 입실 시각을 확인하면 집계됩니다.','Calculated from admission request and actual arrival times.')],[t('병상 준비시간','Bed preparation time'),t('퇴실과 청소·준비 완료 시각을 확인하면 집계됩니다.','Calculated from departure and cleaning / preparation completion times.')],[t('초과근무 시간','Overtime hours'),t('예정 근무와 실제 근무 기록을 확인하면 집계됩니다.','Calculated from scheduled and actual worked hours.')]].map(([label,note])=>'<div><span><b>'+label+'</b><small>'+note+'</small></span><span class="ops-measure-unknown">'+t('확인 자료 없음','No measurement records')+'</span></div>').join('')+'</div><p class="ops-record-note">'+t('현재 값은 선택 범위의 가상 기록입니다. 도입 효과와 비용 절감은 실제 운영 기록으로 비교합니다.','Current values describe fictional records in this scope. Operational impact and cost savings require measured operational records.')+'</p>';
    q('#operationsReferenceIntro').textContent=t('아래 두 표는 각각 독립된 8병상 참고 자료입니다. 현재 병원의 운영 일정과 구분해 확인하세요.','These are two independent eight-bed references, separate from this hospital’s operational schedule.');
    const workbook=q('#workbookPlan>summary');if(workbook)workbook.textContent=t('제공 자료 · ICU.xlsx','Provided material · ICU.xlsx');
    const sandbox=q('#flowDetails>summary');if(sandbox){sandbox.dataset.noTranslate='';sandbox.textContent=t('가상 운영 예시 · 30일 시나리오','Fictional operations example · 30-day scenario');}
  }
  function decoratePatient(bed){
    const body=q('#publicPatientBody');if(!body)return;body.querySelector('#patientOperations')?.remove();
    const b=model().beds.find(b=>b.id===bed.id);if(!b)return;
    const panel=document.createElement('section');panel.id='patientOperations';panel.className='patient-operations';panel.dataset.noTranslate='';
    panel.innerHTML=sectionTitle(t('연결된 업무','Connected work'))+'<div class="ops-patient-work"><span><small>'+t('담당 간호사','Assigned nurse')+'</small><b>'+E(nurseName(b.owner))+'</b></span><span><small>'+t('입실 예약 시각','Reserved arrival')+'</small><b>'+E(b.kind==='reserved'?clock(b.expected_t):t('기록 없음','Not recorded'))+'</b></span><button type="button" data-operations-patient-bed="'+E(b.id)+'">'+t('준비·다음 업무 보기','Preparation and next work')+' ↗</button></div>';
    body.querySelector('.patient-sheet-source')?.before(panel);
  }
  function decorateNurse(){
    if(typeof picked==='undefined'||!picked?.startsWith('N:'))return;
    const n=model().nurseContext.find(n=>n.id===picked.slice(2)),box=q('#detail');if(!n||!box)return;
    box.querySelector('#nurseOperationContext')?.remove();const section=document.createElement('section');section.id='nurseOperationContext';section.dataset.noTranslate='';
    section.innerHTML='<h3>'+t('업무 연결','Connected work')+'</h3><p>'+t('담당 병상 ','Assigned beds ')+n.assigned.length+' · '+t('지원 병상 ','Coverage beds ')+n.cover.length+' · '+t('대응 업무 ','Response tasks ')+n.events.length+'</p>'+(n.devices.length?'<small>'+n.devices.map(r=>E(r.bed)+' · '+E(r.key.toUpperCase())).join('<br>')+'</small>':'')+'<button type="button" data-operations-nurse="'+E(n.id)+'">'+t('담당·지원 범위 보기','View assignments and coverage')+' ↗</button>';box.append(section);
  }
  function update(){
    if(!ready||!state())return;const d=model();summary(d);renderPlan(d);renderDialog(d);
    q('#workspacePurpose').textContent=t('병상 준비 · 간호 지원 · 환자 이동을 한눈에','Bed preparation, nursing support and patient movement in one view');
    const show=['ward','patients'].includes(document.body.dataset.workspaceView);q('#operationsSummary').hidden=!show;q('#workspacePurpose').hidden=!show;
    q('#workspaceStats').classList.add('ops-secondary-census');q('#workspaceStats').hidden=!show;
    q('#operationsSummary').setAttribute('aria-label',t('병동 운영 요약','Ward operations summary'));q('.ops-tabs').setAttribute('aria-label',t('운영 계획 보기','Operational planning views'));
    q('#transportOperationsNote').textContent=t('환자 인계 → 이송 → 병상 정리 → 준비 확인','Patient handoff → transport → turnover → preparation checks');
    const referenceNote=q('#facilityPlanNote');if(referenceNote&&referenceNote.parentElement!==q('#operationsReferences'))q('#operationsReferences').prepend(referenceNote);
  }
  function setup(){
    const heading=q('#workspaceHeading'),planning=q('#planningView');if(!heading||!planning)return;
    const purpose=document.createElement('p');purpose.id='workspacePurpose';purpose.dataset.noTranslate='';q('#workspaceTitle').after(purpose);
    const strip=document.createElement('section');strip.id='operationsSummary';strip.dataset.noTranslate='';strip.setAttribute('aria-label',t('병동 운영 요약','Ward operations summary'));strip.innerHTML=['capacity','arrivals','support'].map(kind=>'<button type="button" class="ops-summary-item" data-operations-kind="'+kind+'"><span><small></small><strong></strong></span><span class="ops-summary-note"></span><span class="ops-summary-arrow" aria-hidden="true">↗</span></button>').join('');heading.after(strip);
    const note=document.createElement('p');note.id='transportOperationsNote';note.dataset.noTranslate='';q('#transportSceneBar')?.after(note);
    const plan=document.createElement('section');plan.id='operationsPlanning';plan.dataset.noTranslate='';plan.innerHTML='<div class="ops-tabs" role="tablist" aria-label="Operational planning">'+['timeline','performance','references'].map(key=>'<button type="button" id="ops-tab-'+key+'" role="tab" aria-controls="operations-'+key+'" data-operations-tab="'+key+'"></button>').join('')+'</div><section id="operations-timeline" role="tabpanel" aria-labelledby="ops-tab-timeline" data-operations-panel="timeline"><div id="operationsTimeline"></div></section><section id="operations-performance" role="tabpanel" aria-labelledby="ops-tab-performance" data-operations-panel="performance"><div id="operationsPerformance"></div></section><section id="operations-references" role="tabpanel" aria-labelledby="ops-tab-references" data-operations-panel="references"><p id="operationsReferenceIntro"></p><div id="operationsReferences"></div></section>';
    const refs=[...planning.querySelectorAll('.flow-panel')];planning.prepend(plan);refs.forEach(node=>q('#operationsReferences').append(node));refs.forEach(node=>node.querySelector('details').open=false);
    const dialog=document.createElement('dialog');dialog.id='operationsDetail';dialog.dataset.noTranslate='';dialog.setAttribute('aria-labelledby','operationsDetailTitle');dialog.innerHTML='<header class="ops-dialog-head"><div><small id="operationsDetailScope"></small><h2 id="operationsDetailTitle"></h2></div><button type="button" id="operationsDetailClose">×</button></header><div class="ops-dialog-navigation"><button id="operationsDetailBack" type="button" hidden></button></div><div id="operationsDetailBody"></div>';document.body.append(dialog);
    q('#operationsDetailClose').onclick=()=>dialog.close();dialog.onclose=()=>{if(opener?.isConnected)opener.focus({preventScroll:true});};dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
    q('#operationsDetailBack').onclick=()=>{selectedBed=null;selectedNurse=null;renderDialog(model(),true);q('#operationsDetailClose').focus();};
    document.addEventListener('click',event=>{
      const kind=event.target.closest('[data-operations-kind]'),bed=event.target.closest('[data-operations-bed]'),nurse=event.target.closest('[data-operations-nurse]'),locate=event.target.closest('[data-operations-locate]'),patient=event.target.closest('[data-operations-patient-bed]'),tabButton=event.target.closest('[data-operations-tab]');
      if(kind)open(kind.dataset.operationsKind);
      else if(bed){selectedBed=bed.dataset.operationsBed;if(!dialog.open)open('capacity',selectedBed);else{renderDialog(model(),true);q('#operationsDetailClose').focus();}}
      else if(nurse)open('support',null,nurse.dataset.operationsNurse);
      else if(patient){const id=patient.dataset.operationsPatientBed,returnTarget=document.body.dataset.workspaceView==='patients'?q('#patientCards [data-patient="'+id+'"]'):bedEl[id]?.r.parentElement;q('#publicPatient').close();open('capacity',id);opener=returnTarget||opener;}
      else if(locate){const id=locate.dataset.operationsLocate;q('#workspaceNav [data-workspace-view=ward]').click();const node=bedEl[id]?.r.parentElement;if(node){all('.ops-selected-bed').forEach(e=>e.classList.remove('ops-selected-bed'));node.classList.add('ops-selected-bed');opener=node;dialog.close();node.scrollIntoView({block:'center',inline:'center',behavior:'instant'});node.focus({preventScroll:true});}}
      else if(tabButton)tabSelect(tabButton.dataset.operationsTab);
    });
    q('.ops-tabs').addEventListener('keydown',event=>{const buttons=all('[data-operations-tab]'),index=buttons.indexOf(document.activeElement);if(index<0)return;let next;if(event.key==='ArrowRight')next=(index+1)%buttons.length;else if(event.key==='ArrowLeft')next=(index+buttons.length-1)%buttons.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=buttons.length-1;else return;event.preventDefault();tabSelect(buttons[next].dataset.operationsTab,true);});
    q('#workspaceNav').addEventListener('click',()=>queueMicrotask(update));
    q('#hospitalScope').addEventListener('change',()=>{if(dialog.open)dialog.close();});q('#wardScope').addEventListener('change',()=>{if(dialog.open)dialog.close();});
    ready=true;tabSelect(tab);update();
  }
  const nativeOpen=window.openPublicBed;window.openPublicBed=function(bed){const result=nativeOpen.apply(this,arguments);decoratePatient(bed);return result;};
  const nativeDetail=window.detail;window.detail=function(){const result=nativeDetail.apply(this,arguments);decorateNurse();return result;};
  const nativeDraw=window.draw;window.draw=function(){const result=nativeDraw.apply(this,arguments);update();return result;};
  document.addEventListener('icu-language',()=>queueMicrotask(()=>{lastPlan='';lastDialog='';update();decorateNurse();}));
  window.SICUOperations=Object.freeze({describe:()=>model(),open,showTab:tabSelect,update});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
