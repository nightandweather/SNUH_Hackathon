"use strict";
const $=(q,root=document)=>root.querySelector(q);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=0)=>Number.isFinite(v)?new Intl.NumberFormat('ko-KR',{maximumFractionDigits:d}).format(v):'—';
const pct=v=>Number.isFinite(v)?`${Math.round(v*100)}%`:'—';
const iconPaths={dashboard:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',activity:'<path d="M2 12h4l3-8 5 16 3-8h5"/>',bed:'<path d="M3 18v3m18-3v3M3 5v13h18V9H9v9M3 8h6m-6 6h18"/>',arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',expand:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',collapse:'<path d="M3 8h5V3m8 0v5h5M8 21v-5H3m13 5v-5h5"/>',alert:'<path d="m12 3 10 17H2zM12 9v4m0 3v1"/>',shield:'<path d="M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>'};
const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name]||iconPaths.activity}</svg>`;
const nav=[['hospital','dashboard','실시간 병원 지도'],['patients','activity','환자 위험·경과'],['beds','bed','ICU 병상 계획']];
const U={view:'hospital',selected:null,query:'',phaseFilter:'active',chart:'risk',inputsOpen:false,actor:'시뮬레이션 운영자',toastTimer:null};
let S=null,fetching=false,lastRendered=-1,navSignature='',lastAnnouncement=0;
for(const [key,attr] of [['pericare-theme','theme'],['pericare-text','text']]){try{const value=localStorage.getItem(key);if(value)document.documentElement.dataset[attr]=value;}catch{}}
function time(minute,long=false){
  if(!S||!Number.isFinite(minute))return '—';
  const d=new Date(new Date(S.base_time).getTime()+minute*60000),t=d.toLocaleTimeString('en-GB',{timeZone:'Asia/Seoul',hourCycle:'h23',hour:'2-digit',minute:'2-digit'});
  const differentDay=d.toLocaleDateString('en-CA',{timeZone:'Asia/Seoul'})!==new Date(S.clock).toLocaleDateString('en-CA',{timeZone:'Asia/Seoul'});return (long||differentDay)?`${d.toLocaleDateString('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit'}).replace(/\.$/,'')} ${t}`:t;
}
function toast(message,error=false){const t=$('#toast');t.textContent=message;t.className=error?'visible error':'visible';clearTimeout(U.toastTimer);U.toastTimer=setTimeout(()=>t.className='',4000);}
function chip(label,color=''){return `<span class="chip ${color}">${esc(label)}</span>`;}
const riskClass=v=>!Number.isFinite(v)?'unavailable':v>=70?'high':v>=40?'mid':'low';
const riskColor=v=>!Number.isFinite(v)?'var(--muted)':v>=70?'var(--red)':v>=40?'var(--amber)':'var(--teal)';
const riskLabel=v=>!Number.isFinite(v)?'예측 없음':v>=70?'▲ 높음':v>=40?'◇ 주의':'○ 낮음';
const validPrediction=p=>!['unavailable','pending','completed'].includes(p.prediction.mode)&&Number.isFinite(p.prediction.need_score);
const autoEnabled=()=>Boolean(S?.automation?.enabled);
const roleName=key=>S?.automation?.roles?.[key]?.name||'진료팀';
const patient=(pid=U.selected)=>S?.patients.find(p=>p.id===pid)||S?.patients[0];
const activeReservation=p=>S.reservations.find(r=>r.patient_id===p.id&&['confirmed','occupied'].includes(r.status));
function head(eyebrow,title,description,actions=''){return `<div class="page-header"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions?`<div class="page-header-actions">${actions}</div>`:''}</div>`;}
function empty(title,detail=''){return `<div class="empty">${esc(title)}${detail?`<p>${esc(detail)}</p>`:''}</div>`;}
function notice(text,color='gray',name='shield'){return `<div class="notice ${color}">${icon(name)}<span>${text}</span></div>`;}
function recLabel(r){return {BOOK_NOW:'예약 진행 시점',PLAN:'예약 시점 대기',UPDATE:'예약 조정',KEEP:'예약 유지',WAIT:'병상 확보 대기',BLOCKED:'관측 확인',REVIEW_RELEASE:'회복 재평가',ADMITTED:'ICU 재실',NO_ICU:'회복 관찰',MONITOR:'관측 지속',COMPLETED:'입원 경과 종료'}[r.status]||r.status;}
function workflowPill(p){const w=p.workflow||{},held=['quality_hold','capacity_wait'].includes(w.stage);return chip(w.label||recLabel(p.recommendation),held?'amber':'green');}
function issue(p){if(['DISCHARGED','DECEASED','TRANSFERRED'].includes(p.phase))return '';const f=p.prediction.features,w=p.workflow||{};return p.prediction.mode==='unavailable'?'예측 모델 연결 확인 · 자동 예약 보류':w.stage==='quality_hold'?`${f.quality_issues.join(' · ')||'관측 재확인'} · 자동 이동 보류`:p.phase!=='PREOP'&&f.quality_issues.length?`${f.quality_issues.join(' · ')} · 관측 품질 확인`:w.stage==='capacity_wait'?'조건에 맞는 병상 확보 대기':'';}
function clinicalAlerts(){
  const ps=S.patients.filter(p=>issue(p));if(!ps.length)return '';
  return `<div class="core-alerts" role="region" aria-label="현재 확인이 필요한 환자"><b>${icon('alert')} 확인 필요 ${ps.length}명</b>${ps.slice(0,2).map(p=>`<button data-action="inspect" data-patient="${esc(p.id)}">${esc(p.id)} · ${esc(issue(p))}</button>`).join('')}${ps.length>2?`<button data-view="patients">전체 환자에서 확인 ↗</button>`:''}</div>`;
}
async function refresh(force=false){
  if(fetching)return;fetching=true;
  try{
    const response=await fetch('/api/state',{cache:'no-store'});if(!response.ok)throw Error(`서버 응답 ${response.status}`);
    S=await response.json();
    if(!S.patients.some(p=>p.id===U.selected))U.selected=[...S.patients].sort((a,b)=>(b.prediction.need_score??-1)-(a.prediction.need_score??-1))[0]?.id;
    setHospitalConnection(true);$('#connection').className='connection';$('#connection').innerHTML='<i></i> 연결됨';updateHeader();
    if(force||(S.revision!==lastRendered&&!$('#modal').open))render();
    const event=S.automation?.log?.filter(e=>['admission','discharge','quality','ward_arrival'].includes(e.kind)).at(-1);
    if(event&&event.id>lastAnnouncement){if(lastAnnouncement)$('#announcement').textContent=`${time(event.minute)} ${event.actor}, ${event.patient_id}, ${event.title}`;lastAnnouncement=event.id;}
  }catch(e){setHospitalConnection(false);$('#connection').className='connection off';$('#connection').innerHTML='<i></i> 연결 끊김';if(!S||lastRendered<0)$('#content').innerHTML=empty('화면을 불러오지 못했습니다',`서버 실행 상태를 확인하고 새로고침하세요. ${e.message}`);console.error(e);}
  finally{fetching=false;}
}
async function post(path,body={}){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),data=await response.json();if(!response.ok){const e=Error(data.error||`오류 ${response.status}`);e.status=response.status;throw e;}return data;}
async function act(action,body={},message=''){
  if(U.busy)return null;U.busy=true;
  if(action==='advance'){$('#running-status').textContent='반영 중';document.querySelectorAll('[data-action="advance"],#play').forEach(b=>b.disabled=true);}
  try{
    let result;
    try{result=await post(`/api/actions/${action}`,{...body,expected_revision:body.expected_revision??S.revision,actor:U.actor});}
    catch(e){
      // Retry clock intent once after a rejected concurrent tick. Clinical writes never retry.
      if(e.status!==409||!['play','advance'].includes(action)||body.expected_revision!==undefined)throw e;
      const latest=await fetch('/api/state',{cache:'no-store'});if(!latest.ok)throw e;S=await latest.json();
      result=await post(`/api/actions/${action}`,{...body,expected_revision:S.revision,actor:U.actor});
    }
    await refresh(true);if(message)toast(message);return result;
  }catch(e){if(e.status===409)$('#modal').close();toast(e.message,true);await refresh(true);return null;}
  finally{U.busy=false;if(S)updateHeader();}
}
function updateHeader(){
  document.documentElement.dataset.screen=U.view;
  const d=new Date(S.clock),t=d.toLocaleTimeString('en-GB',{timeZone:'Asia/Seoul',hourCycle:'h23',hour:'2-digit',minute:'2-digit',second:'2-digit'});$('#clock').innerHTML=`${t.slice(0,5)}<span>${t.slice(5)}</span>`;
  $('#clock-date').textContent=d.toLocaleDateString('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit'})+' · KST';
  $('#play').textContent=S.running?'Ⅱ 일시정지':'▶ 시뮬레이션 시작';$('#running-status').textContent=U.busy?'반영 중':S.running?'진행 중':'일시정지';$('#speed').value=S.speed;const h=S.hospital;$('#operation-day').textContent=`운영 ${h.day}일차 / ${h.days}일`;$('#operation-progress').max=h.horizon_minutes;$('#operation-progress').value=S.minute;$('#operation-remaining').textContent=h.ended?'운영 종료':`남은 ${fmt((h.horizon_minutes-S.minute)/1440,1)}일`;$('#play').disabled=h.ended||U.busy;document.querySelectorAll('[data-action=advance]').forEach(b=>b.disabled=h.ended||U.busy); 
  $('#care-mode').textContent=autoEnabled()?'가상 의료진 자동 진행':S.hospital.replay_mode==='recorded_events'?'실제 기록 재생':'관측 기록 보기';
  const unavailable=S.patients.some(p=>p.prediction.mode==='unavailable');$('#source-badge').textContent=unavailable?'예측 연결 확인':`${S.source==='synthetic'?'합성 데이터':'입력 데이터'} · ${S.model_backend==='demo'?'모의 예측':'외부 모델'}`;
  $('#footer-status').textContent=autoEnabled()?'가상 의료진이 입원·예약·이송·전실·퇴원을 진행합니다.':'관측 기록만 재생합니다. 실제 환자의 이동·퇴원은 생성하지 않습니다.';
  $('#view-label').textContent=nav.find(n=>n[0]===U.view)?.[2]||'';
  if(navSignature!==U.view){const focused=document.activeElement?.closest?.('.nav-item')?.dataset.view;$('#navigation').innerHTML=nav.map(([id,i,label])=>`<button class="nav-item ${U.view===id?'active':''}" data-view="${id}" ${U.view===id?'aria-current="page"':''}>${icon(i)}<span>${label}</span></button>`).join('');navSignature=U.view;if(focused)$('#navigation').querySelector(`[data-view="${focused}"]`)?.focus({preventScroll:true});}
  $('#text-size').setAttribute('aria-pressed',String(document.documentElement.dataset.text==='large'));$('#text-size').textContent=document.documentElement.dataset.text==='large'?'기본 글씨':'큰 글씨';
}
function navigate(view,pid){const changed=view!==U.view||(view==='patients'&&pid&&pid!==U.selected);if(!nav.some(n=>n[0]===view))view='hospital';if(view!=='hospital'&&typeof exitMapExpanded==='function')exitMapExpanded();U.view=view;if(pid)U.selected=pid;location.hash=view+(view==='patients'?'/'+encodeURIComponent(U.selected||''):'');updateHeader();render();if(changed)window.scrollTo({top:0,behavior:'instant'});}
function render(){
  if(!S)return;if(U.view==='hospital'){renderHospital();lastRendered=S.revision;return;}stopHospitalAnimation();
  const inputs=$('#clinical-inputs');if(inputs)U.inputsOpen=inputs.open;
  const root=$('#content'),active=document.activeElement,focused=active&&root.contains(active),key=focused?{id:active.id,data:{...active.dataset},start:active.selectionStart,end:active.selectionEnd}:null;
  const scroll=window.scrollY,saved=[...root.querySelectorAll('.patient-directory-list,.gantt-wrap')].map(n=>({cls:n.className,left:n.scrollLeft,top:n.scrollTop}));
  root.innerHTML=U.view==='beds'?bedView():patientView();lastRendered=S.revision;
  for(const v of saved){const n=[...root.querySelectorAll('.patient-directory-list,.gantt-wrap')].find(n=>n.className===v.cls);if(n){n.scrollLeft=v.left;n.scrollTop=v.top;}}
  if(key){const next=key.id?document.getElementById(key.id):[...root.querySelectorAll('[data-action],[data-view]')].find(n=>Object.entries(key.data).every(([k,v])=>n.dataset[k]===v));(next||root).focus({preventScroll:true});if(next&&typeof next.setSelectionRange==='function'&&Number.isFinite(key.start))next.setSelectionRange(key.start,key.end);}
  if(Number.isFinite(scroll))window.scrollTo({top:scroll,behavior:'instant'});
}
function trend(p){const h=p.history.filter(h=>Number.isFinite(h.need_score)),last=h.at(-1),past=[...h].reverse().find(h=>h.minute<=(last?.minute??0)-15);if(!last||!past)return '변화 관찰 중';const d=last.need_score-past.need_score;return d===0?'최근 15분 유지':`최근 15분 ${d>0?'↑ 상승':'↓ 감소'} ${Math.abs(d)}점`;}
function predictionCards(p){if(['DISCHARGED','DECEASED','TRANSFERRED'].includes(p.phase))return `<div class="duration-grid"><div class="duration-card"><span>관측된 병원 체류</span><strong>${fmt((p.discharge_minute-p.admission_minute)/1440,1)}<small>일</small></strong><p>입원부터 실제 종료까지</p></div><div class="duration-card"><span>병원 경과 종료</span><strong>${esc(p.phase_label)}</strong><p>${time(p.discharge_minute,true)}</p></div><div class="duration-card"><span>현재 병상 점유</span><strong>종료</strong><p>예측 기간 만료로 퇴원시키지 않습니다</p></div></div>`;const pr=p.prediction,valid=validPrediction(p),mode=pr.mode==='demo'?'모의 범위':'모델 범위';return `<div class="duration-grid">${[['집중관리 지속 예측',pr.intensive_hours,pr.intensive_hours_upper,'시간','집중관리가 필요할 경우'],['ICU 재실 예측',pr.icu_los_hours,pr.icu_los_upper,'시간',p.phase==='ICU'?'현재 시점의 잔여 예측':'ICU를 이용할 경우'],['잔여 입원기간',pr.hospital_los_days,pr.hospital_los_upper,'일','현재 시점 이후']].map(([label,v,upper,unit,sub])=>`<div class="duration-card"><span>${label}</span><strong>${valid?fmt(v,1):'—'}<small>${unit}</small></strong><p>${sub}</p><small>${mode} ${valid?fmt(v,1):'—'}–${valid?fmt(upper,1):'—'} ${unit}</small></div>`).join('')}</div>`;}
function bookingSteps(p){
  const r=p.recommendation,w=p.workflow||{},reservation=activeReservation(p),icu=p.phase==='ICU';
  if(['DISCHARGED','DECEASED','TRANSFERRED'].includes(p.phase))return `<div class="care-next"><b>${esc(p.phase_label)} · ${time(p.discharge_minute,true)}</b><p>관측된 입원 경과를 보관합니다. 현재 병상 점유·예약 대상에서는 제외했습니다.</p></div>`;
  if(p.phase==='ICU'&&!reservation)return `<div class="care-next"><b>${esc(w.label||'ICU 재실 관찰')}</b><p>${esc(p.location)} · ${esc(w.detail||'실제 재실 상태에서 회복 경과를 평가합니다.')}</p></div>`;
  if(w.route==='ward'||p.phase==='WARD')return `<div class="care-next"><b>${esc(w.label||'일반병동 회복 관찰')}</b><p>${esc(w.detail||'현재 회복 경과를 관찰합니다.')}</p>${Number.isFinite(w.ward_due)?`<span>병동 인계 예정 ${time(w.ward_due)}</span>`:''}</div>`;
  if(!reservation&&!p.planned_icu&&!['BOOK_NOW','PLAN','UPDATE','KEEP','WAIT','BLOCKED','REVIEW_RELEASE'].includes(r.status))return `<div class="care-next"><b>${esc(w.label||'수술·회복 경과 관찰')}</b><p>${esc(w.detail||r.reason)}</p></div>`;
  const prepared=['bed_ready','transporting','icu_monitoring'].includes(w.stage),moving=w.stage==='transporting';
  const arrival=Number.isFinite(w.transfer_due)?w.transfer_due:reservation?.start??r.start;
  const initial=reservation?.initial_booking_forecast,due=reservation?initial?.recommended_due_minute:r.due;
  const steps=[[reservation?'예약 당시 추천':'추천 예약',time(due),reservation?(initial?'당시 예측 기준':'기존 추천시각 기록 없음'):'현재 예측 기준',!!reservation&&Number.isFinite(due)],['예약 확정',reservation?time(reservation.created_minute):'대기',reservation?.bed_id||r.bed_id||'병상 확보 대기',!!reservation||icu],['준비 완료',prepared?'완료':Number.isFinite(w.prep_due)?time(w.prep_due):'대기',prepared?'장비·인수 준비 확인':w.stage==='preparing'?'간호팀 준비 중':'예약 후 준비',prepared||icu],['ICU 입실',icu?'입실 완료':time(arrival),icu?p.location:moving?'이송·인계 중':'예상 시각',icu]];
  return `<ol class="booking-steps" aria-label="예약과 입실 진행">${steps.map(([label,v,sub,done],i)=>`<li class="${done?'done':''}"><span class="step-dot">${done?'✓':i+1}</span><span>${label}</span><b>${esc(v)}</b><small>${esc(sub)}</small></li>`).join('')}</ol>`;
}
function patientEvents(p,limit=5){const log=(S.automation?.log||[]).filter(e=>e.patient_id===p.id).slice(-limit).reverse();return log.length?`<ol class="clinical-events">${log.map(e=>`<li><time>${time(e.minute)}</time><div><b>${esc(e.title)}</b><p>${esc(e.actor)} · ${esc(e.detail)}</p></div></li>`).join('')}</ol>`:empty('의료진 진행 기록을 기다립니다','시뮬레이션을 시작하면 실제 수행한 판단과 인계가 표시됩니다.');}
function patientView(){
  const p=patient();if(!p)return empty('환자 데이터가 없습니다');const pr=p.prediction,v=pr.features.latest,w=p.workflow||{};
  const visible=[...S.patients].sort((a,b)=>(b.prediction.need_score??-1)-(a.prediction.need_score??-1)).filter(q=>(U.phaseFilter==='all'||(U.phaseFilter==='active'?!['DISCHARGED','DECEASED','TRANSFERRED'].includes(q.phase):q.phase===U.phaseFilter))&&(!U.query||[q.id,q.surgery,q.name,q.department].some(v=>String(v).toLowerCase().includes(U.query.toLowerCase()))));
  return head('환자별 집중관리 예측','환자 위험·회복 경과','집중관리 필요성과 기간을 확인하고, 병상 준비로 이어지는 과정을 봅니다.')+`<div class="patient-layout core-patient-layout"><aside class="panel patient-directory"><div class="directory-tools"><label class="search">${icon('search')}<input id="patient-search" type="search" placeholder="환자·수술 검색" value="${esc(U.query)}" aria-label="환자 검색"></label><select id="phase-filter" aria-label="환자 진료 단계">${[['active','현재 입원'],['all','전체 이력'],['DISCHARGED','병원 퇴원'],['ADMITTING','신규 입원'],['OR','수술 중'],['PACU','회복실'],['ICU','ICU 재실'],['WARD','일반병동'],['PREOP','수술 전']].map(([v,t])=>`<option value="${v}" ${U.phaseFilter===v?'selected':''}>${t}</option>`).join('')}</select><span>${visible.length}명 · 위험도 순</span></div><div class="patient-directory-list">${visible.map(q=>`<button class="${q.id===p.id?'selected':''}" data-action="select-patient" data-patient="${esc(q.id)}" aria-pressed="${q.id===p.id}"><span class="directory-top"><b>${esc(q.id)}</b><strong style="color:${riskColor(q.prediction.need_score)}">${validPrediction(q)?fmt(q.prediction.need_score):'—'}</strong></span><small>${esc(q.surgery)}</small><small>${esc(q.phase_label)} · ${esc(q.location)}</small>${issue(q)?'<small class="attention-label">! 확인 필요</small>':''}</button>`).join('')||empty('검색 결과가 없습니다')}</div></aside><div class="patient-main">
  <section class="panel"><div class="patient-hero"><div><span class="eyebrow">${esc(p.id)}</span><h2>${esc(p.surgery)}</h2><p>${p.age}세 · ${p.sex==='M'?'남':p.sex==='F'?'여':esc(p.sex)} · ${esc(p.department)} · ASA ${p.asa}</p><div class="hero-chips">${chip(p.phase_label,'blue')}${chip(p.location)}${p.planned_icu?chip('예정 ICU','purple'):''}${p.emergency?chip('응급','red'):''}</div></div><button class="button" data-action="locate-patient" data-patient="${esc(p.id)}">지도에서 보기 ↗</button></div><div class="patient-risk-row"><div><span>동적 집중관리 위험</span><strong style="color:${riskColor(pr.need_score)}">${validPrediction(p)?fmt(pr.need_score):'—'}<small>/100</small></strong><p>${riskLabel(pr.need_score)} · ${trend(p)}</p></div><div><span>집중관리 필요 예측</span><b>${pct(pr.need_probability)}</b><p>지원 필요성</p></div><div><span>ICU 이용 예측</span><b>${pct(pr.icu_probability)}</b><p>${p.phase==='ICU'?'현재 실제 재실':p.planned_icu?'예정 입실 반영':'이용 가능성'}</p></div></div>${issue(p)?notice(esc(issue(p)),'amber','alert'):''}</section>
  ${hospitalJourney(p)}${predictionCards(p)}
  <section class="panel"><div class="panel-heading"><div><h2>위험·회복 추세</h2><p>최근 관측 ${pr.features.observation_age_minutes===null?'없음':pr.features.observation_age_minutes+'분 전'} · ${time(v.minute)}</p></div><div class="segmented" role="group" aria-label="경과 그래프 선택">${[['risk','위험'],['vitals','순환'],['oxygen','산소화']].map(([v,t])=>`<button data-action="chart" data-chart="${v}" aria-pressed="${U.chart===v}" class="${U.chart===v?'active':''}">${t}</button>`).join('')}</div></div><div class="chart-wrap">${trajectoryChart(p)}</div><div class="core-vitals">${[['MAP',v.map,'mmHg'],['HR',v.hr,'bpm'],['SpO₂',v.spo2,'%'],['NE',v.norepi,'µg/kg/min']].map(([k,val,unit])=>`<div><span>${k}</span><b>${fmt(val,k==='NE'?3:1)}</b><small>${unit}</small></div>`).join('')}</div></section>
  <section class="panel"><div class="panel-heading"><div><h2>예약·준비·입실</h2><p>${esc(roleName(w.owner))} · ${esc(w.detail||p.recommendation.reason)}</p></div>${workflowPill(p)}</div><div class="panel-body">${bookingSteps(p)}</div></section>
  <section class="panel"><div class="panel-heading"><h2>의료진 판단·인계</h2><span class="muted">최근 5건</span></div><div class="panel-body">${patientEvents(p)}</div></section>
  <details id="clinical-inputs" class="panel clinical-inputs" ${U.inputsOpen?'open':''}><summary id="clinical-inputs-summary">예측에 사용된 병력·처치와 위험 요인</summary><div class="panel-body"><p><b>기저질환</b> ${esc(p.conditions.join(' · ')||'기록 없음')}</p><div class="input-history">${[...p.pre_admission,...p.treatments.slice(-4)].sort((a,b)=>b.minute-a.minute).slice(0,7).map(e=>`<p><time>${time(e.minute,e.minute<0)}</time> ${esc(e.label)} ${esc(e.dose??'')} ${esc(e.unit??'')}</p>`).join('')}</div><h3>주요 위험 요인 · ${pr.mode==='demo'?'모의 점수 기여':'모델 설명'}</h3>${pr.contributions.slice(0,4).map(c=>`<div class="factor-row"><span>${esc(c.label)}<small>${esc(c.detail)}</small></span><b style="color:${c.points<0?'var(--teal)':'var(--red)'}">${c.points>0?'+':''}${fmt(c.points,1)}</b></div>`).join('')||empty('사용 가능한 설명이 없습니다')}<p class="muted">${pr.mode==='demo'?'합성 데이터와 규칙 기반 시연 값입니다. 범위는 검증된 신뢰구간이 아닙니다.':'모델 범위와 기여도의 정의는 연결된 모델을 따릅니다.'}</p></div></details>
  </div></div>`;
}
function upcomingPlans(){return S.patients.filter(p=>['PREOP','OR','PACU'].includes(p.phase)&&(activeReservation(p)||p.planned_icu||['BOOK_NOW','PLAN','UPDATE','KEEP','WAIT','REVIEW_RELEASE'].includes(p.recommendation.status)||p.workflow?.route==='icu')).sort((a,b)=>{const priority=p=>['quality_hold','capacity_wait'].includes(p.workflow?.stage)?-10000:0;return priority(a)-priority(b)+(activeReservation(a)?.start??a.recommendation.start??Infinity)-(activeReservation(b)?.start??b.recommendation.start??Infinity);});}
function bedCard(b){
  const scene=S.scene.beds.find(x=>x.id===b.id),status=scene?.status||'available',reserved=b.reservations.filter(r=>r.status==='confirmed'),known=S.patients.find(p=>p.id===b.occupant_id);
  return `<button class="bed bed-${status} core-bed" data-action="locate-bed" data-bed="${esc(b.id)}" aria-label="${esc(b.id)} ${bedStatus({status})} 지도에서 보기"><span class="bed-top"><strong>${esc(b.id)}</strong>${chip(bedStatus({status}),status==='available'?'green':status==='cleaning'?'amber':status==='occupied'?'blue':'')}</span><span class="occupant">${b.occupant_id?esc(b.occupant_id):reserved.length?esc(reserved[0].patient_id):status==='closed'?'가동 중지':'입실 환자 없음'}</span><span class="bed-note">${b.occupant_id?(known?esc(known.surgery):'기존 비수술 환자'):status==='cleaning'?`청소 완료 ${time(b.available_minute)}`:reserved.length?`입실 예정 ${time(reserved[0].start)}`:status==='closed'?esc(b.closed_reason):'병상·장비 준비됨'}</span><span class="bed-capabilities">${b.capabilities.map(c=>`<span>${c==='ventilator'?'환기':c==='crrt'?'CRRT':esc(c)}</span>`).join('')}</span></button>`;
}
function gantt(){
  const start=S.minute,horizon=1440;
  const block=(a,b,label,cls)=>{const left=Math.max(0,a-start)/horizon*100,right=Math.min(horizon,b-start)/horizon*100;if(right<=left||left>=100)return '';return `<span class="gantt-block ${cls}" style="left:${left}%;width:${right-left}%" title="${esc(label)} · ${time(a,true)} → ${time(b,true)}">${esc(label)}</span>`;};
  return `<div class="gantt-wrap"><div class="gantt core-gantt"><div class="gantt-axis"><span>병상</span><div class="gantt-ticks">${[0,240,480,720,960,1200,1440].map(m=>`<span>${time(start+m)}</span>`).join('')}</div></div>${S.beds.map(b=>`<div class="gantt-row"><button data-action="locate-bed" data-bed="${esc(b.id)}" title="${esc(b.id)}" aria-label="${esc(b.id)} 지도에서 보기">${esc(mapCaption(b.id,'bed'))}</button><div class="gantt-track">${!b.enabled?block(start,start+horizon,'가동 중지','closed'):b.occupant_id?block(start,start+horizon,`${b.occupant_id} · 실제 퇴실 전까지 점유`,'actual-occupied'):b.available_minute>start?block(start,b.available_minute,'청소·준비','cleaning'):''}${b.reservations.filter(r=>r.status==='confirmed').map(r=>block(r.start,r.end,r.patient_id,'reservation')).join('')}${b.occupant_id&&b.availability_forecast_known!==false&&b.available_minute>start&&b.available_minute<start+horizon?`<span class="forecast-marker" style="left:${(b.available_minute-start)/horizon*100}%" title="청소 포함 가용 예상 ${time(b.available_minute)} · 실제 퇴실 미확인"><span>가용 예상</span></span>`:''}${b.occupant_id&&b.availability_forecast_known!==false&&b.available_minute<=start?'<span class="forecast-overdue">가용 예상 경과 · 재실 유지</span>':b.occupant_id&&b.availability_forecast_known===false?'<span class="forecast-overdue">퇴실 시각 미확인 · 재실 유지</span>':''}</div></div>`).join('')}</div></div>`;
}
function bedView(){
  const plans=upcomingPlans(),confirmed=S.reservations.filter(r=>r.status==='confirmed'),cleaning=S.scene.beds.filter(b=>b.status==='cleaning').length;
  return head('집중치료 자원 운영','ICU 병상 계획','확정 예약과 실제 점유를 구분하고, 의료진의 준비와 이송을 확인합니다.')+clinicalAlerts()+`<div class="capacity-strip"><div><span>현재 ICU 재실</span><strong>${S.summary.occupied_beds}<small> / ${S.summary.enabled_beds} 가동</small></strong></div><div><span>예약 후 입실 대기</span><strong>${confirmed.length}<small>명</small></strong></div><div><span>현재 빈 병상</span><strong>${S.summary.available_beds}<small>개</small></strong><p>예약 병상 포함 · 청소 중 ${cleaning}개 제외</p></div></div>
  <section class="panel"><div class="panel-heading"><div><h2>예약·입실 진행</h2><p>추천은 예측값이며, 확정·준비·입실은 수행한 기록입니다.</p></div>${chip(autoEnabled()?'의료진이 자동 진행':'관측 기록 보기','green')}</div><div class="table-scroll"><table class="booking-table"><thead><tr><th>환자·수술</th><th>집중관리 / ICU</th><th>추천 예약 / 확정</th><th>준비 완료 / 입실</th><th>병상·진행</th></tr></thead><tbody>${plans.map(p=>{const r=p.recommendation,w=p.workflow||{},res=activeReservation(p);return `<tr><td><button class="patient-link" data-action="inspect" data-patient="${esc(p.id)}">${esc(p.id)} ↗</button><span class="cell-secondary">${esc(p.surgery)}</span></td><td><b>${fmt(p.prediction.intensive_hours,1)}h / ${fmt(p.prediction.icu_los_hours,1)}h</b><span class="cell-secondary">ICU 이용 ${pct(p.prediction.icu_probability)}</span></td><td><b>${res?'당시 추천':'추천'} ${time(res?res.initial_booking_forecast?.recommended_due_minute:r.due)}</b><span class="cell-secondary">${res?'확정 '+time(res.created_minute):'확정 대기'}</span></td><td><b>${['bed_ready','transporting'].includes(w.stage)?'준비 완료':Number.isFinite(w.prep_due)?'준비 '+time(w.prep_due):'준비 대기'}</b><span class="cell-secondary">입실 ${time(w.transfer_due??res?.start??r.start)} · 예상</span></td><td><b>${esc(res?.bed_id||r.bed_id||'확보 대기')}</b><span class="cell-secondary">${workflowPill(p)}</span></td></tr>`;}).join('')||`<tr><td colspan="5">${empty('새로운 ICU 입실 계획이 없습니다','현재 환자들의 회복 경과를 관찰합니다.')}</td></tr>`}</tbody></table></div></section>
  <section class="panel"><div class="panel-heading"><div><h2>병동별 실제 상태</h2><p>병상 선택 → 지도에서 위치와 담당 환자 확인</p></div></div><div class="panel-body">${['SICU','CCU'].map(unit=>`<div class="unit-block"><div class="unit-heading"><h3>${unit==='SICU'?'외과계 ICU':'심장계 ICU'}</h3><small>${S.beds.filter(b=>b.unit===unit&&b.enabled).length}개 가동</small></div><div class="bed-grid">${S.beds.filter(b=>b.unit===unit).map(bedCard).join('')}</div></div>`).join('')}</div></section>
  <section class="panel"><div class="panel-heading"><div><h2>향후 24시간 점유·예약</h2><p>재실 표시는 실제 퇴실 전까지 유지합니다. 가용 예상은 퇴실 완료를 뜻하지 않습니다.</p></div><div class="legend"><span><i style="background:var(--blue)"></i>실제 재실</span><span><i style="background:var(--purple)"></i>확정 예약</span><span><i style="background:var(--amber)"></i>청소·준비</span></div></div><div class="panel-body">${gantt()}</div></section>`;
}
function openModal(title,body){$('#modal-content').innerHTML=`<div class="modal-header"><h2 id="modal-title">${esc(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="닫기">${icon('close')}</button></div><div class="modal-body">${body}</div>`;const m=$('#modal');if(m.open)m.close();m.showModal();}
function resetModal(){openModal('시연을 처음부터 다시 시작',`<p>현재 환자 경과와 예약을 기본 합성 시나리오로 되돌립니다. 실행 중인 시간은 멈춥니다.</p><div class="form-actions"><button class="button" data-action="close-modal">돌아가기</button><button class="button primary" data-action="confirm-reset">처음부터 시작</button></div>`);U.resetRevision=S.revision;}
function helpModal(){openModal('PeriCare v6.1 사용 안내',`<ol class="help-list"><li><b>시뮬레이션 시작</b>을 누릅니다. 가상 의사와 간호사가 입원, 평가, 예약, 준비, 이송, 전실, 병원 퇴원을 스스로 진행합니다.</li><li><b>실시간 병원 지도</b>에서 환자·간호사·병상을 선택합니다. 환자 선택 목록으로도 상세 내용을 볼 수 있습니다.</li><li><b>환자 위험·경과</b>에서 집중관리 필요성과 지속기간, ICU 이용·재실, 잔여 입원기간을 확인합니다.</li><li><b>ICU 병상 계획</b>에서 추천 예약 시점과 확정·준비·입실을 비교합니다. 실제 재실과 가용 예상을 구분합니다.</li></ol><p>기본 60명의 기존 환자와 하루 24명의 신규 유입을 포함한 7일 시나리오입니다. +1일과 운영 배속으로 여러 날을 볼 수 있고, 천천히 재생하면 움직임과 인계를 자세히 볼 수 있습니다. 지도는 화면 가득 보기로 넓힐 수 있습니다. 아이콘을 선택하면 상세 패널이 열리고 Esc로 닫힙니다. 큰 글씨·테마·데이터 연결은 상단 설정에서, 이동 효과는 지도 도구에서 조절합니다. Tab과 Enter로 아이콘을 선택할 수 있습니다.</p><p class="muted">기본 데이터·예측·의료진은 시연용입니다. 데이터 연결과 모델 교체는 압축 파일의 README 및 docs 문서를 참고하세요.</p><div class="form-actions"><button class="button primary" data-action="close-modal">안내 닫기</button></div>`);}
async function clickAction(a,button){
  const pid=button.dataset.patient;
  if(a.startsWith('map-'))return hospitalAction(a,button);
  if(a==='inspect'||a==='select-patient')return navigate('patients',pid);
  if(a==='locate-patient'||a==='locate-bed'){MapUI.selected={kind:a==='locate-bed'?'bed':'patient',id:a==='locate-bed'?button.dataset.bed:pid};MapUI.detailOpen=true;return navigate('hospital',pid);}
  if(a==='chart'){U.chart=button.dataset.chart;return render();}
  if(a==='play'){if(!S.running&&S.automation?.eligible&&!autoEnabled()&&!(await act('automation',{enabled:true})))return;return act('play',{running:!S.running,speed:Number($('#speed').value)});}
  if(a==='advance'){const minutes=Math.min(Number(button.dataset.minutes||5),S.hospital.horizon_minutes-S.minute);if(minutes<=0)return;return act('advance',{minutes},`${fmt(minutes/60,1)}시간 경과를 반영했습니다`);}
  if(a==='reset'){if(S.running&&!(await act('play',{running:false})))return;return resetModal();}
  if(a==='confirm-reset'){const result=await act('reset',{seed:S.seed,expected_revision:U.resetRevision},'시연을 처음부터 시작합니다');if(result){$('#modal').close();U.query='';U.phaseFilter='active';U.selected=null;resetMapSelection();await refresh(true);}return;}
  if(a==='theme'){document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('pericare-theme',document.documentElement.dataset.theme);}catch{}return;}
  if(a==='text-size'){const d=document.documentElement;d.dataset.text=d.dataset.text==='large'?'normal':'large';try{localStorage.setItem('pericare-text',d.dataset.text);}catch{}updateHeader();if(U.view==='hospital')updateMapZoom();return;}
  if(a==='data'){$('#app-options').open=false;return dataModal();}if(a==='import-data')return importData();if(a==='help'){$('#app-options').open=false;return helpModal();}if(a==='close-modal')return $('#modal').close();
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-action],[data-view]');if(!b||b.disabled)return;if(b.dataset.view)navigate(b.dataset.view,b.dataset.patient);else if(b.dataset.action)clickAction(b.dataset.action,b);});
document.addEventListener('toggle',e=>{if(e.target.classList?.contains('clinical-inputs'))U.inputsOpen=e.target.open;},true);
document.addEventListener('input',e=>{if(e.target.id==='patient-search'){U.query=e.target.value;render();}});
document.addEventListener('change',e=>{if(e.target.id==='phase-filter'){U.phaseFilter=e.target.value;render();}if(e.target.id==='speed')act('play',{running:S.running,speed:Number(e.target.value)});});
function readHash(){const [v,id]=location.hash.slice(1).split('/');if(nav.some(n=>n[0]===v)){U.view=v;if(id){try{U.selected=decodeURIComponent(id);}catch{}}}}
window.addEventListener('resize',()=>{if(!S)return;if(U.view==='hospital')updateMapZoom();else if(U.view==='patients')render();});
window.addEventListener('hashchange',()=>{readHash();if(S){updateHeader();render();}});
document.addEventListener('DOMContentLoaded',()=>{readHash();refresh(true);setInterval(()=>refresh(),2000);},{once:true});
function trajectoryChart(p){
  let series,max=100,threshold=70,legend='동적 위험 지표 · ICU 이용 예측(%)';
  if(U.chart==='vitals'){series=[{color:'var(--teal)',data:p.observations.map(o=>[o.minute,o.map])},{color:'var(--blue)',data:p.observations.map(o=>[o.minute,o.hr])}];max=160;threshold=65;legend='MAP (mmHg) · HR (bpm)';}
  else if(U.chart==='oxygen'){series=[{color:'var(--blue)',data:p.observations.map(o=>[o.minute,o.spo2])}];max=100;threshold=94;legend='SpO₂ (%)';}
  else series=[{color:'var(--teal)',data:p.history.map(o=>[o.minute,o.need_score])},{color:'var(--amber)',data:p.history.map(o=>[o.minute,Number.isFinite(o.icu_probability)?o.icu_probability*100:null])}];
  const all=series.flatMap(s=>s.data).filter(d=>Number.isFinite(d[0]));if(!all.length)return empty('관측 경과가 아직 없습니다');
  const xmin=Math.min(...all.map(d=>d[0])),xmax=Math.max(xmin+5,p.discharge_minute??S.minute),w=(window.innerWidth||1000)<=760?380:760,h=225,pad=36,bottom=27;
  const x=t=>pad+(t-xmin)/(xmax-xmin)*(w-pad-36),y=v=>h-bottom-v/max*(h-bottom-15);
  const lines=series.map(s=>{let path='',active=false;s.data.forEach(([t,v])=>{if(!Number.isFinite(v)){active=false;return;}path+=`${active?'L':'M'}${x(t).toFixed(1)},${y(v).toFixed(1)} `;active=true;});return `<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`;}).join('');
  const marks=p.treatments.filter(t=>t.minute>=xmin&&t.minute<=xmax).slice(-8).map(t=>`<line x1="${x(t.minute)}" x2="${x(t.minute)}" y1="15" y2="${h-bottom}" stroke="var(--purple)" stroke-dasharray="2 6" opacity=".22"><title>${esc(t.label)} ${time(t.minute)}</title></line>`).join('');
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(legend)} 경과">${[0,.25,.5,.75,1].map(q=>`<line class="chart-grid" x1="${pad}" x2="${w-36}" y1="${y(max*q)}" y2="${y(max*q)}"/><text class="chart-text" x="${pad-8}" y="${y(max*q)+3}" text-anchor="end">${Math.round(max*q)}</text>`).join('')}<line x1="${pad}" x2="${w-36}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="var(--amber)" stroke-dasharray="4 4" opacity=".5"/>${marks}${lines}${[0,.25,.5,.75,1].map(q=>`<text class="chart-text" x="${x(xmin+(xmax-xmin)*q)}" y="${h-7}" text-anchor="middle">${time(xmin+(xmax-xmin)*q)}</text>`).join('')}</svg><div class="legend" style="padding:0 18px 6px">${legend.split(' · ').map((v,i)=>`<span><i style="background:${series[i]?.color||'var(--teal)'}"></i>${v}</span>`).join('')}<span><i style="background:var(--purple)"></i>관측된 처치</span></div>`;
}

function hospitalJourney(p){
 const terminal=['DISCHARGED','DECEASED','TRANSFERRED'].includes(p.phase),asOf=terminal?p.discharge_minute:S.minute;
 return `<section class="panel hospital-journey"><div><span>실제 입원</span><b>${time(p.admission_minute,true)}</b><small>${fmt((asOf-p.admission_minute)/1440,1)}일 경과</small></div><div><span>관측된 수술 종료</span><b>${time(p.actual_end_minute,true)}</b><small>${Number.isFinite(p.actual_end_minute)?'수술 후 '+fmt((asOf-p.actual_end_minute)/1440,1)+'일':'수술 전·수술 중'}</small></div><div><span>병원 퇴원·종료</span><b>${terminal?time(p.discharge_minute,true):'입원 중'}</b><small>${terminal?p.phase_label:'잔여기간 예측과 실제 퇴원은 별도'}</small></div></section>`;
}
function dataModal(){openModal('실제 관측 자료 연결',`<p>환자·입원·수술 연결키와 단위를 정리한 JSON을 불러옵니다. 시간에 따른 입원·관측·전실·퇴원이 있으면 기록된 사건을 순서대로 재생합니다.</p><p class="muted">재생 예제는 합성 자료입니다. 실제 입력 자료에서는 측정값이나 퇴원을 만들어내지 않습니다. 기본 모의 예측을 실제 모델로 교체하는 방법은 포함된 문서에 있습니다.</p><label class="file-input-label">자료 선택<input id="dataset-file" type="file" accept=".json,application/json"></label><p id="data-import-status" role="status"></p><div class="data-links"><a href="/api/example/replay" download>입퇴원 기록 재생 예제</a><a href="/api/export/data" download>현재 관측 자료 내보내기</a></div><div class="form-actions"><button class="button" data-action="close-modal">닫기</button><button class="button primary" data-action="import-data">자료 불러오기</button></div><small class="muted">불러오면 현재 화면의 자료와 예약을 교체합니다. 기존 감사 기록은 보관합니다.</small>`);}
async function importData(){
 const file=$('#dataset-file')?.files?.[0];if(!file)return toast('JSON 파일을 선택하세요',true);
 if(file.size>20*1024*1024)return toast('자료는 20MB 이하로 준비하세요',true);
 try{if(S.running&&!(await act('play',{running:false})))return;const dataset=JSON.parse(await file.text());$('#data-import-status').textContent='연결키·단위·관측 시각을 확인합니다.';if(await act('import',{dataset},'관측 자료를 연결했습니다')){$('#modal').close();resetMapSelection();MapUI.mounted=false;U.selected=null;U.query='';U.phaseFilter='active';await refresh(true);}}
 catch(e){toast('자료 형식을 확인하세요: '+e.message,true);}
}
