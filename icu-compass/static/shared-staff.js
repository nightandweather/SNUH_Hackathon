/* Browser-local fictional personnel only. Never writes to K-MIMIC case data. */
const StaffSimulation=(()=>{
 'use strict';
 const NS='http://www.w3.org/2000/svg';
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const scenes={
  calm:{name:['평온한 근무','Calm shift'],steps:[['정기 라운딩','Routine rounding'],['관찰과 기록','Observation and documentation'],['간호 준비','Care preparation'],['업무 정리','Task review'],['인계 준비 완료','Ready for handover']]},
  busy:{name:['간호 업무 집중','Busy shift'],steps:[['동시 간호 요청','Concurrent care requests'],['업무 우선순위 조정','Prioritize tasks'],['간호사 지원 배치','Nursing support'],['검체·기구 정리','Specimen and equipment tasks'],['업무 재분담 완료','Tasks redistributed']]},
  help:{name:['응급 대응 · 지원 호출','Response and standby call'],steps:[['대응 요청 · 모의','Simulated response request'],['대기 간호사 호출','Call standby nurse'],['간호사 침상 이동','Nurses approach bedside'],['Dr. 도착 · 모의','Dr. arrives in simulation'],['팀 대응 · 모의','Simulated team response']]},
  arrival:{name:['ICU 입실 이송 · 모의','Transport into ICU · simulation'],steps:[['입실 이송 준비','Prepare incoming transport'],['이송원 환자 인수','Porter receives patient'],['ICU로 이동','Transport into ICU'],['침상 인계','Bedside handoff'],['입실 이송 시연 완료','Incoming transport demo complete']]},
  departure:{name:['ICU 퇴실 이송 · 모의','Transport out of ICU · simulation'],steps:[['전동 이송 준비','Prepare outgoing transport'],['이송원에게 인계','Handoff to porter'],['침상 출발','Leave bedside'],['목적지로 이동','Transport to destination'],['퇴실 이송 시연 완료','Outgoing transport demo complete']]}
 };
 const staff=[
  {id:'N1',role:'nurse',gender:'female',home:[1.8,6.2]},
  {id:'N2',role:'nurse',gender:'male',home:[9.8,16.3]},
  {id:'N3',role:'nurse',gender:'female',home:[17.8,6.2]},
  {id:'N4',role:'nurse',gender:'male',home:[25.8,16.3]},
  {id:'NC',role:'charge',gender:'female',home:[1.8,16.3]},
  {id:'Dr.',role:'doctor',gender:'male',home:[25.8,6.2]}
 ];
 let context=null,panel=null,layer=null,scene='calm',stage=0,target=0,timer=null,picked='',replay=null;
 const words=pair=>pair[context?.lang==='en'?1:0],t=(ko,en)=>words([ko,en]);
 const stateWords={rounding:['라운딩','Rounding'],checking:['기록 확인 · 모의','Record check · simulated'],documenting:['관찰·기록','Documentation'],preparing:['간호 준비','Preparing care'],working:['간호 업무','Care tasks'],standby:['대기 · 호출 가능','Standby · callable'],called:['호출 수신 · 모의','Called · simulated'],moving:['이동 중 · 모의','Moving · simulated'],responding:['침상 대응 · 모의','At bedside · simulated'],handoff:['이송 인계 · 모의','Transport handoff · simulated'],review:['회진·검토 · 모의','Review · simulated']};
 const palette={rounding:'#398c9d',checking:'#398c9d',documenting:'#398c9d',preparing:'#ad7c37',working:'#ad7c37',standby:'#74879a',called:'#ad7c37',moving:'#7964a8',responding:'#b85660',handoff:'#397fa5',review:'#f9fbff'};

 // Original published character drawing, including its male Dr. and N badge.
 function avatar(person){
  const isDoctor=person.role==='doctor',female=!isDoctor&&person.gender==='female';
  const hair=female?'<path d="M-.82-.35Q-1.2-1.8 0-1.8Q1.2-1.8 .82-.35L1 .1H-.95Z" fill="#674839"/>':'<path d="M-.76-1Q-.95-1.85 .1-1.8Q.95-1.7 .75-1Z" fill="#49382f"/>';
  return `<g class="staff-avatar" data-character="${female?'female':'male'}"><path class="avatar-care" d="M-1.1 .9V.1Q-1.1-.35-.55-.45H.55Q1.1-.35 1.1.1V.9" fill="white" stroke="#bccbdc" stroke-width=".24"/>${hair}<path class="avatar-scrubs" d="M-.9 1V.05Q-.9-.3-.45-.35L0-.12 .45-.35Q.9-.3 .9.05V1Z" fill="${isDoctor?'#f9fbff':'#398c9d'}" stroke="#476377" stroke-width=".07"/><ellipse cx="0" cy="-1.03" rx=".66" ry=".69" fill="#f4c7a2" stroke="#705747" stroke-width=".05"/><path d="M-.66-1.2Q-.56-1.8 .2-1.64L.67-1.18Q.25-1.1-.05-1.52Q-.2-1.2-.66-1.2" fill="${female?'#674839':'#49382f'}"/><circle cx="-.23" cy="-1" r=".065" fill="#283b4b"/><circle cx=".23" cy="-1" r=".065" fill="#283b4b"/><path d="M-.13-.73Q0-.62 .13-.73" fill="none" stroke="#925347" stroke-width=".06" stroke-linecap="round"/>${isDoctor?'<path d="M-.42-.3V.15Q0 .6 .42 .15V-.3M0 .38V.62" fill="none" stroke="#52748b" stroke-width=".08"/>':''}<rect x="-.75" y=".45" width="1.5" height=".65" rx=".2" fill="${isDoctor?'#6b567c':'#216476'}" stroke="white" stroke-width=".07"/><text class="staff-glyph" y=".91" fill="white" text-anchor="middle" font-size=".51">${escape(person.id)}</text></g>`;
 }
 function frame(kind='calm',step=0,bed=0){
  if(!Object.hasOwn(scenes,kind))kind='calm';
  step=Math.max(0,Math.min(4,Math.floor(Number(step)||0)));bed=Math.max(0,Math.min(7,Math.floor(Number(bed)||0)));
  const x=4+(bed%4)*8,y=bed<4?6.2:16.3,assigned=bed%4;
  const people=staff.map((p,index)=>({...p,home:[...p.home],x:p.home[0],y:p.home[1],state:p.role==='doctor'?'review':p.role==='charge'?'standby':['rounding','documenting','preparing','standby'][(index+step)%4],tasks:p.role==='doctor'?0:Math.floor((step+index%2)/2)}));
  const nurse=people[assigned],charge=people[4],doctor=people[5];
  if(kind==='busy'){
   people.forEach((p,index)=>{if(index<4){p.state=step<2?'preparing':'working';p.tasks=step+(index%2);}else if(index===4){p.state=step<2?'standby':'working';p.tasks=Math.max(0,step-1);}});
   nurse.x=x-2.2;nurse.y=y;charge.x=x+2.2;charge.y=y;
  }else if(kind==='help'){
   nurse.state='responding';nurse.x=x-2.2;nurse.y=y;
   charge.state=step===0?'standby':step===1?'called':step===2?'moving':'responding';
   if(step>=2){charge.x=x+2.2;charge.y=bed<4?16.3:6.2;}
   doctor.state=step<2?'review':step===2?'moving':'responding';
   if(step>=2){doctor.x=x+2.2;doctor.y=y;}
  }else if(kind==='arrival'||kind==='departure'){
   nurse.state=step>=2&&step<4?'handoff':'preparing';nurse.x=x-2.2;nurse.y=bed<4?6.2:16.3;
   charge.state=step>=3?'documenting':'standby';
  }
  // Keep neighboring figures and their labels separated, including when a
  // responding doctor moves into a nurse's original place.
  separatePeople(people,assigned);
  const transport=kind==='arrival'||kind==='departure';
  const progress=kind==='departure'?1-step/4:step/4;
  return {scene:kind,stage:step,bed,people,simulation:true,porter:transport?{x,y:(bed<4?11:13)+((bed<4?5.5:17)-(bed<4?11:13))*progress,visible:step<4,incoming:kind==='arrival'}:null};
 }
 function separatePeople(people,assigned){
  const placed=[],priority=[assigned,5,4,...[0,1,2,3].filter(i=>i!==assigned)];
  const slots=[1.8,6.2,9.8,14.2,17.8,22.2,25.8,30.2].flatMap(px=>[6.2,16.3].map(py=>[px,py]));
  for(const index of priority){const p=people[index],options=[[p.x,p.y],...slots].sort((a,b)=>Math.hypot(a[0]-p.x,a[1]-p.y)-Math.hypot(b[0]-p.x,b[1]-p.y));const pos=options.find(a=>placed.every(b=>Math.hypot(a[0]-b[0],a[1]-b[1])>=2.25))||options[0];[p.x,p.y]=pos;placed.push(pos);}
 }
 // The clinical timeline owns the clock and the source snapshots. This pure
 // projection accepts only replay coordinates, never measurements or case data.
 function replayFrame(options={}){
  const rawMinute=Number(options.minute),minute=Number.isFinite(rawMinute)?Math.max(0,rawMinute):0;
  const bed=Math.max(0,Math.min(7,Math.floor(Number(options.bedIndex)||0))),assigned=bed%4;
  const phase=['nurse','doctor','hold','handoff','idle'].includes(options.phase)?options.phase:(Math.floor(minute/10)%2?'doctor':'nurse');
  const people=staff.map(p=>({...p,home:[...p.home],x:p.home[0],y:p.home[1],state:p.role==='doctor'?'review':'standby',tasks:null}));
  const x=4+assigned*8,y=bed<4?6.2:16.3,nurse=people[assigned],doctor=people[5];
  if(phase!=='idle'){nurse.x=x-2.2;nurse.y=y;nurse.state=phase==='handoff'?'handoff':'checking';}
  if(phase==='doctor'||phase==='hold'){doctor.x=x+2.2;doctor.y=y;}
  separatePeople(people,assigned);
  return {scene:'replay',minute,phase,bed,running:options.running===true,people,simulation:true,porter:null,
          reason_ko:typeof options.reason_ko==='string'?options.reason_ko.slice(0,240):'',
          reason_en:typeof options.reason_en==='string'?options.reason_en.slice(0,240):''};
 }
 function leaveReplay(){
  if(!replay)return;replay=null;
  if(typeof window!=='undefined'&&typeof CustomEvent!=='undefined')window.dispatchEvent(new CustomEvent('staff-simulation-manual'));
 }
 function setReplayFrame(options){
  stop();replay=options==null?null:replayFrame(options);
  // Commit the old positions before applying a new frame, including a layer
  // transplanted after the main renderer replaces its ward SVG.
  layer?.getBoundingClientRect?.();update();
 }
 function svgNode(name,attributes,parent){const element=document.createElementNS(NS,name);for(const [key,value]of Object.entries(attributes))element.setAttribute(key,String(value));parent.appendChild(element);return element;}
 function stop(){if(timer!==null)clearInterval(timer);timer=null;}
 function advance(){if(stage>=4){stop();update();return;}stage++;if(stage===4)stop();update();}
 function play(){leaveReplay();if(timer!==null){stop();update();return;}if(stage===4)stage=0;timer=setInterval(advance,3200);update();}
 function reset(){leaveReplay();stop();stage=0;picked='';update();}
 function selectScene(value){leaveReplay();stop();scene=Object.hasOwn(scenes,value)?value:'calm';stage=0;picked='';update();}
 function ensurePanel(){
  if(panel?.isConnected)return;
  panel=document.createElement('section');panel.id='staffSimulationPanel';panel.className='staff-simulation';panel.dataset.simulated='true';
  panel.innerHTML='<div class="staff-simulation-head"><h3 data-staff-title></h3><span class="staff-demo-badge" data-staff-badge></span></div><p class="staff-simulation-note" data-staff-note></p><div class="staff-simulation-controls"><label><span data-scene-label></span><select data-staff-scene></select></label><label><span data-bed-label></span><select data-staff-bed></select></label><button data-staff-play></button><button data-staff-next></button><button data-staff-reset></button><button data-staff-call></button></div><div class="staff-simulation-status" role="status" aria-live="polite" data-staff-status></div><div class="staff-simulation-selection" data-staff-picked hidden></div>';
  document.getElementById('floors')?.before(panel);
  panel.querySelector('[data-staff-scene]').onchange=e=>selectScene(e.target.value);
  panel.querySelector('[data-staff-bed]').onchange=e=>{target=Number(e.target.value);reset();};
  panel.querySelector('[data-staff-play]').onclick=play;panel.querySelector('[data-staff-next]').onclick=()=>{leaveReplay();stop();advance();};panel.querySelector('[data-staff-reset]').onclick=reset;
  panel.querySelector('[data-staff-call]').onclick=()=>{selectScene('help');stage=1;update();};
 }
 function ensureLayer(){
  const svg=context?.svg;if(!svg?.isConnected)return false;
  if(layer?.ownerSVGElement===svg&&layer.isConnected)return true;
  layer=svgNode('g',{'class':'staff-simulation-layer','data-simulated':'true'},svg);
  for(const person of staff){const group=svgNode('g',{'class':'sim-person '+(person.role==='doctor'?'doctor':'nurse'),'data-sim-staff':person.id,tabindex:'0',role:'button'},layer);group.innerHTML=avatar(person);svgNode('title',{},group);svgNode('text',{class:'sim-person-state',x:0,y:1.7,'text-anchor':'middle'},group);const choose=()=>{picked=person.id;update();};group.addEventListener('click',choose);group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose();}});}
  const route=svgNode('path',{class:'sim-porter-route',fill:'none','pointer-events':'none'},layer);route.dataset.route='';
  const porter=svgNode('g',{class:'sim-porter','pointer-events':'none'},layer);
  porter.innerHTML='<g fill="none" stroke="#256e9d" stroke-width=".11" stroke-linecap="round" stroke-linejoin="round"><circle cx="-1.7" cy="-.65" r=".25" fill="#256e9d"/><path d="M-1.7-.35v.8m0-.55 .55 .35H-.7m-1 .25-.3 .6m.3-.6 .3 .6M-.8 .35H1.8V-.05M-.7 .35v.35m2.25-.35v.35"/><circle cx="-.5" cy=".8" r=".16"/><circle cx="1.45" cy=".8" r=".16"/><circle cx="-.4" cy="-.1" r=".22"/><path d="M-.15-.05H.6L1.45 .1"/></g>';
  svgNode('text',{class:'sim-map-caption',x:16,y:23.6,'text-anchor':'middle','pointer-events':'none'},layer);
  return true;
 }
 function update(){
  if(!context)return;if(!context.svg?.isConnected){stop();return;}
  ensurePanel();const current=replay||frame(scene,stage,target);
  const q=s=>panel.querySelector(s);
  q('[data-staff-title]').textContent=t('병동·간호사 근무 시나리오','Ward and nursing-work scenarios');q('[data-staff-badge]').textContent=replay?t('10분 기록 재생 · 모의 이동','10-min record replay · simulated movement'):t('모의 인력','Simulated staff');
  q('[data-staff-note]').textContent=replay?t('주 타임라인의 실제 기록 시점에 맞춘 가상 N·Dr. 이동입니다. 10분 간격은 재생 간격이며 측정·처치가 실제 수행된 간격이나 담당 의료진을 뜻하지 않습니다.','Fictional N and Dr. movement follows the main record timeline. Ten minutes is the replay interval, not an observed measurement or treatment frequency or actual staff assignment.'):t('N·Dr.와 이송원은 가상 인력입니다. 호출·수행 건수·이동은 이 브라우저 안의 시연이며 실제 환자 기록이나 계획표의 병상 색상·점유를 바꾸지 않습니다.','N, Dr. and porters are fictional personnel. Calls, task counts and movement are browser-local demonstrations; patient records, plan colors and occupancy are unchanged.');
  q('[data-scene-label]').textContent=t('수동 근무 시나리오','Manual work scenario');q('[data-bed-label]').textContent=t('시연 병상','Demo bed');
  const sceneOptions=Object.entries(scenes).map(([id,s])=>`<option value="${id}">${escape(words(s.name))}</option>`).join(''),bedOptions=Array.from({length:8},(_,i)=>`<option value="${i}">${String(i+1).padStart(2,'0')}</option>`).join('');
  if(q('[data-staff-scene]').innerHTML!==sceneOptions)q('[data-staff-scene]').innerHTML=sceneOptions;q('[data-staff-scene]').value=scene;
  if(q('[data-staff-bed]').innerHTML!==bedOptions)q('[data-staff-bed]').innerHTML=bedOptions;q('[data-staff-bed]').value=String(target);
  q('[data-staff-play]').textContent=timer===null?t('수동 시연 재생','Play manual demo'):t('수동 시연 일시정지','Pause manual demo');q('[data-staff-next]').textContent=t('다음 단계','Next stage');q('[data-staff-next]').disabled=!replay&&stage===4;q('[data-staff-reset]').textContent=t('처음으로','Reset');q('[data-staff-call]').textContent=t('대기 간호사 호출 · 모의','Call standby nurse · simulated');
  const replayStep=replay?(replay.phase==='idle'?t('입실 대기','Awaiting patients'):replay.phase==='handoff'?t('N 이송 인계','N transport handoff'):replay.phase==='nurse'?t('N 침상 기록 확인','N bedside record check'):t('Dr. 침상 검토','Dr. bedside review')):'';
  const replayReason=replay?(context.lang==='en'?replay.reason_en:replay.reason_ko):'';
  q('[data-staff-status]').textContent=replay?`${t('재생 경과','Replay elapsed')} +${replay.minute} min · ${replay.phase==='idle'?t('대기 구역','Standby area'):t('병상','Bed')+' '+String(replay.bed+1).padStart(2,'0')} · ${replayReason||replayStep} · ${replay.running?t('재생 중','Playing'):t('일시정지','Paused')}`:`${words(scenes[scene].name)} · ${stage+1}/5 · ${words(scenes[scene].steps[stage])}`;
  const who=current.people.find(p=>p.id===picked),selection=q('[data-staff-picked]');selection.hidden=!who;if(who)selection.textContent=`${who.id} · ${t('가상 인력','Fictional staff')} · ${words(stateWords[who.state])} · ${replay?t('실제 수행 내역과 무관한 시연','Movement demonstration, not observed care'):`${t('모의 업무 완료','Simulated tasks completed')} ${who.tasks}`}`;
  if(ensureLayer()){
   for(const person of current.people){const group=layer.querySelector(`[data-sim-staff="${person.id}"]`);group.setAttribute('transform',`translate(${person.x} ${person.y}) scale(.72)`);group.style.transform=`translate(${person.x}px,${person.y}px) scale(.72)`;group.classList.toggle('is-picked',person.id===picked);group.querySelector('.avatar-scrubs').setAttribute('fill',palette[person.state]);group.querySelector('.avatar-care').setAttribute('stroke-dasharray',person.role==='charge'?'.14 .10':'');const label=`${person.id} · ${t('가상 인력','Fictional staff')} · ${words(stateWords[person.state])}`;group.setAttribute('aria-label',label);group.querySelector('title').textContent=label;group.querySelector('.sim-person-state').textContent=person.state==='standby'?t('대기','Standby'):person.state==='moving'?t('이동','Moving'):person.state==='responding'?t('대응','Respond'):person.state==='checking'?t('기록 확인','Check record'):person.role==='doctor'?'':t('간호','Care');}
   const porter=layer.querySelector('.sim-porter'),route=layer.querySelector('[data-route]');porter.style.display=current.porter?.visible?'':'none';route.style.display=current.porter?.visible?'':'none';
   if(current.porter){porter.setAttribute('transform',`translate(${current.porter.x} ${current.porter.y}) scale(.65)`);porter.style.transform=`translate(${current.porter.x}px,${current.porter.y}px) scale(.65)`;route.setAttribute('d',`M${current.porter.x} ${target<4?11:13}V${target<4?5.5:17}`);}
   layer.querySelector('.sim-map-caption').textContent=`${t('모의 인력·이동','Simulated personnel and movement')} · ${replay?replayStep:words(scenes[scene].steps[stage])}`;
  }
  const note=document.getElementById('staffNote');if(note){note.textContent=t('가상 N·Dr.를 병동 지도에 표시합니다. 실제 K-MIMIC 의료진 배정과 수행 간호사는 연결되지 않았습니다.','Fictional N and Dr. appear on the ward map. Actual K-MIMIC staff assignments and performing nurses are not linked.');note.closest('details')?.setAttribute('open','');}
  const roster=document.getElementById('rosterSummary');if(roster){roster.innerHTML=`<span class="staff-demo-badge">${t('모의 근무 인력','Simulated roster')}</span>`+current.people.map(p=>`<div class="sim-roster-row"><b>${p.id}</b><span>${escape(words(stateWords[p.state]))}</span><small>${p.role==='doctor'||replay?'':`${p.tasks} ${t('모의 업무','demo tasks')}`}</small></div>`).join('');roster.closest('details')?.setAttribute('open','');}
 }
 function mount(next){
  const previous=context,scope=String(next.hospital||'')+'|'+String(next.unit||'')+'|'+String(next.planDay??'');
  context={svg:next.svg,lang:next.lang==='en'?'en':'ko',scope};
  if(previous&&previous.scope!==scope){stop();scene='calm';stage=0;target=0;picked='';replay=null;layer?.remove();layer=null;}
  if(previous?.svg!==next.svg&&layer&&next.svg?.isConnected){next.svg.appendChild(layer);layer.getBoundingClientRect?.();}
  else if(previous?.svg!==next.svg)layer=null;
  update();
 }
 function dispose(){stop();layer?.remove();panel?.remove();layer=null;panel=null;context=null;scene='calm';stage=0;target=0;picked='';replay=null;}
 if(typeof window!=='undefined')window.addEventListener('pagehide',dispose);
 return {mount,dispose,frame,avatar,replayFrame,setReplayFrame};
})();
if(typeof window!=='undefined')window.StaffSimulation=StaffSimulation;
if(typeof module!=='undefined'&&module.exports)module.exports=StaffSimulation;
