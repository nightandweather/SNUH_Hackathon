/* Explicit browser-local fictional movement demonstrations. Never derives death from vitals. */
const Transfers=(()=>{
 const NS='http://www.w3.org/2000/svg',clone=x=>structuredClone(x);
 const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const text=(ko,en)=>typeof I18n!=='undefined'&&I18n.language==='ko'?ko:en;
 const definitions={
  arrival:{title:['ICU 입실 이송','Transport into ICU'],stages:[['입실 예정','Admission planned'],['이송원 환자 인수','Porter receives patient'],['ICU로 이송 중','Transporting into ICU'],['병상 인계 중','Bedside handoff'],['입실 완료','Admission complete']],route:['수술실 → ICU','Operating room → ICU'],color:'#256e9d'},
  departure:{title:['일반병동으로 전동','Transfer to ward'],stages:[['전동 예정','Transfer planned'],['이송원에게 인계','Handoff to porter'],['병상 출발','Leaving bed'],['일반병동으로 이송','Transport to ward'],['이송·병상 정리 완료','Transport and turnover complete']],route:['ICU → 일반병동','ICU → general ward'],color:'#256e9d'},
  or_death:{title:['수술 중 사망 · 입실 취소','Death in OR · admission cancelled'],stages:[['수술 후 ICU 예약','Postoperative ICU reservation'],['수술실 사망 통보','Death notification from OR'],['ICU 입실 취소 확인','ICU admission cancellation confirmed'],['예약 정리 · 병상 보류','Reservation reconciliation · bed held'],['예약 해제 완료','Reservation released']],route:['수술실 통보 → ICU 예약 취소','OR notification → ICU reservation cancelled'],color:'#6b576f'},
  icu_death:{title:['ICU 병상 내 사망','Death in ICU'],stages:[['사망 확인 (모의 기록)','Death confirmed (simulation)'],['사후 이송 대기','Awaiting post-mortem transport'],['이송원 인계·출발','Porter handoff and departure'],['사후 이송 · 병상 정리','Post-mortem transport · bed turnover'],['이송·병상 정리 완료','Transport and turnover complete']],route:['ICU → 사후 이송 목적지','ICU → post-mortem destination'],color:'#6b576f'}
 };
 const minutes=[0,2,5,8,10];let base=null,active=null,timer=null,lastFingerprint='',panel=null;
 const automatic=new Map();let autoTimer=null;
 const def=e=>definitions[e.kind],words=a=>text(a[0],a[1]);
 const all=d=>d.floors.flatMap(f=>f.units.flatMap(u=>u.beds));
 const status=(key,label,color,ink='#fff')=>({key,label,color,ink});
 function projectEvent(data,event){
  const out=clone(data),bed=all(out).find(b=>b.id===event.bed);if(!bed)return out;
  const k=event.kind,s=event.stage,d=def(event);let st;
  bed.flow={...event,label:words(d.stages[s]),route:words(d.route),title:words(d.title),suppressVitals:true};
  bed.unavailable=false;
  if(k==='arrival'){
   bed.patient=null;bed.reservation={source:'simulation_schedule',label:words(d.title),expected_t:data.t+10,note:words(d.stages[s])};
   if(s<3)st=status('reserved',s===0?text('예약','RESERVED'):text('입실 이송 중','IN TRANSIT'),'#fff1b8','#67521c');
   else if(s===3){bed.unavailable=true;st=status('transit',text('인계 중','HANDOFF'),'#256e9d');}
   else{bed.reservation=null;bed.patient={...clone(event.patient),pid:'SIM-TRANSFER-'+event.bed,source:'synthetic',dx:'Fictional postoperative admission',risk:15,abn:[],simulation_override:null,arrest:false,vent:0,pressor:0,devices:{iv:true},extra_observations:{},care_indicators:{calendar_day:0,cpr_today:false,surgery_today:true,pressor_unstable:false},vitals:{hr:82,sbp:118,map:82,spo2:98,rr:18},admit_t:event.admitTime??data.t,transfer_review:{}};bed.flow.suppressVitals=false;st=typeof Readiness!=='undefined'?Readiness.status(bed.patient):status('watch',text('입실 완료 · 검토','ADMITTED · REVIEW'),'#3475c5');}
  }else if(k==='or_death'){
   bed.patient=null;
   if(s===0){bed.reservation={label:words(d.title),source:'simulation_schedule'};st=status('reserved',text('수술 후 예약','RESERVED'),'#fff1b8','#67521c');}
   else{bed.reservation=null;bed.unavailable=s<4;st=s<4?status('cancelled',text('입실 취소 · 보류','CANCELLED · HOLD'),'#e6dfeb','#584562'):status('empty',text('빈 병상','EMPTY'),'#e7ebf0','#475569');}
  }else{
   bed.reservation=null;
   if(s<2){bed.patient=clone(event.patient);if(k==='icu_death'){bed.patient.vitals={hr:null,sbp:null,map:null,spo2:null,rr:null};bed.patient.abn=[];bed.patient.arrest=false;bed.patient.simulation_override=null;bed.patient.care_indicators={};bed.patient.devices={};}st=k==='icu_death'?status('deceased',text('사망 · 이송 대기','DECEASED · WAIT'),'#6b576f'):status('transit',text('전동 대기','TRANSFER WAIT'),'#256e9d');}
   else{bed.patient=null;bed.unavailable=s<4;st=s<4?status('turnover',text('이송·병상 정리','TRANSPORT / TURNOVER'),'#dce6f1','#294964'):status('empty',text('빈 병상','EMPTY'),'#e7ebf0','#475569');}
  }
  if(s===4&&k!=='arrival'&&event.nextReservation){
   bed.reservation={source:'simulation_schedule',label:text('다음 입실 예약','Next admission reserved')};
   st=status('reserved',text('다음 입실 예약','NEXT ADMISSION RESERVED'),'#fff1b8','#67521c');
  }
  bed.flow.status=st;bed.flow.ink=st.ink;
  // Removed from the current ICU bed; death is an explicit fixture, never a vital-sign inference.
  if(k==='icu_death'||!bed.patient){out.incidents=(out.incidents||[]).filter(i=>i.bed!==event.bed);}
  if(!bed.patient){out.nurses.forEach(n=>{n.beds=n.beds.filter(b=>b!==event.bed);n.cover=n.cover.filter(b=>b!==event.bed);});}
  return out;
 }
 function fingerprint(d){return JSON.stringify([d.seed,d.hospital_profiles,d.demo_profile]);}
 function patientKey(b){return b?.patient?`${b.patient.pid}:${b.patient.admit_t??''}`:'';}
 function automaticProjection(data,event,elapsed){
  const old=event.oldBed,next=event.newBed,leaving=!!old.patient,arriving=!!next.patient;
  const departureMs=leaving?4000:0,total=departureMs+(arriving?4000:0);
  if(elapsed>=total)return {data,event:null,done:true};
  const kind=leaving&&elapsed<departureMs?'departure':'arrival',local=kind==='departure'?elapsed:elapsed-departureMs;
  const stage=Math.min(3,Math.floor(local/1000));
  const e={kind,bed:next.id,unit:event.unit,patient:kind==='departure'?old.patient:next.patient,stage,previousStage:Math.max(0,stage-1),motionAt:event.started+ (kind==='arrival'?departureMs:0)+stage*1000,startClock:event.clock,automatic:true};
  let out=projectEvent(data,e);const b=all(out).find(x=>x.id===next.id);
  if(kind==='departure'&&stage===3){b.patient=null;b.unavailable=true;b.flow.status=status('turnover',text('병상 정리','BED TURNOVER'),'#dce6f1','#294964');}
  return {data:out,event:e,done:false};
 }
 function stopAutomatic(){if(autoTimer)clearInterval(autoTimer);autoTimer=null;automatic.clear();}
 function project(d){
  if(active&&fingerprint(d)!==lastFingerprint)clear(false);
  if(!active&&base&&base!==d){
   const prior=new Map(all(base).map(b=>[b.id,b]));
   for(const f of d.floors)for(const u of f.units)for(const b of u.beds){
    const old=prior.get(b.id);
    if(!old||patientKey(old)===patientKey(b)||[old.patient,b.patient].some(p=>p&&p.source!=='synthetic'))continue;
    automatic.set(b.id,{oldBed:clone(old),newBed:clone(b),unit:u.id,started:performance.now(),clock:d.clock});
   }
  }
  base=d;if(active)return projectEvent(d,active);
  let result=d;
  for(const [id,event] of automatic){const projected=automaticProjection(result,event,performance.now()-event.started);if(projected.done)automatic.delete(id);else{result=projected.data;event.visible=projected.event;}}
  if(automatic.size&&!autoTimer)autoTimer=setInterval(()=>{if(base)acceptState(base);},250);
  if(!automatic.size&&autoTimer){clearInterval(autoTimer);autoTimer=null;}
  return result;
 }
 function stop(){if(timer)clearInterval(timer);timer=null;}
 function clear(redraw=true){stop();stopAutomatic();active=null;if(redraw&&base)acceptState(base);}
 function clearForScope(d){stop();stopAutomatic();active=null;return base||d;}
 function scopeUnit(){if(!base)return null;const us=base.floors.flatMap(f=>f.units).filter(u=>(u.hospital_id||'A')===Network.hospital);const ward=document.querySelector('#wardScope')?.value;return us.find(u=>u.id===ward)||us.find(u=>u.id.endsWith('SICU')&&!u.id.endsWith('CSICU')&&!u.id.endsWith('NSICU')&&!u.id.endsWith('TSICU'))||us[0];}
 function start(){
  stop();stopAutomatic();const u=scopeUnit(),kind=document.querySelector('#transferKind').value;
  if(!u||u.beds.some(b=>b.patient&&b.patient.source!=='synthetic'))return;
  const vacant=['arrival','or_death'].includes(kind),bed=vacant?(u.beds.find(b=>!b.patient&&b.reservation)||u.beds.find(b=>!b.patient)):([...u.beds].reverse().find(b=>b.patient&&!b.patient.simulation_override)||u.beds.find(b=>b.patient));
  if(!bed){document.querySelector('#transferStatus').textContent=text('시연에 필요한 병상 상태가 없습니다. 다른 시나리오를 선택해 주세요.','No suitable bed for this demonstration. Select another scenario.');return;}
  const patient=bed.patient||u.beds.find(b=>b.patient)?.patient;if(!patient)return;
  active={kind,bed:bed.id,unit:u.id,stage:0,patient:clone(patient),nextReservation:!!document.querySelector('#transferReserveNext')?.checked,admitTime:base.t+10,motionAt:performance.now(),startClock:base.clock};lastFingerprint=fingerprint(base);acceptState(base);
 }
 function step(n){if(!active)return;active.previousStage=active.stage;active.motionAt=performance.now();active.stage=Math.max(0,Math.min(4,n));if(active.stage===4)stop();acceptState(base);}
 function svgEl(tag,attrs,parent){const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));parent.appendChild(e);return e;}
 function draw(){
  ensurePanel();updatePanel();document.querySelectorAll('.transfer-overlay').forEach(e=>e.remove());
  for(const event of active?[active]:[...automatic.values()].map(e=>e.visible).filter(Boolean))drawEvent(event);
 }
 function drawEvent(active){
  const bed=S.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).find(b=>b.id===active.bed);if(!bed)return;
  const entry=bedEl[bed.id],svg=entry?.r.ownerSVGElement;if(!svg)return;
  const unit=S.floors.flatMap(f=>f.units).find(u=>u.id===active.unit),d=def(active),s=active.stage;
  const g=svgEl('g',{'class':'transfer-overlay','pointer-events':'none','aria-label':words(d.title)+' · '+words(d.stages[s]),role:'img'},svg);
  const y=unit.h/2,doorX=unit.x+unit.w-.7,nearX=bed.x,nearY=bed.y<y?bed.y+2.1:bed.y-2.1;
  if(active.kind==='or_death'){
   svgEl('path',{d:`M${doorX} ${y}H${nearX}V${nearY}`,fill:'none',stroke:d.color,'stroke-width':'.07','stroke-dasharray':'.2 .16'},g);
   const line=svgEl('text',{x:nearX,y:nearY,'text-anchor':'middle','font-size':'.55',fill:d.color,'paint-order':'stroke',stroke:'#fff','stroke-width':'.18'},g);line.textContent=s===0?text('수술실 → 예약 병상','OR → reserved bed'):text('수술실 통보 · 입실 취소','OR notice · admission cancelled');
  }else if(s<4){
   const incoming=active.kind==='arrival',points=incoming?[[doorX,y],[nearX,y],[nearX,nearY]]:[[nearX,nearY],[nearX,y],[doorX,y]];
   svgEl('path',{d:points.map(([x,y],i)=>`${i?'L':'M'}${x} ${y}`).join(' '),fill:'none',stroke:d.color,'stroke-width':'.09','stroke-dasharray':'.3 .18',opacity:'.8'},g);
   const progress=s/3,dist=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1])),total=dist.reduce((a,b)=>a+b,0);let rest=progress*total,pos=points[0],from=points[0],to=points[1];
   for(let i=0;i<dist.length;i++){from=points[i];to=points[i+1];if(rest<=dist[i]||i===dist.length-1){const ratio=dist[i]?Math.min(1,rest/dist[i]):0;pos=[from[0]+(to[0]-from[0])*ratio,from[1]+(to[1]-from[1])*ratio];break}rest-=dist[i];}
   const facing=(to[0]-from[0])<0?-1:1;
   const cart=svgEl('g',{},g);
   const elapsed=(performance.now()-(active.motionAt||0))/1000,previous=(active.previousStage??s)/3;
   if(previous!==progress&&elapsed<1.5&&!matchMedia('(prefers-reduced-motion: reduce)').matches){svgEl('animateMotion',{path:points.map(([x,y],i)=>`${i?'L':'M'}${x} ${y}`).join(' '),dur:'1.5s',begin:`-${Math.max(0,elapsed)}s`,keyPoints:`${previous};${progress}`,keyTimes:'0;1',calcMode:'linear',fill:'freeze'},cart).beginElementAt(-Math.max(0,elapsed));}else cart.setAttribute('transform',`translate(${pos[0]} ${pos[1]})`);
   svgEl('rect',{x:-2.6,y:-1.8,width:5.2,height:3.1,rx:'.35',fill:'#ffffff',stroke:d.color,'stroke-width':'.07'},cart);
   const icon=svgEl('g',{transform:`scale(${facing} 1)`,fill:'none',stroke:d.color,'stroke-width':'.10','stroke-linecap':'round','stroke-linejoin':'round'},cart);
   svgEl('circle',{cx:-1.7,cy:-.65,r:'.25',fill:d.color},icon);svgEl('path',{d:'M-1.7 -.35v.8m0-.55 .55 .35H-.7m-1 .25-.3 .6m.3-.6 .3 .6M-.8 .35H1.8V-.05M-.7 .35v.35m2.25-.35v.35'},icon);svgEl('circle',{cx:-.5,cy:.8,r:'.16'},icon);svgEl('circle',{cx:1.45,cy:.8,r:'.16'},icon);
   if(active.kind==='icu_death')svgEl('path',{d:'M-.7 .15Q-.5-.65 .3-.45L1.6-.05V.15Z',fill:'#e6dfeb'},icon);
   else{svgEl('circle',{cx:-.4,cy:-.1,r:'.22'},icon);svgEl('path',{d:'M-.15-.05H.6L1.45 .1'},icon);}
   const txt=svgEl('text',{x:0,y:-1.2,'text-anchor':'middle','font-size':'.46',fill:d.color},cart);txt.textContent=text('이송원','PORTER')+' · '+(incoming?'OR → ICU':'ICU →');
  }
  const caption=svgEl('text',{x:unit.x+unit.w/2,y:unit.h+1.65,'text-anchor':'middle','font-size':'.52',fill:d.color,'paint-order':'stroke',stroke:'#fff','stroke-width':'.15'},g);caption.textContent=`${bed.id} · ${words(d.stages[s])} · +${minutes[s]} min`;
 }
 function ensurePanel(){if(panel)return;panel=document.createElement('section');panel.id='transferPanel';panel.dataset.noTranslate='';panel.innerHTML='<h3 id="transferTitle"></h3><p id="transferNote"></p><div class="transfer-controls"><select id="transferKind" aria-label="Transfer scenario"></select><button id="transferStart"></button><button id="transferPlay"></button><button id="transferNext"></button><button id="transferClear"></button><label><input type="checkbox" id="transferReserveNext"><span id="transferReserveLabel"></span></label></div><p id="transferStatus" role="status" aria-live="polite"></p><ol id="transferSteps"></ol>';document.querySelector('#floors').before(panel);
  document.querySelector('#transferKind').onchange=updatePanel;document.querySelector('#transferStart').onclick=start;document.querySelector('#transferNext').onclick=()=>{stop();step(active.stage+1)};document.querySelector('#transferClear').onclick=()=>clear();document.querySelector('#transferPlay').onclick=()=>{if(timer){stop();updatePanel();return}if(!active)return;if(active.stage===4)step(0);timer=setInterval(()=>step(active.stage+1),2200);updatePanel()};
 }
 function updatePanel(){if(!panel)return;const selected=document.querySelector('#transferKind').value||'arrival',u=scopeUnit();document.querySelector('#transferTitle').textContent=text('이송·입실 취소·사망 시연','Transport, cancellations and death scenarios');document.querySelector('#transferNote').textContent=text('가상 지도 시연 · 현재 선택 병동에만 적용됩니다. 시연 단계는 이 브라우저에서만 바뀌며 실제 입퇴실 기록·이송 지시를 변경하지 않습니다.','Fictional map demonstration for the selected ward. Stages change only in this browser; no real admission records or transport orders are changed.');
  const sel=document.querySelector('#transferKind');const opts=Object.entries(definitions).map(([key,v])=>`<option value="${key}">${E(words(v.title))}</option>`).join('');if(sel.innerHTML!==opts){sel.innerHTML=opts;sel.value=selected;}
  document.querySelector('#transferStart').textContent=text('시연 적용','Apply demo');document.querySelector('#transferPlay').textContent=timer?text('일시정지','Pause'):text('자동 재생','Play stages');document.querySelector('#transferNext').textContent=text('다음 단계','Next stage');document.querySelector('#transferClear').textContent=text('시연 해제','Clear demo');
  document.querySelector('#transferReserveLabel').textContent=text('퇴실 후 다음 입실 예약','Reserve next admission after departure');document.querySelector('#transferReserveNext').disabled=selected==='arrival';
  document.querySelector('#transferStart').disabled=!u||u.beds.some(b=>b.patient&&b.patient.source!=='synthetic');document.querySelector('#transferNext').disabled=!active||active.stage===4;document.querySelector('#transferPlay').disabled=!active;document.querySelector('#transferClear').disabled=!active;
  const current=active?`${active.bed} · ${words(def(active).route)} · ${words(def(active).stages[active.stage])} · +${minutes[active.stage]} min`:text(`${u?.id||''} · 시나리오를 선택하고 적용하세요.`,`${u?.id||''} · Select and apply a scenario.`);const label=document.querySelector('#transferStatus');if(label.textContent!==current)label.textContent=current;
  const autoCount=[...automatic.keys()].filter(id=>S.floors.some(f=>f.units.some(u=>u.beds.some(b=>b.id===id)))).length;if(autoCount)label.textContent=text(`${autoCount}개 병상 환자 변경 · 퇴실/정리/입실 이송 자동 재생 중`,`${autoCount} bed changes · automatic departure / turnover / arrival`);
  document.querySelector('#transferSteps').innerHTML=active?def(active).stages.map((a,i)=>`<li class="${i===active.stage?'current':i<active.stage?'done':''}" ${i===active.stage?'aria-current="step"':''}>${E(words(a))}<small>+${minutes[i]} min</small></li>`).join(''):'';
 }
 function card(b){return `<div class="flow-card-note" data-no-translate><b>${E(b.flow.title)}</b><p>${E(b.flow.label)}</p><small>${E(b.flow.route)} · +${minutes[b.flow.stage]} min</small><p><b>${E(b.flow.status.label)}</b> · ${text('지도·환자 표 동시 반영','Map and patient list synchronized')}</p>${b.patient&&b.flow.stage===4?`<div>${E(b.patient.pid)} · HR ${b.patient.vitals.hr} · MAP ${b.patient.vitals.map} · SpO₂ ${b.patient.vitals.spo2}%</div>`:''}<p>${text('가상 지도 시연','Fictional map demonstration')}</p></div>`;}
 function openDetails(id){const b=typeof S==='undefined'?null:all(S).find(b=>b.id===id);if(!b?.flow)return false;let dialog=document.querySelector('#transferDetail');if(!dialog){dialog=document.createElement('dialog');dialog.id='transferDetail';dialog.dataset.noTranslate='';document.body.append(dialog);}dialog.innerHTML=`<div class="transfer-dialog-head"><h2>${E(id)}</h2><button>${text('✕ 닫기','✕ Close')}</button></div>${card(b)}<p>${b.flow.kind==='or_death'?text('사망 발생 장소는 수술실입니다. ICU 입실은 취소되며, 예약 정리가 끝나기 전에는 수용 가능한 빈 병상으로 집계하지 않습니다.','The death occurred in the operating room. ICU admission is cancelled; the bed remains unavailable until reservation reconciliation is complete.'):b.flow.kind==='icu_death'?text('명시적으로 설정한 가상 사망 기록입니다. 활력징후로 사망을 추정하지 않습니다. 사후 이송과 병상 정리 완료 전에는 빈 병상이 아닙니다.','This is an explicitly configured fictional death, not inferred from vital signs. The bed is not available until post-mortem transport and turnover finish.'):text('이송원과 이동 경로를 보여주는 시연입니다. 실제 의료진 호출이나 이송 지시를 전송하지 않습니다.','This demonstrates porter movement and the transport route. No real dispatch or transfer orders are sent.')}</p>`;dialog.querySelector('button').onclick=()=>dialog.close();dialog.showModal();dialog.querySelector('button').focus();return true;}
 return {project,projectEvent,automaticProjection,busy:()=>automatic.size>0,draw,card,openDetails,clearForScope};
})();
