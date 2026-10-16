/* Retrospective display only. Never use these estimates for AI, alarms or staff routing. */
const ReplayObservations = (() => {
  'use strict';
  const VARIABLES = Object.freeze({hr:{label:'HR',unit:'bpm'},sbp:{label:'SBP',unit:'mmHg'},dbp:{label:'DBP',unit:'mmHg'},map:{label:'MAP',unit:'mmHg'},spo2:{label:'SpO₂',unit:'%'},rr:{label:'RR',unit:'/min'},temp:{label:'Temp',unit:'°C'}});
  const TABLE_KEYS = ['hr','sbp','map','spo2','rr'];
  const MAX_GAP = 60; // Display design limit; not a clinically validated interpolation threshold.
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tr = (lang, ko, en) => lang === 'en' ? en : ko;
  const format = n => finite(n) ? String(Math.round(n * 100) / 100) : '—';
  const time = (n,lang) => finite(n) ? `ICU +${format(n)} ${tr(lang,'분','min')}` : '—';

  function sourceBounds(c) {
    let start=Infinity,end=-Infinity;
    for(const row of c?.rows || []) if(finite(row.minute)){start=Math.min(start,row.minute);end=Math.max(end,row.minute);}
    return start<=end ? {start,end} : null;
  }
  function collectSeries(c,key) {
    if (!Object.hasOwn(VARIABLES,key)) return [];
    const grouped = new Map();
    function add(minute,value,historical,conflict) {
      if (!finite(minute) || minute < 0 || !finite(value)) return;
      let entry=grouped.get(minute);
      if (!entry) {entry={minute,values:new Set(),historical:false,conflict:false};grouped.set(minute,entry);}
      entry.values.add(value);entry.historical ||= historical;entry.conflict ||= conflict;
    }
    for (const r of c?.rows || []) {
      const value=r.vitals?.[key],age=r.age?.[key];
      if (!finite(r.minute)||!finite(age)||age<0) continue;
      add(r.minute-age,value,false,r.same_time_conflict?.[key]===true);
    }
    for (const e of c?.historical_vital_observations || []) {
      if (e.historical_only !== true || e.table !== 'CHARTEVENTS' || e.variable !== key) continue;
      const expected=VARIABLES[key].unit;
      if (e.unit !== expected && !(key==='temp' && e.unit==='C')) continue;
      add(e.chart_minute,e.value,true,e.same_time_conflict===true);
    }
    return [...grouped.values()].sort((a,b)=>a.minute-b.minute).map(e=>({minute:e.minute,value:e.values.size===1?[...e.values][0]:null,conflict:e.conflict||e.values.size>1,historical:e.historical}));
  }
  function atSeries(series,key,minute,bounds,{interpolate=false}={}) {
    const base={key,unit:VARIABLES[key]?.unit||'',selectedMinute:minute,value:null,kind:'missing',estimated:false,forDisplayOnly:true};
    if (!Object.hasOwn(VARIABLES,key)||!finite(minute)||!bounds) return {...base,reason:'invalid-source'};
    if (minute<bounds.start||minute>bounds.end) return {...base,reason:'outside-source-range'};
    const index=series.findLastIndex(e=>e.minute<=minute),before=series[index],after=series[index+1];
    if (!before) return {...base,reason:'before-first-observation'};
    if (before.conflict) return {...base,kind:'conflict',reason:'same-time-conflict',observedMinute:before.minute,age:minute-before.minute};
    const observed={...base,value:before.value,observedMinute:before.minute,age:minute-before.minute,historical:before.historical};
    if (before.minute===minute) return {...observed,kind:'measured'};
    if (interpolate && after && after.minute<=bounds.end && !after.conflict && finite(after.value) && after.minute-before.minute<=MAX_GAP) {
      const value=before.value+(after.value-before.value)*(minute-before.minute)/(after.minute-before.minute);
      return {...base,kind:'interpolated',estimated:true,value,historical:before.historical||after.historical,
        endpointMinutes:[before.minute,after.minute],endpointValues:[before.value,after.value],usesFutureObservation:true,gap:after.minute-before.minute};
    }
    return {...observed,kind:'carried',reason:after?.conflict?'next-observation-conflict':after&&after.minute-before.minute>MAX_GAP?'gap-too-wide':'last-observation'};
  }
  function numericAt(c,key,minute,options={}) {return atSeries(collectSeries(c,key),key,minute,sourceBounds(c),options);}

  function numericCell(item,lang) {
    const unit=esc(item.unit),isEstimate=item.kind==='interpolated';
    const flag=typeof VitalIndicators!=='undefined'?VitalIndicators.classify(item.key,item.kind==='conflict'?null:item.value):{out:false};
    let caption,title;
    if (isEstimate) {
      caption=tr(lang,'보간 추정','Interpolated');
      title=tr(lang,`${time(item.endpointMinutes[0],lang)}의 ${format(item.endpointValues[0])}과 ${time(item.endpointMinutes[1],lang)}의 ${format(item.endpointValues[1])} 사이 선형 보간. 선택 시점 이후의 관측값을 사용하는 후향적 화면 추정치입니다.`,
        `Linear interpolation between ${format(item.endpointValues[0])} at ${time(item.endpointMinutes[0],lang)} and ${format(item.endpointValues[1])} at ${time(item.endpointMinutes[1],lang)}. Retrospective display uses a later observation.`);
    } else if (item.kind==='measured') {caption=tr(lang,'관측','Measured')+' · '+time(item.observedMinute,lang);title=caption;}
    else if (item.kind==='carried') {caption=tr(lang,`${format(item.age)}분 전 관측`,`${format(item.age)} min since observation`);title=tr(lang,'최근 관측값 유지 · ','Last measured value · ')+time(item.observedMinute,lang);}
    else if (item.kind==='conflict') {caption=tr(lang,'동일 시각 값 충돌','Conflicting observations');title=caption+' · '+time(item.observedMinute,lang);}
    else {caption=tr(lang,item.reason==='outside-source-range'?'기록 범위 밖':'관측 없음',item.reason==='outside-source-range'?'Outside source range':'No observation');title=caption;}
    if(flag.out)title+=' · '+tr(lang,'표시 범위 이탈: ','Outside display range: ')+flag.rangeText;
    if (item.historical) title+=' · '+tr(lang,'기록 시각 기준 · 당시 가용 시각 미확인','By chart time · Availability then unknown');
    return `<td class="replay-number replay-${esc(item.kind)}${flag.out?' vital-out-of-range':''}" data-vital-out="${flag.out?'true':'false'}" data-observation-kind="${esc(item.kind)}" title="${esc(title)}"><strong>${isEstimate?'≈ ':''}${format(item.value)}${flag.out?' '+(flag.direction==='low'?'↓':'↑'):''}</strong><span class="replay-unit">${unit}</span><small>${esc(caption)}</small>${isEstimate?`<small class="replay-endpoints">${esc(format(item.endpointMinutes[0]))} → ${esc(format(item.endpointMinutes[1]))} ${tr(lang,'분','min')}</small>`:''}</td>`;
  }
  const styles=`
.replay-observations{margin:16px 0;padding:18px;background:#fff;border:1px solid #d6e1ee;border-radius:14px;color:#20334e}
.replay-observations header{color:#20334e;position:static;padding:0;border:0;box-shadow:none;background:transparent;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:8px}.replay-observations h3{color:#20334e;margin:0;font-size:17px}.replay-interpolation-toggle{color:#20334e;display:flex;align-items:center;gap:8px;font-weight:700;cursor:pointer}.replay-interpolation-toggle input{width:18px;height:18px;accent-color:#1765ad}.replay-observations .replay-table-note{font-size:12px;line-height:1.6;color:#5b6d83;margin:6px 0 12px}.replay-table-scroll{overflow-x:auto;max-width:100%}.replay-observations table{border-collapse:collapse;width:100%;min-width:720px;table-layout:fixed}.replay-observations th{background:#edf3f9;color:#324b69;text-align:left;font-size:12px;padding:9px 7px}.replay-observations th:first-child{width:6%}.replay-observations th:nth-child(2){width:18%}.replay-observations td{padding:10px 7px;border-bottom:1px solid #e2e9f1;vertical-align:middle}.replay-observations tbody tr:last-child td{border-bottom:0}.replay-patient-button{border:0!important;border-radius:6px;background:transparent!important;color:#174d83!important;font-size:14px;font-weight:800;padding:3px 0!important;text-align:left;cursor:pointer}.replay-patient-button:focus-visible{outline:3px solid #1765ad;outline-offset:3px}.replay-observations td small{display:block;color:#65758a;font-size:10px;line-height:1.5;margin-top:3px;overflow-wrap:anywhere}.replay-observations .replay-state{display:inline-block;font-size:11px;color:#324b69;background:#edf3f8;border-radius:5px;padding:2px 5px}.replay-state[data-state=red],.replay-state[data-state=critical]{background:#ffe9eb;color:#9a2635}.replay-state[data-state=blue],.replay-state[data-state=watch]{background:#e7f1ff;color:#205891}.replay-state[data-state=green],.replay-state[data-state=stable]{background:#e3f5ee;color:#146f50}.replay-state[data-state=yellow],.replay-state[data-state=reserved]{background:#fff4c9;color:#7e6108}.replay-state[data-state=empty]{background:#edf0f4;color:#637286}.replay-number strong{font-size:17px;font-variant-numeric:tabular-nums}.replay-unit{font-size:10px;color:#6b7b90;margin-left:3px}.replay-number.replay-interpolated{background:#fff8e6}.replay-number.replay-interpolated strong{color:#8a5d00}.replay-number.replay-interpolated small{color:#8a5d00}.replay-number.replay-missing strong,.replay-number.replay-conflict strong{color:#8290a3}.replay-number.replay-conflict{background:#fff1eb}.replay-lab-summary{font-size:12px}.replay-empty td{background:#f9fafc}
`;
  /**
   * slots: at most eight {case, minute, caseIndex, label, status:{key,label}, lab?}.
   * lab optionally {label,value,unit,minute}; supply only selected-time eligible actual lab results.
   * Returns markup only. Caller attaches checkbox change and existing [data-case] click handlers.
   */
  function renderTable({slots=[],lang='ko',interpolate=false,includeLab=false}={}) {
    const display=Array.from({length:8},(_,i)=>slots[i]||{});
    const rows=display.map((slot,index)=>{
      const c=slot.case,status=slot.status||{},statusLabel=status.label||(!c?tr(lang,'빈 병상','Empty bed'):tr(lang,'입실','Occupied'));
      const patient=c?(slot.label||c.display_name||c.id||tr(lang,'환자','Patient')):'—';
      const patientText=c&&Number.isInteger(slot.caseIndex)&&slot.caseIndex>=0?`<button type="button" class="replay-patient-button" data-case="${slot.caseIndex}">${esc(patient)}</button>`:`<strong>${esc(patient)}</strong>`;
      const bounds=sourceBounds(c);
      const cells=TABLE_KEYS.map(key=>numericCell(c?atSeries(collectSeries(c,key),key,slot.minute,bounds,{interpolate}):{key,unit:VARIABLES[key].unit,kind:'missing',value:null},lang)).join('');
      let labCell='';if(includeLab){const lab=slot.lab,valid=lab&&finite(lab.minute)&&finite(slot.minute)&&lab.minute<=slot.minute;labCell=`<td class="replay-lab-summary">${valid?`${esc(lab.label)} <b>${esc(lab.value??'—')}</b> ${esc(lab.unit||'')}<small>${esc(time(lab.minute,lang))}</small>`:`—<small>${tr(lang,'연결된 결과 없음','No linked result')}</small>`}</td>`;}
      return `<tr class="${c?'replay-occupied':'replay-empty'}" data-replay-bed="${index+1}"><td><b>${String(index+1).padStart(2,'0')}</b></td><td>${patientText}<br><span class="replay-state" data-state="${esc(status.key||(!c?'empty':''))}">${esc(statusLabel)}</span>${c?`<small>${esc(time(slot.minute,lang))}</small>`:''}</td>${cells}${labCell}</tr>`;
    }).join('');
    return `<section class="replay-observations" aria-label="${tr(lang,'8병상 관측 요약','Eight-bed observation summary')}"><style>${styles}${typeof VitalIndicators!=='undefined'?VitalIndicators.styles:''}</style><header><h3>${tr(lang,'8병상 관측 요약','Eight-bed observation summary')}</h3><label class="replay-interpolation-toggle"><input type="checkbox" data-replay-interpolate ${interpolate?'checked':''}>${tr(lang,'보간 보기','Interpolated view')}</label></header><p class="replay-table-note">${tr(lang,'재생 시점마다 갱신됩니다. 값 아래에 실제 관측 시각을 표시합니다. 보간은 60분 이내 두 관측 사이에서만 표시하며, ≈ 값은 이후 관측을 사용하는 화면 재생용 추정치입니다. 빨간 값·화살표는 설정한 표시 범위 이탈이며, 보간값도 ≈ 표시를 유지합니다. AI·알림·의료진 이동 판단에는 사용하지 않습니다.','Updates with each replay step. Actual observation times appear below values. Interpolation is limited to a gap of 60 minutes. ≈ values are retrospective display estimates using a later observation. Red values and arrows mark configured display-range crossings; estimates retain ≈ and are excluded from AI, alerts and staff routing.')}</p>${typeof VitalIndicators!=='undefined'?VitalIndicators.settings(lang):''}<div class="replay-table-scroll"><table><thead><tr><th scope="col">${tr(lang,'병상','Bed')}</th><th scope="col">${tr(lang,'환자 · 상태','Patient · Status')}</th>${TABLE_KEYS.map(key=>`<th scope="col">${VARIABLES[key].label} <small>(${esc(VARIABLES[key].unit)})</small></th>`).join('')}${includeLab?`<th scope="col">${tr(lang,'최근 검사','Latest lab')}</th>`:''}</tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }
  return Object.freeze({numericAt,collectSeries,sourceBounds,renderTable,numericCell,variables:VARIABLES,maxInterpolationGap:MAX_GAP});
})();
if(typeof window!=='undefined')window.ReplayObservations=ReplayObservations;
if(typeof module!=='undefined'&&module.exports)module.exports=ReplayObservations;
