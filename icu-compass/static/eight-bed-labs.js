/* Selected-time laboratory summaries for the eight-bed replay table. */
const EightBedLabs=(()=>{
 'use strict';
 const cache=new Map(),mounts=new WeakMap();let selectedQuery='';
 const choices=[['','최근 실제 검사','Latest actual result'],['Hb','혈색소 · Hb','Hemoglobin · Hb'],['Creatinine','크레아티닌','Creatinine'],['Lactate','젖산','Lactate'],['Potassium','칼륨','Potassium'],['Glucose','포도당','Glucose']];
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 const quantitativeQueries=new Set(['hb','creatinine','lactate','potassium','glucose']);
 const numericValue=v=>finite(v)||(typeof v==='string'&&v.trim()!==''&&Number.isFinite(Number(v)));
 function matchesQuery(r,query){
  const q=query.toLowerCase(),name=String(r.name||'');if(!q)return true;
  if(q==='hb'){if(!/(?:^|[^a-z])hb(?:\s*\(|\s*$)/i.test(name))return false;}
  else if(!name.toLowerCase().includes(q)&&!String(r.itemid||'').toLowerCase().includes(q))return false;
  if(quantitativeQueries.has(q)&&(!numericValue(r.value)||typeof r.unit!=='string'||!r.unit.trim()||/urine|소변|요검사/i.test(name)))return false;
  return true;
 }
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const t=(lang,ko,en)=>lang==='en'?en:ko;
 const when=(m,lang)=>finite(m)?`ICU ${m<0?'−':'+'}${Math.abs(m).toLocaleString(undefined,{maximumFractionDigits:1})} ${t(lang,'분','min')}`:'—';
 function contextFor(slot){
  const c=slot?.case,minute=slot?.minute;if(!c||!finite(minute)||!Array.isArray(c.rows))return null;
  const id=c.source_case_id||c.id,index=c.rows.findLastIndex(r=>finite(r.minute)&&r.minute<=minute);
  if(typeof id!=='string'||index<0)return null;
  return {id,index,minute,rowMinute:c.rows[index].minute};
 }
 function latestEligible(data,context,query=''){
  if(!data||data.case_id!==context.id||data.row_index!==context.index||!finite(data.as_of_minute)||data.as_of_minute>context.minute||data.as_of_minute!==context.rowMinute)return null;
  return (data.labs||[]).filter(r=>finite(r.chart_minute)&&finite(r.available_minute)&&r.chart_minute<=r.available_minute&&r.available_minute<=data.as_of_minute&&matchesQuery(r,query)).sort((a,b)=>b.chart_minute-a.chart_minute)[0]||null;
 }
 async function load(context,query){
  const key=JSON.stringify([context.id,context.index,query]);if(cache.has(key))return cache.get(key);
  const args=new URLSearchParams({case_id:context.id,row_index:String(context.index),lab_query:query});
  const pending=fetch('api/case-detail?'+args,{cache:'no-store'}).then(async response=>{if(!response.ok)throw Error('Laboratory request failed');const data=await response.json();if(data.case_id!==context.id||data.row_index!==context.index)throw Error('Mismatched laboratory response');return data;}).catch(error=>{cache.delete(key);throw error;});
  cache.set(key,pending);while(cache.size>200)cache.delete(cache.keys().next().value);return pending;
 }
 function cellHTML(lab,context,lang){
  if(!lab)return `—<small>${t(lang,'이 시점까지 연결된 결과 없음','No linked result by this time')}</small>`;
  const age=context.minute-lab.chart_minute;
  return `<span class="eight-lab-name">${esc(lab.name||t(lang,'검사','Test'))}</span><strong>${esc(lab.value??'—')}</strong> <span>${esc(lab.unit||'')}</span>${typeof lab.unit!=='string'||!lab.unit.trim()?`<small>${t(lang,'원문 값 · 단위 미기재','Raw source value · Unit not recorded')}</small>`:''}<small>${esc(when(lab.chart_minute,lang))} · ${t(lang,`${Math.round(age)}분 전 관측`,`${Math.round(age)} min since collection`)}</small>${lab.same_time_conflict?`<small class="eight-lab-conflict">${t(lang,'동일 시각 결과 충돌 · 상세 확인','Same-time result conflict · Check details')}</small>`:''}`;
 }
 function mount(host,{slots=[],lang='ko',interpolate=false}={}){
  if(!host)return;const section=host.matches?.('.replay-observations')?host:host.querySelector('.replay-observations');if(!section)return;
  const table=section.querySelector('table'),head=table?.querySelector('thead tr');if(!table||!head)return;
  section.querySelector('[data-eight-lab-controls]')?.remove();section.querySelectorAll('[data-eight-lab-column]').forEach(el=>el.remove());
  const state={serial:0,section};mounts.set(host,state);
  const controls=document.createElement('div');controls.dataset.eightLabControls='';
  controls.innerHTML=`<style>.eight-lab-controls{color:#20334e;display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0 14px}.eight-lab-controls label{color:#20334e;font-size:13px;font-weight:700;display:flex;gap:8px;align-items:center}.eight-lab-controls select{min-height:36px;max-width:270px;padding:7px 10px;border:1px solid #aabed1;border-radius:7px;background:white;color:#20334e}.eight-lab-controls p{font-size:11px;color:#61718a;margin:0}.replay-observations th.eight-lab-heading{width:28%}.eight-lab-cell{font-size:11px;overflow-wrap:anywhere}.eight-lab-cell strong{font-size:16px}.eight-lab-name{display:block;font-size:11px;line-height:1.4;margin-bottom:4px}.eight-lab-cell small.eight-lab-conflict{color:#9d4e09}.replay-observations table:has(.eight-lab-heading){min-width:720px}</style><div class="eight-lab-controls"><label>${t(lang,'검사실 항목','Laboratory test')}<select data-eight-lab-query>${choices.map(([query,ko,en])=>`<option value="${esc(query)}" ${query===selectedQuery?'selected':''}>${esc(t(lang,ko,en))}</option>`).join('')}</select></label><p>${t(lang,'재생 시점에 맞춰 갱신 · 새 결과가 없으면 마지막 실제값과 검사 시각 유지','Refreshes at replay time · Last actual value and collection time remain until the next result')}</p></div>`;
  section.querySelector('.replay-table-scroll').before(controls);
  const th=document.createElement('th');th.scope='col';th.className='eight-lab-heading';th.dataset.eightLabColumn='';th.textContent=t(lang,'검사실 · 실제 결과','Laboratory · Actual result');head.append(th);
  const rows=Array.from(table.querySelectorAll('tbody tr')).slice(0,8),cells=rows.map(row=>{const td=document.createElement('td');td.className='eight-lab-cell';td.dataset.eightLabColumn='';row.append(td);return td;});
  async function refresh(){
   const serial=++state.serial,query=selectedQuery;
   await Promise.all(cells.map(async(cell,i)=>{
    const context=contextFor(slots[i]);cell.innerHTML=context?`<small>${t(lang,'검사 불러오는 중…','Loading laboratory result…')}</small>`:'—';
    if(!context)return;const current=()=>mounts.get(host)===state&&state.serial===serial&&host.isConnected&&cell.isConnected&&section.contains(cell)&&section.querySelector('table')===table;
    try{const data=await load(context,query);if(!current())return;cell.innerHTML=cellHTML(latestEligible(data,context,query),context,lang);}
    catch(error){if(current())cell.innerHTML=`<small>${t(lang,'검사를 불러오지 못함 · 항목을 다시 선택하세요','Unable to load results · Select the test again')}</small>`;}
   }));
  }
  controls.querySelector('[data-eight-lab-query]').addEventListener('change',event=>{selectedQuery=event.target.value;refresh();});
  refresh();return {refresh};
 }
 return {mount,contextFor,latestEligible,cellHTML};
})();
if(typeof window!=='undefined')window.EightBedLabs=EightBedLabs;
if(typeof module!=='undefined'&&module.exports)module.exports=EightBedLabs;
