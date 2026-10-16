function removeLegacyMappingBlock(body){
 const heading=[...body.querySelectorAll('h3')].find(h=>h.textContent===t('장비·처치 연결 상태','Device and treatment mapping'));if(!heading)return;
 // Exactly the legacy description, list and source note; never walk into chat.
 let node=heading.nextElementSibling;for(const tag of ['P','UL','P']){if(!node||node.tagName!==tag)break;const next=node.nextElementSibling;node.remove();node=next;}heading.remove();
}
let lastOpener=null;
const sourceOpenCase=openCase;
openCase=function(index){
 pauseRecordPlaybackForDetail();
 sourceOpenCase(index);
 const c=displayCases()[index],r=at(c);if(!c)return;
 const currentVitals=displayVitalSnapshot(c,r).vitals;$('#detailBody').querySelectorAll('.vitals .vital').forEach((el,i)=>{const k=Object.keys(names)[i],flag=window.VitalIndicators?.classify(k,currentVitals[k]);if(!flag)return;el.classList.toggle('vital-out-of-range',flag.out);el.querySelector('strong').innerHTML=VitalIndicators.valueMarkup(k,currentVitals[k],lang);el.title=t('표시 범위: ','Display range: ')+flag.rangeText;});
 $('#trends').insertAdjacentHTML('afterend',transferDetails(c,r)+equipmentDetails(c,r)+historicalVitalPlots(c,r));
 const procedureHeading=[...$('#detailBody').querySelectorAll('h3')].find(h=>h.textContent.startsWith(t('종료 처치 기록','Ended procedure records')));
 if(procedureHeading?.nextElementSibling)procedureHeading.nextElementSibling.insertAdjacentHTML('beforeend',` <strong>${t('후향적 사건 시각 기준 집계입니다. 원본 기록 가용 시각이 미확인인 처치는 당시 알려진 사실로 AI에 전달하지 않습니다.','This count uses retrospective event times. Procedures with unknown record availability are not sent to the AI as facts known at that time.')}</strong>`);
 // The inherited detail shell predates the additional audited device mappings.
 removeLegacyMappingBlock($('#detailBody'));
};
$('#detail').addEventListener('close',()=>{GroundedChat.close();lastOpener?.isConnected&&lastOpener.focus();});
$('#close').onclick=()=>$('#detail').close();
document.querySelectorAll('[data-language]').forEach(b=>b.onclick=()=>{lang=b.dataset.language;render();if($('#detail').open)openCase(selected)});
$('#prev').onclick=()=>{page--;selected=null;render()};$('#next').onclick=()=>{page++;selected=null;render()};
$('#time').onchange=e=>applyGlobalReplayTime(e.target.value);
function changeScope(h,u=''){stopPlanReplay(true);recordPlayback.clear();GroundedChat.close();if($('#detail').open)$('#detail').close();hospital=h;unit=u;page=0;selected=null;render();}
$('#hospitalScope').onchange=e=>changeScope(e.target.value);
$('#wardScope').onchange=e=>changeScope(hospital,e.target.value);
document.addEventListener('click',e=>{const b=e.target.closest('[data-case]');if(b){lastOpener=b;openCase(Number(b.dataset.case));$('#selectedSummary').textContent=patientLabel(displayCases()[Number(b.dataset.case)]);}const h=e.target.closest('[data-hospital]');if(h)changeScope(h.dataset.hospital);});
$('#detailBody').addEventListener('click',e=>{const b=e.target.closest('[data-checkpoint]');if(!b)return;const caseIndex=Number(b.dataset.checkpointCase),rowIndex=Number(b.dataset.checkpoint),c=displayCases()[caseIndex];if(!c||caseIndex!==selected||!Number.isInteger(rowIndex)||!c.rows[rowIndex])return;GroundedChat.close();time=String(c.rows[rowIndex].minute);render();openCase(caseIndex);});
$('#floors').addEventListener('keydown',e=>{const b=e.target.closest('[data-case]');if(b&&(e.key==='Enter'||e.key===' ')){e.preventDefault();lastOpener=b;openCase(Number(b.dataset.case));}});
async function load(){
 stopPlanReplay(true);
 recordPlayback.pause(false);renderRecordPlayback();
 $('#reloadData').disabled=true;$('#error').textContent='';
 try{const r=await fetch('api/cases',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();if(d.source!=='K-MIMIC'||!d.cases?.length)throw Error('No verified source cases');data=d;page=0;selected=null;if(d.gs_cohort)time='initial';lastLoaded=new Date();render();}
 catch(e){$('#error').textContent=t('실제 기록을 불러오지 못했습니다. ','Source records unavailable. ')+e.message;}
 finally{$('#reloadData').disabled=false;}
}
$('#reloadData').onclick=()=>{if($('#detail').open)$('#detail').close();load()};
window.addEventListener('staff-simulation-manual',()=>{stopPlanReplay();recordPlayback.manual();renderRecordPlayback();renderPlanReplay();});
window.addEventListener('pagehide',()=>{stopPlanReplay(true);recordPlayback.clear();});
render();load();
