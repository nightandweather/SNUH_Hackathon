/* Hospital/unit/bed IDs are the join keys; each hospital uses the same patient schema. */
const Network = (()=>{
 let raw=null,hospital='A',ward='',scopeSignature='',cardsSignature='',networkSignature='',optionSignature='',requestSeed=null, profileSignature='';
 const requests=new Map();
 const unitsOf=data=>data.floors.flatMap(f=>f.units);
 function scopeState(data,hospitalId,unitId=''){
   const floors=data.floors.map(f=>({...f,units:f.units.filter(u=>(u.hospital_id||'A')===hospitalId&&(!unitId||u.id===unitId))})).filter(f=>f.units.length);
   const units=new Set(floors.flatMap(f=>f.units.map(u=>u.id))),beds=new Set(floors.flatMap(f=>f.units.flatMap(u=>u.beds.map(b=>b.id))));
   const nurses=data.nurses.filter(n=>units.has(n.unit)),roster=(data.roster||[]).filter(n=>units.has(n.unit));
   const byBed=rows=>(rows||[]).filter(r=>beds.has(r.bed));
   return {...data,floors,nurses,roster,doctors:(data.doctors||[]).filter(d=>units.has(d.unit)),
     incidents:byBed(data.incidents),care_actions:byBed(data.care_actions),activities:byBed(data.activities),diagnostics:byBed(data.diagnostics),
     shift:{...data.shift,on_duty:nurses.length,total_staff:roster.length},
     shift_schedule:(data.shift_schedule||[]).map(s=>({...s,staff_count:roster.filter(n=>n.shift_code===s.code).length})),
     last_handover:data.last_handover?{...data.last_handover,patients:byBed(data.last_handover.patients)}:null,
     handover_history:[],completed_shifts:[],
     log:byBed(data.activities).map(a=>`${a.clock} · ${a.bed} · ${a.text}`)};
 }
 function select(data){
   raw=data;
   if(requestSeed!==data.seed){requests.clear();requestSeed=data.seed;}
   const units=unitsOf(data);
   if(!units.some(u=>(u.hospital_id||'A')===hospital))hospital=units[0]?.hospital_id||'A';
   if(ward&&!units.some(u=>u.id===ward&&(u.hospital_id||'A')===hospital))ward='';
   return scopeState(data,hospital,ward);
 }
 function navigate(h,u='',keepNurse=false){
   if(C.busy)return;
   if(typeof Transfers!=='undefined')raw=Transfers.clearForScope(raw);
   hospital=h;ward=u;if(!keepNurse)me='';picked=null;rosterUnit=u;
   $('#modal').classList.remove('open');$('#detail').textContent='Select a bed to view patient details.';$('#patientPanel').style.display='none';
   const url=new URL(location);url.searchParams.set('hospital',hospital);ward?url.searchParams.set('ward',ward):url.searchParams.delete('ward');me?url.searchParams.set('nurse',me):url.searchParams.delete('nurse');history.replaceState(null,'',url);
   S=select(raw);render();draw();
 }
 function findings(p){
   const v=p.vitals||{},o=p.extra_observations||{},active=(value,predicate)=>value==null?null:predicate(Number(value));
   return [
     ['🩸','Bleeding suspected',p.simulation_override?.scenario==='bleeding'?true:p.source==='synthetic'?false:null],
     ['↓','Low blood pressure',v.sbp==null&&v.map==null?null:(v.sbp!=null&&v.sbp<90)||(v.map!=null&&v.map<65)],
     ['♥','Fast heart rate',active(v.hr,x=>x>100)],['🫁','Low oxygen',active(v.spo2,x=>x<92)],
     ['≋','Fast breathing',active(v.rr,x=>x>=22)],['🧠','Altered consciousness',active(o.gcs,x=>x<15)],
     ['⚡','Pain',active(o.pain,x=>x>=4)],['🌡','Fever',active(o.temperature,x=>x>=38)]
   ];
 }
 // Shared ECMO / CRRT display; underlying evidence remains separate.
 const careSymbols={
   cpr:'<circle cx="52" cy="29" r="6"/><path d="M6 31h9l6 5 5-8h18M20 5v8l7 7 5-3-6-8V4m11 0v9l-7 7M23 23h11m-6-5v8m-4-3 4 4 4-4"/><path d="M49 10c-5-5-9 2 0 7 9-5 5-12 0-7Z" fill="currentColor" stroke="none"/>',
   circuit:'<circle cx="8" cy="23" r="5"/><path d="M13 25h22l7 7H8m-4 0v5h38v-5M13 22c6-10 9 14 16 1s9 13 17-1M14 27c6 8 12-12 18 0s8-4 13 1"/><rect x="46" y="5" width="15" height="29" rx="2"/><path d="M49 15h3l2-5 3 7 2-3M50 21h7m-7 4h7m-4 9v3m-6 0h12"/>',
   crrt:'<circle cx="7" cy="23" r="5"/><path d="M12 25h21l6 7H7m-3 0v5h35M14 22h15V8h10m-23 19h14v-8h9"/><rect x="40" y="3" width="19" height="32" rx="3"/><path d="M44 9h11m-11 5h11m-9 5h7l-1 10h-5zM44 35v3m11-3v3"/>',
   pressor:'<rect x="2" y="13" width="12" height="15" rx="2"/><path d="M4 20h3l2-4 2 8 2-3M18 4v28m-3-25h23m5-3v28m-3-25h20"/><rect x="20" y="8" width="9" height="13" rx="2"/><rect x="32" y="8" width="9" height="13" rx="2"/><rect x="46" y="8" width="10" height="13" rx="2"/><path d="M23 13h3m9 0h3m11 0h4M24 21v10h27V21M36 21v9M29 33h19v5H29zM32 35h5m3 0h5"/>',
   vent:'<path d="M24 6C7 0 1 16 8 27c4 7 14 8 20 1l4-8-5-3 3-3-5-3M20 17h1m4 5h8"/><path d="M33 22c3-9 6 9 9 0s5 8 8-1"/><rect x="49" y="6" width="13" height="28" rx="2"/><path d="M52 15h2l2-5 2 7 2-3m-8 9h7m-7 4h7m-4 7v3m-5 0h10"/>',
   surgery:'<path d="M7 31h48M8 26h42l8-9M11 31v6m37-6v6M17 5h13a7 7 0 0 1 7 7H10a7 7 0 0 1 7-7Zm7 7v5m-8-5-2 5m16-5 2 5M24 5V2h20"/><circle cx="10" cy="22" r="4"/><circle cx="50" cy="12" r="5"/><path d="m47 17-8 8m14-8-5 8M17 23h18l5 3"/>'
 };
 const careDefinitions=[['cpr_today','cpr','CPR today','#b44436'],['ecmo_crrt','circuit','ECMO / CRRT','#245a91'],['pressor_unstable','pressor','Pressor escalation / unstable','#ae721e'],['ventilator','vent','Ventilator','#287b70'],['surgery_today','surgery','Surgery today','#655494']];
 function careIndicators(p){
   const f=p.care_indicators||{},d=p.devices||{},bool=v=>typeof v==='boolean'?v:null;
   const sameDay=Number.isInteger(p.calendar_day)&&p.calendar_day===f.calendar_day;
   const a=bool(d.ecmo),b=bool(d.crrt);
   return {cpr_today:sameDay?bool(f.cpr_today):null,
     ecmo:a,crrt:b,
     pressor_unstable:bool(f.pressor_unstable),ventilator:bool(d.ventilator),
     surgery_today:sameDay?bool(f.surgery_today):null};
 }
 function careDisplayIndicators(p){
   const s=careIndicators(p);
   return {cpr_today:s.cpr_today,ecmo_crrt:s.ecmo===true||s.crrt===true?true:s.ecmo===false&&s.crrt===false?false:null,pressor_unstable:s.pressor_unstable,ventilator:s.ventilator,surgery_today:s.surgery_today};
 }
 function careStrip(p,legend=false){
   const states=legend?Object.fromEntries(careDefinitions.map(([key])=>[key,true])):careDisplayIndicators(p);
   return `<span class="care-strip${legend?' care-key':''}">${careDefinitions.map(([key,icon,label,color])=>{
     const value=states[key],status=value===true?'Active':value===false?'Not active':'Unknown';
     return `<span class="care-badge ${value===true?'is-active':value===false?'is-inactive':'is-unknown'}" style="--care-color:${color}" title="${label} · ${status}" aria-label="${label} · ${status}"><span class="care-icon"><svg viewBox="0 0 64 40" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${careSymbols[icon]}</svg>${value===null?'<span class="unknown-mark">?</span>':''}</span><span class="care-label">${label}</span><span class="care-state">${legend?'':status}</span></span>`;
   }).join('')}</span>`;
 }
 function careMapIcons(p){
   const states=careDisplayIndicators(p);
   return careDefinitions.map(([key,icon,label,color],i)=>{
     const value=states[key],status=value===true?'Active':value===false?'Not active':'Unknown';
     return `<g transform="translate(${i*.9} 0)" role="img" aria-label="${label} · ${status}"><title>${label} · ${status}</title><rect x="0" y=".04" width=".84" height=".72" rx=".1" fill="${value===true?color:'#f4f6f8'}" stroke="${value===true?color:'#9ca8b4'}" stroke-width=".035" ${value===null?'stroke-dasharray=".08 .06"':''}/><svg x=".04" y=".12" width=".76" height=".48" viewBox="0 0 64 40" fill="none" color="${value===true?'#fff':'#667587'}" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${careSymbols[icon]}</svg>${value===null?'<text x=".67" y=".85" font-size=".32" fill="#52647c">?</text>':''}</g>`;
   }).join('');
 }

 function bedDrawing(occupied){return `<svg class="patient-bed-drawing" viewBox="0 0 240 37" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 5v26h226V5M6 25h226M2 32h234M14 33v3m210-3v3"/><rect x="11" y="11" width="216" height="14" rx="2"/>${occupied?'<circle cx="27" cy="17" r="7"/><path d="M34 17h68l12-4 9 9 12-5h73"/>':''}</svg>`;}
 function chips(p){
   const activeNames=findings(p).filter(row=>row[2]===true).map(row=>row[1]);
   const devices=Object.entries({oxygen:'Oxygen',iv:'IV cannula',central_line:'Central line',arterial_line:'Arterial line',urinary_catheter:'Urinary catheter',drain:'Drain'}).filter(([key])=>p.devices?.[key]===true).map(([,label])=>`<span class="device-chip active">${label}</span>`).join('');
   return `${careStrip(p)}${bedDrawing(true)}<div class="finding-summary ${activeNames.length?'has-findings':''}">${activeNames.length?activeNames.join(' · '):'No active demo finding'}</div><div class="device-chips">${devices}</div>`;
 }
 function render(){
   const signature=`${hospital}:${ward}:${raw.seed}`;
   if(scopeSignature!==signature){
     scopeSignature=signature;built=false;staffOptionsSignature='';H.signature='';cardsSignature='';
     for(const map of [floorSvg,linkG,nurseEl,doctorEl,bedEl,bedPos])for(const key in map)delete map[key];
   }
   if(!$('#careIconLegend').children.length)$('#careIconLegend').innerHTML=careStrip(null,true);
   const all=unitsOf(raw),local=all.filter(u=>(u.hospital_id||'A')===hospital),hospitals=[...new Set(all.map(u=>u.hospital_id||'A'))];
   const options=JSON.stringify([hospital,all.map(u=>[u.id,u.name])]);
   if(optionSignature!==options){optionSignature=options;
     $('#hospitalScope').innerHTML=hospitals.map(id=>`<option value="${esc(id)}">Demo Hospital ${esc(id)}</option>`).join('');
     $('#wardScope').innerHTML='<option value="">All wards in this hospital</option>'+local.map(u=>`<option value="${esc(u.id)}">${esc(u.id)} · ${esc(u.name)}</option>`).join('');
   }
   const profile=raw.hospital_profiles?.[hospital]||raw.demo_profile;
   const profileKey=`${hospital}:${profile}:${raw.seed}`;
   if(profileSignature!==profileKey){profileSignature=profileKey;$('#profile').value=profile;}
   $('#controlTarget').textContent=` · Demo Hospital ${hospital}`;
   $('#hospitalScope').value=hospital;$('#wardScope').value=ward;
   const beds=S.floors.flatMap(f=>f.units.flatMap(u=>u.beds));
   $('#scopeSummary').textContent=`Demo Hospital ${hospital} · ${ward||'All wards in this hospital'} · ${beds.length} Beds`;
   $('#networkClock').textContent=`Snapshot · ${raw.clock} · Simulation`;
   const stats=hospitals.map(id=>{const us=all.filter(u=>(u.hospital_id||'A')===id),ids=new Set(us.map(u=>u.id)),bs=us.flatMap(u=>u.beds),bids=new Set(bs.map(b=>b.id));return {id,total:bs.length,empty:bs.filter(b=>!b.patient&&!b.reservation&&!b.unavailable).length,reserved:bs.filter(b=>!b.patient&&b.reservation&&!b.unavailable).length,blocked:bs.filter(b=>b.unavailable).length,occupied:bs.filter(b=>b.patient).length,events:raw.incidents.filter(i=>bids.has(i.bed)).length,nurses:raw.nurses.filter(n=>ids.has(n.unit)).length};});
   const ns=JSON.stringify([I18n.language,hospital,stats,[...requests]]);
   if(ns!==networkSignature){networkSignature=ns;$('#networkCards').innerHTML=stats.map(s=>`<article class="hospital-card ${hospital===s.id?'selected':''}"><h3>Demo Hospital ${esc(s.id)}</h3><div class="hospital-numbers"><div><strong>${s.empty}</strong><small>Available beds</small></div><div><strong>${s.occupied}/${s.total}</strong><small>Occupied</small></div><div><strong>${s.reserved}</strong><small>Reserved beds</small></div></div><div class="tag">${s.blocked?`${I18n.language==='ko'?'보류·정리 중':'Held / turnover'} ${s.blocked} · `:''}On-duty nurses ${s.nurses} · Active events ${s.events}</div><div class="acceptance">${s.empty?'Acceptance unconfirmed':'No empty beds'}</div><div class="hospital-actions"><button data-hospital="${s.id}">View hospital</button><button data-acceptance="${s.id}" ${!s.empty||requests.has(s.id)?'disabled':''}>${requests.has(s.id)?'Hospital response pending (simulation)':'Request acceptance (simulation)'}</button></div></article>`).join('');}
   const ps=JSON.stringify([I18n.language,hospital,ward,beds.map(b=>[b.id,b.patient,b.reservation,b.flow,b.unavailable]),S.incidents.map(i=>i.bed)]);
   if(cardsSignature!==ps){cardsSignature=ps;
     $('#patientCards').innerHTML=S.floors.flatMap(f=>f.units).map(u=>`<section class="unit-patients"><h3>${esc(u.id)} · ${esc(u.name)} ${ward?'':`<button data-ward="${esc(u.id)}">View ward</button>`}</h3><div class="bed-grid">${u.beds.map(b=>{const p=b.patient,status=bedStatus(b);return `<button data-bed-status="${status.key}" class="patient-card ${p?'':'vacant '+status.key}" data-patient="${esc(b.id)}" style="--bed-color:${status.color};--flow-ink:${status.ink||'#fff'}" aria-label="${esc(b.id)} · ${status.label}"><div class="card-top"><b>${esc(b.id)}</b><span class="state-pill">${status.label}</span></div>${b.flow?Transfers.card(b):p?`<div class="patient-id">${esc(p.pid)} · Simulation</div><div class="vitals-line">HR <b>${p.vitals.hr??'?'}</b> · MAP <b>${p.vitals.map??'?'}</b> · SpO₂ <b>${p.vitals.spo2??'?'}%</b> · RR <b>${p.vitals.rr??'?'}</b></div>${chips(p)}${typeof Readiness!=='undefined'?Readiness.badges(p):''}`:`<div class="vacant-note">${bedDrawing(false)}${b.reservation?'Surgery scheduled · postoperative ICU admission':'Available beds'}<br><small>${b.reservation?'Fictional schedule; patient not yet admitted.':'Acceptance unconfirmed'}</small></div>`}</button>`;}).join('')}</div></section>`).join('');
   }
 }
 function init(){
   const query=new URLSearchParams(location.search);hospital=query.get('hospital')||'A';ward=query.get('ward')||((query.get('nurse')||'').replace(/-(?:\d+|charge)$/,''));
   $('#hospitalScope').onchange=e=>navigate(e.target.value);$('#wardScope').onchange=e=>navigate(hospital,e.target.value);
   $('#networkCards').onclick=e=>{const b=e.target.closest('[data-hospital]');if(b)navigate(b.dataset.hospital);const req=e.target.closest('[data-acceptance]');if(req){requests.set(req.dataset.acceptance,'pending');$('#networkRequest').textContent=`Demo Hospital ${req.dataset.acceptance} · Hospital response pending (simulation). Simulated requests only; no hospital has been contacted and no patient has been assigned.`;render();}};
   $('#patientCards').onclick=e=>{const w=e.target.closest('[data-ward]');if(w)navigate(hospital,w.dataset.ward);const b=e.target.closest('[data-patient]');if(b)selectPatient(b.dataset.patient);};
 }
 return {init,select,render,navigate,scopeState,findings,careIndicators,careDisplayIndicators,careMapIcons,get hospital(){return hospital;}};
})();
