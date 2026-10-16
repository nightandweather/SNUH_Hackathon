/* Explicit, reversible porter stories. The canonical replay and criteria stay intact. */
(() => {
  'use strict';
  const M=window.SICUTransportModel,V=window.SICUTransportVisuals,NS='http://www.w3.org/2000/svg';
  const q=s=>document.querySelector(s),all=d=>d?.floors.flatMap(f=>f.units.flatMap(u=>u.beds))||[];
  const ko=()=>I18n.language==='ko',t=(a,b)=>ko()?a:b,words=a=>a[ko()?0:1];
  const DURATION=14000,reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let canonical=null,scene=null,chosen='arrival',progress=0,playing=false,lastTick=0,raf=0,layer=null,view=null,bar=null,checkpoint='';
  const nativeProject=Transfers.project,nativeClear=Transfers.clearForScope,nativeBusy=Transfers.busy;
  function fingerprint(data,coordinated=false){const d=FacilityProfiles.project(data);return JSON.stringify([d.seed,coordinated?null:d.t,coordinated?null:d.clock,d.hospital_profiles,d.demo_profile,all(d).map(b=>[b.id,b.patient?.pid,b.patient?.admit_t,!!b.reservation])]);}
  function removeLayer(){
    if(view?.hardware){view.hardware.style.removeProperty('--bed-mattress');view.hardware.style.removeProperty('--bed-seam');delete view.hardware.dataset.transportBedState;}
    layer?.remove();layer=null;view=null;
  }
  function stopClock(){playing=false;cancelAnimationFrame(raf);raf=0;document.body.dataset.transportScene=scene?'paused':'idle';}
  function cancel(redraw=true){
    const input=canonical;stopClock();scene=null;progress=0;checkpoint='';removeLayer();window.SICUNativeTransport?.clear();
    if(redraw&&input){nativeClear.call(Transfers,input);acceptState(input);}
    updateBar();
  }
  Transfers.project=function(data){
    // Never feed a projected storyboard back into the source transfer controller.
    if(all(data).some(b=>b.flow?.scene==='porter-story'))data=canonical||data;
    const key=fingerprint(data,scene?.coordinated===true);
    if(scene&&key!==scene.fingerprint)cancel(false);
    canonical=FacilityProfiles.project(data);
    const base=nativeProject.call(this,canonical);
    return scene?M.project(base,scene,progress,I18n.language):base;
  };
  Transfers.clearForScope=function(data){const input=canonical||data;cancel(false);return nativeClear.call(this,input);};
  Transfers.busy=function(){return Boolean(scene&&playing)||nativeBusy.call(this);};
  function currentUnit(){
    if(typeof S==='undefined'||!S)return null;
    const units=S.floors.flatMap(f=>f.units),ward=q('#wardScope')?.value;
    return units.find(u=>u.id===ward)||units.find(u=>u.id==='SICU'||u.id.endsWith('-SICU'))||units[0];
  }
  function target(kind){
    const unit=currentUnit();if(!unit)return null;
    const baseUnit=canonical?.floors.flatMap(f=>f.units).find(u=>u.id===unit.id);if(!baseUnit)return null;
    const beds=baseUnit.beds;
    const bed=kind==='arrival'?(beds.find(b=>!b.patient&&!b.reservation&&!b.unavailable)||beds.find(b=>!b.patient&&!b.unavailable)):
      beds.find(b=>b.patient?.source==='synthetic'&&!b.patient.simulation_override)||beds.find(b=>b.patient?.source==='synthetic');
    return bed?{unit:baseUnit,bed}:null;
  }
  function apply(){if(!scene||!canonical)return;acceptState(canonical);}
  function start(kind=chosen,autoplay=true,options={}){
    if(!M.names[kind])return false;
    chosen=kind;
    // An external unified player advances both stored frames and this example.
    // The original standalone scene still pauses the native interval first.
    if(/^(Pause|일시정지)$/.test(q('#sandboxPlay')?.textContent.trim()||''))q('#sandboxPlay').click();
    cancel(false);
    if(canonical)nativeClear.call(Transfers,canonical);
    const choice=target(kind);
    if(!choice){if(canonical)acceptState(canonical);updateBar();return false;}
    const template=choice.bed.patient||choice.unit.beds.find(b=>b.patient)?.patient;
    const coordinated=options.coordinated===true;
    scene={kind,bed:choice.bed.id,unit:choice.unit.id,hospital:Network.hospital,coordinated,fingerprint:fingerprint(canonical,coordinated),patient:M.example(template,kind,choice.bed.id,canonical.t),nextReservation:kind!=='arrival'&&Boolean(q('#transferReserveNext')?.checked)};
    progress=0;checkpoint='';apply();if(autoplay&&!coordinated)play();else updateBar();return true;
  }
  function play(){
    if(!scene)return start(chosen,true);
    if(progress>=1)return start(chosen,true);
    playing=true;lastTick=performance.now();document.body.dataset.transportScene='playing';updateBar();cancelAnimationFrame(raf);raf=requestAnimationFrame(tick);return true;
  }
  function pause(){if(playing&&!scene?.coordinated){progress=Math.min(1,progress+(performance.now()-lastTick)/DURATION);}stopClock();apply();paint();updateBar();}
  function advance(value,run=false){
    if(!scene?.coordinated)return false;
    cancelAnimationFrame(raf);raf=0;progress=Math.min(1,Math.max(0,Number(value)||0));playing=Boolean(run)&&progress<1;
    const state=M.sample(scene.kind,progress),key=[state.phase,state.moved,state.complete].join(':');
    if(!run||key!==checkpoint){checkpoint=key;apply();}
    paint();updateBar();return true;
  }
  function seek(value){if(!scene)return false;stopClock();progress=Math.min(1,Math.max(0,Number(value)||0));checkpoint='';apply();paint();updateBar();return true;}
  function tick(now){
    if(!playing||!scene)return;
    progress=Math.min(1,progress+(now-lastTick)/DURATION);lastTick=now;
    const state=M.sample(scene.kind,progress),key=[state.phase,state.moved,state.complete].join(':');
    if(key!==checkpoint){checkpoint=key;apply();}
    paint();if(progress>=1){stopClock();apply();updateBar();}else raf=requestAnimationFrame(tick);
  }
  function svg(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs||{}))e.setAttribute(k,v);parent?.append(e);return e;}
  function createLayer(unit,bed,root){
    removeLayer();layer=svg('g',{class:'transport-story-layer','data-transport-kind':scene.kind,'data-transport-bed':bed.id,'pointer-events':'none',role:'img'},root);
    const route=M.route(unit,bed,S.elevator_x),dead=scene.kind==='icu_death';
    svg('path',{class:'transport-story-route',d:route.points.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ')},layer);
    const door=svg('g',{class:'transport-story-door',transform:'translate('+route.door.join(' ')+')'},layer);door.innerHTML=V.door({id:'story-'+scene.hospital+'-'+bed.id,open:0});
    const roomDoor=svg('g',{class:'transport-story-room-door',transform:'translate('+route.room.door.join(' ')+') rotate(90) scale(.30)'},layer);roomDoor.innerHTML=V.door({id:'story-room-'+bed.id,open:0});
    const cart=svg('g',{class:'transport-story-cart'},layer);cart.innerHTML=V.cart({occupied:false,deceased:dead,facing:1});
    const bedPatient=svg('g',{class:'transport-story-bed-patient',transform:'translate('+route.bed.join(' ')+')'+(bed.y<5?'':' rotate(180)')},layer);bedPatient.innerHTML=V.bedPatient({deceased:dead});
    const handoff=svg('g',{class:'transport-story-handoff'},layer);handoff.innerHTML=V.bedPatient({deceased:dead});
    const caption=svg('text',{class:'transport-story-caption',x:unit.x+unit.w/2,y:unit.h+1.65,'text-anchor':'middle'},layer);
    const architecture=[...root.querySelectorAll('.spatial-architecture')].find(g=>g.dataset.spatialUnit===unit.id);
    const hardware=architecture?.querySelectorAll('.spatial-bed-silhouette')[unit.beds.findIndex(b=>b.id===bed.id)];
    view={root,unit,bed,route,door,roomDoor,cart,bedPatient,handoff,caption,hardware,lastDistance:null,walkDistance:0,gait:V.gait(0,false)};
  }
  function paint(){
    if(!scene||typeof S==='undefined'||!S)return;
    const unit=S.floors.flatMap(f=>f.units).find(u=>u.id===scene.unit),bed=unit?.beds.find(b=>b.id===scene.bed),root=bedEl[scene.bed]?.r.ownerSVGElement;
    if(!unit||!bed||!root)return;
    if(!layer?.isConnected||view.root!==root)createLayer(unit,bed,root);
    const s=M.sample(scene.kind,progress),incoming=scene.kind==='arrival',motion=reduced.matches?M.sample(scene.kind,[0,.20,.40,.49,.74,.88,1][s.phase]):s;
    const pos=M.point(view.route.points,motion.route),returning=progress>=M.cuts[4],angle=pos.angle+(returning?180:0);
    const delta=view.lastDistance==null?0:Math.abs(pos.distance-view.lastDistance),walking=playing&&!reduced.matches&&s.cartVisible&&delta>.00005;
    if(walking)view.walkDistance+=delta;view.lastDistance=pos.distance;
    view.cart.setAttribute('transform',`translate(${pos.x} ${pos.y}) rotate(${angle}) scale(${view.route.cartScale})`);
    view.gait=V.posePorter(view.cart.querySelector('.transport-porter'),{rotation:angle,facing:1,distance:view.walkDistance,walking});
    view.position={x:pos.x,y:pos.y,angle};view.cart.dataset.walking=String(walking);view.cart.dataset.walkDistance=String(view.walkDistance);
    view.cart.style.opacity=s.cartVisible?'1':'0';view.cart.dataset.occupied=String(s.cartOccupied);view.cart.dataset.route=String(s.route);view.cart.dataset.x=String(pos.x);view.cart.dataset.y=String(pos.y);
    const transfer=s.handoffActive;
    view.cart.querySelector('.transport-cart-patient').setAttribute('opacity',!transfer&&s.cartOccupied?'1':'0');
    view.cart.querySelector('.transport-cart').dataset.occupied=String(s.cartOccupied);
    view.door.dataset.open=String(motion.door);view.door.querySelector('.transport-door').dataset.open=String(motion.door);
    view.door.querySelector('.transport-door-leaf-upper').setAttribute('transform',`translate(0 ${-1.9*motion.door})`);
    view.door.querySelector('.transport-door-leaf-lower').setAttribute('transform',`translate(0 ${1.9*motion.door})`);
    const roomOpen=motion.route>.8||s.phase===3?1:0;
    view.roomDoor.dataset.open=String(roomOpen);view.roomDoor.querySelector('.transport-door').dataset.open=String(roomOpen);
    view.roomDoor.querySelector('.transport-door-leaf-upper').setAttribute('transform',`translate(0 ${-1.9*roomOpen})`);
    view.roomDoor.querySelector('.transport-door-leaf-lower').setAttribute('transform',`translate(0 ${1.9*roomOpen})`);
    view.bedPatient.style.opacity=!transfer&&s.bedOccupied?'1':'0';view.handoff.style.opacity=transfer?'1':'0';
    if(view.hardware){
      const state=s.bedOccupied?(incoming||scene.kind==='icu_death'?'red':'green'):s.turnover?'turnover':s.complete&&scene.nextReservation?'reserved':'empty';
      view.hardware.dataset.transportBedState=state;
      view.hardware.style.setProperty('--bed-mattress',({red:'#f3c9cf',green:'#c5e5d4',turnover:'#dce6ef',reserved:'#fff1b8',empty:'#fff'})[state]);
      view.hardware.style.setProperty('--bed-seam',({red:'#bf6976',green:'#6da789',turnover:'#9db2c6',reserved:'#c8b366',empty:'#c9d7e6'})[state]);
    }
    if(transfer){
      const cartPoint=M.point(view.route.points,1),a=incoming?[cartPoint.x,cartPoint.y]:view.route.bed,b=incoming?view.route.bed:[cartPoint.x,cartPoint.y],h=M.ease(motion.handoff);
      // Face the destination immediately, then slide onto it without a slow spin.
      const toAngle=incoming?(bed.y<5?0:180):cartPoint.angle-90;
      view.handoff.setAttribute('transform',`translate(${a[0]+(b[0]-a[0])*h} ${a[1]+(b[1]-a[1])*h}) rotate(${toAngle})`);
    }
    layer.dataset.phase=String(s.phase);layer.dataset.progress=String(progress);layer.dataset.playing=String(playing);layer.setAttribute('aria-label',scene.bed+' · '+words(M.names[scene.kind])+' · '+words(M.steps[scene.kind][s.phase]));
    view.caption.textContent=scene.bed+' · '+words(M.steps[scene.kind][s.phase]);
  }
  function updateBar(){
    if(!bar)return;
    const s=scene?M.sample(scene.kind,progress):null,choice=target(chosen),can=Boolean(scene||choice);
    q('#transportSceneHeading').textContent=t('이송 장면','Transport scenes');q('#transportSceneFiction').textContent=t('가상 시연','Fictional demonstration');
    bar.querySelectorAll('[data-transport-kind]').forEach(button=>{const kind=button.dataset.transportKind;button.textContent=words(M.names[kind]);button.setAttribute('aria-pressed',String(chosen===kind));});
    q('#transportScenePlay').textContent=playing?t('Ⅱ 일시정지','Ⅱ Pause'):s?.complete?t('↻ 다시 재생','↻ Replay'):t('▶ 재생','▶ Play');q('#transportScenePlay').disabled=!can;
    q('#transportSceneReset').title=t('장면 초기화','Reset scene');q('#transportSceneReset').setAttribute('aria-label',t('장면 초기화','Reset scene'));q('#transportSceneReset').disabled=!scene;
    q('#transportSceneStatus').textContent=scene?scene.bed+' · '+words(M.steps[scene.kind][s.phase]):choice?choice.bed.id+' · '+t('문·환자·카트의 이동을 재생합니다.','Play the door, patient and cart sequence.'):chosen==='arrival'?t('빈 병상이 없어 입실 장면을 시작할 수 없습니다.','No vacant bed is available for an admission scene.'):t('이송할 가상 환자가 없습니다.','No fictional patient is available for this scene.');
    bar.querySelectorAll('.transport-scene-track i').forEach((node,i)=>{node.dataset.state=s?(i<s.phase?'done':i===s.phase?'current':'pending'):'pending';});
    const colors=chosen==='arrival'?['white','red']:chosen==='departure'?['green','white']:['red','white'];
    q('#transportSceneColor').innerHTML='<i data-color="'+colors[0]+'"></i><span>'+({white:t('빈 병상','Empty'),red:'RED',green:'GREEN'})[colors[0]]+'</span><span aria-hidden="true">→</span><i data-color="'+colors[1]+'"></i><span>'+({white:t('빈 병상','Empty'),red:'RED',green:'GREEN'})[colors[1]]+'</span>';
    document.body.dataset.transportScene=scene?(playing?'playing':s.complete?'complete':'paused'):'idle';
  }
  function describe(){const s=scene?M.sample(scene.kind,progress):null;return {kind:null,progress:0,coordinated:false,...(scene?{kind:scene.kind,bed:scene.bed,unit:scene.unit,hospital:scene.hospital,coordinated:scene.coordinated,nextReservation:scene.nextReservation}:{}),...s,playing,reducedMotion:reduced.matches,
    gait:view?{...view.gait}:V.gait(0,false),position:view?.position?{...view.position}:null,
    path:view?{origin:view.route.origin,outside:[...view.route.outside],procedureDoor:[...view.route.procedureDoor],gate:[...view.route.door],roomDoor:[...view.route.room.door],points:view.route.points.map(p=>[...p]),waypoints:view.route.waypoints.map(p=>[...p])}:null,
    available:Object.fromEntries(Object.keys(M.names).map(k=>[k,Boolean(target(k))]))};}
  function setup(){
    const staff=q('#staffMapToolbar');if(!staff)return;
    bar=document.createElement('section');bar.id='transportSceneBar';bar.dataset.noTranslate='';bar.setAttribute('aria-label',t('이송 장면 재생','Transport scene player'));
    bar.innerHTML='<div><div class="transport-scene-heading"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 8h18M5 8V6h5v2m-6 3h15v5H4v-5Zm1 5v3m13-3v3M8 13h8m3-2 2-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg><span id="transportSceneHeading"></span><small id="transportSceneFiction"></small></div><div class="transport-scene-options" role="group" aria-label="Transport scenario"><button class="transport-scene-option" type="button" data-transport-kind="arrival"></button><button class="transport-scene-option" type="button" data-transport-kind="departure"></button><button class="transport-scene-option" type="button" data-transport-kind="icu_death"></button></div></div><div class="transport-scene-actions"><button type="button" id="transportScenePlay"></button><button type="button" id="transportSceneReset">↺</button></div><div class="transport-scene-progress"><div class="transport-scene-track" aria-hidden="true">'+Array.from({length:7},()=>'<i></i>').join('')+'</div><span id="transportSceneStatus" role="status" aria-live="polite"></span><span class="transport-scene-color" id="transportSceneColor"></span></div>';
    staff.after(bar);
    bar.querySelectorAll('[data-transport-kind]').forEach(button=>button.onclick=()=>{const active=Boolean(scene);cancel(active);chosen=button.dataset.transportKind;if(active)start(chosen,false);else updateBar();});
    q('#transportScenePlay').onclick=()=>playing?pause():play();q('#transportSceneReset').onclick=()=>cancel(true);updateBar();
  }
  // Capture before the source handlers, including its closure-local navigation.
  document.addEventListener('click',event=>{
    if(!scene)return;
    if(event.target.closest('#staffReplayToggle,#sandboxPlay,#sandboxReset,#sandboxApply,#transferStart,#transferNext,#transferPlay,#transferClear,#workspaceHome,#entryStart,[data-hospital],[data-ward]'))cancel(true);
  },true);
  document.addEventListener('input',event=>{if(scene&&event.target.matches('#sandboxTime')&&!(scene.coordinated&&event.sicuUnifiedReplay===true)){const value=event.target.value;cancel(true);event.target.value=value;}},true);
  document.addEventListener('change',event=>{if(scene&&event.target.matches('#hospitalScope,#wardScope,#sandboxProfile,#me')){const value=event.target.value;cancel(true);event.target.value=value;}},true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing)pause();});
  document.addEventListener('icu-language',()=>queueMicrotask(()=>{if(scene)apply();paint();updateBar();}));
  reduced.addEventListener('change',()=>paint());
  const nativeDraw=window.draw;
  window.draw=function(){const result=nativeDraw.apply(this,arguments);paint();updateBar();return result;};
  const nativeCard=Transfers.card;
  Transfers.card=function(bed){if(bed.flow?.scene!=='porter-story')return nativeCard.apply(this,arguments);return '<div class="flow-card-note" data-no-translate><b>'+esc(bed.flow.title)+'</b><p>'+esc(bed.flow.label)+'</p><small>'+esc(bed.flow.route)+'</small><p>'+t('가상 이송 장면','Fictional transport scene')+'</p></div>';};
  const nativeDetails=Transfers.openDetails;
  Transfers.openDetails=function(id){
    const bed=typeof S==='undefined'?null:all(S).find(b=>b.id===id);
    if(bed?.flow?.scene!=='porter-story')return nativeDetails.apply(this,arguments);
    let dialog=q('#transportSceneDetail');if(!dialog){dialog=document.createElement('dialog');dialog.id='transportSceneDetail';dialog.dataset.noTranslate='';document.body.append(dialog);}
    const restore=document.activeElement;
    dialog.innerHTML='<div class="transport-scene-dialog-head"><div><small>SICU LINK · TEAM 4</small><h2>'+esc(id)+'</h2></div><button type="button" aria-label="'+t('닫기','Close')+'">×</button></div>'+Transfers.card(bed)+'<p class="transport-scene-dialog-note">'+t('현재 병동을 바꾸거나 장면을 초기화하면 원래 시나리오로 돌아갑니다.','Change the ward or reset this scene to return to the original scenario.')+'</p>';
    dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>{if(restore?.isConnected)restore.focus({preventScroll:true});};dialog.onclick=e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}};
    dialog.showModal();dialog.querySelector('button').focus();return true;
  };
  window.SICUTransportScenes=Object.freeze({start,play,pause,reset:()=>cancel(true),seek,advance,describe});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
