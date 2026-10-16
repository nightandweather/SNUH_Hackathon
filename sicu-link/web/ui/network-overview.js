/* Coordination-only operational folios. Only anonymous allowlist data is rendered;
 * these controls never navigate to a bedside or individual staff workspace. */
(() => {
  'use strict';
  const q=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const t=(a,b)=>I18n.language==='ko'?a:b,E=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let ready=false,current=null,signature='',lastRender=0,detail=null,opener=null,dialogSignature='';
  const raw=()=>window.SICULinkState?.raw;
  const name=h=>I18n.t(h.name),unitName=u=>I18n.t(I18n.language==='ko'?u.nameKo:u.nameEn);
  const title=kind=>({summary:t('ICU 운영 요약','ICU operations'),preparation:t('수용 준비 확인','Preparation checks'),arrivals:t('예정 입실 · 6시간','Expected arrivals · 6h'),support:t('지원 대응 집계','Team response totals')})[kind]||'';
  const attrs=(kind,site='',unit='')=>'data-coordination-task="'+kind+'" data-coordination-site="'+E(site)+'" data-coordination-unit-scope="'+E(unit)+'"';
  function semantic(button){return button?['coordinationTask','coordinationSite','coordinationUnitScope','coordinationUnit','coordinationSummary'].map(key=>button.dataset[key]||'').join('|'):'';}
  function equivalent(button){const key=semantic(button);return key?all('#networkCards button,#networkWork button,#networkDetail button').find(node=>semantic(node)===key):null;}
  function unitButton(unit,hospital){
    return '<button type="button" class="network-unit" data-coordination-unit="'+E(unit.id)+'" data-coordination-site="'+E(hospital.id)+'" aria-label="'+E(name(hospital)+' · '+unitName(unit)+' · '+t('운영 요약 열기','Open operations summary'))+'"><span class="network-unit-heading"><b>'+E(unit.id)+'</b><small>'+E(unit.floor==null?'':unit.floor+'F')+' <i aria-hidden="true">↗</i></small></span><span class="network-unit-name">'+E(unitName(unit))+'</span>'+SICUNetworkVisuals.ward(unit,{language:I18n.language,operational:true})+'<span class="network-unit-census"><span>'+t('사용 ','Occupied ')+unit.counts.occupied+'/'+unit.bedCount+'</span><span>'+t('빈 병상 ','Vacant ')+unit.counts.empty+' · '+t('예약 ','Reserved ')+unit.counts.reserved+'</span></span></button>';
  }
  function hospitalCard(hospital){
    const c=hospital.counts,load=c.total?Math.round(c.occupied/c.total*100):0;
    return '<article class="hospital-card network-hospital" data-network-hospital-card="'+E(hospital.id)+'"><div class="network-hospital-head"><span class="network-hospital-letter" aria-hidden="true">'+E(hospital.id)+'</span><h3>'+E(name(hospital))+'<small class="network-facility-type">'+E(I18n.language==='ko'?hospital.typeKo:hospital.typeEn)+' · '+hospital.units.length+' ICU</small></h3><span class="network-staff-count">'+t('간호사','Nurses')+' <b>'+c.nurses+'</b></span></div><div class="hospital-numbers"><span><strong>'+c.empty+'</strong><small>'+t('빈 병상','Vacant')+'</small></span><span><strong>'+c.occupied+'<em>/'+c.total+'</em></strong><small>'+t('사용 중','Occupied')+'</small></span><span><strong>'+c.reserved+'</strong><small>'+t('입실 예약','Reserved')+'</small></span></div><div class="network-utilization" role="img" aria-label="'+E(t('병상 사용률 ','Bed occupancy ')+load+'%')+'"><span style="width:'+load+'%"></span><small>'+load+'%</small></div><div class="network-unit-plans" data-network-unit-count="'+hospital.units.length+'">'+hospital.units.map(unit=>unitButton(unit,hospital)).join('')+'</div><div class="network-hospital-work"><button type="button" '+attrs('preparation',hospital.id)+'><span>'+t('준비 확인 대기','Preparation checks')+'</span><b>'+(c.unknownPrep+c.pendingPrep+c.turnover)+'</b><i aria-hidden="true">↗</i></button><button type="button" '+attrs('support',hospital.id)+'><span>'+t('지원 대응','Team response')+'</span><b>'+c.support+'</b><i aria-hidden="true">↗</i></button></div><div class="hospital-actions"><button type="button" data-coordination-summary="true" data-coordination-site="'+E(hospital.id)+'">'+t('병원 운영 요약','Hospital operations')+'<span aria-hidden="true">↗</span></button></div></article>';
  }
  function renderSummary(data){
    const c=data.totals;
    q('#networkSummary').innerHTML=[['total',t('전체 병상','Total beds'),c.total],['occupied',t('사용 중','Occupied'),c.occupied],['empty',t('빈 병상','Vacant'),c.empty],['reserved',t('입실 예약','Reserved'),c.reserved],['turnover',t('정리 중','Turnover'),c.turnover],['nurses',t('근무 간호사','Nurses on shift'),c.nurses]].map(([key,label,value])=>'<div data-network-total="'+key+'"><small>'+label+'</small><strong>'+value+'</strong></div>').join('');
    q('#networkRange').innerHTML='<span class="network-live-dot" aria-hidden="true"></span>'+E(data.clock)+' <span>· '+t('시뮬레이션','Simulation')+'</span>';
    q('#networkOverviewLabel').textContent=t('병원별 ICU 운영 현황','ICU operations across the network');
    q('#networkOverviewCount').textContent=c.hospitals+t('개 병원 · ',' hospitals · ')+c.units+' ICU';
    q('#networkLegend').innerHTML=[['occupied',t('사용 중','Occupied')],['empty',t('빈 병상','Vacant')],['reserved',t('예약','Reserved')],['turnover',t('정리 중','Turnover')]].map(([key,label])=>'<span><i data-network-legend="'+key+'"></i>'+label+'</span>').join('');
    q('#networkScopeNote').textContent=t('가상 관제 화면 · 병상 점유와 ICU별 운영 집계만 표시합니다. 빈 병상은 수용 확정이 아니며 인력·장비·정리 상태를 별도로 확인합니다.','Fictional coordination view: bed occupancy and ICU operations only. Vacant beds do not confirm acceptance; staff, equipment and turnover require separate checks.');
  }
  function taskRows(kind){return kind==='summary'?current.hospitals.flatMap(hospital=>hospital.units):current.work[kind]||[];}
  function renderWork(){
    q('#networkWorkTitle').textContent=t('지금 조율할 일','Coordinate next');
    q('#networkWorkNote').textContent=t('ICU별 수요와 준비·대응 현황을 확인합니다.','Review demand, preparation and response by ICU.');
    q('#networkWork').innerHTML=['arrivals','preparation','support'].map(kind=>{
      const rows=taskRows(kind),count=rows.reduce((sum,row)=>sum+(kind==='arrivals'?row.arrivals.count:kind==='support'?row.support.eventCount:row.preparation.pending+row.preparation.unknown+row.preparation.turnover),0);
      const head='<button type="button" class="network-work-heading" '+attrs(kind)+'><span>'+title(kind)+'</span><b>'+count+'</b><i aria-hidden="true">↗</i></button>';
      return '<section class="network-work-column">'+head+(rows.length?rows.slice(0,3).map(row=>'<button type="button" class="network-work-row" '+attrs(kind,row.hospital,row.unit)+'><span class="network-work-site">'+E(row.hospital)+'</span><span><b>'+E(row.unit)+'</b><small>'+(kind==='arrivals'?row.arrivals.count+t('건 · 수용 확인 대기',' arrivals · acceptance unconfirmed'):kind==='preparation'?t('인력·장비·정리 확인','Staff, equipment and turnover checks'):t('배정 합계 ','Assigned total ')+row.support.assignedCount+' · '+t('도착 합계 ','Arrived total ')+row.support.arrivedCount)+'</small></span>'+(kind==='arrivals'?'<time>'+E(row.arrivals.groups[0]?.clock||'')+'</time>':'<i aria-hidden="true">↗</i>')+'</button>').join(''):'<p class="network-empty">'+t('현재 기록된 항목이 없습니다.','No current records.')+'</p>')+(rows.length>3?'<button type="button" class="network-more" '+attrs(kind)+'>'+t('전체 ICU 집계 보기','View all ICU totals')+' →</button>':'')+'</section>';
    }).join('');
  }
  function countsHTML(unit){
    const c=unit.counts;
    return '<dl class="network-unit-operating-counts">'+[[t('사용 / 전체','Occupied / total'),c.occupied+' / '+c.total],[t('빈 병상','Vacant'),c.empty],[t('예약','Reserved'),c.reserved],[t('정리 중','Turnover'),c.turnover],[t('간호사 / 의사','Nurses / physicians'),c.nurses+' / '+c.physicians],[t('활성 이송','Active transport'),c.activeTransport]].map(([label,value])=>'<div><dt>'+label+'</dt><dd>'+value+'</dd></div>').join('')+'</dl>';
  }
  function preparationHTML(unit){
    return '<div class="network-aggregate-section"><h4>'+t('수용 준비 항목','Preparation checks')+'</h4><p>'+unit.preparation.eligible+t('개 비점유 병상 기준 · 준비 기록과 수용 확정은 별도입니다.',' unoccupied beds · recorded preparation is separate from confirmed acceptance.')+'</p><dl class="network-checks">'+Object.entries(unit.preparation.requirements).map(([key,value])=>'<div data-coordination-preparation="'+key+'"><dt>'+({staff:t('인력','Staff'),equipment:t('장비','Equipment'),cleaning:t('정리','Turnover')})[key]+'</dt><dd><span>'+t('확인 ','Confirmed ')+value.confirmed+'</span><span>'+t('진행 ','Pending ')+value.pending+'</span><span>'+t('미확인 ','Unknown ')+value.unknown+'</span></dd></div>').join('')+'</dl></div>';
  }
  function arrivalsHTML(unit){
    return '<div class="network-aggregate-section"><h4>'+t('다음 6시간 입실 예약','Recorded arrivals · next 6h')+'</h4>'+(unit.arrivals.groups.length?'<div class="network-arrival-groups">'+unit.arrivals.groups.map(group=>'<span data-coordination-arrival-at="'+group.at+'"><time>'+E(group.clock)+'</time><b>'+group.count+t('건',' arrivals')+'</b></span>').join('')+'</div>':'<p>'+t('이 시간대에 기록된 예약이 없습니다.','No reservations are recorded within this window.')+'</p>')+'</div>';
  }
  function demandText(known,unknown){return String(known)+(unknown?' + '+t('미확인 ','unknown in ')+unknown+t('건',' events'):'');}
  function supportHTML(unit){
    const s=unit.support;
    return '<div class="network-aggregate-section"><h4>'+t('지원 대응 ','Team response ')+s.eventCount+t('건',' events')+'</h4><dl class="network-response-counts">'+[[t('필요 합계','Known demand'),demandText(s.needKnown,s.needUnknownCount)],[t('배정 합계','Assigned total'),s.assignedCount],[t('도착 합계','Arrived total'),s.arrivedCount],[t('이동 중 합계','En route total'),s.pendingCount],[t('추가 필요','Additional demand'),demandText(s.shortageKnown,s.shortageUnknownCount)]].map(([label,value])=>'<div><dt>'+label+'</dt><dd>'+value+'</dd></div>').join('')+'</dl><p>'+t('대응 건별 인원 합계로, 같은 직원이 여러 대응에 포함될 수 있습니다. 미확인 수요는 0으로 간주하지 않습니다.','Totals add assignments per response event; the same person may be counted in multiple events. Unknown demand is not treated as zero.')+'</p></div>';
  }
  function renderDialog(force=false){
    const dialog=q('#networkDetail');if(!current||!detail||(!dialog.open&&!force))return;
    const key=JSON.stringify([I18n.language,detail,current]);if(!force&&key===dialogSignature)return;dialogSignature=key;
    const rows=taskRows(detail.kind).filter(row=>(!detail.site||row.hospital===detail.site)&&(!detail.unit||(row.unit||row.id)===detail.unit));
    const hospital=current.hospitals.find(item=>item.id===detail.site);
    q('#networkDetailScope').textContent=(hospital?name(hospital):t('전체 병원','All hospitals'))+' · '+current.clock+' · '+t('가상 운영 집계','Fictional operational totals');
    q('#networkDetailTitle').textContent=(detail.unit?detail.unit+' · ':'')+title(detail.kind);
    const body=q('#networkDetailBody'),scroll=body.scrollTop,focused=body.contains(document.activeElement)?document.activeElement:null;
    body.innerHTML='<p class="network-detail-intro">'+t('개인 환자 정보와 직원별 기록 없이 ICU 단위의 운영 현황을 확인합니다.','Review ICU operations without individual patient or staff records.')+'</p>'+rows.map(row=>{
      const unit=row.id?row:current.hospitals.find(h=>h.id===row.hospital).units.find(u=>u.id===row.unit);
      return '<article class="network-detail-row" data-coordination-record="'+detail.kind+'" data-coordination-record-unit="'+E(unit.id)+'"><div class="network-detail-record-head"><span class="network-work-site">'+E(unit.hospital)+'</span><span><b>'+E(unit.id)+'</b><small>'+E(unitName(unit))+'</small></span></div>'+(detail.kind==='summary'?countsHTML(unit):'')+(detail.kind==='summary'||detail.kind==='preparation'?preparationHTML(unit):'')+(detail.kind==='summary'||detail.kind==='arrivals'?arrivalsHTML(unit):'')+(detail.kind==='summary'||detail.kind==='support'?supportHTML(unit):'')+(detail.kind!=='summary'?'<button type="button" class="network-locate" data-coordination-summary="true" data-coordination-site="'+E(unit.hospital)+'" data-coordination-unit-scope="'+E(unit.id)+'">'+t('ICU 운영 요약','ICU operations summary')+' ↗</button>':'')+'</article>';
    }).join('')+(!rows.length?'<p class="network-empty">'+t('현재 기록된 항목이 없습니다.','No current records.')+'</p>':'');
    q('[data-network-close]').setAttribute('aria-label',t('운영 집계 닫기','Close operational totals'));body.scrollTop=scroll;
    if(focused)equivalent(focused)?.focus({preventScroll:true});
  }
  function open(kind,site,unit,button){
    if(document.body.dataset.workspaceMode!=='center')return;
    detail={kind,site:site||'',unit:unit||''};if(!q('#networkDetail').open)opener=button;
    renderDialog(true);if(!q('#networkDetail').open)q('#networkDetail').showModal();q('[data-network-close]').focus({preventScroll:true});
  }
  function render(force=false){
    if(!ready||!raw())return;
    const cards=q('#networkCards'),replaced=!cards.querySelector('.network-hospital');
    if(!force&&!replaced&&performance.now()-lastRender<200)return;lastRender=performance.now();
    current=SICUCoordinationModel.derive(raw());
    const key=JSON.stringify([I18n.language,current]);
    if(force||replaced||key!==signature){
      signature=key;const focused=(cards.contains(document.activeElement)||q('#networkWork').contains(document.activeElement))?document.activeElement:null;
      cards.innerHTML=current.hospitals.map(hospitalCard).join('');renderSummary(current);renderWork();
      if(focused)equivalent(focused)?.focus({preventScroll:true});
    }
    renderDialog();
  }
  function setup(){
    if(ready||!q('#networkCards')||!q('#networkView'))return;
    ready=true;const panel=q('#networkView .network-panel');panel.dataset.noTranslate='';panel.classList.add('network-overview');panel.querySelector(':scope>p.tag')?.setAttribute('hidden','');
    const intro=document.createElement('div');intro.className='network-overview-top';intro.innerHTML='<span id="networkOverviewLabel"></span><span id="networkOverviewCount"></span><span id="networkRange"></span>';
    const summary=document.createElement('div');summary.id='networkSummary';const legend=document.createElement('div');legend.id='networkLegend';
    const cards=q('#networkCards');cards.classList.add('network-overview-grid');panel.insertBefore(intro,cards);panel.insertBefore(summary,cards);panel.insertBefore(legend,cards);
    const note=document.createElement('p');note.id='networkScopeNote';cards.after(note);
    const work=document.createElement('section');work.className='network-work';work.innerHTML='<div class="network-work-title"><h3 id="networkWorkTitle"></h3><p id="networkWorkNote"></p></div><div id="networkWork"></div>';note.after(work);
    const dialog=document.createElement('dialog');dialog.id='networkDetail';dialog.dataset.noTranslate='';dialog.dataset.coordinationDialog='true';dialog.setAttribute('aria-labelledby','networkDetailTitle');dialog.innerHTML='<div class="network-detail-head"><div><small id="networkDetailScope"></small><h2 id="networkDetailTitle"></h2></div><button type="button" data-network-close aria-label="Close">×</button></div><div id="networkDetailBody"></div>';document.body.append(dialog);
    dialog.addEventListener('close',()=>{const target=opener;opener=null;if(document.body.dataset.workspaceMode==='center')(target?.isConnected?target:equivalent(target))?.focus({preventScroll:true});});
    dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
    document.addEventListener('click',event=>{
      const close=event.target.closest('[data-network-close]');if(close){dialog.close();return;}
      const task=event.target.closest('[data-coordination-task]');if(task){open(task.dataset.coordinationTask,task.dataset.coordinationSite,task.dataset.coordinationUnitScope,task);return;}
      const unit=event.target.closest('[data-coordination-unit]');if(unit){open('summary',unit.dataset.coordinationSite,unit.dataset.coordinationUnit,unit);return;}
      const site=event.target.closest('[data-coordination-summary]');if(site)open('summary',site.dataset.coordinationSite,site.dataset.coordinationUnitScope,site);
    });render(true);
  }
  const nativeDraw=window.draw;window.draw=function(...args){const result=nativeDraw.apply(this,args);setup();render();return result;};
  const nativeClear=Transfers.clearForScope;Transfers.clearForScope=function(...args){const result=nativeClear.apply(this,args);if(result?.floors)window.SICULinkState.raw=FacilityProfiles.project(result);return result;};
  const nativeRender=Network.render;Network.render=function(...args){const result=nativeRender.apply(this,args);setup();render();return result;};
  document.addEventListener('icu-language',()=>queueMicrotask(()=>render(true)));
  window.SICUNetworkOverview=Object.freeze({describe:()=>current,render:()=>render(true),close:()=>{detail=null;q('#networkDetail')?.close();}});
  setup();
})();
