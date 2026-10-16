/* Read-only staff sheet. No inferred career, dated rota or prior patient history. */
(() => {
  'use strict';
  const q=s=>document.querySelector(s),E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const t=(a,b)=>I18n.language==='ko'?a:b;
  let snapshot=null,selected='',opener=null,signature='',handoff=false;
  const state=()=>typeof S==='undefined'?null:S;
  const stamp=()=>{const s=state();return s?JSON.stringify([s.seed,Network.hospital,s.floors.flatMap(f=>f.units.map(u=>u.id)),SICUNurseProfile.derive(s,selected)]):'';};
  const marker=id=>[...document.querySelectorAll('#floors .nurse[data-staff-id]')].find(e=>e.dataset.staffId===id);
  const rosterButton=id=>[...document.querySelectorAll('#rosterTable .roster-staff[data-slot]')].find(e=>e.dataset.slot===id);
  const none=()=>t('이력 미등록','History not supplied');
  const role=()=>snapshot.role==='charge'?t('책임간호사','Charge nurse'):t('담당간호사','Bedside nurse');
  const dutyName=code=>({D:t('주간','Day'),E:t('오후','Evening'),N:t('야간','Night')})[code]||t('미확인','Unknown');
  const time=d=>d?.startClock&&d?.endClock?d.startClock+'–'+d.endClock:t('시간 미확인','Time unknown');
  const bedGlyph=row=>{
    let art=SICUVisuals.topview({occupied:row.occupied}).replace('<svg ','<svg data-occupied="'+row.occupied+'" ');
    if(row.occupied)art=art.replace('</svg>','<g class="nurse-patient-occupant" data-source="bed.patient" transform="translate(80 109) scale(72)" pointer-events="none">'+SICUTransportVisuals.bedPatient({deceased:row.deceased})+'</g></svg>');
    return art;
  };
  const rowHTML=row=>{
    const p=row.patient,gender=p?.sex==='F'?t('여','F'):p?.sex==='M'?t('남','M'):null;
    const context=p?[p.pid,p.age==null?null:p.age+t('세',' years'),gender].filter(v=>v!==null).map(E).join(' · '):t(row.reserved?'입실 예약 · 아직 환자 없음':'현재 환자 없음',row.reserved?'Reserved · no patient yet':'No patient currently admitted');
    return '<button type="button" class="nurse-patient-row" data-nurse-patient-bed="'+E(row.bedId)+'" data-relationship="'+row.relationship+'" data-patient-pid="'+E(p?.pid)+'" data-patient-admit="'+E(p?.admit_t)+'"><span class="nurse-bed-figure" aria-hidden="true">'+bedGlyph(row)+'</span><span class="nurse-patient-identity"><b>'+E(row.bedId)+'</b><span>'+context+'</span></span><span class="nurse-last-assigned" data-nurse-field="lastAssignedDate" data-record-state="unknown"><small>'+t('이전 담당일','Previously assigned')+'</small><span>'+none()+'</span></span><span class="nurse-row-arrow" aria-hidden="true">↗</span></button>';
  };
  function render(){
    const d=snapshot,dialog=q('#nurseSheet');if(!d||!dialog)return;
    dialog.lang=I18n.language;dialog.dataset.nurseId=d.slotId;dialog.dataset.staffId=d.staffId||'';
    const unit=I18n.language==='ko'?(d.unitNameKo||I18n.t(d.unitName))+' ('+d.unitNameEn+')':d.unitNameEn;
    const nurse={id:d.slotId,role:d.role};
    q('#nurseSheetBody').innerHTML='<header class="nurse-sheet-head"><span class="nurse-sheet-avatar" aria-hidden="true"><svg viewBox="-1.35 -1.8 2.7 3.5">'+SICUStaffVisuals.avatar(nurse,false)+'</svg></span><div class="nurse-sheet-identity"><p>'+E(I18n.t(d.hospitalName||'Demo Hospital '+d.hospitalId))+' / '+E(unit)+'</p><h2 id="nurseSheetTitle">'+role()+' <span>'+E(d.slotId.match(/-C$/)?'NC':'N'+d.slotId.match(/\d+$/)?.[0])+'</span></h2><div><b>'+E(d.staffId||t('직원 ID 미확인','Staff ID unknown'))+'</b><span>'+t('배치 슬롯','Staffing slot')+' '+E(d.slotId)+'</span></div></div></header><div class="nurse-sheet-time"><span class="nurse-fictional-label">'+t('가상 간호사','SIMULATED STAFF')+'</span><span>'+t('조회 기준','Snapshot')+' <time>'+E(d.clock||'—')+'</time></span><span>'+t('선택 시점의 담당·근무 기록','Assignments and duty at the selected time')+'</span></div><div class="nurse-sheet-content"><section aria-labelledby="nurseDutyTitle"><div class="nurse-section-title"><h3 id="nurseDutyTitle">'+t('근무 일정','Duty schedule')+'</h3><span>'+t('선택한 직원 기준','Selected staff member')+'</span></div><div class="nurse-duty-track"><div data-nurse-field="previousPersonalDuty" data-record-state="unknown"><small>'+t('직전 근무','Previous duty')+'</small><strong>'+none()+'</strong><span>'+t('날짜·근무조 자료 없음','Dated individual rota unavailable')+'</span></div><div class="nurse-current-duty" data-nurse-field="currentDuty" data-record-state="partial"><small>'+t('현재 근무','Current duty')+'</small><strong>'+E(d.currentDuty.code||'—')+' <span>'+dutyName(d.currentDuty.code)+'</span></strong><span>'+E(time(d.currentDuty))+'</span><span class="nurse-date-unknown">'+t('근무 날짜 미제공','Duty date not supplied')+'</span></div><div data-nurse-field="nextPersonalDuty" data-record-state="unknown"><small>'+t('다음 개인 근무','Next personal duty')+'</small><strong>'+none()+'</strong><span>'+t('날짜·근무조 자료 없음','Dated individual rota unavailable')+'</span></div></div><p class="nurse-team-shift" data-nurse-field="nextTeamShift">'+t('다음 팀 교대','Next team change')+' <b>'+E(d.nextTeamShift?.code||'—')+' · '+E(time(d.nextTeamShift))+'</b><span>'+t('병동 팀 시간표이며 개인의 다음 듀티가 아닙니다.','Ward team timetable; not this person’s next duty.')+'</span></p></section><section class="nurse-tenure" aria-labelledby="nurseTenureTitle"><h3 id="nurseTenureTitle">'+t('경력','Experience')+'</h3><dl><div data-nurse-field="totalYears" data-record-state="unknown"><dt>'+t('총 간호 경력','Total nursing experience')+'</dt><dd>'+t('미등록','Not supplied')+'</dd></div><div data-nurse-field="unitYears" data-record-state="unknown"><dt>'+t('현재 병동 경력','Experience in this unit')+'</dt><dd>'+t('미등록','Not supplied')+'</dd></div></dl></section><section aria-labelledby="nursePatientsTitle"><div class="nurse-section-title"><h3 id="nursePatientsTitle">'+t('현재 담당 환자','Current assigned patients')+'</h3><span>'+d.currentPatients.length+t('명',' patients')+' · '+d.assigned.length+t('병상 배정',' beds assigned')+'</span></div><div id="nurseAssignedPatients">'+(d.assigned.length?d.assigned.map(rowHTML).join(''):'<p class="nurse-empty">'+t('현재 직접 배정된 병상이 없습니다.','No beds are directly assigned at this time.')+'</p>')+'</div><p class="nurse-history-note">'+t('이전 담당일은 동일 환자·동일 입원 건의 과거 배정 이력이 있어야 표시됩니다. 현재 원본에는 제공되지 않았습니다.','A prior assignment date requires the same patient, admission and staff assignment history. It is not supplied in the current source.')+'</p></section>'+(d.coverage.length?'<section aria-labelledby="nurseCoverageTitle"><div class="nurse-section-title"><h3 id="nurseCoverageTitle">'+t('지원 중인 병상','Coverage beds')+'</h3><span>'+t('직접 담당과 구분','Separate from direct assignments')+'</span></div>'+d.coverage.map(rowHTML).join('')+'</section>':'')+'</div><footer class="nurse-sheet-source">'+t('날짜·경력·과거 담당 이력은 임의로 채우지 않았습니다. 현재 화면은 가상 시뮬레이션 기록입니다.','Dates, experience and prior assignment history are not fabricated. This view contains fictional simulation records.')+'</footer>';
    q('.nurse-sheet-source').id='nurseSheetSource';
    const close=q('#nurseSheetClose');close.setAttribute('aria-label',t('간호사 상세 닫기','Close nurse details'));close.title=t('닫기','Close');
  }
  function open(id,source){
    const data=SICUNurseProfile.derive(state(),id);if(!data)return;
    const dialog=q('#nurseSheet');if(!dialog)return;
    if(!dialog.open)opener=source||document.activeElement;
    selected=id;snapshot=data;signature=stamp();render();
    if(!dialog.open)dialog.showModal();q('#nurseSheetBody').scrollTop=0;q('#nurseSheetClose').focus({preventScroll:true});
  }
  function setup(){
    const dialog=document.createElement('dialog');dialog.id='nurseSheet';dialog.dataset.noTranslate='';dialog.setAttribute('aria-labelledby','nurseSheetTitle');dialog.setAttribute('aria-describedby','nurseSheetSource');
    dialog.innerHTML='<button id="nurseSheetClose" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button><div id="nurseSheetBody"></div>';document.body.append(dialog);
    q('#nurseSheetClose').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{if(handoff){handoff=false;return;}const roster=opener?.matches('.roster-staff[data-slot]')?rosterButton(selected):null;const target=opener?.isConnected?opener:roster||marker(selected);target?.focus({preventScroll:true});});
    dialog.addEventListener('click',event=>{
      const button=event.target.closest('[data-nurse-patient-bed]');
      if(button){if(signature!==stamp()){dialog.close();return;}const id=button.dataset.nursePatientBed,target=typeof bedEl!=='undefined'?bedEl[id]?.r.parentElement:null;handoff=true;dialog.close();if(target)target.focus({preventScroll:true});selectPatient(id);return;}
      if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}
    });
    const activate=event=>{
      if(event.type==='keydown'&&!['Enter',' '].includes(event.key))return;
      if(event.repeat)return;
      const staff=event.target.closest('#floors .nurse[data-staff-id]'),roster=event.target.closest('#rosterTable .roster-staff[data-slot]');
      const id=staff?.dataset.staffId||roster?.dataset.slot;if(!id)return;
      queueMicrotask(()=>{if(picked==='N:'+id)open(id,staff||roster);});
    };
    document.addEventListener('click',activate);document.addEventListener('keydown',activate);
  }
  const nativeDraw=window.draw;window.draw=function(){
    const focused=document.activeElement,rosterFocus=focused?.matches('.roster-staff[data-slot]')?{slot:focused.dataset.slot,label:focused.textContent}:null;
    const result=nativeDraw.apply(this,arguments);
    if(q('#nurseSheet')?.open&&signature!==stamp())q('#nurseSheet').close();
    if(rosterFocus&&document.activeElement===document.body&&!q('dialog[open],.modal.open')){
      const target=rosterButton(rosterFocus.slot);if(target?.textContent===rosterFocus.label)target.focus({preventScroll:true});
    }
    return result;
  };
  document.addEventListener('icu-language',()=>queueMicrotask(()=>{if(q('#nurseSheet')?.open)render();}));
  window.SICUNurseSheet=Object.freeze({open,describe:()=>snapshot});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
