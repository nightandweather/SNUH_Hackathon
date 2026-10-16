/* Planning is a second view of the same replay owner, never another timer. */
(() => {
  'use strict';
  const q=s=>document.querySelector(s),t=(a,b)=>I18n.language==='ko'?a:b;
  let ready=false;
  function sync(){
    if(!ready)return;
    const play=q('#sandboxPlay'),apply=q('#sandboxApply'),time=q('#sandboxTime');
    const unified=window.SICUUnifiedReplay?.describe();
    const loaded=!q('#sandboxReset').disabled,loading=Boolean(unified?.loading||apply.disabled);
    const playing=Boolean(unified?.playing||/^(Pause|일시정지)$/.test(play.textContent.trim()));
    const d=window.SICUOperations?.describe();
    const profile=typeof S!=='undefined'&&S?(S.hospital_profiles?.[Network.hospital]||S.demo_profile):'';
    const option=[...q('#sandboxProfile').options].find(o=>o.value===profile);
    q('#planningReplayTitle').textContent=t('통합 시나리오 재생','Unified scenario replay');
    q('#planningReplayScenario').textContent=option?.textContent||t('저장된 초기 상태','Stored initial state');
    q('#planningReplayBasis').textContent=t('07:00–07:30 · 7개 가상 기록과 이송 예시','07:00–07:30 · seven fictional states with a porter example');
    const clock=unified?.clock||d?.clock||'07:00';
    q('#planningReplayClock').textContent=clock;
    q('#planningReplayState').textContent=loading?t('시나리오 불러오는 중','Loading scenario'):playing?t('재생 중','Playing'):unified?.complete?t('재생 완료','Complete'):loaded?t('일시정지','Paused'):t('초기 스냅샷','Initial snapshot');
    const toggle=q('#planningReplayToggle');toggle.disabled=loading;
    toggle.textContent=loading?t('불러오는 중…','Loading…'):playing?t('Ⅱ 일시정지','Ⅱ Pause'):t('▶ 재생','▶ Play');
    toggle.setAttribute('aria-pressed',String(playing));
    toggle.setAttribute('aria-label',playing?t('운영 시나리오 일시정지','Pause operations scenario'):t('운영 시나리오 재생','Play operations scenario'));
    const reset=q('#planningReplayReset');reset.disabled=loading||q('#sandboxReset').disabled;
    reset.setAttribute('aria-label',t('시나리오 처음으로','Reset scenario'));reset.title=reset.getAttribute('aria-label');
    const range=q('#planningReplayTime');range.disabled=loading||time.disabled;
    for(const key of ['min','max','step'])range[key]=time[key];
    range.value=unified?.frame??time.value;range.setAttribute('aria-label',t('재생 시점 선택','Select replay state'));
    range.setAttribute('aria-valuetext',clock+' · '+t('시뮬레이션 시각','simulation time'));
    range.style.setProperty('--replay-progress',((unified?.progress??Number(time.value)/Number(time.max))*100)+'%');
    q('#planningReplaySettings').textContent=t('시나리오 설정 ↗','Scenario settings ↗');
    q('#planningReplayFootnote').textContent=t('병동 화면과 같은 재생입니다. 상태 변화와 선택한 가상 이송 예시를 함께 보여주며, 아래 6시간 일정은 예측 결과가 아닙니다.','This shares the ward replay: state changes and the selected fictional porter example run together. The six-hour schedule below is not a forecast.');
    if(d){
      const values=[[t('재실','Occupied'),d.metrics.occupied+'/'+d.metrics.total],[t('지원 대응','Team response'),d.support.length],[t('진행 이송','Active transport'),d.currentFlows?.length??d.metrics.activeTransport]];
      [...q('#planningReplayCurrent').children].forEach((node,i)=>{node.dataset.planningCurrent=['occupied','support','transport'][i];node.querySelector('small').textContent=values[i][0];node.querySelector('b').textContent=values[i][1];});
      q('#planningReplayCurrent').setAttribute('aria-label',t('선택한 시점의 운영 상태','Operational state at the selected time'));
    }
    const error=q('#sandboxStatus').textContent;
    q('#planningReplayError').textContent=unified?.error||(!loading&&error&&!/^(Applied · fictional scenario|적용됨 · 가상 시나리오)$/.test(error)?error:'');
  }
  function setup(){
    if(ready||!q('#operationsTimeline')||!q('#staffReplayToggle'))return;
    const panel=document.createElement('section');panel.id='planningReplay';panel.dataset.noTranslate='';panel.setAttribute('aria-labelledby','planningReplayTitle');
    panel.innerHTML='<div class="planning-replay-heading"><div><h3 id="planningReplayTitle"></h3><p><b id="planningReplayScenario"></b><span id="planningReplayBasis"></span></p></div><button type="button" id="planningReplaySettings"></button></div><div class="planning-replay-player"><div class="planning-replay-clock"><output id="planningReplayClock" for="planningReplayTime">07:00</output><small id="planningReplayState"></small></div><div class="planning-replay-track"><input type="range" id="planningReplayTime" min="0" max="6" step="1" value="0" disabled><div aria-hidden="true"><span>07:00</span><span>07:15</span><span>07:30</span></div></div><div class="planning-replay-actions"><button type="button" id="planningReplayToggle"></button><button type="button" id="planningReplayReset" disabled><span aria-hidden="true">↺</span></button></div></div><div id="planningReplayCurrent"><span><small></small><b></b></span><span><small></small><b></b></span><span><small></small><b></b></span></div><p id="planningReplayFootnote"></p><p id="planningReplayError" role="status"></p>';
    q('#operationsTimeline').before(panel);
    q('#planningReplayToggle').onclick=()=>{const owner=window.SICUUnifiedReplay;if(owner&&!owner.describe().playing&&/^(Pause|일시정지)$/.test(q('#sandboxPlay').textContent.trim()))q('#sandboxPlay').click();else if(owner)owner.toggle();else q('#staffReplayToggle').click();sync();};
    q('#planningReplayReset').onclick=()=>{if(window.SICUUnifiedReplay)SICUUnifiedReplay.reset();else q('#sandboxReset').click();sync();};
    q('#planningReplayTime').oninput=event=>{if(window.SICUUnifiedReplay){SICUUnifiedReplay.seekFrame(Number(event.target.value));sync();return;}const native=q('#sandboxTime');if(native.disabled)return;native.value=event.target.value;native.dispatchEvent(new Event('input',{bubbles:true}));sync();};
    q('#planningReplaySettings').onclick=()=>q('#staffReplaySettings').click();
    const observer=new MutationObserver(sync);
    for(const id of ['#sandboxPlay','#sandboxApply','#sandboxReset','#sandboxMinute','#sandboxStatus'])observer.observe(q(id),{attributes:true,attributeFilter:['disabled'],childList:true,subtree:true,characterData:true});
    q('#sandboxProfile').addEventListener('change',sync);
    ready=true;sync();
  }
  const nativeDraw=window.draw;window.draw=function(...args){const result=nativeDraw.apply(this,args);setup();sync();return result;};
  document.addEventListener('icu-language',()=>queueMicrotask(sync));
  document.addEventListener('sicu-unified-replay',sync);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
