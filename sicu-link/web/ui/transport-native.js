/* Native transport presentation only. Five source stages and patient data stay intact. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const M=window.SICUTransportModel;
  const supported = new Set(['arrival','departure','icu_death']);
  const observed = new Map(), tails = new Map(), visualNodes = new Map();
  const TAIL_MS = 1800, MANUAL_MOVE_MS = 1200, AUTOMATIC_MOVE_MS = 850;
  let raf = 0, scope = '', lastTime = null, descriptions = [];
  const now = () => performance.now();
  const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const t = (ko,en) => (typeof I18n !== 'undefined' ? I18n.language === 'ko' : document.documentElement.lang.startsWith('ko')) ? ko : en;
  const current = () => typeof S !== 'undefined' && S ? S : null;
  const eligible = bed => bed.flow && supported.has(bed.flow.kind) && bed.flow.scene !== 'porter-story';
  const clamp = value => Math.max(0,Math.min(1,value));
  function node(tag,attributes,parent) {
    const item = document.createElementNS(NS,tag);
    Object.entries(attributes || {}).forEach(([key,value]) => item.setAttribute(key,String(value)));
    if (parent) parent.append(item);
    return item;
  }
  function modelScope(model) {
    const units = model.floors.flatMap(f => f.units);
    return JSON.stringify([model.seed,model.demo_profile,model.hospital_profiles,
      typeof Network !== 'undefined' ? Network.hospital : '',units.map(u => u.id)]);
  }
  function clear() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0; observed.clear(); tails.clear(); descriptions = [];
    visualNodes.forEach(item => item.group.remove());visualNodes.clear();
    scope = ''; lastTime = null;
    document.querySelectorAll('.sicu-native-transport').forEach(item => item.remove());
  }
  function routeFor(unit,bed) {
    const hospital = unit.hospital_id || 'A';
    const elevator = {A:35,B:31,C:51}[hospital] ?? Number(current()?.elevator_x || 35);
    const shared=M.route(unit,bed,elevator),object=p=>({x:p[0],y:p[1]});
    return {origin:shared.origin,entry:object(shared.outside),door:object(shared.door),
      procedureDoor:object(shared.procedureDoor),roomDoor:object(shared.room.door),
      modelPoints:shared.points,points:shared.points.map(object),waypoints:shared.waypoints.map(object),cartScale:shared.cartScale};
  }
  function pointOn(route,progress) {
    const point=M.point(route.modelPoints,progress),angle=point.angle*Math.PI/180;
    return {...point,dx:Math.cos(angle),dy:Math.sin(angle)};
  }
  function targetFor(kind,stage) {
    // Route progress is procedure staging -> bedside. Loading is separate.
    return kind === 'arrival' ? [0,0,.57,1,1][stage] : [0,1,.55,0,0][stage];
  }
  function progressFor(record,time) {
    const rawFraction = reduced() ? 1 : clamp(((record.pausedAt??time)-record.moveAt)/record.duration);
    const fraction=record.kind!=='arrival'&&record.stage===3?clamp(rawFraction/.85):rawFraction;
    const eased = M.ease(fraction);
    return {value:record.from+(record.to-record.from)*eased,rawFraction,
      moving:record.pausedAt==null&&fraction<1 && Math.abs(record.to-record.from)>.001};
  }
  function tailFor(record,time) {
    if (tails.has(record.bed) || record.returned) return;
    record.returned = true;
    tails.set(record.bed,{token:record.token,bed:record.bed,unit:record.unit,kind:'arrival',stage:4,
      automatic:record.automatic,route:record.route,started:time,expires:time+TAIL_MS});
  }
  function observe(model,time) {
    const key = modelScope(model);
    if ((scope && key !== scope) || (lastTime != null && Number(model.t)<lastTime)) clear();
    scope = key; lastTime = Number(model.t);
    const present = new Set(),beds = new Map();
    for (const floor of model.floors) for (const unit of floor.units) for (const bed of unit.beds) {
      beds.set(bed.id,bed);
      if (!eligible(bed)) continue;
      const flow = bed.flow,stage = Math.max(0,Math.min(4,Number(flow.stage)||0));
      const token = JSON.stringify([bed.id,flow.kind,Boolean(flow.automatic),flow.startClock,flow.patient?.pid,flow.patient?.admit_t]);
      let record = observed.get(bed.id);
      present.add(bed.id);
      if (!record || record.token !== token || stage < record.stage) {
        tails.delete(bed.id);
        const previous = Number.isFinite(flow.previousStage) ? Math.max(0,Math.min(4,flow.previousStage)) : stage;
        record = {token,bed:bed.id,unit:unit.id,kind:flow.kind,stage,automatic:Boolean(flow.automatic),
          route:routeFor(unit,bed),from:targetFor(flow.kind,previous),to:targetFor(flow.kind,stage),
          moveAt:Number.isFinite(flow.motionAt)?flow.motionAt:time,
          duration:flow.automatic?AUTOMATIC_MOVE_MS:MANUAL_MOVE_MS,returned:false};
        observed.set(bed.id,record);
      } else if (stage !== record.stage) {
        const previous = progressFor(record,time).value;
        record.from = previous; record.to = targetFor(flow.kind,stage);record.moveAt = time;
        record.pausedAt=null;
        record.stage = stage;record.route = routeFor(unit,bed);
        if (flow.kind === 'arrival' && stage === 4) tailFor(record,time);
      }
    }
    for (const [id,record] of observed) if (!present.has(id)) {
      const bed = beds.get(id);
      // Native automatic arrivals stop at stage 3, then reveal the canonical patient.
      // Scope/seek/reset cancellation clears observations before reaching this branch.
      if (record.kind === 'arrival' && record.automatic && record.stage >= 2 && bed?.patient && !bed.flow?.scene) tailFor(record,time);
      observed.delete(id);
    }
    for (const [id,tail] of tails) if (time>=tail.expires || !beds.has(id) || beds.get(id)?.flow?.scene === 'porter-story') tails.delete(id);
  }
  function removeNativeOverlays(model) {
    const ids = model.floors.flatMap(f => f.units.flatMap(u => u.beds.filter(eligible).map(b => b.id)));
    document.querySelectorAll('.transfer-overlay').forEach(group => {
      const caption = group.lastElementChild?.textContent || '';
      if (ids.some(id => caption.startsWith(id+' · '))) group.remove();
    });
  }
  function cartState(record,time) {
    if (record.expires) {
      const fraction = clamp((time-record.started)/TAIL_MS);
      return {progress:reduced()?0:1-M.ease(clamp(fraction/.85)),occupied:false,deceased:false,
        doorOpen:fraction<.86?1:clamp((1-fraction)/.14),moving:!reduced()&&fraction<.85,animating:time<record.expires,phase:'empty-return',
        label:t('환자 인계 완료 · 빈 카트 복귀','Handoff complete · empty cart returning')};
    }
    const movement = progressFor(record,time),arrival = record.kind === 'arrival';
    const occupied = arrival ? record.stage>0 && record.stage<4 : record.stage>=2 && record.stage<4;
    const closing=!arrival&&record.stage===3;
    const doorOpen=record.stage===0||record.stage===4?0:closing?(movement.rawFraction<.86?1:clamp((1-movement.rawFraction)/.14)):1;
    return {progress:movement.value,occupied,deceased:record.kind==='icu_death' && occupied,
      doorOpen,moving:movement.moving,animating:movement.moving||(closing&&record.pausedAt==null&&movement.rawFraction<1),phase:'native',
      label:arrival?t('ICU 입실 이송','Transport into ICU'):record.kind==='icu_death'?t('명시적 사후 이송','Explicit post-mortem transport'):t('일반병동으로 전동','Transfer to ward')};
  }
  function drawItem(record,time) {
    const entry = typeof bedEl !== 'undefined' ? bedEl[record.bed] : null;
    const svg = entry?.r?.ownerSVGElement;
    const visuals = window.SICUTransportVisuals;
    if (!svg || !visuals) return null;
    const state = cartState(record,time),position = pointOn(record.route,state.progress);
    let cached = visualNodes.get(record.bed);
    if (!cached || cached.token!==record.token || cached.kind!==record.kind || cached.svg!==svg || cached.group.parentNode!==svg || cached.visuals!==visuals) {
      cached?.group.remove();
      const group = node('g',{class:'sicu-native-transport','data-native-bed':record.bed,
        'data-native-kind':record.kind,'pointer-events':'none',role:'img'},svg);
      const title = node('title',{},group);
      const path = node('path',{d:record.route.points.map((p,i)=>(i?'L':'M')+p.x+' '+p.y).join(' '),fill:'none',
        stroke:'#718b9f','stroke-width':'.075','stroke-dasharray':'.18 .18',opacity:'.6'},group);
      const doorway = node('g',{class:'native-transport-door',
        transform:`translate(${record.route.door.x} ${record.route.door.y}) scale(.8)`},group);
      doorway.innerHTML = visuals.door({id:'native-'+record.bed,open:state.doorOpen});
      const roomDoorway=node('g',{class:'native-transport-room-door',transform:`translate(${record.route.roomDoor.x} ${record.route.roomDoor.y}) rotate(90) scale(.30)`},group);
      roomDoorway.innerHTML=visuals.door({id:'native-room-'+record.bed,open:0});
      const cart = node('g',{class:'native-transport-cart'},group);
      cart.innerHTML = visuals.cart({occupied:false,deceased:record.kind==='icu_death',facing:1});
      const label = node('text',{'text-anchor':'middle','font-size':'.48',fill:'#48657c',
        'paint-order':'stroke',stroke:'#fff','stroke-width':'.17'},group);
      cached = {token:record.token,kind:record.kind,svg,visuals,group,title,path,doorway,roomDoorway,cart,label,lastDistance:null,walkDistance:0,
        door:doorway.querySelector('.transport-door'),upper:doorway.querySelector('.transport-door-leaf-upper'),
        lower:doorway.querySelector('.transport-door-leaf-lower'),art:cart.querySelector('.transport-cart'),
        roomDoor:roomDoorway.querySelector('.transport-door'),roomUpper:roomDoorway.querySelector('.transport-door-leaf-upper'),roomLower:roomDoorway.querySelector('.transport-door-leaf-lower'),
        patient:cart.querySelector('.transport-cart-patient'),porter:cart.querySelector('.transport-porter')};
      cached.cartTitle=cached.art?.querySelector('title');
      visualNodes.set(record.bed,cached);
    }
    const set = (element,key,value) => {if(element && element.getAttribute(key)!==String(value))element.setAttribute(key,String(value));};
    set(cached.group,'data-native-stage',record.stage);set(cached.group,'data-native-phase',state.phase);
    set(cached.group,'data-cart-occupied',state.occupied);set(cached.group,'data-explicit-death',state.deceased);
    set(cached.group,'aria-label',record.bed+' · '+state.label);
    if(cached.title.textContent!==record.bed+' · '+state.label)cached.title.textContent=record.bed+' · '+state.label;
    set(cached.doorway,'data-open',state.doorOpen);set(cached.door,'data-open',state.doorOpen);
    set(cached.upper,'transform',`translate(0 ${-1.9*state.doorOpen})`);
    set(cached.lower,'transform',`translate(0 ${1.9*state.doorOpen})`);
    const roomOpen=state.progress>.8?1:0;
    set(cached.roomDoorway,'data-open',roomOpen);set(cached.roomDoor,'data-open',roomOpen);
    set(cached.roomUpper,'transform',`translate(0 ${-1.9*roomOpen})`);set(cached.roomLower,'transform',`translate(0 ${1.9*roomOpen})`);
    const showCart = Boolean(record.expires || record.stage<4),direction=record.expires || record.to<record.from ? -1 : 1;
    let dx=position.dx*direction,dy=position.dy*direction;if(!dx&&!dy)dx=1;
    const facing=1,rotation=Math.atan2(dy,dx)*180/Math.PI;
    set(cached.cart,'display',showCart?'inline':'none');set(cached.label,'display',showCart?'inline':'none');
    set(cached.cart,'data-loaded',state.occupied);
    set(cached.cart,'transform',`translate(${position.x} ${position.y}) rotate(${rotation}) scale(${record.route.cartScale})`);
    set(cached.art,'transform',`scale(${facing} 1)`);set(cached.art,'data-facing',facing);
    const delta=cached.lastDistance==null?0:Math.abs(position.distance-cached.lastDistance),walking=!reduced()&&state.moving&&showCart&&delta>.00005;
    if(walking)cached.walkDistance+=delta;cached.lastDistance=position.distance;
    const gait=visuals.posePorter(cached.porter,{rotation,facing,distance:cached.walkDistance,walking});
    set(cached.cart,'data-walking',walking);set(cached.cart,'data-walk-distance',cached.walkDistance);
    set(cached.art,'data-occupied',state.occupied);set(cached.art,'data-deceased',state.deceased);
    set(cached.patient,'opacity',state.occupied?1:0);
    const cartTitle=state.occupied?(state.deceased?t('명시적 사후 이송','Explicit post-mortem transport'):t('환자 탑승 이송침대','Occupied transport cart')):t('빈 이송침대','Empty transport cart');
    if(cached.cartTitle && cached.cartTitle.textContent!==cartTitle)cached.cartTitle.textContent=cartTitle;
    set(cached.label,'x',position.x);set(cached.label,'y',position.y-1.55);
    const label=state.phase==='empty-return'?t('빈 카트','EMPTY CART'):state.occupied?t('환자 이송','PATIENT TRANSFER'):t('이송원','PORTER');
    if(cached.label.textContent!==label)cached.label.textContent=label;
    return {bed:record.bed,unit:record.unit,kind:record.kind,stage:record.stage,automatic:record.automatic,
      phase:state.phase,progress:state.progress,occupied:state.occupied,deceased:state.deceased,
      doorOpen:state.doorOpen,position:{x:position.x,y:position.y,angle:rotation},route:record.route.points.map(p=>({...p})),
      origin:record.route.origin,procedureDoor:{...record.route.procedureDoor},roomDoor:{...record.route.roomDoor},gait,moving:state.moving,animating:state.animating};
  }
  function render(time) {
    const model = current();
    if (!model) {clear();return;}
    for (const [id,tail] of tails) if (time>=tail.expires) tails.delete(id);
    descriptions = [];
    for (const [id,record] of observed) {
      if (tails.has(id)) continue;
      const description = drawItem(record,time);if (description) descriptions.push(description);
    }
    for (const tail of tails.values()) {const description=drawItem(tail,time);if(description)descriptions.push(description);}
    const activeIds=new Set(descriptions.map(item=>item.bed));
    for(const [id,item] of visualNodes)if(!activeIds.has(id)){item.group.remove();visualNodes.delete(id);}
    const moving = descriptions.some(item => item.animating) || tails.size>0;
    if (moving && !raf) raf = requestAnimationFrame(frame);
    else if (!moving && raf) {cancelAnimationFrame(raf);raf=0;}
  }
  function frame(time) {
    raf = 0;
    render(time);
  }
  function draw() {
    const model = current();if (!model) return;
    const time = now();observe(model,time);removeNativeOverlays(model);render(time);
  }
  const nativeDraw = Transfers.draw;
  Transfers.draw = function () {const result=nativeDraw.apply(this,arguments);draw();return result;};
  const nativeBusy = Transfers.busy;
  Transfers.busy = function () {return nativeBusy.apply(this,arguments) || tails.size>0;};
  const nativeClear = Transfers.clearForScope;
  Transfers.clearForScope = function () {clear();return nativeClear.apply(this,arguments);};
  // Capture user resets before source handlers can publish the replacement frame.
  document.addEventListener('click',event => {
    if (event.target.closest?.('#transferStart,#transferClear,#sandboxApply,#sandboxReset')) clear();
    const play=event.target.closest?.('#transferPlay');
    if(play){
      const time=now(),pausing=/^(Pause|일시정지)$/.test(play.textContent.trim());
      for(const record of observed.values())if(!record.automatic){
        if(pausing&&record.pausedAt==null)record.pausedAt=time;
        else if(!pausing&&record.pausedAt!=null){record.moveAt+=time-record.pausedAt;record.pausedAt=null;}
      }
      render(time);
    }
  },true);
  document.addEventListener('input',event => {if(event.target.id==='sandboxTime')clear();},true);
  document.addEventListener('icu-language',() => draw());
  window.SICUNativeTransport = Object.freeze({clear,draw,describe:() => ({
    scope,activeCount:observed.size,tailCount:tails.size,rafActive:Boolean(raf),
    busy:tails.size>0,items:descriptions.map(item => ({...item,position:{...item.position},route:item.route.map(p=>({...p}))}))
  })});
})();
