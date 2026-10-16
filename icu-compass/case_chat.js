(() => {
'use strict';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const styles = document.createElement('style');
styles.textContent = '.case-dialog{width:min(1240px,96vw);max-height:92vh;padding:0;border:1px solid #d5e2e8;border-radius:18px;color:#163247;background:#f5f8fa;box-shadow:0 25px 80px #16324744}.case-dialog::backdrop{background:#16324788}.case-head{padding:22px 26px;background:white;display:flex;align-items:start;justify-content:space-between;gap:15px;border-bottom:1px solid #dce6eb}.case-head h2{margin:7px 0}.case-body{display:grid;grid-template-columns:290px 1fr;gap:22px;padding:22px}.case-source{background:white;padding:18px;border-radius:12px;border:1px solid #dce6eb;height:fit-content}.case-source dl{margin:12px 0}.case-source dt{font-size:12px;color:#657b88}.case-source dd{margin:3px 0 12px;font-size:19px;font-weight:700}.case-thread{min-width:0}.case-hint{border:1px solid #dce6eb;background:white;padding:14px 16px;border-radius:10px;line-height:1.6;font-size:13px}.case-round{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#657b88;margin:20px 0 10px}.case-turn{border:1px solid #dce6eb;border-left:4px solid var(--role);background:white;padding:15px 18px;border-radius:10px;margin:10px 0}.case-turn .who{font-size:12px;color:var(--role);font-weight:800}.case-turn p{white-space:pre-wrap;line-height:1.65}.case-cite{font-size:11px;padding:4px 7px;background:#edf4f6;border-radius:5px;display:inline-block;margin:3px 5px 0 0}.case-composer{margin-top:18px;background:white;padding:16px;border-radius:12px;border:1px solid #dce6eb}.case-composer textarea{display:block;width:100%;resize:vertical;border:1px solid #ccdce4;border-radius:8px;padding:12px;margin:8px 0;font:14px system-ui;min-height:75px;color:#163247}.case-composer button:disabled{opacity:.5;cursor:wait}.case-question{font-size:13px;background:#eaf3f7;padding:12px;border-radius:8px;white-space:pre-wrap}.case-state{font-size:13px;line-height:1.5;margin:8px 0;min-height:20px}.case-new{font-size:12px;margin-top:12px}.case-badge{font-size:11px;color:#6b5318;background:#fff4d8;padding:5px 8px;border-radius:6px;display:inline-block}.case-meta{font-size:12px;color:#657b88}.case-error{color:#a72c2c}.case-loading{border-left:3px solid #087d80;padding-left:12px}@media(max-width:850px){.case-body{grid-template-columns:1fr;padding:14px}.case-source dl{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.case-head{padding:17px}.case-source dd{font-size:16px}.case-dialog{max-height:96vh}}';
document.head.append(styles);
const dialog = document.createElement('dialog');
dialog.className='case-dialog';dialog.setAttribute('aria-labelledby','case-title');
dialog.innerHTML='<div class="case-head"><div><div class="eyebrow">MULTI-ROLE CASE DISCUSSION</div><h2 id="case-title">Patient discussion</h2><span class="case-badge">Simulated roles · research demo</span><p class="case-meta">Qwen · KHDP internal API · one model, three clinical roles</p></div><button id="case-close" aria-label="Close discussion">Close ✕</button></div><div class="case-body"><aside class="case-source" id="case-source"></aside><section class="case-thread"><div class="case-hint"><b>Recorded evidence, simulated discussion.</b> Nurse, physician and agent messages are generated role-play, not actual clinical communications or completed care. The patient role states what is missing; no patient speech is invented. CXR is unavailable for this stay.</div><div id="case-turns" aria-live="polite"></div><form class="case-composer" id="case-form"><label for="case-speaker"><b>Speak as</b></label> <select id="case-speaker"><option value="moderator">Team facilitator</option><option value="nurse">Nurse (simulated)</option><option value="physician">Physician (simulated)</option><option value="patient">Patient (simulated)</option><option value="llm_agent">LLM agent (simulated)</option></select><p class="case-meta">Your role sets the discussion perspective. Typed statements do not become K-MIMIC observations.</p><label for="case-message"><b>Your message</b></label><textarea id="case-message" maxlength="1200" placeholder="What should the team verify first, based on these observations?"></textarea><div class="controls"><button class="primary" type="submit" id="case-send">Start discussion</button><button type="button" id="case-continue">Continue round</button><button type="button" id="case-new">New snapshot</button></div><p class="case-state" id="case-status" role="status"></p><small>Only this selected extract and discussion go to the KHDP internal model. Six rounds per snapshot. Keep questions about the displayed record.</small></form></section></div>';
document.body.append(dialog);
const el = id => dialog.querySelector('#'+id);
let current=null, version=0;
const cases=new Map();
const labels={patient:'Patient · record limitation',nurse:'Nurse · simulated',physician:'Physician · simulated',llm_agent:'LLM agent · simulated'};
const speakers={moderator:'Team facilitator',nurse:'You · simulated nurse',physician:'You · simulated physician',patient:'You · simulated patient',llm_agent:'You · simulated LLM agent'};
const colors={patient:'#99721b',nurse:'#2565a0',physician:'#7956a7',llm_agent:'#087d80'};
const units={hr:['HR','bpm'],map:['MAP','mmHg'],spo2:['SpO₂','%'],rr:['RR','/min'],sbp:['SBP','mmHg']};
function sourcePanel(s) {
  const m=s.measurements;
  el('case-source').innerHTML='<div class="eyebrow">'+(current.result?'FROZEN SOURCE SNAPSHOT':'SELECTED RECORD PREVIEW')+'</div><h3 style="margin-top:10px">'+esc(s.replay_id)+'</h3><p class="case-meta">'+esc(s.bed)+' · admission +'+esc(s.source_offset_min)+' min<br>Replay clock '+esc(s.replay_clock)+'</p><dl>'+Object.entries(units).map(([k,[name,unit]])=>'<div><dt>'+name+' · '+unit+'</dt><dd>'+(m[k]?.value==null?'Missing':esc(m[k].value))+'</dd><small>'+(m[k]?.age_min==null?'No fresh observation':'Measured '+esc(m[k].age_min)+' min before grid')+'</small></div>').join('')+'</dl><p class="case-meta"><b>Not in the extract</b><br>Symptoms · GCS · diagnosis · treatment · patient-linked CXR</p><p class="case-meta">K-MIMIC · '+esc(s.source?.dataset || 'dataset 001')+'<br>Values are frozen on the server when the discussion starts. Replay may continue separately.</p>';
}
function evidence(key,s){if(units[key]){const m=s.measurements[key];return units[key][0]+': '+(m.value==null?'missing':m.value+' '+m.unit)+(m.value==null?'':' · measured +'+m.observed_offset_min+' min; grid +'+s.grid_offset_min+' min');}if(key==='qsofa')return 'qSOFA incomplete · no total assigned';if(key==='thresholds')return s.thresholds.length?s.thresholds.map(t=>t.key+' '+t.value+' '+t.op+' '+t.threshold+' '+t.unit).join('; '):'No configured threshold crossed';return 'Missing inputs · not assumed normal';}
function render(){
  if(!current)return;
  el('case-title').textContent=current.bed+' / '+current.pid+' · Case discussion';
  const r=current.result;sourcePanel(r?r.snapshot:current.preview);
  el('case-turns').innerHTML=r?r.rounds.map((round,i)=>'<div class="case-round">Round '+(i+1)+' · '+esc(r.model)+'</div><div class="case-question"><b>'+esc(speakers[round.speaker]||'Team facilitator')+'</b><br>'+esc(round.question)+'</div>'+round.turns.map(t=>'<article class="case-turn" style="--role:'+colors[t.role]+'"><div class="who">'+labels[t.role]+'</div><p>'+esc(t.text)+'</p>'+t.evidence_keys.map(k=>'<span class="case-cite">'+esc(evidence(k,r.snapshot))+'</span>').join('')+'</article>').join('')).join(''):'<p class="muted" style="padding:18px 0">Start a discussion to hear the patient record limitation, the nurse’s report, the physician’s review and the agent’s evidence check.</p>';
  el('case-send').textContent=current.busy?'Team is responding…':r?'Send to team':'Start discussion';
  el('case-send').disabled=current.busy;el('case-continue').disabled=current.busy||!r;el('case-message').disabled=current.busy;el('case-speaker').disabled=current.busy;el('case-new').disabled=current.busy;
  el('case-status').textContent=current.status||'';el('case-status').className='case-state'+(current.error?' case-error':current.busy?' case-loading':'');
}
function findBed(id){return state?.floors.flatMap(f=>f.units.flatMap(u=>u.beds)).find(b=>b.id===id&&b.patient);}
function fresh(b){const p=b.patient,c=p.clinical;return {bed:b.id,pid:p.pid,busy:false,result:null,status:'',error:false,preview:{bed:b.id,replay_id:p.pid,source_offset_min:c.source_offset_min,replay_clock:state.clock,source:c.provenance,measurements:Object.fromEntries(Object.keys(units).map(k=>[k,{value:p.vitals[k]??null,age_min:c.measurement_age_min[k]??null}]))}};}
function openCase(id){const b=findBed(id);if(!b)return;version++;const key=b.id+'|'+b.patient.pid+'|'+b.patient.admit_t;current=cases.get(key)||fresh(b);cases.set(key,current);if(cases.size>32)cases.delete(cases.keys().next().value);el('case-message').value='';render();if(!dialog.open)dialog.showModal();}
async function submit(question){
 if(!current||current.busy)return;
 const target=current,v=version;target.busy=true;target.error=false;target.status='Requesting a grounded discussion from Qwen. This may take up to 100 seconds.';render();
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),110000);
 try{
  const body={bed:target.bed,patient_id:target.pid,speaker:el('case-speaker').value,message:question};if(target.result)body.session_id=target.result.session_id;
  const response=await fetch(api('/api/case-conversation'),{method:'POST',headers:{'Content-Type':'application/json','X-ICU-Case':'1'},body:JSON.stringify(body),signal:controller.signal});let data;
  try{data=await response.json();}catch(e){throw Error('The KHDP proxy could not return the request. Please try again.');}
  if(!response.ok)throw Error(data.error||'Discussion request failed.');
  while(data.pending){
    await new Promise(resolve=>setTimeout(resolve,1500));
    const check=await fetch(api('/api/case-result')+'?id='+encodeURIComponent(data.job_id),{headers:{'X-ICU-Case':'1'},signal:controller.signal});
    try{data=await check.json();}catch(e){throw Error('Could not retrieve the model response from the KHDP proxy.');}
    if(!check.ok)throw Error(data.error||'Model request failed.');
  }
  target.result=data;target.status='Round '+data.rounds.length+' completed · actual KHDP model response · simulated discussion';
  if(current===target&&version===v)el('case-message').value='';
 }catch(e){target.error=true;target.status=e.name==='AbortError'?'The request timed out. No replacement dialogue was generated.':e.message;}
 finally{clearTimeout(timer);target.busy=false;if(current===target&&version===v){render();el('case-status').scrollIntoView({block:'nearest',behavior:'smooth'});}}
}
el('case-form').onsubmit=e=>{e.preventDefault();const q=el('case-message').value.trim();submit(q||'Review the recorded observations together. What needs verification first?');};
el('case-continue').onclick=()=>submit('Continue the team discussion. Identify the next unanswered question using the same frozen observations; do not invent new findings or completed actions.');
el('case-new').onclick=()=>{if(!current||current.busy)return;const b=findBed(current.bed);if(!b||b.patient.pid!==current.pid){current.status='This patient is no longer in the bed. Close and select a current patient.';current.error=true;render();return;}version++;current=fresh(b);cases.set(b.id+'|'+b.patient.pid+'|'+b.patient.admit_t,current);el('case-message').value='';render();};
el('case-close').onclick=()=>dialog.close();
document.querySelector('#patients').addEventListener('click',e=>{const row=e.target.closest('[data-bed]');if(row)openCase(row.dataset.bed);});
document.querySelector('#patients').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const row=e.target.closest('[data-bed]');if(row){e.preventDefault();openCase(row.dataset.bed);}}});
})();