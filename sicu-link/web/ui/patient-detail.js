/* A read-only patient sheet composed from the existing public record and care nodes. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const element = (tag, className, html) => {
    const node = document.createElement(tag);
    node.className = className;
    if (html !== undefined) node.innerHTML = html;
    return node;
  };
  const closeIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
  const nativeOpen = window.openPublicBed;
  let selectedBed = '', opener = null;

  function render(bed, language) {
    const ko = language === 'ko', t = (a,b) => ko ? a : b;
    const dialog = document.getElementById('publicPatient');
    const body = document.getElementById('publicPatientBody');
    const close = document.getElementById('publicClose');
    const patient = bed.patient;
    const model = typeof S !== 'undefined' ? S : null;
    const unit = model?.floors.flatMap(f => f.units).find(u => u.beds.some(b => b.id === bed.id));
    const clock = model?.clock || '';
    const unitName = unit ? FacilityRuntime.unitName(unit) : '';
    const hospitalName = unit ? I18n.t(unit.hospital_name || 'Demo Hospital '+(unit.hospital_id || 'A')) : '';
    const anatomy = body.querySelector('.anatomy-panel');
    const care = body.querySelector('.sicu-detail-care');
    const titleId = 'patientSheetTitle';

    dialog.classList.add('patient-sheet');
    dialog.lang = language;
    dialog.dataset.patientBed = bed.id;
    dialog.setAttribute('aria-labelledby', titleId);
    dialog.setAttribute('aria-describedby', 'patientSheetSource');
    body.dataset.noTranslate = '';
    close.innerHTML = closeIcon;
    close.setAttribute('aria-label', t('환자 상세 닫기','Close patient details'));
    close.title = t('닫기','Close');
    close.dataset.noTranslate = '';

    const head = element('div','patient-sheet-head');
    const index = element('div','patient-bed-index','<span>BED</span><strong>'+esc(bed.id.split('-').pop())+'</strong>');
    index.setAttribute('aria-hidden','true');
    const identity = element('div','patient-identity');
    identity.append(element('p','patient-sheet-context',esc([hospitalName,unitName].filter(Boolean).join(' / '))));
    identity.append(element('h2','',esc(bed.id)));
    identity.lastElementChild.id = titleId;
    const gender = patient?.sex === 'F' ? t('여','F') : patient?.sex === 'M' ? t('남','M') : patient?.sex || t('성별 미확인','Sex unknown');
    const age = patient?.age == null ? t('나이 미확인','Age unknown') : patient.age+t('세',' years');
    const metadata = patient ? [patient.pid,age,gender] : [bed.reservation ? t('입실 예약','Reserved admission') : t('빈 병상','Empty bed')];
    identity.append(element('p','patient-identity-meta',metadata.filter(Boolean).map(item=>'<span>'+esc(item)+'</span>').join('')));
    if(patient){
      const clinical=SICUClinicalDetails.derive(patient,{language,demoRecord:SICUClinicalDemo.find(patient)});
      const summary=element('dl','patient-primary-summary');
      for(const [key,label] of [['diagnosis',t('주진단','Primary diagnosis')],['procedure',t('주수술','Primary procedure')]]){
        const item=clinical[key],row=element('div','');row.dataset.clinicalField=key;row.dataset.detailKind=item.kind;
        row.innerHTML='<dt>'+label+'</dt><dd>'+esc(item.value)+(item.kind==='fictional_example'?'<small class="clinical-example-label">'+t('시연 예시','Demo example')+'</small>':'')+'</dd>';
        summary.append(row);
      }
      identity.append(summary);
    }
    const context = element('div','patient-sheet-asof','<span class="patient-demo-tag">'+t('가상 데이터','SIMULATION')+'</span><small>'+esc(clock ? clock+' · '+t('시뮬레이션 시점','Simulation time') : t('시뮬레이션','Simulation'))+'</small>');
    head.append(index,identity,context);
    body.replaceChildren(head);

    if (patient) {
      const vitals = element('section','patient-vitals');
      vitals.setAttribute('aria-label',t('선택 시점 활력징후','Vitals at the selected simulation time'));
      for (const [key,label,unitLabel,name] of [
        ['hr','HR','bpm',t('심박수','Heart rate')],
        ['map','MAP','mmHg',t('평균동맥압','Mean arterial pressure')],
        ['spo2','SpO₂','%',t('산소포화도','Oxygen saturation')],
        ['rr','RR','/min',t('호흡수','Respiratory rate')]
      ]) {
        const value = patient.vitals?.[key];
        const item = element('div','patient-vital');
        item.dataset.vital = key;
        item.dataset.value = value == null ? 'unknown' : String(value);
        item.innerHTML = '<span class="patient-vital-label">'+label+'<small>'+name+'</small></span><div class="patient-vital-value"><strong>'+esc(value ?? '—')+'</strong><span>'+esc(value == null ? t('미확인','Unknown') : unitLabel)+'</span></div>';
        vitals.append(item);
      }
      body.append(vitals);

      const content = element('div','patient-sheet-body');
      const location = element('section','patient-location');
      if (anatomy) {
        anatomy.removeAttribute('style');
        anatomy.querySelector('h3').textContent = t('관찰 부위','Anatomical observations');
        anatomy.querySelectorAll('[style]').forEach(node=>node.removeAttribute('style'));
        location.append(anatomy);
      }
      const careSection = element('section','patient-care-section');
      const heading = element('div','patient-section-heading','<h3>'+t('간호 상태','Care indicators')+'</h3><span>'+t('6개 항목','6 indicators')+'</span>');
      careSection.append(heading);
      if (care) careSection.append(care);
      const course = element('div','patient-course');
      const bleeding = patient.simulation_override?.scenario === 'bleeding';
      let diagnosis = patient.dx || '';
      if (diagnosis === 'Fictional postoperative monitoring case') diagnosis = t('수술 후 ICU 모니터링','Postoperative ICU monitoring');
      if (diagnosis === 'Fictional postoperative admission') diagnosis = t('수술 후 ICU 입실','Postoperative ICU admission');
      const summary = bleeding ? t('수술 후 출혈 의심 시나리오','Suspected postoperative bleeding scenario') : diagnosis;
      course.innerHTML = '<span class="patient-section-label">'+t('현재 경과','Current course')+'</span><p>'+esc(summary || t('연결된 경과 정보 없음','No linked clinical summary'))+'</p>';
      if (bleeding) course.append(element('small','',t('가상 시나리오에 설정된 상태입니다.','A condition set in the fictional scenario.')));
      careSection.append(course);

      const devices = element('details','patient-device-details');
      devices.innerHTML = '<summary>'+t('연결 장비 상세','Device details')+'<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="m6 8 4 4 4-4"/></svg></summary>';
      const deviceList = element('dl','patient-device-list');
      for (const [key,kr,en] of [
        ['oxygen','산소 공급','Oxygen'],['ventilator','인공호흡기','Ventilator'],['iv','정맥주입','IV cannula'],
        ['central_line','중심정맥관','Central line'],['arterial_line','동맥관','Arterial line'],
        ['urinary_catheter','유치도뇨관','Urinary catheter'],['drain','배액관','Drain'],
        ['ecmo','ECMO','ECMO'],['crrt','CRRT','CRRT']
      ]) {
        const value = patient.devices?.[key];
        const row = element('div','');
        row.dataset.device = key;
        row.innerHTML = '<dt>'+t(kr,en)+'</dt><dd data-device-state="'+(value === true ? 'active' : value === false ? 'inactive' : 'unknown')+'">'+(value === true ? t('사용 중','Active') : value === false ? t('없음','Not active') : t('미확인','Unknown'))+'</dd>';
        deviceList.append(row);
      }
      devices.append(deviceList);
      careSection.append(devices);
      content.append(location,careSection);
      body.append(content);
    } else {
      const empty = element('div','patient-sheet-empty');
      empty.innerHTML = '<div class="patient-empty-bed" aria-hidden="true">'+SICUVisuals.topview({occupied:false})+'</div><div><h3>'+t(bed.reservation?'입실을 준비하고 있습니다.':'현재 비어 있는 병상입니다.',bed.reservation?'Preparing for admission.':'This bed is currently empty.')+'</h3><p>'+t(bed.reservation?'수술 후 입실 예약이 있으며, 아직 환자가 입실하지 않았습니다.':'병상 수용 여부와 인력·장비 준비는 해당 병원의 확인이 필요합니다.',bed.reservation?'A postoperative admission is reserved; the patient has not arrived.':'Acceptance and staff/equipment readiness require hospital confirmation.')+'</p></div>';
      body.append(empty);
    }
    const source = element('div','patient-sheet-source','<span class="patient-source-dot" aria-hidden="true"></span><p>'+t('선택 시점의 가상 기록입니다. 실제 환자 기록이나 AI 생성 답변이 아닙니다.','Fictional records at the selected time. Not real patient records or an AI-generated response.')+'</p>');
    source.id = 'patientSheetSource';
    body.append(source);
    body.scrollTop = 0;
    close.focus({preventScroll:true});
  }

  window.openPublicBed = function(bed, language) {
    if (!bed) return;
    const dialog = document.getElementById('publicPatient');
    if (!dialog.open) opener = document.activeElement;
    selectedBed = bed.id;
    const result = nativeOpen.apply(this,arguments);
    render(bed,language === 'ko' ? 'ko' : 'en');
    return result;
  };
  const dialog = document.getElementById('publicPatient');
  dialog.addEventListener('close',()=>{
    if (dialog.open) return;
    const fallback = typeof bedEl !== 'undefined' ? bedEl[selectedBed]?.r.parentElement : null;
    const target = opener?.isConnected ? opener : fallback;
    target?.focus?.({preventScroll:true});
  });
  dialog.addEventListener('click',event=>{
    if (event.target !== dialog) return;
    const box=dialog.getBoundingClientRect();
    if(event.clientX<box.left || event.clientX>box.right || event.clientY<box.top || event.clientY>box.bottom)dialog.close();
  });
  document.addEventListener('icu-language',()=>queueMicrotask(()=>{
    if (!dialog.open || typeof S === 'undefined') return;
    const bed=S.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).find(b=>b.id===selectedBed);
    if(bed)window.openPublicBed(bed,I18n.language);
  }));
})();
