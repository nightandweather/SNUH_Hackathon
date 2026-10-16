/* Clinician figures and replay cues; the original app owns coordinates and care. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const q = s => document.querySelector(s);
  const ko = () => document.documentElement.lang.startsWith('ko');
  const t = (a,b) => ko() ? a : b;
  const observations = new Map();
  const assignments = new Map();
  let previewNurseId = '', previewNode = null;
  let toolbarReady = false, startRequested = false, timeline = null;
  const nativeAvatar = window.staffAvatar;
  window.staffAvatar = (staff,doctor) => window.SICUStaffVisuals.avatar(staff,doctor);
  window.staffAvatar.sicuOriginal = nativeAvatar;

  function status(person, doctor) {
    if (!doctor && person.on_break) return 'break';
    if (person.status === 'moving') return 'moving';
    if (person.status === 'called') return 'called';
    if (person.status === 'responding' || person.status === 'incident' || person.incident) return 'responding';
    if (!doctor && person.diagnostic_id) return 'task';
    if (!doctor && person.cover?.length) return 'coverage';
    return doctor ? 'available' : 'care';
  }
  function statusName(value) {
    return ({moving:t('이동 중','En route'),called:t('호출됨','Called'),responding:t('대응 중','Responding'),break:t('휴식 중','On break'),task:t('검사 업무','Diagnostic task'),coverage:t('지원 간호','Coverage'),care:t('간호 중','Providing care'),available:t('대기 중','Available')})[value];
  }
  function roleName(person,doctor) { return doctor ? t('의사','Physician') : person.role === 'charge' ? t('책임간호사','Charge nurse') : t('간호사','Nurse'); }
  function svg(tag, attributes, parent) {
    const node = document.createElementNS(NS,tag);
    Object.entries(attributes || {}).forEach(([key,value]) => node.setAttribute(key,value));
    if(parent) parent.append(node);
    return node;
  }
  function cue(marker) {
    let group = marker.querySelector('.staff-motion-cue');
    if(group) return group;
    group = svg('g',{class:'staff-motion-cue','aria-hidden':'true','pointer-events':'none'},marker);
    svg('ellipse',{class:'staff-ground',cx:'0',cy:'1.1',rx:'.68',ry:'.10'},group);
    svg('path',{class:'staff-step staff-step-one',d:'M-.44 1.29h.31'},group);
    svg('path',{class:'staff-step staff-step-two',d:'M.13 1.29h.31'},group);
    svg('circle',{class:'staff-state-dot',cx:'.75',cy:'.43',r:'.15'},group);
    const direction = svg('g',{class:'staff-direction',transform:'translate(1.1 .08)'},group);
    svg('path',{d:'M-.23 0H.3M.08-.21.3 0 .08.21'},direction);
    return group;
  }
  function selectedNurse() {
    if (typeof S === 'undefined' || !S) return null;
    if(previewNurseId&&previewNode?.isConnected){
      const preview=S.nurses.find(person=>person.id===previewNurseId);
      if(preview)return preview;
    }
    if(typeof picked !== 'string' || !picked.startsWith('N:')) return null;
    return S.nurses.find(person => picked === 'N:' + person.id) || null;
  }
  function selection() {
    if (typeof S === 'undefined' || !S) return;
    const nurse = selectedNurse();
    for (const person of S.nurses) {
      const marker = nurseEl[person.id];
      if (marker) marker.dataset.staffSelected = String(picked === 'N:' + person.id);
    }
    for (const person of S.doctors || []) {
      const marker = doctorEl[person.id];
      if (marker) marker.dataset.staffSelected = String(picked === 'MD:' + person.id);
    }
    // Assignment is the source nurse.beds relation. Coverage stays independent.
    const assigned = new Set(nurse ? nurse.beds || [] : []), live = new Set();
    const portals = window.SICUWardSpaces?.contexts() || [];
    const contexts = portals.length ? portals.map(context=>({floor:{...context.floor,units:[context.unit]},staffLayer:context.staffLayer,map:context.svg})) :
      S.floors.map(floor=>{const staffLayer=typeof floorSvg!=='undefined'?floorSvg[floor.floor]:null;return {floor,staffLayer,map:staffLayer?.ownerSVGElement};});
    for (const {floor,staffLayer,map} of contexts) {
      if (!map) continue;
      live.add(map);
      let view = assignments.get(map);
      if (!view || !view.group.isConnected) {
        const group = svg('g', {class:'staff-assignment-layer', 'aria-hidden':'true', 'pointer-events':'none', focusable:'false'});
        map.insertBefore(group, staffLayer);
        view = {group, beds:new Map()};
        assignments.set(map, view);
      }
      view.group.dataset.selectedNurse = nurse?.id || '';
      const visible = new Set();
      for (const unit of floor.units) for (const bed of unit.beds) {
        if (!assigned.has(bed.id)) continue;
        visible.add(bed.id);
        let outline = view.beds.get(bed.id);
        if (!outline) {
          outline = svg('rect', {class:'staff-assignment-outline', 'data-bed-id':bed.id,
            fill:'none', rx:'.28', 'pointer-events':'none'}, view.group);
          view.beds.set(bed.id, outline);
        }
        // Inside the existing eight-unit-wide bed-space walls; no native room,
        // bed, patient, staff or door coordinates are changed.
        const upper = Number(bed.y) < Number(unit.h) / 2;
        const geometry = {x:Number(bed.x)-3.86,y:upper ? .14 : Number(bed.y)-2.36,width:7.72,height:4.72};
        Object.entries(geometry).forEach(([key,value]) => {
          if (outline.getAttribute(key) !== String(value)) outline.setAttribute(key,value);
        });
        outline.dataset.nurseId = nurse.id;
      }
      view.beds.forEach((outline,id) => {if (!visible.has(id)) {outline.remove();view.beds.delete(id);}});
      view.group.dataset.assignedCount = String(visible.size);
    }
    assignments.forEach((view,map) => {
      if (!live.has(map)) {view.group.remove();assignments.delete(map);}
    });
  }
  function decorate() {
    if(typeof S === 'undefined' || !S) return;
    const epoch = String(S.seed) + ':' + Network.hospital;
    if(!timeline || timeline.epoch !== epoch || Number(S.t) < timeline.t) observations.clear();
    timeline = {epoch,t:Number(S.t)};
    const active = new Set();
    for(const [person,doctor] of [...S.nurses.map(n => [n,false]),...(S.doctors || []).map(n => [n,true])]) {
      const marker = doctor ? doctorEl[person.id] : nurseEl[person.id];
      if(!marker) continue;
      active.add(person.id);
      if(!marker.querySelector('.sicu-staff-avatar')) {
        const container = svg('g'); container.innerHTML = window.SICUStaffVisuals.avatar(person,doctor);
        marker.querySelector('.staff-avatar')?.replaceWith(container.firstElementChild);
      }
      cue(marker);
      const state = status(person,doctor), position = staffPos(person), previous = observations.get(person.id);
      marker.dataset.staffId = person.id;
      marker.dataset.staffRole = doctor ? 'physician' : person.role === 'charge' ? 'charge' : 'nurse';
      marker.dataset.staffState = state;
      if (!doctor) {
        const color = window.SICUStaffVisuals.uniformColor(person,false);
        marker.dataset.uniformRole = person.role === 'charge' ? 'charge' : 'bedside';
        marker.dataset.uniformColor = color;
        marker.style.setProperty('--staff-uniform-color',color);
        marker.querySelector('.avatar-scrubs').setAttribute('fill',color);
      }
      const changed = previous && previous.floor === person.floor && Math.hypot(position.x-previous.x,position.y-previous.y) > .05;
      if(state === 'moving' && changed) {
        const heading = Math.atan2(position.y-previous.y,position.x-previous.x)*180/Math.PI;
        marker.querySelector('.staff-direction').setAttribute('transform','translate(1.1 .08) rotate('+heading+')');
        marker.dataset.staffDirection = 'observed';
      } else if(state !== 'moving' || !previous) delete marker.dataset.staffDirection;
      observations.set(person.id,{x:position.x,y:position.y,floor:person.floor});
      const incident = S.incidents.find(item => item.id === person.incident);
      if(incident?.bed) marker.dataset.staffDestination = incident.bed; else delete marker.dataset.staffDestination;
      const identity = typeof staffIdentity === 'function' && !doctor ? staffIdentity(person) : person.id;
      const description = roleName(person,doctor)+' '+identity+' · '+person.unit+' · '+statusName(state)+(incident?.bed?' · '+t('목적 병상 ','Destination ')+incident.bed:'')+' · '+t('시뮬레이션','Simulation');
      marker.setAttribute('aria-label',description);
      marker.dataset.staffSelected = String(typeof picked !== 'undefined' && picked === (doctor?'MD:':'N:')+person.id);
    }
    for(const id of observations.keys()) if(!active.has(id)) observations.delete(id);
    selection();
    updateToolbar();
  }
  function playbackActive() {
    return Boolean(window.SICUUnifiedReplay?.describe().playing) || typeof S !== 'undefined' && Boolean(S?.running) || /^(Pause|일시정지)$/.test(q('#sandboxPlay')?.textContent.trim() || '');
  }
  function activeProfile() {
    return typeof S !== 'undefined' && S ? S.hospital_profiles?.[Network.hospital] || S.demo_profile : '';
  }
  function updateToolbar() {
    document.body.dataset.staffPlayback = playbackActive() ? 'playing' : 'paused';
    if(!toolbarReady) return;
    const play=q('#sandboxPlay'),apply=q('#sandboxApply'),profile=q('#sandboxProfile'),loading=Boolean(apply?.disabled);
    if(startRequested && play && !play.disabled) { startRequested=false;play.click(); }
    else if(startRequested && !loading && q('#sandboxStatus')?.textContent && play?.disabled) startRequested=false;
    const activeOption=profile && [...profile.options].find(option=>option.value===activeProfile());
    q('#staffScenarioName').textContent=activeOption?.textContent || '';
    q('#staffReplayTime').textContent=q('#sandboxMinute')?.textContent || '07:00';
    q('#staffReplayToggle').disabled=loading;
    q('#staffReplayToggle').textContent=loading?t('불러오는 중…','Loading…'):playbackActive()?t('Ⅱ 일시정지','Ⅱ Pause'):t('▶ 재생','▶ Play');
    q('#staffReplaySettings').textContent=t('시나리오 설정','Scenario settings');
    q('#staffSimLabel').textContent=t('가상 시나리오','Fictional scenario');
  }
  function setupToolbar() {
    const map=q('.floor-plan');if(!map || !q('#sandboxApply')) return;
    const bar=document.createElement('div');bar.id='staffMapToolbar';bar.dataset.noTranslate='';
    bar.innerHTML='<div class="staff-role-key"></div><div class="staff-replay-controls"><small id="staffSimLabel"></small><span id="staffScenarioName"></span><time id="staffReplayTime"></time><button id="staffReplayToggle" type="button"></button><button id="staffReplaySettings" type="button"></button></div>';
    const caption=q('.map-caption') || map.querySelector(':scope>p.tag');
    if(caption) caption.after(bar);else map.prepend(bar);
    function renderRoles() {
      bar.querySelector('.staff-role-key').innerHTML=[[{id:'N',role:'bedside'},false],[{id:'C',role:'charge'},false],[{id:'MD'},true]].map(([person,doctor])=>'<span><svg viewBox="-1.3 -1.7 2.6 3.15" aria-hidden="true">'+window.SICUStaffVisuals.avatar(person,doctor)+'</svg>'+roleName(person,doctor)+'</span>').join('');
      updateToolbar();
    }
    q('#staffReplayToggle').onclick=()=>{
      const play=q('#sandboxPlay'),apply=q('#sandboxApply');
      if(!play.disabled) play.click();
      else if(!apply.disabled){
        const profile=q('#sandboxProfile');
        if([...profile.options].some(option=>option.value===activeProfile())) profile.value=activeProfile();
        startRequested=true;apply.click();
      }
      updateToolbar();
    };
    q('#staffReplaySettings').onclick=()=>{q('#demoTools').open=true;q('#publicSandbox').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});q('#sandboxProfile').focus({preventScroll:true});};
    toolbarReady=true;
    const observer=new MutationObserver(updateToolbar);
    for(const selector of ['#sandboxPlay','#sandboxApply','#sandboxMinute','#sandboxStatus']) observer.observe(q(selector),{attributes:true,attributeFilter:['disabled'],childList:true,subtree:true,characterData:true});
    q('#sandboxProfile').addEventListener('change',updateToolbar);
    document.addEventListener('icu-language',()=>queueMicrotask(()=>{renderRoles();decorate();}));
    renderRoles();decorate();
  }
  const nativeDetail=window.detail;
  window.detail=function(){const result=nativeDetail.apply(this,arguments);selection();return result;};
  const nativeSelectPatient=window.selectPatient;
  window.selectPatient=function(bed){
    // A public bed dialog clears staff selection without activating the
    // private patient-panel workflow keyed by a picked bed identifier.
    if(typeof picked!=='undefined')picked=null;
    const result=nativeSelectPatient.apply(this,arguments);selection();return result;
  };
  const nativeDraw=window.draw;
  window.draw=function(){const result=nativeDraw.apply(this,arguments);decorate();return result;};
  window.SICUStaff=Object.freeze({decorate,syncSelection:selection,syncPlayback:updateToolbar});
  const previewTarget=target=>target?.closest?.('#floors .nurse[data-staff-id]');
  const preview=node=>{
    previewNode=node;previewNurseId=node?.dataset.staffId||'';
    selection();
  };
  document.addEventListener('pointerover',event=>{
    const node=previewTarget(event.target);
    if(node&&!node.contains(event.relatedTarget))preview(node);
  });
  document.addEventListener('pointerout',event=>{
    const node=previewTarget(event.target);
    if(node&&!node.contains(event.relatedTarget))preview(previewTarget(document.activeElement));
  });
  document.addEventListener('focusin',event=>{
    const node=previewTarget(event.target);if(node)preview(node);
  });
  document.addEventListener('focusout',event=>{
    const node=previewTarget(event.target);if(node&&!node.contains(event.relatedTarget))preview(previewTarget(event.relatedTarget));
  });
  window.addEventListener('blur',()=>preview(null));
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',setupToolbar);else setupToolbar();
})();
