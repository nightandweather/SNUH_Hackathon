/* SICU LINK: a display workspace, not a replacement for authentication or care logic. */
(() => {
  'use strict';
  const q = s => document.querySelector(s);
  const all = s => [...document.querySelectorAll(s)];
  const ko = () => I18n.language === 'ko';
  const t = (a, b) => ko() ? a : b;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icons = {
    ward:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v6m6-6v6M9 15v5m6-5v5"/>',
    patients:'<circle cx="9" cy="7" r="3"/><path d="M3 20v-3a6 6 0 0 1 12 0v3m2-15h4m-4 5h4m-3 5h3"/>',
    planning:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-14 4h2m6 0h2m-10 3h2"/>',
    network:'<circle cx="12" cy="6" r="3"/><circle cx="5" cy="18" r="3"/><circle cx="19" cy="18" r="3"/><path d="m10.5 9-4 6m7-6 4 6M8 18h8"/>',
    settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="white"/><circle cx="15" cy="17" r="3" fill="white"/>'
  };
  const icon = key => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+icons[key]+'</svg>';
  const copy = {
    brandSubtitle:['외과계 ICU 간호 상황판','Surgical ICU nursing workspace'],
    preparing:['돌봄의 흐름을 준비하고 있습니다','Preparing your care workspace'],
    headlineOne:['병상을 보고,','See every bed.'], headlineTwo:['돌봄을 연결하다.','Connect every team.'],
    entryDescription:['환자가 제때 필요한 돌봄을 받고,<br>간호 업무가 한곳에 몰리지 않도록.<br><span class="entry-purpose-detail">병상·간호인력·이송을 연결해 준비 지연과 대기를 줄이는 ICU 운영을 제안합니다.</span>','Timely care for patients.<br>Shared support for nursing teams.<br><span class="entry-purpose-detail">Connecting beds, nurses and transport to reduce preparation delays and waiting.</span>'],
    entryArtCaption:['환자 곁의 간호, 이어지는 협력','Care at the bedside. Coordination across teams.'],
    entryTitle:['어디에서 시작할까요?','Choose your workspace'], entryNote:['병원 상황판 또는 통합 관제를 선택하세요.','Open a hospital workspace or the coordination center.'],
    hospitalMode:['병원 상황판','Hospital'], centerMode:['통합 관제','Coordination center'],
    centerTitle:['세 병원, 하나의 관제 화면','Three hospitals. One connected view.'],
    centerDescription:['병원·ICU별 병상과 인력 현황을 함께 살펴보고,<br>입실 준비와 지원·이송을 조율합니다.<br>환자·직원 개인 상세는 표시하지 않습니다.','Review bed and staffing summaries by hospital and ICU.<br>Coordinate preparation, support and transport.<br>Individual patient and staff details are not displayed.'],
    demoScope:['가상 병원 유형·배치 예시로 구성한 시뮬레이션입니다.','A simulation using fictional hospital types and layouts.'],
    start:['상황판 열기','Open workspace']
  };
  let initialized = false, entered = false, entryMode = 'hospital', entryHospital = 'A', activeView = 'ward';
  let hospitalSignature = '', statsSignature = '', entryOpener = null;
  let preference = {};
  try { preference = JSON.parse(localStorage.getItem('sicu.link.workspace') || '{}'); } catch (_) {}
  const query = new URLSearchParams(location.search);
  entryHospital = query.get('hospital') || preference.hospital || 'A';
  entryMode = query.get('workspace') === 'center' ? 'center' : query.get('workspace') === 'hospital' ? 'hospital' : preference.mode === 'center' ? 'center' : 'hospital';
  const state = window.SICULinkState;
  const rawUnits = () => state.raw?.floors.flatMap(f => f.units) || [];
  const hospitals = () => [...new Set(rawUnits().map(u => u.hospital_id || 'A'))];
  const hospitalName = h => I18n.t(rawUnits().find(u => (u.hospital_id || 'A') === h)?.hospital_name || ('Demo Hospital '+h));
  const viewNames = () => ({ward:t('병동 현황','Ward overview'),patients:t('환자 목록','Patients'),planning:t('운영 계획','Operations planning'),network:t('통합 현황','Network overview')});

  function setEntryMode(mode) {
    entryMode = mode === 'center' ? 'center' : 'hospital';
    all('[data-entry-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.entryMode === entryMode)));
    q('#entryHospitalChoices').hidden = entryMode === 'center';
    q('#entryCenterDescription').hidden = entryMode !== 'center';
    updateEntry();
  }
  function updateEntry() {
    const ids = hospitals();
    if (!ids.includes(entryHospital) && ids.length) entryHospital = ids[0];
    const rows = ids.map(id => {
      const units = rawUnits().filter(u => (u.hospital_id || 'A') === id);
      return {id,name:hospitalName(id),type:FacilityRuntime.typeName(id),units:units.length,beds:units.reduce((n,u) => n+u.beds.length,0)};
    });
    const signature = JSON.stringify([rows,I18n.language]);
    if (signature !== hospitalSignature) {
      hospitalSignature = signature;
      q('#entryHospitalChoices').innerHTML = rows.map(r => '<button type="button" class="entry-hospital" data-entry-hospital="'+esc(r.id)+'" aria-pressed="false"><span class="entry-hospital-letter" aria-hidden="true">'+esc(r.id)+'</span><span class="entry-hospital-text"><strong>'+esc(r.name)+'</strong><small class="entry-hospital-type">'+esc(r.type)+'</small><small class="entry-hospital-metrics"><b>'+r.units+'</b> '+t('개 ICU','ICUs')+' <i>·</i> <b>'+r.beds+'</b> '+t('병상','beds')+'</small></span><span class="entry-choice-check" aria-hidden="true">✓</span></button>').join('');
    }
    all('[data-entry-hospital]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.entryHospital === entryHospital)));
    const selected=rows.find(row=>row.id===entryHospital),art=q('.entry-art');
    const artPath=entryMode==='center'?'assets/identity/entry-illustration.svg':'assets/identity/facility-'+entryHospital.toLowerCase()+'.svg';
    if(art.getAttribute('src')!==artPath)art.setAttribute('src',artPath);
    art.alt=entryMode==='center'?t('가상 병원 네트워크 개념도','Fictional hospital network concept'):hospitalName(entryHospital)+' · '+FacilityRuntime.layoutName(entryHospital)+' · '+t('가상 구성 개념도','Fictional facility concept');
    const footer=q('.entry-story-footer');
    footer.firstElementChild.textContent=entryMode==='center'?'NETWORK / '+rows.reduce((sum,row)=>sum+row.beds,0)+' BEDS':entryHospital+' / '+(selected?.beds || '—')+' BEDS';
    footer.lastElementChild.textContent=entryMode==='center'?t('환자 곁의 간호, 이어지는 협력','Care at the bedside. Coordination across teams.'):FacilityRuntime.layoutName(entryHospital);
    q('#entrySummary').textContent = rows.length ? (entryMode === 'center' ? t('전체 병원 네트워크로 시작합니다.','Start with the complete hospital network.') : hospitalName(entryHospital)+' · '+t('병동 현황으로 시작합니다.','Start with the ward overview.')) : '';
    q('#entryStart').disabled = !state.raw;
    q('#entryStart span:first-child').textContent = entryMode === 'center' ? t('통합 관제 열기','Open coordination center') : t('상황판 열기','Open hospital workspace');
    q('#entryAvailability').textContent = state.raw ? '' : t('작업 공간을 불러오는 중입니다…','Loading the workspace…');
  }
  function openEntry(reopening = false, opener = null) {
    if (reopening) { entryMode = document.body.dataset.workspaceMode || entryMode; entryHospital = Network.hospital; entryOpener = opener || q('#workspaceHome'); }
    q('#entryClose').hidden = !entered;
    setEntryMode(entryMode);
    q('#workspaceEntry').showModal();
    document.body.dataset.startup = 'selection';
    q('#startupScreen').hidden = true;
    q('#entryTitle').focus();
  }
  function enterWorkspace() {
    if (!state.raw) return;
    document.body.dataset.workspaceMode = entryMode;
    document.dispatchEvent(new CustomEvent('sicu-workspace-mode',{detail:{mode:entryMode,hospital:entryHospital}}));
    const local = rawUnits().filter(u => (u.hospital_id || 'A') === entryHospital);
    const desired = query.get('ward');
    const nurse = state.raw.nurses.find(n => n.id === query.get('nurse') && local.some(u => u.id === n.unit));
    const ward = entryMode === 'center' ? '' : (local.find(u => u.id === desired)?.id || nurse?.unit || local.find(u => /(?:^|-)SICU$/.test(u.id))?.id || local[0]?.id || '');
    Network.navigate(entryHospital,ward,Boolean(nurse && nurse.unit === ward));
    try { localStorage.setItem('sicu.link.workspace', JSON.stringify({mode:entryMode,hospital:entryHospital})); } catch (_) {}
    entered = true;
    document.body.dataset.startup = 'ready';
    q('#workspaceEntry').close();
    setView(entryMode === 'center' ? 'network' : 'ward', false);
    const url = new URL(location); url.searchParams.set('workspace',entryMode);url.hash = activeView;
    if(entryMode==='center'){url.searchParams.delete('ward');url.searchParams.delete('nurse');url.searchParams.delete('consult');}
    history.replaceState(null,'',url);
    window.scrollTo(0,0);
    q('#workspaceHome').focus({preventScroll:true});
    sync();
  }
  function setView(view, focus = true) {
    const center=document.body.dataset.workspaceMode==='center';
    if(center)view='network';
    if (view === 'network' && document.body.dataset.workspaceMode !== 'center') view = 'ward';
    if (!['ward','patients','planning','network'].includes(view)) view = 'ward';
    activeView = view;
    document.body.dataset.workspaceView = view;
    all('[data-sicu-panel]').forEach(panel => panel.hidden = panel.dataset.sicuPanel !== view);
    all('#workspaceNav [data-workspace-view]').forEach(button => {
      const selected = button.dataset.workspaceView === view;
      button.classList.toggle('is-current',selected);
      if (selected) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
      button.hidden = center ? button.dataset.workspaceView!=='network' : button.dataset.workspaceView==='network';
    });
    q('.side').hidden = view === 'network' || view === 'planning';
    q('.scopebar').hidden = view === 'network';
    q('#workspaceTitle').textContent = viewNames()[view];
    q('#ward-map').open = true;
    const url = new URL(location); url.hash = view; history.replaceState(null,'',url);
    if (focus) { window.scrollTo(0,0); q('#workspaceTitle').focus({preventScroll:true}); }
  }
  function collectTools() {
    const destination = q('#demoToolBody');
    for (const selector of ['#publicSandbox','#transferPanel']) {
      const panel = q(selector);
      if (panel && panel.parentElement !== destination) destination.append(panel);
    }
    q('#readinessHelp')?.remove();
    q('#readinessLegend')?.remove();
  }
  function sync() {
    if (!initialized) return;
    updateEntry(); collectTools(); window.SICUCare?.decorate(); window.FacilityRuntime?.decorate();
    q('#workspaceHospital').textContent = document.body.dataset.workspaceMode === 'center' ? t('통합 관제','Coordination center') : hospitalName(Network.hospital);
    q('#workspaceScopeType').textContent = document.body.dataset.workspaceMode === 'center' ? t('병원 네트워크','Hospital network') : t('병원 상황판','Hospital workspace');
    if (typeof S === 'undefined' || !S) return;
    const units = S.floors.flatMap(f => f.units), beds = units.flatMap(u => u.beds);
    q('#workspaceContext').textContent = activeView === 'network' ? t('규모가 다른 세 병원의 수용 현황과 운영 흐름','Availability across three hospital scales') : hospitalName(Network.hospital)+' · '+FacilityRuntime.typeName(Network.hospital)+' / '+(units.length === 1 ? FacilityRuntime.unitName(units[0]) : t('전체 병동','All wards'));
    const counts = {critical:0,watch:0,stable:0,reserved:0,empty:0};
    beds.forEach(b => { const key = bedStatus(b).key; if (key in counts) counts[key]++; });
    const signature = JSON.stringify([counts, beds.length, I18n.language]);
    if (signature !== statsSignature) {
      statsSignature = signature;
      const labels = {critical:'RED',watch:'BLUE',stable:'GREEN',reserved:t('입실 예약','Reserved'),empty:t('빈 병상','Empty')};
      q('#workspaceStats').innerHTML = '<span class="workspace-bed-total">'+beds.length+' <small>'+t('병상','beds')+'</small></span>'+Object.entries(counts).map(([key,n]) => '<span class="census-item" data-census="'+key+'"><i></i><span>'+labels[key]+'</span><b>'+n+'</b></span>').join('');
    }
    q('#workspaceStats').hidden = activeView === 'network' || activeView === 'planning';
  }
  function updateLanguage() {
    all('[data-copy]').forEach(node => {const words=copy[node.dataset.copy];if(words) node.innerHTML=words[ko()?0:1];});
    all('#workspaceNav [data-workspace-view]').forEach(button => button.querySelector('span').textContent = viewNames()[button.dataset.workspaceView]);
    q('#workspaceTitle').textContent = viewNames()[activeView];
    q('#demoTools summary>span').textContent = t('시연 도구','Demo tools');
    q('#workspaceHome').setAttribute('aria-label',t('첫 화면으로 돌아가기','Back to start'));
    q('#workspaceHome').title=t('첫 화면으로 돌아가기','Back to start');
    q('#entryClose').setAttribute('aria-label',t('작업 공간 선택창 닫기','Close workspace selection'));
    q('#boardTextSize').setAttribute('aria-label',t('큰 글씨','Large text'));
    q('#simulationClock small').textContent = t('시뮬레이션','Simulation');
    q('#sourceRelease small').textContent = t('참조 원본 배포','Reference release');
    q('#uiRelease small').textContent = t('최신 UI 업데이트','Latest UI update');
    q('#sourceRelease').title = t('참조 원본 페이지에 표시된 배포 시각 · 한국 표준시','Release time declared by the reference page · Korea Standard Time');
    q('#uiRelease').title = t('현재 버전의 UI 업데이트 시각 · 새로고침 시각과 구분됩니다','UI update time for this version · independent of page refresh');
    q('#publicClose').textContent = t('✕ 닫기','✕ Close'); q('#publicClose').dataset.noTranslate = '';
    const caption = q('.map-caption');
    if (caption) caption.textContent = t('6개 간호 상태 · 색 채움: 해당 · 윤곽: 없음 · ?: 미확인','6 care indicators · Filled: active · Outline: not active · ?: unknown');
    sync();
  }
  function setup() {
    const header = q('header');
    q('header h1').classList.add('sicu-sr-only');
    const brand = document.createElement('button'); brand.id='workspaceHome';brand.type='button';brand.className='workspace-brand';brand.dataset.noTranslate='';brand.setAttribute('aria-haspopup','dialog');brand.setAttribute('aria-controls','workspaceEntry');
    brand.innerHTML='<img src="assets/identity/logo-mark.svg" alt="" width="36" height="36"><span>SICU <b>LINK</b><small class="team-signature">TEAM 4</small></span>';
    header.prepend(brand);
    brand.addEventListener('click',()=>openEntry(true,brand));
    const scope = document.createElement('div'); scope.id='workspaceIdentity';scope.dataset.noTranslate='';scope.innerHTML='<small id="workspaceScopeType"></small><strong id="workspaceHospital"></strong>';
    brand.after(scope);
    const clock = document.createElement('div'); clock.id='simulationClock';clock.dataset.noTranslate='';clock.innerHTML='<small></small>';clock.append(q('#clock'));header.append(clock);
    const size = document.createElement('button');size.id='boardTextSize';size.type='button';size.innerHTML='<span aria-hidden="true">가<sup>+</sup></span>';size.dataset.noTranslate='';
    let large=false;try{large=localStorage.getItem('icu.ui.largeText')==='true';}catch(_){}
    function setLarge(value){large=value;document.body.dataset.textSize=large?'large':'normal';size.setAttribute('aria-pressed',String(large));try{localStorage.setItem('icu.ui.largeText',String(large));}catch(_){}}
    size.onclick=()=>setLarge(!large);setLarge(large);header.append(size,q('#languageSwitch'));
    const releases=document.createElement('div');releases.id='releaseInfo';releases.dataset.noTranslate='';
    releases.innerHTML='<a id="sourceRelease" href="https://icu-ward-board-20261016.kanghoun.chatgpt.site/?lang=ko&amp;hospital=B" target="_blank" rel="noopener"><small></small><time></time><span aria-hidden="true">↗</span></a><div id="uiRelease"><small></small><time></time></div>';
    for(const [id,meta] of [['sourceRelease','icu-release-at'],['uiRelease','sicu-ui-updated-at']]){
      const value=q('meta[name="'+meta+'"]')?.content;
      const date=new Date(value);
      const time=releases.querySelector('#'+id+' time');
      if(Number.isNaN(+date)){time.textContent='—';continue;}
      time.dateTime=value;
      time.textContent=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date)+' KST';
    }
    header.after(releases);
    const nav=document.createElement('nav');nav.id='workspaceNav';nav.dataset.noTranslate='';nav.setAttribute('aria-label',t('주요 화면','Workspace views'));nav.innerHTML=['network','ward','patients','planning'].map(key=>'<button type="button" data-workspace-view="'+key+'">'+icon(key)+'<span></span></button>').join('');releases.after(nav);
    nav.addEventListener('click',event=>{const button=event.target.closest('[data-workspace-view]');if(button)setView(button.dataset.workspaceView);});
    const heading=document.createElement('section');heading.id='workspaceHeading';heading.innerHTML='<div data-no-translate><p id="workspaceContext"></p><h2 id="workspaceTitle" tabindex="-1"></h2></div><div id="workspaceStats" data-no-translate></div>';nav.after(heading);heading.append(q('.scopebar'));
    const tools=document.createElement('details');tools.id='demoTools';tools.innerHTML='<summary data-no-translate>'+icon('settings')+'<span></span><small>SCENARIO · REPLAY · TRANSPORT</small></summary><div id="demoToolBody"></div>';heading.append(tools);
    const main=q('main');main.id='workspaceMain';const content=main.firstElementChild;
    const ward=document.createElement('section');ward.id='wardView';ward.dataset.sicuPanel='ward';q('.floor-plan').id='ward-map';ward.append(q('.floor-plan'));
    const patients=document.createElement('section');patients.id='patientsView';patients.dataset.sicuPanel='patients';patients.append(q('.patient-board'));
    const planning=document.createElement('section');planning.id='planningView';planning.dataset.sicuPanel='planning';all('.flow-panel').forEach(p=>planning.append(p));
    const network=document.createElement('section');network.id='networkView';network.dataset.sicuPanel='network';network.append(q('.network-panel'));
    content.replaceChildren(network,ward,patients,planning);
    const footer=document.createElement('footer');footer.id='workspaceFooter';const notice=q('.public-notice');const noticeDetails=document.createElement('details');noticeDetails.innerHTML='<summary data-no-translate>'+t('가상 데이터 · 시뮬레이션 안내','Fictional data · simulation information')+'</summary>';const noticeText=document.createElement('div');while(notice.firstChild)noticeText.append(notice.firstChild);noticeDetails.append(noticeText);notice.append(noticeDetails);footer.append(notice);const freshness=q('#refreshStamp');if(freshness)footer.append(freshness);main.after(footer);
    const scenario=q('.scenario-card');if(scenario)q('#demoToolBody').append(scenario);
    const floorHint=q('.floor-plan>p.tag');if(floorHint){floorHint.classList.add('map-caption');floorHint.dataset.noTranslate='';}
    q('#entryHospitalChoices').addEventListener('click',event=>{const button=event.target.closest('[data-entry-hospital]');if(button){entryHospital=button.dataset.entryHospital;updateEntry();}});
    all('[data-entry-mode]').forEach(b=>b.addEventListener('click',()=>setEntryMode(b.dataset.entryMode)));
    q('#entryStart').addEventListener('click',enterWorkspace);
    const returnEntryFocus=()=>{(entryOpener?.isConnected?entryOpener:q('#workspaceHome')).focus({preventScroll:true});};
    q('#entryClose').addEventListener('click',()=>{q('#workspaceEntry').close();document.body.dataset.startup='ready';returnEntryFocus();});
    q('#workspaceEntry').addEventListener('cancel',event=>{if(!entered)event.preventDefault();else{document.body.dataset.startup='ready';queueMicrotask(returnEntryFocus);}});
    q('#networkCards').addEventListener('click',event=>{if(event.target.closest('[data-hospital]'))setView('ward');});
    document.body.dataset.workspaceMode=entryMode;
    initialized=true; state.notify=sync;
    updateLanguage();setView('ward',false);sync();
    document.addEventListener('icu-language',()=>queueMicrotask(updateLanguage));
    const elapsed=performance.now();
    setTimeout(()=>openEntry(false),Math.max(0,1350-elapsed));
  }
  const nativeDraw=window.draw;
  window.draw=function(){const result=nativeDraw.apply(this,arguments);sync();return result;};
  window.SICULink=Object.freeze({setView,sync,openEntry});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
