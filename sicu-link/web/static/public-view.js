/* Public read-only snapshot adapter. No upstream service credentials or calls. */
(()=>{
 const originalFetch=window.fetch.bind(window);
 let current=null;
 const snapshot=originalFetch('snapshot.json').then(r=>{if(!r.ok)throw new Error('Snapshot unavailable');return r.json();}).then(s=>{current=s;return s;});
 window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  if(url.pathname.includes('/api/')){
   if(url.pathname.endsWith('/api/state'))return new Response(JSON.stringify(current||await snapshot),{headers:{'Content-Type':'application/json'}});
   return new Response(JSON.stringify({error:'Public preview is read-only. Live AI and simulation controls require the KHDP server version.'}),{status:403,headers:{'Content-Type':'application/json'}});
  }
  return originalFetch(input,options);
 };
 window.openPublicBed=(bed,language)=>{
  if(!bed)return;const ko=language==='ko',p=bed.patient,dialog=document.getElementById('publicPatient'),body=document.getElementById('publicPatientBody');body.replaceChildren();
  const add=(tag,text,cl)=>{const n=document.createElement(tag);n.textContent=text;if(cl)n.className=cl;body.append(n);return n;};
  add('h2',`${bed.id} · ${ko?'환자 상세':'Patient details'}`);
  add('p',ko?'가상 데이터 · 선택 시점의 시뮬레이션 · 실제 환자 기록이 아닙니다.':'Fictional data · simulation at selected time · not a real patient record.','public-source');
  if(!p){add('p',bed.reservation?(ko?'수술 후 입실 예정 · 아직 환자가 입실하지 않았습니다.':'Postoperative admission reserved · patient not yet admitted.'):(ko?'빈 병상 · 병원의 수용 확정을 의미하지 않습니다.':'Empty bed · acceptance has not been confirmed.'));}
  else{
   add('p',`${p.pid} · ${p.age} ${ko?'세':'years'} · ${p.sex}`);
   add('p',p.simulation_override?.scenario==='bleeding'?(ko?'모의 경과: 수술 후 출혈 의심 시나리오가 주입되어 있습니다.':'Simulated course: a suspected postoperative bleeding scenario is active.'):(ko?'모의 경과: 수술 후 ICU 모니터링 중인 가상 환자입니다.':'Simulated course: fictional postoperative ICU monitoring.'));
   const table=document.createElement('table');for(const [key,label,unit] of [['hr','HR','bpm'],['map','MAP','mmHg'],['spo2','SpO₂','%'],['rr','RR','/min']]){const row=table.insertRow();row.insertCell().textContent=label;row.insertCell().textContent=`${p.vitals?.[key]??'?'} ${unit}`;}body.append(table);
   const anatomy=document.createElement('div');anatomy.innerHTML=Anatomy.render(p,language)+Readiness.render(p);body.insertBefore(anatomy,table);
   add('h3',ko?'간호 상태 · 장비':'Care indicators · devices');
   const states=Network.careDisplayIndicators(p),labels=ko?['당일 CPR','ECMO / CRRT','승압제 증량·불안정','인공호흡기','당일 수술']:['CPR today','ECMO / CRRT','Pressor escalation / unstable','Ventilator','Surgery today'];
   Object.values(states).forEach((v,i)=>add('div',`${labels[i]}: ${v===true?(ko?'해당':'Active'):v===false?(ko?'없음':'Not active'):(ko?'미확인':'Unknown')}`));
   add('p',ko?'이 요약은 화면의 가상 상태값을 표시한 것입니다. AI 생성 답변이나 실제 진료 판단이 아닙니다.':'This summary displays fictional fixture values. It is not an AI-generated response or a clinical assessment.','public-source');
  }
  dialog.showModal();document.getElementById('publicClose').focus();
 };

 let frames=[],frame=0,timer=null,loading=false;
 const labels={ko:['샌드박스 · 가상 ICU 시뮬레이션','평온한 근무','출혈 의심','응급상황 집중','적용','재생','일시정지','처음으로','재생 시점','세 병원에 선택한 시나리오를 적용합니다. 5분 간격으로 계산한 30분 시뮬레이션이며, 공개 화면에서는 실제 환자·모델 API를 사용하지 않습니다.'],en:['Sandbox · fictional ICU simulation','Calm shift','Suspected bleeding','Emergency surge','Apply','Play','Pause','Reset','Replay time','Applies the selected scenario to all three hospitals. Thirty simulated minutes in 5-minute steps. This public view uses no real patient records or model API.']};
 function language(){return document.documentElement.lang.startsWith('ko')?'ko':'en'}
 function updateSandbox(){const w=labels[language()];document.querySelectorAll('[data-sb-label]').forEach(el=>el.textContent=w[Number(el.dataset.sbLabel)]);const play=document.getElementById('sandboxPlay');play.textContent=timer?w[6]:w[5];play.disabled=loading||!frames.length;document.getElementById('sandboxApply').disabled=loading;document.getElementById('sandboxReset').disabled=loading||!frames.length;document.getElementById('sandboxTime').disabled=loading||!frames.length;document.getElementById('sandboxMinute').textContent=`07:${String(frame*5).padStart(2,'0')}`;}
 function stop(){if(timer)clearInterval(timer);timer=null;updateSandbox()}
 function showFrame(){current=structuredClone(frames[frame]);document.getElementById('sandboxTime').value=frame;document.getElementById('publicPatient').close();if(typeof acceptState==='function')acceptState(current);updateSandbox()}
 async function applyScenario(){if(loading)return;stop();loading=true;updateSandbox();const status=document.getElementById('sandboxStatus');status.textContent=language()==='ko'?'시나리오 불러오는 중…':'Loading scenario…';try{const response=await originalFetch(`scenarios/${document.getElementById('sandboxProfile').value}.json`);if(!response.ok)throw Error('HTTP '+response.status);const loaded=await response.json();if(!Array.isArray(loaded)||!loaded.length)throw Error('No frames');frames=loaded;frame=0;showFrame();status.textContent=language()==='ko'?'적용됨 · 가상 시나리오':'Applied · fictional scenario';}catch(e){status.textContent=e.message;}finally{loading=false;updateSandbox();}}
 document.addEventListener('DOMContentLoaded',()=>{
 const panel=document.createElement('section');panel.id='publicSandbox';panel.dataset.noTranslate='';panel.innerHTML=`<h2 data-sb-label="0"></h2><p data-sb-label="9"></p><div class="sandbox-controls"><select id="sandboxProfile" aria-label="Sandbox scenario"><option value="calm" data-sb-label="1"></option><option value="bleeding" selected data-sb-label="2"></option><option value="surge" data-sb-label="3"></option></select><button id="sandboxApply" data-sb-label="4"></button><button id="sandboxPlay"></button><button id="sandboxReset" data-sb-label="7"></button><label for="sandboxTime" data-sb-label="8"></label><input id="sandboxTime" type="range" min="0" max="6" value="0" step="1"><output id="sandboxMinute">07:00</output></div><div id="sandboxStatus" role="status"></div>`;document.querySelector('header').after(panel);
 document.getElementById('sandboxApply').onclick=applyScenario;
 document.getElementById('sandboxTime').oninput=e=>{stop();frame=Number(e.target.value);showFrame()};
 document.getElementById('sandboxReset').onclick=()=>{stop();frame=0;showFrame()};
 document.getElementById('sandboxPlay').onclick=()=>{if(timer){stop();return}if(frame===frames.length-1)frame=0;timer=setInterval(()=>{if(typeof Transfers!=='undefined'&&Transfers.busy())return;if(frame<frames.length-1){frame++;showFrame()}if(frame===frames.length-1)stop()},1800);showFrame()};
 new MutationObserver(updateSandbox).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});updateSandbox();
 document.getElementById('publicClose').onclick=()=>document.getElementById('publicPatient').close();});
})();
