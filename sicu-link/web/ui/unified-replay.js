/* A single presentation clock for the source's seven stored states and one
 * explicitly fictional porter example. Source frames and caches remain native.
 */
(() => {
  'use strict';
  const DURATION=14000,FRAMES=6;
  const q=selector=>document.querySelector(selector);
  const t=(a,b)=>document.documentElement.lang.startsWith('ko')?a:b;
  const clamp=value=>Math.min(1,Math.max(0,Number(value)||0));
  const kinds=['arrival','departure','icu_death'];
  let token=0,raf=0,lastTick=0,lastEvent=0,internal=0;
  let playing=false,loading=false,prepared=false,progress=0,frame=0;
  let selectedKind='arrival',available=false,hasScene=false,scope=null,error=null,notice=false,ready=false;
  let sourceFrame=-1;
  let pendingSource=null,protectedProfile=null,recovering=false;
  const scenes=()=>window.SICUTransportScenes;
  const profile=()=>typeof S!=='undefined'&&S?(S.hospital_profiles?.[Network.hospital]||S.demo_profile||''):'';
  const currentScope=()=>({hospital:typeof Network==='undefined'?'':Network.hospital,ward:q('#wardScope')?.value||'',profile:profile()});
  const sameScope=(a,b)=>Boolean(a&&b&&a.hospital===b.hospital&&a.ward===b.ward&&a.profile===b.profile);
  const nativeFrame=()=>Math.min(FRAMES,Math.max(0,Number(q('#sandboxTime')?.value)||0));
  const loaded=()=>Boolean(q('#sandboxReset')&&!q('#sandboxReset').disabled);
  const nativePlaying=()=>/^(Pause|일시정지)$/.test(q('#sandboxPlay')?.textContent.trim()||'');
  const text=(id,value)=>{const node=q(id);if(node&&node.textContent!==String(value))node.textContent=String(value);};
  function guarded(callback){internal++;try{return callback();}finally{internal--;}}
  function restorePreparationFocus(node){
    if(node?.isConnected&&document.activeElement===document.body&&!document.querySelector('dialog[open]'))node.focus({preventScroll:true});
  }
  function stopNative(){const button=q('#sandboxPlay');if(button&&nativePlaying())guarded(()=>button.onclick.call(button));}
  function sceneState(){return scenes()?.describe?.()||{};}
  function kindAvailable(){const value=sceneState().available;return typeof value==='boolean'?value:Boolean(value?.[selectedKind]);}
  function describe(){
    const state=sceneState();
    const active=Boolean(hasScene&&state.kind===selectedKind&&state.coordinated);
    return {playing,loading:loading||recovering,progress,frame,clock:q('#sandboxMinute')?.textContent||'07:00',selectedKind,
      complete:prepared&&progress>=1,available:prepared?Boolean(available&&active):kindAvailable(),
      phase:active&&Number.isFinite(state.phase)?state.phase:null,error,scope:(prepared||loading)&&scope?{...scope}:currentScope(),
      prepared,recordsOnly:prepared&&!active};
  }
  function emit(force=false){
    const now=performance.now();if(!force&&now-lastEvent<100)return;lastEvent=now;
    document.dispatchEvent(new CustomEvent('sicu-unified-replay',{detail:describe()}));
  }
  function sync(forceEvent=false){
    if(!ready)return;
    const d=describe(),bar=q('#unifiedReplay');
    bar.dataset.playing=String(playing);bar.dataset.loading=String(d.loading);bar.dataset.prepared=String(prepared);
    bar.dataset.selectedKind=selectedKind;bar.dataset.recordsOnly=String(d.recordsOnly);bar.dataset.available=String(d.available);
    bar.dataset.frame=String(frame);bar.dataset.phase=d.phase==null?'':String(d.phase);
    text('#unifiedReplayTitle',t('상태 변화 · 간호사 대응 · 환자 이송','Patient status · nursing response · transport'));
    text('#unifiedReplayBasis',t('30분 가상 기록 · 이송 예시를 함께 재생합니다.','30-minute fictional records + a porter example.'));
    text('#unifiedReplayClock',d.clock);
    text('#unifiedReplayClockLabel',t('시뮬레이션 시각','Simulation time'));
    text('#unifiedReplayKindLabel',t('함께 볼 이송 예시','Transport example'));
    const names={arrival:t('입실','Admission'),departure:t('병동 전동','Ward transfer'),icu_death:t('사후 이송','Post-mortem transport')};
    [...q('#unifiedReplayKind').options].forEach(option=>{if(option.textContent!==names[option.value])option.textContent=names[option.value];});
    q('#unifiedReplayKind').value=selectedKind;
    const state=sceneState(),steps=window.SICUTransportModel?.steps?.[selectedKind];
    const phaseText=d.phase==null?'':steps?.[d.phase]?.[document.documentElement.lang.startsWith('ko')?0:1]||'';
    const unavailable=selectedKind==='arrival'?t('빈 병상이 없어 입실 예시 없이 기록만 재생합니다.','No vacant bed: replaying records without an admission example.'):
      t('해당 이송 예시를 시작할 환자가 없어 기록만 재생합니다.','No patient is available for this transport example; replaying records only.');
    const status=d.loading?t('가상 기록을 불러오는 중','Loading fictional records'):error?t('재생 준비를 확인해 주세요.','Review replay preparation.'):
      d.recordsOnly?(notice?t('이송 예시가 해제되어 기록만 재생합니다.','The transport example ended; replaying records only.'):unavailable):
      d.complete?t('재생 완료 · 마지막 상태','Complete · final state'):
      prepared?(state.bed?state.bed+' · ':'')+(phaseText||t('기록 재생','Record replay')):
      t('재생을 누르면 상태 변화와 이동을 함께 확인할 수 있습니다.','Play to follow recorded state changes and movement together.');
    text('#unifiedReplayStatus',status);text('#unifiedReplayError',error||'');
    const toggle=q('#unifiedReplayToggle'),label=d.loading?t('불러오는 중…','Loading…'):playing?t('일시정지','Pause'):d.complete?t('다시 재생','Replay'):t('재생','Play');
    toggle.disabled=d.loading;toggle.setAttribute('aria-pressed',String(playing));
    toggle.setAttribute('aria-label',playing?t('통합 재생 일시정지','Pause combined replay'):t('상태 변화와 이송 예시 함께 재생','Play records and transport example together'));
    const icon=playing?'<path d="M8 5v14M16 5v14"/>':'<path d="m9 5 10 7-10 7Z"/>';
    const markup='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+icon+'</svg><span>'+label+'</span>';
    const presentation=String(playing)+'|'+label;
    if(toggle.dataset.presentation!==presentation){toggle.innerHTML=markup;toggle.dataset.presentation=presentation;}
    q('#unifiedReplayReset').disabled=d.loading||!loaded();
    q('#unifiedReplayReset').setAttribute('aria-label',t('통합 재생 처음으로','Reset combined replay'));
    q('#unifiedReplayReset').title=t('처음으로','Reset');
    const range=q('#unifiedReplayTime');range.disabled=d.loading;range.value=String(progress*100);
    range.setAttribute('aria-label',t('통합 재생 시점','Combined replay position'));
    range.setAttribute('aria-valuetext',d.clock+' · '+Math.round(progress*100)+'%');
    range.style.setProperty('--unified-progress',(progress*100)+'%');
    text('#unifiedReplaySettings',t('시나리오 설정 ↗','Scenario settings ↗'));
    text('#individualTransportExamples>summary',t('개별 이송 예시','Individual transport examples'));
    document.body.dataset.staffPlayback=playing||nativePlaying()?'playing':'paused';
    emit(forceEvent);
  }
  function writeFrame(next,force=false){
    const input=q('#sandboxTime');if(!input||input.disabled)return false;
    if(!force&&next===sourceFrame)return true;
    sourceFrame=next;frame=next;input.value=String(next);
    // Reuse the source refresh guard so an in-flight poll captured before this
    // frame change cannot overwrite a later seek, replay checkpoint or reset.
    if(typeof stateEpoch!=='undefined')stateEpoch++;
    const event=new Event('input',{bubbles:true});event.sicuUnifiedReplay=true;
    guarded(()=>input.dispatchEvent(event));
    return true;
  }
  function advance(value,run){
    progress=clamp(value);const next=Math.min(FRAMES,Math.floor(progress*FRAMES+1e-9));
    writeFrame(next);
    if(hasScene){
      const state=sceneState();
      if(state.kind===selectedKind&&state.coordinated)guarded(()=>scenes().advance(progress,run));
      else{hasScene=false;available=false;notice=true;}
    }
  }
  function stopClock(){cancelAnimationFrame(raf);raf=0;playing=false;lastTick=0;}
  function cancel(restore=true){
    if(pendingSource)pendingSource.cancelled=true;
    token++;stopClock();loading=false;prepared=false;hasScene=false;available=false;error=null;notice=false;
    if(restore&&scenes())guarded(()=>scenes().reset());
    frame=nativeFrame();sourceFrame=frame;progress=frame/FRAMES;scope=currentScope();sync(true);
  }
  async function waitForSource(ticket){
    const began=performance.now();
    while(q('#sandboxApply')?.disabled||recovering){
      if(ticket!==token)return false;
      if(performance.now()-began>20000)throw new Error(t('가상 기록 불러오기를 완료하지 못했습니다.','Fictional records did not finish loading.'));
      await new Promise(resolve=>setTimeout(resolve,40));
    }
    return ticket===token;
  }
  async function loadSource(apply){
    const record={profile:q('#sandboxProfile').value,cancelled:false};pendingSource=record;
    try{
      await guarded(()=>apply.onclick.call(apply));
      // applyScenario owns an unabortable private fetch and frame cache. If the
      // user changed scope while it loaded, refill that cache for the currently
      // active hospital before releasing the late-acceptance guard.
      while(record.cancelled&&record.profile!==profile()){
        const active=profile(),select=q('#sandboxProfile');
        if(!active||![...select.options].some(option=>option.value===active))break;
        protectedProfile=active;recovering=true;sync(true);select.value=active;
        await guarded(()=>apply.onclick.call(apply));
        const status=q('#sandboxStatus')?.textContent||'';
        if(!/^(Applied · fictional scenario|적용됨 · 가상 시나리오)$/.test(status))throw new Error(status||t('현재 병원의 기록을 다시 불러오지 못했습니다.','Could not reload the current hospital records.'));
        record.profile=active;
      }
      const status=q('#sandboxStatus')?.textContent||'';
      if(!/^(Applied · fictional scenario|적용됨 · 가상 시나리오)$/.test(status))throw new Error(status||t('가상 기록을 불러오지 못했습니다.','Could not load fictional records.'));
      // A canceled preparation must not launch native automatic transfers from
      // differences between the initial snapshot and the recovered source frame.
      if(record.cancelled&&scenes())guarded(()=>scenes().reset());
      protectedProfile=null;
    }catch(reason){
      if(record.cancelled){error=reason?.message||String(reason);sync(true);}
      else throw reason;
    }finally{
      if(pendingSource===record)pendingSource=null;
      recovering=false;sync(true);
    }
  }
  async function prepare(value){
    if(prepared&&sameScope(scope,currentScope()))return true;
    const active=document.activeElement;
    const focus=active?.matches('#unifiedReplayToggle,#unifiedReplayTime,#planningReplayToggle,#planningReplayTime')?active:null;
    const ticket=++token;loading=true;error=null;notice=false;scope=currentScope();stopClock();sync(true);
    try{
      stopNative();
      if(scenes())guarded(()=>scenes().reset());
      if(!await waitForSource(ticket))return false;
      if(!loaded()||protectedProfile){
        const select=q('#sandboxProfile'),apply=q('#sandboxApply'),active=profile();
        if([...select.options].some(option=>option.value===active))select.value=active;
        await loadSource(apply);
        if(ticket!==token)return false;
        if(!await waitForSource(ticket))return false;
      }
      if(ticket!==token)return false;
      if(!loaded())throw new Error(q('#sandboxStatus')?.textContent||t('가상 기록을 불러오지 못했습니다.','Could not load fictional records.'));
      if(!sameScope(scope,currentScope())){cancel(true);return false;}
      if(typeof scenes()?.advance!=='function')throw new Error(t('이송 예시 준비를 완료하지 못했습니다.','The transport example is not ready.'));
      progress=0;frame=0;sourceFrame=-1;writeFrame(0,true);
      available=Boolean(guarded(()=>scenes().start(selectedKind,false,{coordinated:true})));
      hasScene=available;prepared=true;loading=false;
      advance(value,false);sync(true);restorePreparationFocus(focus);return true;
    }catch(reason){
      if(ticket!==token)return false;
      loading=false;prepared=false;hasScene=false;available=false;stopClock();error=reason?.message||String(reason);sync(true);restorePreparationFocus(focus);return false;
    }
  }
  function tick(now){
    if(!playing||!prepared)return;
    if(!sameScope(scope,currentScope())){cancel(true);return;}
    const value=Math.min(1,progress+Math.max(0,now-lastTick)/DURATION);lastTick=now;
    if(value>=1)playing=false;
    advance(value,playing);sync(value>=1);
    if(playing)raf=requestAnimationFrame(tick);else{raf=0;window.SICUStaff?.syncPlayback();}
  }
  async function play(){
    if(playing)return true;
    const value=progress>=1?0:progress;
    if(progress>=1)cancel(true);
    const pending=prepare(value),ticket=token;
    if(!await pending||ticket!==token)return false;
    playing=true;lastTick=performance.now();advance(progress,true);sync(true);window.SICUStaff?.syncPlayback();
    cancelAnimationFrame(raf);raf=requestAnimationFrame(tick);return true;
  }
  function pause(){
    token++;
    if(loading){if(pendingSource)pendingSource.cancelled=true;loading=false;stopClock();sync(true);return;}
    const value=playing?Math.min(1,progress+Math.max(0,performance.now()-lastTick)/DURATION):progress;
    stopClock();if(prepared)advance(value,false);sync(true);window.SICUStaff?.syncPlayback();
  }
  function toggle(){return playing||loading?pause():play();}
  function reset(){
    cancel(true);progress=0;frame=0;sourceFrame=-1;if(loaded())writeFrame(0,true);sourceFrame=nativeFrame();sync(true);
  }
  async function seek(value){
    pause();const wanted=clamp(value);
    const pending=prepare(wanted),ticket=token;
    if(!await pending||ticket!==token)return false;
    advance(wanted,false);sync(true);return true;
  }
  function seekFrame(value){return seek(Math.min(FRAMES,Math.max(0,Math.round(Number(value)||0)))/FRAMES);}
  function setKind(value){
    if(!kinds.includes(value))return false;
    if(value===selectedKind)return true;
    reset();selectedKind=value;available=kindAvailable();sync(true);return true;
  }
  function setup(){
    if(ready||!q('#staffMapToolbar')||!q('#transportSceneBar')||!q('#demoToolBody'))return;
    const panel=document.createElement('section');panel.id='unifiedReplay';panel.dataset.noTranslate='';panel.setAttribute('aria-labelledby','unifiedReplayTitle');
    panel.innerHTML='<div class="unified-replay-heading"><div><h3 id="unifiedReplayTitle"></h3><p id="unifiedReplayBasis"></p></div><button type="button" id="unifiedReplaySettings"></button></div><div class="unified-replay-player"><div class="unified-replay-clock"><output id="unifiedReplayClock" for="unifiedReplayTime">07:00</output><small id="unifiedReplayClockLabel"></small></div><div class="unified-replay-track"><input type="range" id="unifiedReplayTime" min="0" max="100" step=".1" value="0"><div aria-hidden="true"><span>07:00</span><span>07:15</span><span>07:30</span></div></div><div class="unified-replay-actions"><button type="button" id="unifiedReplayToggle"></button><button type="button" id="unifiedReplayReset"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4v6h6M4.8 9a7.5 7.5 0 1 1-.2 5"/></svg></button></div></div><div class="unified-replay-context"><label><span id="unifiedReplayKindLabel"></span><select id="unifiedReplayKind"><option value="arrival"></option><option value="departure"></option><option value="icu_death"></option></select></label><span id="unifiedReplayStatus" role="status" aria-live="polite"></span></div><p id="unifiedReplayError" role="alert"></p><div class="unified-replay-support"></div>';
    const staff=q('#staffMapToolbar');staff.before(panel);panel.querySelector('.unified-replay-support').append(staff);
    const examples=document.createElement('details');examples.id='individualTransportExamples';examples.dataset.noTranslate='';examples.append(document.createElement('summary'));
    examples.append(q('#transportSceneBar'));const note=q('#transportOperationsNote');if(note)examples.append(note);q('#demoToolBody').append(examples);
    q('#unifiedReplayToggle').onclick=toggle;q('#unifiedReplayReset').onclick=reset;
    q('#unifiedReplayTime').oninput=event=>seek(Number(event.target.value)/100);
    q('#unifiedReplayKind').onchange=event=>setKind(event.target.value);
    q('#unifiedReplaySettings').onclick=()=>q('#staffReplaySettings').click();
    ready=true;scope=currentScope();frame=nativeFrame();sourceFrame=frame;progress=frame/FRAMES;sync(true);
  }
  window.SICUUnifiedReplay=Object.freeze({play,pause,toggle,reset,seek,seekFrame,setKind,describe});
  const nativeAccept=window.acceptState;
  window.acceptState=function(data){
    if(pendingSource?.cancelled||protectedProfile){
      const active=profile(),incoming=data?.hospital_profiles?.[Network.hospital]||data?.demo_profile||'';
      if(active&&incoming&&incoming!==active){protectedProfile=active;return;}
    }
    return nativeAccept.apply(this,arguments);
  };
  // Capture before original private navigation and replay handlers. Marked input
  // belongs to this owner; ordinary advanced controls hand ownership back safely.
  document.addEventListener('click',event=>{
    if(internal||event.sicuUnifiedReplay)return;
    if(event.target.closest('#sandboxApply'))protectedProfile=null;
    if(event.target.closest('#staffReplayToggle,#sandboxPlay,#sandboxReset,#sandboxApply,#applyProfile,#reset,#transportScenePlay,#transportSceneReset,[data-transport-kind],#transferStart,#transferNext,#transferPlay,#transferClear,#workspaceHome,#entryStart,[data-hospital],[data-ward],[data-operations-locate],[data-network-locate],[data-network-work-hospital]'))cancel(true);
  },true);
  document.addEventListener('input',event=>{if(!internal&&!event.sicuUnifiedReplay&&event.target.matches('#sandboxTime')){const value=event.target.value;cancel(true);event.target.value=value;}},true);
  document.addEventListener('change',event=>{if(!internal&&!event.sicuUnifiedReplay&&event.target.matches('#hospitalScope,#wardScope,#sandboxProfile,#profile,#me')){const value=event.target.value;cancel(true);event.target.value=value;}},true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&(playing||loading))pause();});
  document.addEventListener('icu-language',()=>queueMicrotask(()=>sync(true)));
  const nativeDraw=window.draw;
  window.draw=function(){
    const result=nativeDraw.apply(this,arguments);setup();
    if((prepared||loading)&&!internal&&!sameScope(scope,currentScope()))cancel(true);
    else if(!prepared&&!loading){frame=nativeFrame();sourceFrame=frame;progress=frame/FRAMES;scope=currentScope();}
    sync();return result;
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
