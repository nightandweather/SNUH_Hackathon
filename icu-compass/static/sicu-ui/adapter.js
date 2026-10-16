/* SICU LINK presentation adapter. No fetch, clinical inference or data replacement.
 * The existing clinical controller owns all patient IDs, observations, replay and API calls.
 */
(function(){
 'use strict';
 const q=s=>document.querySelector(s),NS='http://www.w3.org/2000/svg';
 let view='ward',historyOpen=false;
 const label=(ko,en)=>lang==='en'?en:ko;
 const labels={ward:['병동 현황','Ward'],patients:['환자 목록 · 검사','Patients & tests'],planning:['31일 운영 계획','31-day plan'],sources:['데이터 연결','Data connection']};
 function node(tag,attrs={}){const el=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);return el;}
 function setView(next){
  if(!Object.hasOwn(labels,next))return;
  view=next;document.body.dataset.sicuView=view;
  if(view==='planning')q('#workbookPlan').open=true;
  if(view==='sources')q('.research-notes').open=true;
  syncLabels();
 }
 function syncLabels(){
  const updated=q('#refreshStamp span:last-child time');if(updated)updated.textContent=new Date(SICU_UPDATED_AT).toLocaleString(lang==='en'?'en-GB':'ko-KR',{timeZone:'Asia/Seoul'})+' KST';
  q('#sicuViewTitle').textContent=label(...labels[view]);
  q('#sicuSubtitle').textContent=label('환자 상태 · 간호 지원 · 이송 흐름','Patient status · Care support · Transfers');
  q('#sicuIdentity').textContent=label('K-MIMIC · GS 환자 기록','K-MIMIC · GS patient records');
  for(const b of document.querySelectorAll('#sicuNav [data-sicu-view]')){b.textContent=label(...labels[b.dataset.sicuView]);b.setAttribute('aria-pressed',String(b.dataset.sicuView===view));}
  q('#sicuToolsLabel').textContent=label('시점·시연 설정','Time & simulation settings');
  q('#sicuClinicalToolsLabel').textContent=label('개별 환자 기록 재생','Patient record replay');
  q('#sicuStaffToolsLabel').textContent=label('간호사·의사 수동 시연','Manual staff simulation');
  q('#sicuKey').textContent=label('RED 전실 보류 · BLUE 검토 · GREEN 후보 · 노랑 예약 · 회색 빈 병상 — 월간표 시나리오 색상','RED hold · BLUE review · GREEN candidate · Yellow reserved · Gray empty — monthly scenario colors');
 }
 function init(){
  if(q('#sicuNav'))return;
  document.body.classList.add('sicu-private');document.body.dataset.sicuView='ward';
  const header=q('body > header'),brand=document.createElement('a');brand.className='sicu-brand';brand.href='#ward';brand.setAttribute('aria-label','SICU LINK');
  brand.innerHTML='<img alt="" src="'+SICU_ASSETS.logo+'"><span>SICU <b>LINK</b><small>TEAM 4</small></span>';
  brand.onclick=e=>{e.preventDefault();setView('ward');window.scrollTo({top:0,behavior:'smooth'});};
  const identity=document.createElement('span');identity.id='sicuIdentity';identity.className='sicu-identity';
  header.prepend(brand,identity);
  const nav=document.createElement('nav');nav.id='sicuNav';nav.setAttribute('aria-label','Workspace');
  for(const key of Object.keys(labels)){const b=document.createElement('button');b.type='button';b.dataset.sicuView=key;b.onclick=()=>setView(key);nav.append(b);}
  header.after(nav);
  const heading=document.createElement('section');heading.id='sicuHeading';heading.innerHTML='<div><span class="sicu-eyebrow">SURGICAL ICU · CARE COORDINATION</span><h1 id="sicuViewTitle"></h1><p id="sicuSubtitle"></p></div><div id="sicuCounters"></div>';
  nav.after(heading);q('#sicuCounters').append(q('#bedCounts'));
  q('.scenario-card').hidden=true;
  const controls=document.createElement('details');controls.id='sicuTools';controls.innerHTML='<summary id="sicuToolsLabel"></summary>';
  q('.scopebar').append(controls);controls.append(q('#simulationControls'));q('#simulationControls').open=true;
  const stamp=q('#refreshStamp');nav.before(stamp);
  const info=document.createElement('footer');info.id='sicuFooter';document.body.append(info);info.append(q('#notice'),q('#src'));
  const record=document.createElement('details');record.id='sicuRecordTools';record.innerHTML='<summary id="sicuClinicalToolsLabel"></summary>';q('#recordPlayback').before(record);record.append(q('#recordPlayback'));
  const staff=document.createElement('details');staff.id='sicuStaffTools';staff.innerHTML='<summary id="sicuStaffToolsLabel"></summary>';record.after(staff);controls.append(record,staff);record.append(q('#slots'));
  const key=document.createElement('p');key.id='sicuKey';q('#floors').before(key);
  q('#showMonthlyPlan').addEventListener('click',()=>setView('planning'));
  q('#showCasePool').addEventListener('click',()=>setView('patients'));
  q('#planTable').addEventListener('click',e=>{if(e.target.closest('[data-monthly-row]'))setView('ward');});
  syncLabels();
 }
 function decorateMap(){
  const svg=q('#floors .ward-map-viewport > svg');if(!svg)return;
  for(const bed of svg.querySelectorAll('[data-map-bed]')){
   if(bed.dataset.sicuDecorated)continue;bed.dataset.sicuDecorated='true';
   const i=Number(bed.dataset.mapBed),x=4+i%4*8,y=i<4?2.2:19.8,rect=bed.querySelector('.bed');
   rect.style.stroke=rect.style.fill;rect.style.fillOpacity=bed.dataset.mapStatus==='empty'?'0.65':bed.dataset.mapStatus==='reserved'?'0.75':'0.13';
   const occupied=bed.hasAttribute('data-case'),img=node('image',{href:occupied?SICU_ASSETS.bed:SICU_ASSETS.empty,x:x+.8,y:y-1.7,width:2.5,height:3.35,'pointer-events':'none'});bed.append(img);
   if(occupied){const head=node('ellipse',{cx:x+2.05,cy:y-.85,rx:.26,ry:.21,fill:'#c6d7e9',stroke:'#577a9e','stroke-width':'.04','pointer-events':'none'});bed.append(head);}
   const icons=bed.querySelector('.bed-care-icons');if(icons){icons.setAttribute('transform',`translate(${x-3.15} ${y-1.45}) scale(1.1)`);Array.from(icons.children).forEach((icon,n)=>icon.setAttribute('transform',`translate(${n%3*.97} ${Math.floor(n/3)*.91})`));}
   const equipment=bed.querySelector('.bed-equipment-summary');if(equipment){equipment.setAttribute('x',x-3.15);equipment.setAttribute('y',y+.83);equipment.setAttribute('text-anchor','start');const full=equipment.textContent;equipment.textContent=full.length>23?full.slice(0,22)+'…':full;const title=node('title');title.textContent=full;equipment.append(title);}
   const state=bed.querySelector('.bed-t');state.setAttribute('x',x-3.15);state.setAttribute('y',y+1.42);state.setAttribute('text-anchor','start');
  }
  if(!svg.querySelector('.sicu-station')){const g=node('g',{class:'sicu-station','pointer-events':'none'});g.innerHTML=SICUSpatialSymbols.station();const inner=g.querySelector('svg');inner.setAttribute('x','12');inner.setAttribute('y','8');inner.setAttribute('width','8');inner.setAttribute('height','2.4');const txt=node('text',{x:16,y:10.65,'text-anchor':'middle','font-size':'.42',fill:'#5e7690'});txt.textContent=label('간호 스테이션','Nursing station');g.append(txt);svg.insertBefore(g,svg.querySelector('[data-map-bed]'));}
  for(const person of svg.querySelectorAll('[data-sim-staff]')){
   const old=person.querySelector('.staff-avatar');if(!old||old.classList.contains('sicu-staff-avatar'))continue;
   const id=person.dataset.simStaff,doctor=id==='Dr.',charge=id==='NC',holder=node('g');holder.innerHTML=SICUStaffVisuals.avatar({id,role:charge?'charge':doctor?'doctor':'nurse'},doctor);
   const avatar=holder.firstElementChild;
   if(id==='N2'||id==='N4'){
    avatar.querySelector('.sicu-clinician-hair-back')?.remove();
    const hair=avatar.querySelector('.sicu-clinician-hair-front');
    if(hair)hair.setAttribute('d','M-.49-1.02q-.01-.47.49-.47t.49.47Q.25-1.15 0-1.15t-.49.13Z');
    avatar.querySelector('.sicu-nurse-hair-part')?.remove();
    avatar.dataset.character='male';
   }else avatar.dataset.character=doctor?'male':'female';
   // Preserve upstream work-state fill and care-history outline.
   for(const [selector,attr] of [['.avatar-scrubs','fill'],['.avatar-care','stroke-dasharray']]){const v=old.querySelector(selector)?.getAttribute(attr);if(v)avatar.querySelector(selector).setAttribute(attr,v);}
   old.replaceWith(avatar);
  }
 }
 function sync(){init();syncLabels();const monthly=q('#monthlyReplay');if(monthly&&!monthly.classList.contains('sicu-monthly')){monthly.classList.add('sicu-monthly');q('main').before(monthly);}
  const events=monthly?.querySelector('details');if(events&&!events.dataset.sicuHistory){events.dataset.sicuHistory='true';events.open=historyOpen;events.addEventListener('toggle',()=>{historyOpen=events.open;});}
  const staff=q('#staffSimulationPanel');if(staff&&staff.parentElement!==q('#sicuStaffTools'))q('#sicuStaffTools').append(staff);
  decorateMap();
 }
 const upstreamRender=render;
 render=function(){const result=upstreamRender.apply(this,arguments);sync();return result;};
 window.SICUPrivateUI=Object.freeze({sync,setView});sync();
})();
