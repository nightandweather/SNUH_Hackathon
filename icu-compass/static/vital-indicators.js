/* Local presentation thresholds. These are demo display settings, not clinical normal ranges. */
const VitalIndicators=(()=>{
 'use strict';
 const STORAGE_KEY='icu-vital-display-ranges-v1';
 const definitions={hr:['HR','심박수','bpm'],map:['MAP','평균동맥압','mmHg'],spo2:['SpO₂','산소포화도','%'],rr:['RR','호흡수','/min'],sbp:['SBP','수축기혈압','mmHg'],dbp:['DBP','이완기혈압','mmHg'],temp:['Temp','체온','°C']};
 const defaults={hr:{min:40,max:140},map:{min:60,max:null},spo2:{min:88,max:100},rr:{min:null,max:35},sbp:{min:90,max:null},dbp:{min:null,max:null},temp:{min:null,max:null}};
 const copy=r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,{...v}]));
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const t=(lang,ko,en)=>lang==='en'?en:ko;
 const number=n=>finite(n)?String(n):'—';
 let ranges=copy(defaults);
 function endpoint(value){
  if(value===null||value===undefined||typeof value==='string'&&!value.trim())return null;
  if(typeof value==='string'&&!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim()))throw Error('invalid_range');
  const numeric=typeof value==='string'?Number(value):value;
  if(!finite(numeric)||numeric<0)throw Error('invalid_range');return numeric;
 }
 function normalized(input,base){
  if(!input||typeof input!=='object'||Array.isArray(input))throw Error('invalid_range');const next=copy(base);
  for(const [key,bounds] of Object.entries(input)){
   if(!Object.hasOwn(definitions,key)||!bounds||typeof bounds!=='object'||Array.isArray(bounds))throw Error('invalid_range');
   const min=Object.hasOwn(bounds,'min')?endpoint(bounds.min):next[key].min,max=Object.hasOwn(bounds,'max')?endpoint(bounds.max):next[key].max;
   if(min!==null&&max!==null&&min>max)throw Error('invalid_range');next[key]={min,max};
  }return next;
 }
 function save(){try{if(typeof localStorage!=='undefined')localStorage.setItem(STORAGE_KEY,JSON.stringify(ranges));}catch(error){/* Local display remains usable if storage is unavailable. */}}
 try{if(typeof localStorage!=='undefined'){const stored=localStorage.getItem(STORAGE_KEY);if(stored)ranges=normalized(JSON.parse(stored),defaults);}}catch(error){ranges=copy(defaults);}
 function configure(input){ranges=normalized(input,ranges);save();return copy(ranges);}
 function reset(){ranges=copy(defaults);save();return copy(ranges);}
 function rangeText({min,max}){return min!==null&&max!==null?`${number(min)}–${number(max)}`:min!==null?`≥ ${number(min)}`:max!==null?`≤ ${number(max)}`:'—';}
 function classify(key,value){
  const bounds=ranges[key]||{min:null,max:null},valid=finite(value)&&value>=0;
  const direction=valid&&bounds.min!==null&&value<bounds.min?'low':valid&&bounds.max!==null&&value>bounds.max?'high':null;
  return {out:direction!==null,direction,rangeText:rangeText(bounds),min:bounds.min,max:bounds.max,valid};
 }
 function valueMarkup(key,value,lang='ko'){
  const state=classify(key,value);if(!state.valid)return '<span class="vital-display-missing">—</span>';
  const label=definitions[key]?.[0]||key,arrow=state.direction==='high'?'↑':state.direction==='low'?'↓':'',description=state.out?t(lang,state.direction==='high'?'표시 상한 초과':'표시 하한 미만',state.direction==='high'?'Above display limit':'Below display limit'):t(lang,'표시 범위 안','Within display range');
  const title=`${label} ${number(value)} · ${description} · ${t(lang,'시연 표시 범위','Demo display range')} ${state.rangeText}`;
  return `<span class="vital-display-value${state.out?' vital-display-out':''}" data-vital-direction="${state.direction||'none'}" aria-label="${esc(title)}" title="${esc(title)}">${number(value)}${arrow?` <span aria-hidden="true">${arrow}</span>`:''}</span>`;
 }
 const styles=`
.vital-display-out{color:#b71f32!important;font-weight:850}.vital-display-missing{color:#7b8999}.vital-indicator-settings{margin:14px 0;padding:13px 15px;border:1px solid #d5e0eb;border-radius:10px;background:#f8fafc;color:#21374f}.vital-indicator-settings summary{font-size:13px;font-weight:800;cursor:pointer;color:#21374f}.vital-indicator-settings p{color:#5c6f85;font-size:12px;line-height:1.6;margin:9px 0}.vital-indicator-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:10px}.vital-indicator-settings fieldset{border:1px solid #d4dfeb;border-radius:8px;min-width:0;margin:0;padding:10px;background:#fff}.vital-indicator-settings legend{font-size:12px;font-weight:800;color:#304b66;padding:0 4px}.vital-indicator-fields{display:flex;gap:10px}.vital-indicator-settings label{display:grid;gap:5px;flex:1;min-width:0;font-size:11px;color:#4b6079}.vital-indicator-settings input{min-width:0;width:100%;height:35px;padding:6px 8px;border:1px solid #afbed1;border-radius:6px;background:#fff;color:#21374f;font:inherit;font-size:13px;box-sizing:border-box}.vital-indicator-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:12px}.vital-indicator-actions button{min-height:36px;border:1px solid #a9bfd6;border-radius:7px;background:#fff;color:#214f7b;padding:7px 12px;font-size:12px;font-weight:750;cursor:pointer}.vital-indicator-status{font-size:12px;color:#32664a}.vital-indicator-status[role=alert]{color:#b71f32}.vital-reference{margin:16px 0;padding:17px;border:1px solid #c9d9e9;border-radius:11px;background:#f5f9fd;color:#21374f}.vital-reference h3,.vital-reference h4{color:#21374f;margin:0 0 10px}.vital-reference p{font-size:12px;line-height:1.6;color:#526981}.vital-reference-formula{white-space:pre-wrap;padding:10px;border-radius:7px;background:#e9f0f8;font-family:inherit;font-size:13px;overflow-wrap:anywhere}.vital-reference-scroll{overflow:auto}.vital-reference table{width:100%;border-collapse:collapse;background:#fff;font-size:12px;min-width:440px}.vital-reference th,.vital-reference td{padding:9px;border:1px solid #d9e3ed;text-align:left;vertical-align:top;color:#263e56}.vital-reference th{background:#edf3f9}.vital-reference-result{display:block;padding:10px 12px;margin:10px 0;border-radius:7px;background:#e6eef7;color:#244766;font-size:14px}.vital-reference-result.incomplete{background:#fff2d8;color:#805d15}.vital-reference a{color:#175c9f;text-decoration:underline}.vital-reference-links{display:flex;gap:15px;flex-wrap:wrap;font-size:12px;margin-top:10px}
`;
 function settings(lang='ko'){
  const heading=t(lang,'표시 범위 · 시연 설정 (임상 정상범위 아님)','Display ranges · Demo settings (not clinical normal ranges)');
  return `<details class="vital-indicator-settings"><summary>${heading}</summary><p>${t(lang,'초기값은 기존 시연의 중증 표시 기준과 SBP 90 표시 기준을 유지합니다. 범위를 벗어난 숫자에 빨간색 ↑/↓를 표시합니다. 빈 칸은 해당 방향 제한 없음이며, 이 브라우저에만 저장됩니다. 진단·처치·AI 판단 기준으로 사용하지 않습니다.','Defaults preserve the existing demo severe-state display thresholds and the SBP 90 display threshold. Out-of-range numbers appear red with ↑/↓. A blank endpoint means no bound. Settings are saved only in this browser and are not used for diagnosis, treatment or AI decisions.')}</p><form data-vital-settings-form><div class="vital-indicator-grid">${Object.entries(definitions).filter(([key])=>['hr','map','spo2','rr','sbp'].includes(key)).map(([key,[label,ko,unit]])=>`<fieldset><legend>${esc(label)}${lang==='ko'?' · '+esc(ko):''} (${esc(unit)})</legend><div class="vital-indicator-fields">${['min','max'].map(bound=>`<label>${t(lang,bound==='min'?'하한':'상한',bound==='min'?'Lower bound':'Upper bound')}<input type="number" min="0" step="any" data-vital-key="${key}" data-vital-bound="${bound}" value="${ranges[key][bound]??''}" aria-label="${esc(label+' '+t(lang,bound==='min'?'표시 하한':'표시 상한',bound==='min'?'display lower bound':'display upper bound'))}" placeholder="${t(lang,'제한 없음','No limit')}"></label>`).join('')}</div></fieldset>`).join('')}</div><div class="vital-indicator-actions"><button type="submit">${t(lang,'표시 범위 적용','Apply display ranges')}</button><button type="button" data-vital-reset>${t(lang,'시연 기본값','Demo defaults')}</button><span class="vital-indicator-status" data-vital-status role="status" aria-live="polite"></span></div></form></details>`;
 }
 function bindSettings(host,onChange){
  const section=host?.matches?.('.vital-indicator-settings')?host:host?.querySelector?.('.vital-indicator-settings');if(!section)return;
  const form=section.querySelector('[data-vital-settings-form]'),status=section.querySelector('[data-vital-status]');if(!form)return;
  const lang=section.querySelector('summary').textContent.includes('Display ranges')?'en':'ko';
  form.addEventListener('submit',event=>{event.preventDefault();const input={};for(const field of form.querySelectorAll('[data-vital-key]')){input[field.dataset.vitalKey]??={};input[field.dataset.vitalKey][field.dataset.vitalBound]=field.value;}try{configure(input);status.setAttribute('role','status');status.textContent=t(lang,'표시 범위를 적용했습니다.','Display ranges applied.');onChange?.(copy(ranges));}catch(error){status.setAttribute('role','alert');status.textContent=t(lang,'0 이상인 숫자를 입력하고 하한이 상한 이하인지 확인하세요.','Enter numbers of zero or above and ensure each lower bound is at most its upper bound.');}});
  section.querySelector('[data-vital-reset]').addEventListener('click',()=>{reset();for(const field of form.querySelectorAll('[data-vital-key]'))field.value=ranges[field.dataset.vitalKey][field.dataset.vitalBound]??'';status.setAttribute('role','status');status.textContent=t(lang,'시연 기본값으로 되돌렸습니다.','Demo defaults restored.');onChange?.(copy(ranges));});
 }
 const sourceHosts=new Set(['nature.com','www.nature.com','jamanetwork.com','www.jamanetwork.com','pubmed.ncbi.nlm.nih.gov','pmc.ncbi.nlm.nih.gov','doi.org','dx.doi.org','qsofa.org','www.qsofa.org']);
 function safeLink(url,label){try{const parsed=new URL(url);if(parsed.protocol!=='https:'||!sourceHosts.has(parsed.hostname)||parsed.username||parsed.password)return '';return `<a href="${esc(parsed.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;}catch(error){return '';}}
 function referencePanel(assessment,lang='ko'){
  if(!assessment||typeof assessment!=='object')return '';
  const calculators=Array.isArray(assessment.calculators)?assessment.calculators:assessment.calculator&&typeof assessment.calculator==='object'?[assessment.calculator]:assessment.qsofa&&typeof assessment.qsofa==='object'?[assessment.qsofa]:Array.isArray(assessment.components)?[assessment]:[];
  if(!calculators.length)return '';
  return `<section class="vital-reference"><h3>${t(lang,'공식 · 입력값 확인','Formula · Input verification')}</h3><p>${t(lang,'선택 시점에서 확인된 입력으로 계산 과정을 보여주는 참고 패널입니다. qSOFA는 ICU 환자의 전실 가능 여부나 처치 지시를 결정하는 기준이 아닙니다. 점수만으로 진단하거나 대응을 결정하지 않습니다.','This reference panel shows calculation steps using inputs confirmed at the selected time. qSOFA does not determine ICU transfer readiness or treatment orders. The score alone is not a diagnosis or an action recommendation.')}</p>${calculators.map(calc=>{
   const components=Array.isArray(calc.components)?calc.components:[],missing=Array.isArray(calc.missing)?calc.missing:calc.missing?[String(calc.missing)]:[];
   const unavailable=c=>c.value===null||c.value===undefined||c.missing===true||c.conflict===true||c.same_time_conflict===true||(typeof c.value==='number'&&!finite(c.value));
   const incomplete=missing.length>0||components.length===0||components.some(unavailable)||!finite(calc.score);
   const name=calc.name||calc.label||calc.id||'qSOFA';
   const links=[safeLink(calc.source_url,t(lang,'공식 출처','Formula source')),safeLink(calc.method_url||assessment.method_url,t(lang,'계산 방법 참고','Method reference'))].filter(Boolean).join('');
   return `<article><h4>${esc(name)}</h4>${calc.formula?`<div class="vital-reference-formula">${esc(calc.formula)}</div>`:''}<div class="vital-reference-scroll"><table><thead><tr><th>${t(lang,'입력','Input')}</th><th>${t(lang,'값','Value')}</th><th>${t(lang,'계산 규칙','Calculation rule')}</th><th>${t(lang,'점수','Points')}</th></tr></thead><tbody>${components.map(c=>`<tr><td>${esc(c.name||c.key||'—')}</td><td>${esc(unavailable(c)?'—':c.value)} ${esc(c.unit||'')}</td><td>${esc(c.rule||'—')}</td><td>${!unavailable(c)&&finite(c.points)?number(c.points):'—'}</td></tr>`).join('')}</tbody></table></div><strong class="vital-reference-result${incomplete?' incomplete':''}">${incomplete?t(lang,'입력 부족 · 총점 미산출','Incomplete inputs · Total not calculated'):`${t(lang,'총점','Total')}: ${number(calc.score)}`}</strong>${missing.length?`<p>${t(lang,'누락 입력','Missing inputs')}: ${missing.map(v=>esc(typeof v==='object'?(v.name||v.key||'—'):v)).join(' · ')}</p>`:''}${links?`<div class="vital-reference-links">${links}</div>`:''}</article>`;
  }).join('')}</section>`;
 }
 return {classify,valueMarkup,settings,bindSettings,referencePanel,styles,configure,reset,getRanges:()=>copy(ranges),storageKey:STORAGE_KEY};
})();
if(typeof window!=='undefined')window.VitalIndicators=VitalIndicators;
if(typeof module!=='undefined'&&module.exports)module.exports=VitalIndicators;
