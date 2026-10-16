/* A display boundary for the public fictional prototype, not authentication. */
(() => {
  'use strict';
  const q=s=>document.querySelector(s);
  const center=()=>document.body.dataset.workspaceMode==='center';
  const personalDialogs=['publicPatient','nurseSheet','operationsDetail','transferDetail','transportSceneDetail'];
  const privateBodies=['publicPatientBody','nurseSheetBody','operationsDetailBody','detail','cCtx','cScenario','patientAnatomy','cChat','cCareActions','cActivities','patientTrends','patientDiagnostics'];
  const concealed=['#wardView','#patientsView','#planningView','.side','.scopebar','#demoTools','#contextReferences','#operationsSummary','#workspacePurpose','#modal',...personalDialogs.map(id=>'#'+id)];
  const retained=new Map();
  let previousMode=null,applying=false;
  function forgetSelection(){
    if(typeof picked!=='undefined')picked=null;
    if(typeof me!=='undefined')me='';
    document.querySelectorAll('[data-staff-selected=true],.ops-selected-bed').forEach(node=>{node.dataset.staffSelected='false';node.classList.remove('ops-selected-bed');});
  }
  function clearPersonalViews(){
    for(const id of personalDialogs){const node=q('#'+id);if(node?.open)node.close();}
    q('#modal')?.classList.remove('open');
    for(const id of privateBodies){const node=q('#'+id);if(node?.childNodes.length)node.replaceChildren();}
    for(const id of ['cCareInput','cIn']){const node=q('#'+id);if(node)node.value='';}
    q('#cImg')?.removeAttribute('src');
    if(typeof C!=='undefined'){
      C.stop=true;C.bed=null;C.patient_key=null;C.nurse_id=null;C.staff_id=null;
      C.history=[];C.actions=[];C.activities=[];
    }
    forgetSelection();
  }
  function conceal(node){
    if(!retained.has(node))retained.set(node,{inert:node.inert,aria:node.getAttribute('aria-hidden')});
    node.inert=true;node.setAttribute('aria-hidden','true');
  }
  function restore(){
    for(const [node,saved]of retained){node.inert=saved.inert;if(saved.aria===null)node.removeAttribute('aria-hidden');else node.setAttribute('aria-hidden',saved.aria);}
    retained.clear();
  }
  function normalizeURL(){
    if(!center())return;
    const url=new URL(location);url.searchParams.set('workspace','center');
    for(const key of ['nurse','ward','consult'])url.searchParams.delete(key);
    url.hash='network';if(url.href!==location.href)history.replaceState(null,'',url);
    if(document.body.dataset.workspaceView!=='network')window.SICULink?.setView('network',false);
  }
  function apply(){
    if(applying)return;applying=true;
    try{
      const mode=center()?'center':'hospital';
      if(mode!==previousMode){
        if(mode==='center'){
          window.SICUUnifiedReplay?.reset();
          const play=q('#sandboxPlay');if(/^(Pause|일시정지)$/.test(play?.textContent.trim()||''))play.onclick.call(play);
          window.SICUTransportScenes?.reset();
          if(q('#modal')?.classList.contains('open')&&typeof closeConsult==='function')closeConsult();
          window.SICUNetworkOverview?.close();
          clearPersonalViews();
        }else restore();
        previousMode=mode;
      }
      if(mode==='center'){
        normalizeURL();
        for(const selector of concealed){const node=q(selector);if(node)conceal(node);}
        clearPersonalViews();
      }
    }finally{applying=false;}
  }
  function guard(object,key,blocked=null){
    const native=object?.[key];if(typeof native!=='function')return;
    object[key]=function(...args){if(center()){clearPersonalViews();return blocked;}return native.apply(this,args);};
  }
  for(const key of ['openPublicBed','selectPatient','detail','openConsult'])guard(window,key);
  guard(Transfers,'openDetails',true);
  function guardExport(name,methods){
    const original=window[name];if(!original)return;
    const wrapped={...original};
    for(const [key,blocked]of Object.entries(methods))guard(wrapped,key,blocked);
    window[name]=Object.freeze(wrapped);
  }
  guardExport('SICUNurseSheet',{open:null,describe:null});
  guardExport('SICUOperations',{open:null,describe:null});
  guardExport('SICUObservations',{describe:null,connections:null});
  const blockedSelector=[...concealed,'[data-patient]','[data-nurse-patient-bed]','[data-consult-bed]','[data-operations-kind]','[data-operations-bed]','[data-operations-nurse]','[data-operations-patient-bed]','[data-operations-locate]','[data-network-locate]','[data-hospital]','[data-ward]'].join(',');
  function block(event){
    if(!center()||event.type==='keydown'&&!['Enter',' '].includes(event.key))return;
    if(event.target instanceof Element&&event.target.closest(blockedSelector)){
      event.preventDefault();event.stopImmediatePropagation();clearPersonalViews();
    }
  }
  document.addEventListener('click',block,true);document.addEventListener('keydown',block,true);
  document.addEventListener('sicu-workspace-mode',apply);
  for(const type of ['hashchange','popstate'])window.addEventListener(type,()=>{normalizeURL();apply();});
  document.addEventListener('icu-language',()=>queueMicrotask(apply));
  const nativeDraw=window.draw;window.draw=function(...args){const result=nativeDraw.apply(this,args);apply();return result;};
  window.SICUCoordinationContext=Object.freeze({describe:()=>({mode:center()?'center':'hospital',scope:center()?'operations-only':'hospital',authentication:false,livePatientData:false}),apply});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply);else apply();
})();
