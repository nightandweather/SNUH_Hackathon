"""Reuse canonical presentation styles and existing private clinical detail controller.
No patient rows or credentials are copied into public assets.
"""
from pathlib import Path
import re, hashlib, json
from datetime import datetime, timezone
updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds")
root=Path(__file__).resolve().parents[1]
public=root.parent/'public-icu-preview/dist'
source=(public/'index.html').read_text()
old=(root/'static/kmimic-board.html').read_text()
styles='\n'.join(re.findall(r'<style>(.*?)</style>',source,re.S))
(root/'static/shared-presentation.css').write_text(styles+'\n'+(public/'static/app-shell.css').read_text())
# Export the same canonical card pictograms for the private data adapter.
icons=(public/'static/network.js').read_text().replace('careDisplayIndicators,careMapIcons,get hospital', 'careDisplayIndicators,careMapIcons,careStrip,bedDrawing,get hospital')
icons=icons.replace('${label} · ${status}', '${label} · ${status}${p?.care_evidence?.[key]?" · "+esc(p.care_evidence[key]):""}')
(root/'static/shared-care-icons.js').write_text(icons)
# Retain the tested patient detail / consultation code unchanged.
script=old.split('<script>\nlet lang=',1)[1].split('</script>',1)[0]
script='let lang='+script
preamble=script[:script.index('function render(){')]
# Use common ICU-relative time by default, rather than different initial times.
preamble=preamble.replace("time='initial'", "time='0'").replace('const at=', 'let at=')
detail=script[script.index('function openCase(index)'):script.index("$('#detail').addEventListener('close'")]
detail=detail.replace('time=String(c.rows[next].minute)', 'setCaseReplayMinute(c,c.rows[next].minute)')
detail=detail.replace('const c=data.cases[index],r=at(c)', 'const c=displayCases()[index],r=at(c)').replace('${c.id} · Digital Twin','${patientLabel(c)} · Digital Twin')
detail=detail.replace('${esc(c.dataset)} / ${esc(c.partition)}', '${esc(clinicalSourceCase(c).dataset)} / ${esc(clinicalSourceCase(c).partition)}')
detail=detail.replace("PatientDetail.mount($('#detailBody'),c,", "PatientDetail.mount($('#detailBody'),clinicalSourceCase(c),")
detail=detail.replace(" GroundedChat.mount($('#detailBody'),c,", " const chatCase={...clinicalSourceCase(c),display_id:patientLabel(c)}; GroundedChat.mount($('#detailBody'),chatCase,")
detail=detail.replace('c.rows.slice(Math.max(0,idx-24),idx+1)', 'c.rows.slice(0,idx+1).filter(point=>point.minute>=r.minute-120)')
detail=detail.replace('const c=displayCases()[index],r=at(c);', 'const c=displayCases()[index],r=at(c),displayVitals=displayVitalSnapshot(c,r);')
detail=detail.replace('${value(r?.vitals[k])}', '${value(displayVitals.vitals[k])}').replace("${r?.age[k]!=null?t(`${r.age[k]}분 전 관측`,`${r.age[k]} min old`):t('미확인','Unknown')}", "${displayVitals.age[k]!=null?t(`${displayVitals.age[k]}분 전 관측`,`${displayVitals.age[k]} min old`):t('미확인','Unknown')}")
detail=detail.replace('</div>${PatientDetail.render(c,lang)}', '</div>${displayVitals.historicalInputsUsed?`<p class="record-time-note">${t(\'기록 시각 기준 · AI 상담은 당시 가용성이 확인된 자료만 사용합니다.\',\'By chart time · AI consultation uses only evidence with confirmed availability at that time.\')}</p>`:\'\'}${PatientDetail.render(c,lang)}')
detail=detail.replace(" PatientDetail.mount($('#detailBody'),", " const trendBlock=$('#trends'),trendTitle=trendBlock.previousElementSibling;$('#detailBody').querySelector('.vitals').after(trendTitle,trendBlock);\n PatientDetail.mount($('#detailBody'),")
detail=detail.replace('<path d="${d}"/>', """<path d="${d}"/>${rows.map((x,i)=>window.VitalIndicators?.classify(k,x.vitals[k]).out?`<circle cx="${10+i*580/Math.max(1,rows.length-1)}" cy="${75-(x.vitals[k]-lo)*55/(hi-lo)}" r="4" style="fill:#b42332;stroke:#fff;stroke-width:1"><title>${x.vitals[k]} ${u}</title></circle>`:'').join('')}""")
events=(root/'static/shared-clinical-events.js').read_text().replace('time=String(c.rows[rowIndex].minute)', 'setCaseReplayMinute(c,c.rows[rowIndex].minute)')
plan_script=(root/'static/workbook-plan.js').read_text()
plan_rows=json.loads(plan_script.split('const rows=',1)[1].split(';\nfunction render',1)[0])
(root/'static/shared-clinical-controller.js').write_text('const WORKBOOK_PLAN_TEMPLATE='+json.dumps(plan_rows,ensure_ascii=False)+';\n'+'const PRESENTATION_UPDATED_AT='+json.dumps(updated_at)+';\n'+preamble+'\n'+(root/'static/shared-clinical-render.js').read_text()+'\n'+detail+'\n'+events)
html='''<!doctype html><html lang="ko" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>K-MIMIC · ICU 상황판</title><link rel="stylesheet" href="shared-presentation.css"><link rel="stylesheet" href="shared-clinical.css"><link rel="stylesheet" href="shared-staff.css"></head><body>
<div class="public-notice" id="notice"></div>
<header><h1 id="title"></h1><div id="languageSwitch" class="ctl" role="group" aria-label="Language / 언어"><button data-language="ko" lang="ko">한국어</button><button data-language="en" lang="en">English</button></div><span class="clock" id="clock"></span><details id="simulationControls"><summary id="replayTitle"></summary><div class="ctl replay-controls"><button id="prev" aria-label="Previous cases">←</button><span id="page"></span><button id="next" aria-label="Next cases">→</button><label id="timeLabel" for="time"></label><select id="time"></select><button id="reloadData"></button><button id="showMonthlyPlan"></button><button id="showCasePool"></button></div><p class="control-note" id="replayNote"></p></details><span class="tag" id="src">KHDP · K-MIMIC · GS</span><div class="refresh-stamp" id="refreshStamp"></div></header>
<section class="network-panel"><div class="section-heading"><div><span class="eyebrow">Hospital network</span><h2 id="networkTitle"></h2></div><span class="tag" id="networkClock"></span></div><p class="tag" id="networkNote"></p><div id="networkCards"></div></section>
<section class="scopebar"><label><span id="hospitalLabel"></span> <select id="hospitalScope"></select></label><label><span id="wardLabel"></span> <select id="wardScope"></select></label><strong id="scopeSummary"></strong></section>
<div class="scenario-card"><div><strong id="profileTitle"></strong><small id="bedCounts"></small></div></div>
<div id="error" role="alert"></div>
<main><div><details class="floor-plan" open><summary id="mapTitle"></summary><p class="tag" id="slots"></p><section id="recordPlayback" class="record-playback" aria-label="Patient record replay"></section><div id="floors"></div></details><div id="eightBedSummary"></div><section class="patient-board"><div class="section-heading"><h2 id="cardsTitle"></h2><span class="tag" id="slotsLabel"></span></div><div id="careIconLegend" aria-label="Five care indicators"></div><p class="care-key-note" id="legend"></p><div id="patientCards"></div></section></div>
<aside class="side"><section><details><summary id="statusTitle"></summary><div id="statusLegend"></div></details></section><section><details><summary id="staffTitle"></summary><p class="tag" id="staffNote"></p></details></section><section><details><summary id="alertsTitle"></summary><div id="incs" class="tag"></div></details></section><section><h3 id="evidenceTitle"></h3><div id="facts"></div><p class="tag" id="procedureNote"></p></section><section><h3 id="selectionTitle"></h3><p id="selectedSummary" class="tag"></p></section><section><details><summary id="shiftTitle"></summary><div class="tag" id="rosterSummary"></div></details></section><section><details><summary id="handoverTitle"></summary><div class="tag" id="handoverSummary"></div></details></section><section><details><summary id="logTitle"></summary><div class="log" id="log"></div></details></section></aside></main>
<details class="research-notes"><summary id="sourcesTitle"></summary><p><a href="cohort/preview.html" id="cohortLink"></a> · <a href="gs/stays.csv" id="gsFullCsv" hidden></a></p><p><a href="workbook.xlsx" id="xlsx"></a> · <a href="workbook-preview.html" id="xlsxPreview"></a></p><p class="tag" id="coverage"></p><p><a href="gs/monthly-summary.json" id="monthlySummary" hidden></a></p><p class="tag" id="monthlyExportNote"></p></details>
<section class="flow-panel"><details id="workbookPlan"><summary id="planTitle"></summary><p class="tag" id="planNote"></p><div class="flow-scroll"><table class="workbook-table" id="planTable"></table></div></details></section>
<section class="flow-panel"><details id="flowDetails"><summary id="flowTitle"></summary><p class="tag" id="flowNote"></p><div class="flow-scroll"><table id="flowTable" aria-label="Thirty-day source event history"></table></div></details></section>
<dialog id="detail"><div class="dialog-head"><div><span class="eyebrow">Digital Twin · K-MIMIC</span><h2 id="detailTitle"></h2></div><button class="close-button" id="close"></button></div><div class="dialog-body" id="detailBody"></div></dialog>
<script>const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));</script><script src="shared-care-icons.js"></script><script src="anatomy.js"></script><script src="grounded-chat.js"></script><script src="patient-detail.js"></script><script src="shared-staff.js"></script><script src="record-visit-planner.js"></script><script src="vital-indicators.js"></script><script src="replay-observations.js"></script><script src="monthly-replay.js"></script><script src="eight-bed-labs.js"></script><script src="shared-clinical-controller.js"></script></body></html>'''
(root/'static/shared-clinical.html').write_text(html)
(root/'static/shared-shell-version.json').write_text(json.dumps({'source':'canonical public presentation','source_sha256':hashlib.sha256(source.encode()).hexdigest(),'private_ui_version':'shared-clinical-v3-source-frame','updated_at':updated_at},indent=2))
print('Built private shared shell from canonical presentation; clinical data remains API-only.')
