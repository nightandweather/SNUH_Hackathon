'use strict';
// Keyed SVG entities stay mounted between polls, preserving focus and motion.
const MapUI={selected:null,zoom:1,fit:false,filter:'all',query:'',follow:false,connected:true,
  nodes:new Map(),scene:null,anchor:0,animation:null,mounted:false,revision:-1,motion:true,detailOpen:false,observer:null,compact:null,
  labels:{patient:new Map(),bed:new Map()}};
try{const saved=localStorage.getItem('pericare-map-motion');MapUI.motion=saved===null?!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches:saved==='on';}catch{}
const mapNow=()=>typeof performance!=='undefined'?performance.now():Date.now();
const shortId=id=>String(id).startsWith('DEMO-')?String(id).slice(5):String(id);
function mapCaption(id,kind='patient'){
  const labels=MapUI.labels[kind];if(labels.has(id))return labels.get(id);
  const raw=kind==='patient'?shortId(id):String(id),limit=kind==='patient'?4:8;
  const used=new Set(labels.values()),items=kind==='patient'?S.scene.patients:S.beds;
  const reserved=new Set(items.map(p=>kind==='patient'?shortId(p.id):String(p.id)).filter(v=>v.length<=limit));
  let label=raw;
  if(raw.length>limit||used.has(raw)){
    let n=labels.size+1;do{label=(kind==='patient'?'P':'B')+String(n++).padStart(3,'0');}while(used.has(label)||reserved.has(label));
  }
  labels.set(id,label);return label;
}
const zoneName=z=>({PREOP:'수술 전 대기',OR:'수술실',PACU:'회복실',SICU:'외과계 ICU',CCU:'심장계 ICU',WARD:'일반병동',ENTRY:'입원 접수',EXIT:'퇴원·출구'}[z]||z);
const bedStatus=b=>({occupied:'재실',closed:'가동 중지',cleaning:'청소·준비',reserved:'예약',available:'가용'}[b.status]||b.status);
const mapSelection=(kind,id)=>MapUI.selected?.kind===kind&&MapUI.selected.id===id;
const glyph=(name,extra='')=>`<use href="#map-${name}" ${extra}/>`;
function hospitalSymbols(){return `<defs>
  <symbol id="map-patient" viewBox="-25 -25 50 50"><circle cx="0" cy="-12" r="7" class="map-skin"/><path d="M-11 13v-14q11-9 22 0v14z" class="map-gown"/><path d="M-6 13v10m12-10v10" class="map-line"/></symbol>
  <symbol id="map-stretcher" viewBox="-25 -25 50 50"><path d="M-23 10h46v-17h-46z" class="map-gown"/><circle cx="-15" cy="-8" r="7" class="map-skin"/><path d="M-4-8h19q7 0 7 12H-4z" class="map-blanket"/><path d="M-24-18v34m48-23v23M-24 12h48" class="map-line"/><circle cx="-17" cy="20" r="3" class="map-wheel"/><circle cx="17" cy="20" r="3" class="map-wheel"/></symbol>
  <symbol id="map-nurse" viewBox="-25 -25 50 50"><circle cx="0" cy="-8" r="7" class="map-skin"/><path d="M-9-14v-9H9v9" class="map-cap"/><path d="M0-21v6m-3-3h6" class="map-cross"/><path d="M-11 16V3q11-8 22 0v13z" class="map-uniform"/><path d="M-6 16v7m12-7v7" class="map-line"/></symbol>
  <symbol id="map-doctor" viewBox="-25 -25 50 50"><circle cy="-12" r="7" class="map-skin"/><path d="M-12 18V1q12-8 24 0v17z" class="map-coat"/><path d="m-5-2 5 12 5-12M-8 4v5q0 6 6 5m9-10v5" class="map-line"/><circle cx="7" cy="12" r="3" class="map-stethoscope"/><path d="M-6 18v5m12-5v5" class="map-line"/></symbol>
  <symbol id="map-bed" viewBox="-30 -25 60 50"><rect x="-25" y="-19" width="50" height="35" rx="5" class="map-empty-bed"/><rect x="-19" y="-13" width="15" height="12" rx="3" class="map-pillow"/><path d="M-25 8h50m-20-24v22m-24 10v5m48-5v5" class="map-line"/></symbol>
  <symbol id="map-lock" viewBox="-12 -15 24 30"><rect x="-10" y="-2" width="20" height="16" rx="3" class="map-lock-fill"/><path d="M-6-2v-6a6 6 0 0 1 12 0v6M0 5v3" class="map-line"/></symbol>
  <symbol id="map-clean" viewBox="-16 -18 32 36"><path d="m11-16-13 22m-5-6 12 7-9 11-13-8z" class="map-clean-fill"/><path d="m-11 8-5 5m10-2-4 5M-1 14l-4 5" class="map-line"/></symbol>
  <marker id="map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" class="map-arrow-fill"/></marker>
  </defs>`;}
function hospitalView(){
  const scene=S.scene;if(!scene)return empty('지도 정보가 없습니다','서버를 최신 버전으로 실행해 주세요.');
  return `${['patient_relative','case_relative'].includes(S.clock_kind)?notice('사례별 상대시각 · 실제 동시 점유와 병상 경쟁은 계산하지 않습니다.'):''}
  <section class="panel hospital-shell hospital-map-panel" aria-labelledby="map-title">
  <h1 id="map-title" class="sr-only">실시간 병원 지도</h1>
  <div class="map-overview-bar"><div class="map-status-bar" id="map-status-bar">${hospitalStats()}</div><span id="map-bed-mix" class="map-bed-mix">${mapBedMix()}</span></div>
  <div class="map-toolbar"><div class="map-control-start"><label class="map-patient-picker"><span class="sr-only">환자 선택</span><select id="map-patient-picker" aria-label="지도에서 환자 선택">${mapPatientOptions()}</select></label><p id="map-live" class="map-live"></p></div><div class="map-tools"><button class="button small" data-action="map-zoom-out" aria-label="지도 축소">−</button><output id="map-zoom-label" aria-label="지도 배율">100%</output><button class="button small" data-action="map-zoom-in" aria-label="지도 확대">＋</button><button class="button small" data-action="map-fit">전체 보기</button><details class="map-options" id="map-options"><summary>지도 도구</summary><div class="map-option-panel"><label>구역 이동<select id="map-zone-picker" aria-label="구역 확대"><option value="">구역 선택</option>${['OR','PACU','SICU','CCU','WARD','ENTRY','EXIT'].map(z=>`<option value="${z}">${zoneName(z)}</option>`).join('')}</select></label><label>강조<select id="map-filter" aria-label="지도 강조 대상">${[['all','모두'],['moving','이동·인계 중'],['high','고위험'],['surgery','수술 중'],['ward','병동 회복'],['discharging','퇴원 진행']].map(([v,t])=>`<option value="${v}" ${MapUI.filter===v?'selected':''}>${t}</option>`).join('')}</select></label><button class="button" id="map-motion" data-action="map-motion" aria-pressed="${MapUI.motion}">${MapUI.motion?'이동 효과 켜짐':'이동 효과 꺼짐'}</button></div></details><button class="button small map-fullscreen" id="map-fullscreen" data-action="map-fullscreen" aria-pressed="false">${icon('expand')}<span>화면 가득 보기</span></button></div></div>
  <div class="map-viewport" id="map-viewport" tabindex="0" aria-label="병원 지도. 방향키로 이동할 수 있습니다." aria-describedby="map-instructions"><svg id="hospital-svg" class="hospital-svg" viewBox="0 0 ${scene.width} ${scene.height}" role="group" aria-label="수술 전 대기, 수술실, 회복실, 외과계 ICU, 심장계 ICU, 일반병동, 입원과 퇴원 위치">${hospitalSymbols()}<g id="map-floor"></g><g id="map-bed-layer"></g><g id="map-route-layer" aria-hidden="true"></g><g id="map-patient-layer"></g><g id="map-staff-layer"></g></svg></div>
  <div class="map-legend" aria-label="지도 범례"><span><i class="map-legend-person patient"></i>환자</span><span><i class="map-legend-person nurse"></i>간호사</span><span><i class="map-legend-person doctor"></i>의사</span><span><i class="map-legend-route"></i>이송</span><span><i class="map-legend-bed available"></i>가용</span><span><i class="map-legend-bed reserved"></i>예약</span><span><i class="map-legend-bed cleaning"></i>청소</span><span class="map-risk-key">▲≥70 · ◇40–69 · ○&lt;40</span></div>
  <p id="map-instructions" class="sr-only">아이콘 또는 환자 선택 목록으로 상세 내용을 엽니다. Esc로 상세 패널을 닫습니다. 지도는 드래그·방향키로 이동할 수 있습니다. 지도 도구에서 구역 확대, 강조, 이동 효과를 설정합니다. 병동에는 현재 추적 환자만 그려집니다. 가동 중지 병상은 잠금 아이콘으로 표시합니다.</p>
  <aside class="map-drawer" id="map-drawer" hidden aria-label="선택한 환자·병상 상세"><div class="map-drawer-toolbar"><b>선택 항목</b><button class="icon-button" data-action="map-close-detail" aria-label="상세 패널 닫기">${icon('close')}</button></div><div id="map-detail" class="map-detail"></div></aside></section>`;
}
function hospitalStats(){
  const h=S.hospital,d=h.daily[String(Math.floor(S.minute/1440))]||{},occupied=S.patients.filter(p=>p.phase==='ICU').length+S.scene.beds.filter(b=>b.external_patient).length;
  return [['현재 입원',h.current_census,'명','추적 수술 코호트','surgery'],['신규 입원',h.admissions,'명',`누적 · 오늘 ${d.admissions||0}명`,'available'],['병원 퇴원',h.discharges,'명',`귀가 퇴원 누적 · 오늘 ${d.discharges||0}명`,'available'],['ICU 재실',occupied,'명',`관측된 ICU 환자 · 가동 ${S.summary.enabled_beds}병상`,'occupied']].map(([label,value,unit,sub,c])=>`<div class="map-stat ${c}" title="${esc(sub)}"><span>${label}</span><strong>${value}<small>${unit}</small></strong><span class="sr-only">${esc(sub)}</span></div>`).join('');
}
function mapBedMix(){
  const ward=S.hospital.ward_capacity,icu=S.beds.length;
  return ward?`일반 ${ward} · ICU ${icu}(가동 ${S.summary.enabled_beds}) <b>${fmt(icu/(ward+icu)*100,1)}%</b>`:icu?`ICU ${icu}병상 · 일반병상 재고 미제공`:'병상 재고 미제공';
}
function mapFloor(scene){
  const hallTop=scene.hallway_y-44;
  let out=`<rect width="${scene.width}" height="${scene.height}" rx="18" class="map-ground"/><rect x="20" y="${hallTop}" width="${scene.width-40}" height="120" rx="18" class="map-hall"/><path d="M40 ${scene.hallway_y}H${scene.width-40}" class="map-hall-center"/><text x="48" y="${scene.hallway_y+48}" class="map-hall-label">이송 복도</text><rect x="610" y="${hallTop+5}" width="710" height="106" rx="14" class="map-station"/><text x="630" y="${hallTop+26}" class="map-station-label">간호 스테이션 · 가상 근무조</text>`;
  for(const z of scene.zones){
    out+=`<g class="map-zone zone-${z.id}"><rect x="${z.x}" y="${z.y}" width="${z.width}" height="${z.height}" rx="16"/><text x="${z.x+22}" y="${z.y+31}" class="map-zone-name">${esc(z.label)}</text><text x="${z.x+22}" y="${z.y+55}" class="map-zone-count">${z.count}명${['SICU','CCU'].includes(z.id)?' · '+scene.beds.filter(b=>b.unit===z.id).length+'병상':z.id==='WARD'?(S.hospital.ward_capacity?' · 배정 '+S.hospital.ward_occupied+'/'+S.hospital.ward_capacity+'병상':' · 병상 재고 미제공'):''}</text></g>`;
  }
  for(const p of scene.patients.filter(p=>p.phase==='OR')){
    const x=p.home.x,y=p.home.y;
    out+=`<g class="map-operating-bay" aria-hidden="true"><rect x="${x-68}" y="${y-27}" width="136" height="81" rx="9"/><path d="M${x-61} ${y-20}h14m-7-7v14" class="map-surgical-cross"/><text x="${x-43}" y="${y-30}" class="map-operating-label">수술 중</text><g transform="translate(${x-43} ${y+3})">${glyph('doctor','x="-13" y="-13" width="26" height="26"')}</g><g transform="translate(${x+44} ${y+3})">${glyph('nurse','x="-13" y="-13" width="26" height="26"')}</g><circle cx="${x+54}" cy="${y-18}" r="4" class="map-surgery-pulse"/></g>`;
  }
  for(const p of scene.patients.filter(p=>['PACU','PREOP','WARD'].includes(p.zone))){
    out+=`<rect x="${p.home.x-32}" y="${p.home.y-24}" width="64" height="51" rx="9" class="map-patient-bay"/>`;
  }
  return out;
}
function mapBedMarkup(b){
  const x=b.position.x,y=b.position.y,selected=mapSelection('bed',b.id);
  const content=b.status==='closed'?glyph('lock','x="-13" y="-15" width="26" height="30"'):b.status==='cleaning'?glyph('clean','x="-15" y="-17" width="30" height="34"'):glyph('bed','x="-27" y="-25" width="54" height="50"');
  return `<g transform="translate(${x} ${y})" class="map-bed bed-${b.status}${selected?' selected':''}" role="button" tabindex="0" data-action="map-select" data-kind="bed" data-id="${esc(b.id)}" aria-label="${esc(b.id)} ${bedStatus(b)}${b.occupant_id?' '+esc(b.occupant_id):''}" aria-pressed="${selected}"><title>${esc(b.id)} · ${bedStatus(b)}</title><rect x="-47" y="-60" width="94" height="138" rx="10" class="map-bed-card"/>${content}<text y="-42" text-anchor="middle" class="map-bed-id">${esc(mapCaption(b.id,'bed'))}</text><text y="72" text-anchor="middle" class="map-bed-status">${bedStatus(b)}</text>${b.external_patient?`<g class="map-external-patient">${glyph('stretcher','x="-24" y="-22" width="48" height="44"')}<text y="35" text-anchor="middle">기존 환자</text></g>`:''}${b.status==='reserved'?'<path d="M29-31h9v15l-4-3-5 3z" class="map-reserved-flag"/>':''}</g>`;
}
function mapEntityMarkup(kind,item){
  const p=kind==='patient'?S.patients.find(p=>p.id===item.id):null;
  const risk=p?.prediction.need_score,valid=Number.isFinite(risk),riskLabel=valid?`${risk>=70?'▲':risk>=40?'◇':'○'}${Math.round(risk)}`:'—';
  const symbol=kind==='staff'?item.kind:((item.motion&&!['ENTRY','EXIT'].includes(item.motion.destination))||['OR','PACU','ICU'].includes(item.phase))?'stretcher':'patient';
  const label=kind==='patient'?mapCaption(item.id):item.id;
  return `<title>${esc(mapEntityLabel(kind,item))}</title><circle r="28" class="map-hit"/><circle r="31" class="map-selection-ring"/>${glyph(symbol,'x="-21" y="-24" width="42" height="48"')}<g class="map-entity-caption"><rect x="${kind==='staff'?-18:-32}" y="27" width="${kind==='staff'?36:64}" height="23" rx="7"/><text y="44" text-anchor="middle">${esc(label)}</text></g>${kind==='patient'?`<g class="map-risk-badge"><rect x="6" y="-33" width="47" height="21" rx="6"/><text x="29" y="-17" text-anchor="middle">${esc(riskLabel)}</text></g>${item.quality_hold?'<g class="map-hold"><circle cx="-21" cy="-21" r="11"/><text x="-21" y="-17" text-anchor="middle">!</text></g>':''}`:''}${item.motion?'<path d="M-8 55h16m-4-4 4 4-4 4" class="map-moving-arrow"/>':''}`;
}
function mapEntityLabel(kind,item){
  if(kind==='staff')return `${item.name} ${item.id}, ${item.status}${item.patient_id?', 담당 '+item.patient_id:''}`;
  const p=S.patients.find(p=>p.id===item.id);
  return `${item.id}, ${p?.surgery||''}, ${p?.phase_label||''}, ${item.motion?item.motion.label+' '+item.motion.origin+'에서 '+item.motion.destination+'로 이동':zoneName(item.zone)}, 동적 위험 ${Number.isFinite(item.risk)?item.risk:'예측 불가'}${item.quality_hold?', 관측 확인으로 이동 보류':''}`;
}
function mapDetail(){
  const sel=MapUI.selected;
  if(!sel)return `<div class="map-detail-heading"><h2>환자·병상을 선택하세요</h2></div><div class="map-detail-body"><p>현재 위험, 필요한 집중관리 기간, 다음 진행 단계가 여기에 표시됩니다.</p><button class="button primary" data-action="map-focus-active">이동 중·고위험 환자 보기 ${icon('arrow')}</button></div>`;
  if(sel.kind==='bed'){
    const b=S.scene.beds.find(b=>b.id===sel.id),raw=S.beds.find(b=>b.id===sel.id);if(!b)return mapMissingDetail();
    return `<div class="map-detail-heading"><span class="eyebrow">ICU 병상</span><h2>${esc(b.id)}</h2>${chip(bedStatus(b),b.status==='available'?'green':b.status==='cleaning'?'amber':'blue')}</div><div class="map-detail-body"><dl class="map-detail-list"><div><dt>실제 재실</dt><dd>${esc(b.occupant_id||'없음')}</dd></div><div><dt>확정 예약</dt><dd>${b.reserved_patient_ids.map(esc).join(', ')||'없음'}</dd></div><div><dt>가용 예상</dt><dd>${b.occupant_id&&raw?.availability_forecast_known===false?'퇴실 시각 미확인':time(b.available_minute,true)}</dd></div><div><dt>장비</dt><dd>${raw?.capabilities.map(c=>c==='ventilator'?'환기':c==='crrt'?'CRRT':esc(c)).join(' · ')||'—'}</dd></div></dl><p class="muted">실제 퇴실·청소 완료 후 다음 입실을 진행합니다.</p>${b.closed_reason?notice(esc(b.closed_reason)):''}${S.patients.some(p=>p.id===b.occupant_id)?`<button class="button primary" data-action="map-select" data-kind="patient" data-id="${esc(b.occupant_id)}">재실 환자 보기</button>`:''}<button class="button" data-view="beds">ICU 병상 계획 ↗</button></div>`;
  }
  if(sel.kind==='staff'){
    const r=S.scene.staff.find(r=>r.id===sel.id);if(!r)return mapMissingDetail();
    return `<div class="map-detail-heading"><span class="eyebrow">가상 의료진 · ${esc(r.id)}</span><h2>${esc(r.name)}</h2>${chip(r.status,r.patient_id?'green':'')}</div><div class="map-detail-body"><dl class="map-detail-list"><div><dt>담당 환자</dt><dd>${esc(r.patient_id||'업무 대기')}</dd></div><div><dt>역할</dt><dd>${esc(S.automation.roles[r.role]?.job||r.role)}</dd></div>${r.destination?`<div><dt>이동·준비 대상</dt><dd>${esc(r.destination)}</dd></div>`:''}</dl>${r.patient_id?`<button class="button primary" data-action="map-select" data-kind="patient" data-id="${esc(r.patient_id)}">담당 환자 위치 보기</button>`:''}<p class="muted">관측 경과와 의료진 판단에 따라 담당 업무를 수행합니다.</p></div>`;
  }
  const p=S.patients.find(p=>p.id===sel.id),entity=S.scene.patients.find(p=>p.id===sel.id);if(!p)return mapMissingDetail();if(['DISCHARGED','DECEASED','TRANSFERRED'].includes(p.phase))return `<div class="map-detail-heading"><span class="eyebrow">${esc(p.id)}</span><h2>${esc(p.phase_label)}</h2>${chip('입원 경과 종료',p.phase==='DISCHARGED'?'green':'blue')}</div><div class="map-detail-body"><p>${esc(p.surgery)}</p><p>관측된 ${p.phase==='DISCHARGED'?'퇴원':'입원 종료'} ${time(p.discharge_minute,true)}</p><p>입원부터 종료까지 ${fmt((p.discharge_minute-p.admission_minute)/1440,1)}일</p><button class="button" data-action="inspect" data-patient="${esc(p.id)}">입원 경과 보기</button></div>`;
  if(!entity)return mapMissingDetail();
  const pr=p.prediction,w=p.workflow||{},v=pr.features.latest,res=activeReservation(p),staff=S.scene.staff.filter(r=>r.patient_id===p.id);
  return `<div class="map-detail-heading"><span class="eyebrow">${esc(p.id)} · ${esc(p.location)}</span><h2>${esc(p.surgery)}</h2>${chip(p.phase_label,'blue')} ${workflowPill(p)}</div><div class="map-detail-body"><div class="map-risk-summary"><div><span>동적 위험</span><strong class="${riskClass(pr.need_score)}">${validNeedPrediction(p)?fmt(pr.need_score):'—'}<small>/100</small></strong></div><div><span>${icuPredictionLabel(p)}</span><b>${pct(pr.icu_probability)}</b></div></div><p class="map-risk-caption">집중관리 필요 ${pct(pr.need_probability)} · ${trend(p)}</p><div class="map-detail-vitals"><div><span>MAP</span><b>${fmt(v.map)}<small>mmHg</small></b></div><div><span>SpO₂</span><b>${fmt(v.spo2)}<small>%</small></b></div><div><span>HR</span><b>${fmt(v.hr)}<small>bpm</small></b></div></div><dl class="map-detail-list"><div><dt>집중관리 지속 예측</dt><dd>${fmt(pr.intensive_hours,1)}시간</dd></div><div><dt>ICU 재실 예측</dt><dd>${fmt(pr.icu_los_hours,1)}시간</dd></div><div><dt>잔여 입원기간</dt><dd>${fmt(pr.hospital_los_days,1)}일</dd></div></dl><div class="map-next-step"><span>${esc(roleName(w.owner))}</span><b>${esc(w.label||'경과 관찰')}</b><p>${esc(w.detail||p.recommendation.reason)}</p>${res?.status==='confirmed'?`<small>${esc(res.bed_id)} · 예약 확정 ${time(res.created_minute)} · 입실 예정 ${time(w.transfer_due??res.start)}</small>`:res?.status==='occupied'?`<small>${esc(res.bed_id)} · 실제 재실</small>`:p.recommendation.bed_id?`<small>추천 예약 ${time(p.recommendation.due)} · 후보 ${esc(p.recommendation.bed_id)}</small>`:''}</div>${entity.motion?`<div class="map-transfer-card"><b>${esc(entity.motion.label)}</b><p>${esc(entity.motion.origin)} ${icon('arrow')} ${esc(entity.motion.destination)}</p><div class="map-transfer-progress"><i style="width:${Math.min(95,Math.max(0,(S.minute-entity.motion.start)/(entity.motion.end-entity.motion.start)*100))}%"></i></div><small>인계 완료 예정 ${time(entity.motion.end)}</small></div>`:''}${issue(p)?notice(esc(issue(p)),'amber','alert'):''}${staff.length?`<div class="map-assigned-staff">${staff.map(r=>`<button data-action="map-select" data-kind="staff" data-id="${esc(r.id)}">${esc(r.id)} · ${esc(r.status)}</button>`).join('')}</div>`:''}<button class="button primary" data-action="inspect" data-patient="${esc(p.id)}">위험 경과·예약 단계 보기 ↗</button></div>`;
}
function mapMissingDetail(){MapUI.selected=null;return `<div class="map-detail-body"><p>선택 항목이 현재 데이터에 없습니다. 지도에서 다시 선택하세요.</p></div>`;}
function mapEvents(){
  const events=(S.source==='import'?S.hospital.events.map((e,i)=>({...e,title:e.label,actor:'기록 재생',id:i})):(S.automation.log||[])).filter(e=>e.patient_id&&['assessment','order','reservation','quality','transport','admission','ward_arrival','discharge','hospital_admission','hospital_discharge_order','hospital_discharge','ready'].includes(e.kind)).slice(-4).reverse();
  return events.map(e=>`<div class="map-event"><time>${time(e.minute)}</time><div><b>${esc(e.title)}</b><p>${esc(e.patient_id)} · ${esc(e.actor)}</p></div><button class="button small ghost" data-action="map-select" data-kind="patient" data-id="${esc(e.patient_id)}" aria-label="${esc(e.patient_id)} 지도에서 보기">↗</button></div>`).join('')||`<div class="map-waiting"><p>시뮬레이션을 시작하면 의료진의 판단과 이동이 표시됩니다.</p></div>`;
}
function reconcileMapLayer(layer,items,kind){
  if(!layer)return;
  const existing=new Map([...layer.children].map(n=>[n.dataset.id,n]));
  for(const item of items){
    let node=existing.get(item.id);existing.delete(item.id);
    if(!node){node=document.createElementNS('http://www.w3.org/2000/svg','g');node.dataset.id=item.id;node.dataset.kind=kind;node.dataset.action='map-select';node.setAttribute('role','button');node.setAttribute('tabindex','0');layer.appendChild(node);}
    if(kind==='bed'){
      const signature=JSON.stringify([item,MapUI.selected,mapCaption(item.id,'bed')]);
      if(node._signature!==signature){const outer=mapBedMarkup(item),begin=outer.indexOf('>')+1;node.innerHTML=outer.slice(begin,outer.lastIndexOf('</g>'));node._signature=signature;}
      node.setAttribute('transform',`translate(${item.position.x} ${item.position.y})`);node.setAttribute('class',`map-bed bed-${item.status}${mapSelection(kind,item.id)?' selected':''}`);node.setAttribute('aria-label',`${item.id}, ${bedStatus(item)}${item.occupant_id?', '+item.occupant_id:''}`);
    }else{
      const patient=kind==='patient'?S.patients.find(p=>p.id===item.id):null;
      const signature=JSON.stringify([item.id,kind==='patient'?mapCaption(item.id):item.id,item.phase,item.risk,item.quality_hold,!!item.motion,item.status,item.patient_id,patient?.surgery]);
      if(node._signature!==signature){node.innerHTML=mapEntityMarkup(kind,item);node._signature=signature;}
      node.setAttribute('class',`map-entity map-${kind}${kind==='staff'?' role-'+item.role+' '+item.kind:' risk-'+riskClass(item.risk)}${item.motion?' in-motion':''}${item.quality_hold?' quality-hold':''}${mapSelection(kind,item.id)?' selected':''}`);
      node.setAttribute('aria-label',mapEntityLabel(kind,item));
      const key=kind+':'+item.id,previous=MapUI.nodes.get(key);
      let transition=previous?.transition;
      if(kind==='patient'&&previous&&!item.motion&&!previous.item.motion&&S.running&&MapUI.motion&&previous.item.zone!==item.zone){
        const a=previous.point||[previous.item.home.x,previous.item.home.y],b=[item.home.x,item.home.y];
        const za=S.scene.zones.find(z=>z.id===previous.item.zone),zb=S.scene.zones.find(z=>z.id===item.zone);
        transition={start:mapNow(),end:mapNow()+1600,points:[a,[za.x+15,a[1]],[za.x+15,S.scene.hallway_y],[zb.x+15,S.scene.hallway_y],[zb.x+15,b[1]],b]};
      }
      MapUI.nodes.set(key,{node,item,kind,transition,point:previous?.point});
    }
    node.setAttribute('aria-pressed',String(mapSelection(kind,item.id)));
  }
  for(const [id,node] of existing){if(document.activeElement===node)$('#map-viewport')?.focus({preventScroll:true});node.remove();MapUI.nodes.delete(kind+':'+id);}
}
function mapPoint(motion,minute,cap=false){
  if(motion.pickup&&minute<motion.start)return mapPoint(motion.pickup,minute);
  let f=Math.max(0,Math.min(cap ? .94 : 1,(minute-motion.start)/Math.max(.01,motion.end-motion.start)));
  const lengths=motion.points.slice(1).map((b,i)=>Math.hypot(b[0]-motion.points[i][0],b[1]-motion.points[i][1]));let distance=lengths.reduce((a,b)=>a+b,0)*f;
  let point=motion.points.at(-1);
  for(let i=0;i<lengths.length;i++){const length=lengths[i],a=motion.points[i],b=motion.points[i+1];if(distance<=length&&length){const q=distance/length;point=[a[0]+(b[0]-a[0])*q,a[1]+(b[1]-a[1])*q];break;}distance-=length;}
  return motion.offset?[point[0]+motion.offset[0],point[1]+motion.offset[1]]:[...point];
}
function sceneMinute(now=mapNow()){
  const scene=MapUI.scene;if(!scene)return 0;
  return scene.as_of_minute+(S.running&&MapUI.motion&&MapUI.connected?Math.min(S.speed,Math.max(0,(now-MapUI.anchor)/2000*S.speed)):0);
}
function updateMapPositions(now=mapNow()){
  const minute=sceneMinute(now),animate=S.running&&MapUI.motion&&MapUI.connected;
  for(const entry of MapUI.nodes.values()){
    const {item,node,kind}=entry;let point;
    if(entry.transition&&animate&&now<entry.transition.end){point=mapPoint(entry.transition,now);}
    else{
      entry.transition=null;
      point=item.motion?mapPoint(item.motion,minute,!!(kind==='patient'||item.motion.destination)):kind==='patient'?[item.home.x,item.home.y]:[...item.position];
    }
    entry.point=point;node.setAttribute('transform',`translate(${point[0].toFixed(2)} ${point[1].toFixed(2)})`);
  }
  if(MapUI.follow&&MapUI.selected?.kind==='patient'&&animate){const e=MapUI.nodes.get('patient:'+MapUI.selected.id);if(e?.point)centerMapPoint(e.point,false);}
}
function startHospitalAnimation(){
  stopHospitalAnimation();if(!S.running||!MapUI.motion||!MapUI.connected||typeof requestAnimationFrame!=='function')return;
  function frame(now){if(U.view!=='hospital'||!$('#hospital-svg')){MapUI.animation=null;return;}if(!document.hidden)updateMapPositions(now);MapUI.animation=requestAnimationFrame(frame);}
  MapUI.animation=requestAnimationFrame(frame);
}
function stopHospitalAnimation(){if(MapUI.animation!==null&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(MapUI.animation);MapUI.animation=null;}
function setHospitalConnection(connected){MapUI.connected=connected;if(!connected)stopHospitalAnimation();if(U.view==='hospital'&&$('#map-live'))updateMapStatus();}
function updateMapStatus(){
  const text=!MapUI.connected?'연결 끊김 · 마지막 확인 위치':!S.running?'일시정지 · '+time(S.minute)+' 기준':!MapUI.motion?'시간 진행 중 · 이동 효과 꺼짐':'실시간 재생 · '+S.speed+'분 / 2초';
  const n=$('#map-live');if(n)n.innerHTML=`<i class="${S.running&&MapUI.connected?'active':''}"></i>${esc(text)}`;
  const root=$('#hospital-svg');if(root)root.classList.toggle('map-animated',!!(S.running&&MapUI.motion&&MapUI.connected));
}
function renderHospital(){
  const root=$('#content');
  if(!$('#hospital-svg')){if(!MapUI.selected&&U.selected)MapUI.selected={kind:'patient',id:U.selected};if(!MapUI.mounted)MapUI.fit=(window.innerWidth||0)>=900;if((window.innerWidth||0)<900)MapUI.zoom=1;root.innerHTML=hospitalView();MapUI.nodes.clear();MapUI.revision=-1;MapUI.mounted=true;bindMapPan();}
  if(!S.scene)return;
  const svg=$('#hospital-svg');if(!svg)return;
  const changed=MapUI.revision!==S.revision;
  if(changed){MapUI.anchor=mapNow();MapUI.scene=S.scene;MapUI.revision=S.revision;}
  svg.setAttribute('viewBox',`0 0 ${S.scene.width} ${S.scene.height}`);
  $('#map-floor').innerHTML=mapFloor(S.scene);
  reconcileMapLayer($('#map-bed-layer'),S.scene.beds,'bed');
  reconcileMapLayer($('#map-patient-layer'),S.scene.patients,'patient');
  reconcileMapLayer($('#map-staff-layer'),S.scene.staff,'staff');
  $('#map-route-layer').innerHTML=S.scene.patients.filter(p=>p.motion).map(p=>`<path d="${p.motion.points.map((q,i)=>(i?'L':'M')+q.join(' ')).join(' ')}" class="map-route${mapSelection('patient',p.id)?' selected':''}" marker-end="url(#map-arrow)"/>`).join('');
  for(const [selector,html] of [['#map-status-bar',hospitalStats()],['#map-bed-mix',mapBedMix()],['#map-detail',MapUI.detailOpen?mapDetail():'']])replaceMapContent(selector,html);
  const picker=$('#map-patient-picker');if(picker){const options=mapPatientOptions();if(picker.innerHTML!==options)picker.innerHTML=options;picker.value=MapUI.detailOpen&&MapUI.selected?.kind==='patient'?MapUI.selected.id:'';}
  const filter=$('#map-filter');if(filter)filter.value=MapUI.filter;
  const drawer=$('#map-drawer');if(drawer)drawer.hidden=!MapUI.detailOpen;
  updateMapStatus();updateMapZoom();applyMapFilter();updateMapPositions();startHospitalAnimation();
}
function replaceMapContent(selector,html){
  const n=$(selector);if(!n||n.innerHTML===html)return;
  const active=document.activeElement,focused=n.contains(active),key=focused?{...active.dataset}:null;
  n.innerHTML=html;
  if(key){const next=[...n.querySelectorAll('button')].find(b=>Object.entries(key).every(([k,v])=>b.dataset[k]===v));(next||$('#map-viewport')).focus({preventScroll:true});}
}
function updateMapZoom(){
  const svg=$('#hospital-svg'),viewport=$('#map-viewport');if(!svg||!viewport)return;
  const drawer=$('#map-drawer');if(drawer){drawer.style.top=(viewport.offsetTop+8)+'px';drawer.style.bottom=(($('.map-legend')?.clientHeight||36)+8)+'px';}
  const compact=(viewport.clientWidth||1050)<650;
  if(MapUI.compact!==compact){MapUI.compact=compact;MapUI.fit=!compact;if(compact)MapUI.zoom=1;}
  const base=Math.max(1050,viewport.clientWidth||1050);
  if(MapUI.fit)MapUI.zoom=Math.max(.25,Math.min(1,(viewport.clientWidth||base)/base,(viewport.clientHeight||720)/(base/S.scene.width*S.scene.height)));
  svg.style.width=(base*MapUI.zoom)+'px';svg.style.minWidth='0';svg.classList.toggle('map-overview',base*MapUI.zoom/S.scene.width<.65);
  $('#map-zoom-label').textContent=Math.round(MapUI.zoom*100)+'%';
  $('#map-motion').setAttribute('aria-pressed',String(MapUI.motion));$('#map-motion').textContent=MapUI.motion?'이동 효과 켜짐':'이동 효과 꺼짐';
  const expanded=!!document.fullscreenElement||!!$('.workspace')?.classList.contains('map-expanded'),button=$('#map-fullscreen');if(button){button.setAttribute('aria-pressed',String(expanded));button.innerHTML=(expanded?icon('collapse'):icon('expand'))+'<span>'+(expanded?'확대 종료':'화면 가득 보기')+'</span>';button.setAttribute('aria-label',expanded?'화면 가득 보기 종료':'화면 가득 보기');}
}
function centerMapPoint(point,smooth=true){
  const svg=$('#hospital-svg'),viewport=$('#map-viewport');if(!svg||!viewport)return;
  const scale=svg.clientWidth/S.scene.width,x=point[0]*scale-viewport.clientWidth/2,y=point[1]*scale-viewport.clientHeight/2;
  if(!smooth){viewport.scrollLeft=x;viewport.scrollTop=y;}else viewport.scrollTo({left:x,top:y,behavior:MapUI.motion?'smooth':'instant'});
}
function applyMapFilter(){
  const query=MapUI.query.trim().toLowerCase();let matches=0;
  for(const entry of MapUI.nodes.values()){
    const item=entry.item,p=entry.kind==='patient'?S.patients.find(p=>p.id===item.id):null;
    const filter=MapUI.filter==='all'||(MapUI.filter==='moving'?!!item.motion:MapUI.filter==='high'?p?.prediction.need_score>=70:MapUI.filter==='surgery'?p?.phase==='OR':MapUI.filter==='ward'?p?.phase==='WARD':MapUI.filter==='discharging'?p?.workflow?.stage==='hospital_discharge_handoff'||p?.phase==='DISCHARGED':true);
    const search=!query||[item.id,p?.name,p?.surgery,p?.location,item.name,item.patient_id].some(v=>String(v||'').toLowerCase().includes(query));
    entry.node.classList.toggle('dimmed',!filter||!search);if(filter&&search)matches++;
  }
  const selection=MapUI.selected;
  if(selection?.kind==='patient'&&!S.patients.some(p=>p.id===selection.id))MapUI.selected=null;
  return matches;
}
function hospitalAction(action,button){
  if(action==='map-close-detail'){closeMapDetail();return;}
  if(action==='map-fullscreen')return toggleMapExpanded();
  if(action==='map-zone'){
    const z=S.scene.zones.find(z=>z.id===button.dataset.zone);if(!z)return;
    MapUI.fit=false;MapUI.zoom=1;updateMapZoom();centerMapPoint([z.x+z.width/2,z.y+Math.min(z.height/2,260)]);return;
  }
  if(action==='map-select'){MapUI.detailOpen=true;MapUI.selected={kind:button.dataset.kind,id:button.dataset.id};if(MapUI.selected.kind==='patient')U.selected=MapUI.selected.id;renderHospital();if(MapUI.follow&&MapUI.selected.kind==='patient'){const e=MapUI.nodes.get('patient:'+MapUI.selected.id);if(e)centerMapPoint(e.point);}return;}
  if(action==='map-motion'){MapUI.motion=!MapUI.motion;try{localStorage.setItem('pericare-map-motion',MapUI.motion?'on':'off');}catch{}renderHospital();return;}
  if(action==='map-focus-active'){
    const p=S.scene.patients.find(p=>p.motion)||[...S.scene.patients].sort((a,b)=>(b.risk||0)-(a.risk||0))[0];
    if(p){MapUI.detailOpen=true;MapUI.selected={kind:'patient',id:p.id};renderHospital();centerMapPoint(MapUI.nodes.get('patient:'+p.id)?.point||[p.home.x,p.home.y]);}return;
  }
  if(action==='map-fit'){MapUI.fit=true;updateMapZoom();$('#map-viewport')?.scrollTo({left:0,top:0,behavior:'instant'});return;}
  if(action==='map-zoom-in'||action==='map-zoom-out'){MapUI.fit=false;MapUI.zoom=Math.max(.25,Math.min(2,MapUI.zoom+(action==='map-zoom-in' ? .25 : -.25)));updateMapZoom();return;}
}

function mapPatientOptions(){return '<option value="">환자를 선택하세요</option>'+S.patients.filter(p=>S.scene.patients.some(q=>q.id===p.id)).map(p=>`<option value="${esc(p.id)}">${mapCaption(p.id)===shortId(p.id)?esc(p.id):esc(mapCaption(p.id))+' · '+esc(p.id)} · ${esc(p.surgery)}</option>`).join('');}
function bindMapPan(){
  const viewport=$('#map-viewport');if(!viewport)return;
  MapUI.observer?.disconnect();if(typeof ResizeObserver!=='undefined'){MapUI.observer=new ResizeObserver(()=>{if(S&&U.view==='hospital')updateMapZoom();});MapUI.observer.observe(viewport);}
  let drag=null,dragged=false;
  viewport.addEventListener('pointerdown',e=>{if(e.button!==0||e.pointerType==='touch')return;drag={x:e.clientX,y:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop,id:e.pointerId};dragged=false;});
  viewport.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>8){dragged=true;viewport.setPointerCapture(e.pointerId);viewport.classList.add('dragging');viewport.scrollLeft=drag.left-dx;viewport.scrollTop=drag.top-dy;}});
  const end=()=>{if(drag){if(viewport.hasPointerCapture?.(drag.id))viewport.releasePointerCapture(drag.id);drag=null;viewport.classList.remove('dragging');}};
  viewport.addEventListener('pointerup',end);viewport.addEventListener('pointercancel',end);
  viewport.addEventListener('click',e=>{if(dragged){e.preventDefault();e.stopPropagation();dragged=false;}},true);
}
document.addEventListener('input',e=>{if(e.target.id==='map-search'){MapUI.query=e.target.value;const n=applyMapFilter();$('#announcement').textContent=`지도에서 ${n}개 항목을 강조합니다.`;}});
document.addEventListener('change',e=>{if(e.target.id==='map-patient-picker'&&e.target.value){MapUI.detailOpen=true;MapUI.selected={kind:'patient',id:e.target.value};U.selected=e.target.value;renderHospital();}if(e.target.id==='map-zone-picker'&&e.target.value){hospitalAction('map-zone',{dataset:{zone:e.target.value}});e.target.value='';$('#map-options').open=false;}if(e.target.id==='map-filter'){MapUI.filter=e.target.value;applyMapFilter();}if(e.target.id==='map-follow'){MapUI.follow=e.target.checked;if(MapUI.follow&&MapUI.selected?.kind==='patient'){const n=MapUI.nodes.get('patient:'+MapUI.selected.id);if(n)centerMapPoint(n.point);}}});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&U.view==='hospital'){if(MapUI.detailOpen){closeMapDetail();}else if($('.workspace')?.classList.contains('map-expanded'))exitMapExpanded();$('#map-options').open=false;}

  if((e.key==='Enter'||e.key===' ')&&e.target.dataset?.action==='map-select'&&e.target.matches?.('g[data-action="map-select"]')){e.preventDefault();hospitalAction('map-select',e.target);}
  if(e.target.id==='map-viewport'&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const v=e.target;v.scrollBy({left:e.key==='ArrowRight'?100:e.key==='ArrowLeft'?-100:0,top:e.key==='ArrowDown'?100:e.key==='ArrowUp'?-100:0,behavior:MapUI.motion?'smooth':'instant'});}
});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopHospitalAnimation();else if(U.view==='hospital'&&S){MapUI.anchor=mapNow();refresh(true);}});

function closeMapDetail(){
  MapUI.detailOpen=false;const picker=$('#map-patient-picker');if(picker)picker.value='';const drawer=$('#map-drawer'),focused=drawer?.contains(document.activeElement);if(drawer)drawer.hidden=true;
  if(focused){const target=MapUI.selected?MapUI.nodes.get(MapUI.selected.kind+':'+MapUI.selected.id)?.node:null;(target||$('#map-patient-picker')||$('#map-viewport'))?.focus({preventScroll:true});}
}
async function toggleMapExpanded(){
  const workspace=$('.workspace');if(!workspace)return;
  if(document.fullscreenElement||workspace.classList.contains('map-expanded'))return exitMapExpanded();
  try{if(workspace.requestFullscreen)await workspace.requestFullscreen();else workspace.classList.add('map-expanded');}catch{workspace.classList.add('map-expanded');}
  requestAnimationFrame(()=>{MapUI.fit=($('#map-viewport')?.clientWidth||1050)>=650;if(!MapUI.fit)MapUI.zoom=1;updateMapZoom();$('#map-viewport')?.scrollTo({left:0,top:0,behavior:'instant'});});
}
async function exitMapExpanded(){
  const workspace=$('.workspace');workspace?.classList.remove('map-expanded');
  if(document.fullscreenElement&&document.exitFullscreen){try{await document.exitFullscreen();}catch{}}
  if(U.view==='hospital')requestAnimationFrame(()=>{updateMapZoom();$('#map-fullscreen')?.focus({preventScroll:true});});
}
document.addEventListener('fullscreenchange',()=>{if(S&&U.view==='hospital')requestAnimationFrame(updateMapZoom);});

function resetMapSelection(){
  MapUI.selected=null;MapUI.detailOpen=false;MapUI.filter='all';MapUI.query='';MapUI.compact=null;
  MapUI.labels.patient.clear();MapUI.labels.bed.clear();
  const options=$('#map-options');if(options)options.open=false;
}
