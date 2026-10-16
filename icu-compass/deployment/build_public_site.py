from pathlib import Path
import sys,json,shutil
from datetime import datetime,timezone
root=Path('/Users/iganghun/Documents/autoresearch/KCD2026 ICU 간호 배치 상황판');sys.path.insert(0,str(root))
import demo_profiles,bed_flow
out=root.parent/'public-icu-preview'; dist=out/'dist';(dist/'static').mkdir(parents=True,exist_ok=True)
h=demo_profiles.create('bleeding',multi_hospital=True); state=h.state();state.update(running=False,speed=2,seed=1,cohort='surgical',source=['synthetic'],demo_profile='bleeding',profiles=demo_profiles.PROFILES,hospital_profiles=h.hospital_profiles,bed_flow=bed_flow.build('bleeding'),handover_receipts=[])
assert all(b['patient']['source']=='synthetic' for f in state['floors'] for u in f['units'] for b in u['beds'] if b.get('patient'))
(dist/'snapshot.json').write_text(json.dumps(state,ensure_ascii=False))
for n in ['network.js','i18n.js','app-shell.css','anatomy.js','transfers.js','readiness.js']:shutil.copyfile(root/'static'/n,dist/'static'/n)
s=(root/'static/index.html').read_text()
s=s.replace('<script src="static/i18n.js">','<script src="static/public-view.js"></script><script src="static/i18n.js">')
s=s.replace('function selectPatient(bed){','function selectPatient(bed){ if(Transfers.openDetails(bed))return; window.openPublicBed(findBed(bed),I18n.language); return;')
s=s.replace('Click the patient for live Qwen role-play: nurse + patient, with an optional physician. These findings are not source-record observations.','Public preview: select a bed for its fictional patient summary. No live AI calls.')
s=s.replace('Review patient & discuss','Review patient')
s=s.replace('$("#src").textContent = `Patient data: ${S.source.map(x=>SRC[x]||x).join(" + ")} · Scenario ${S.seed}`;','$("#src").textContent = "Public sandbox · fictional simulation";')
s=s.replace('<body>','<body><div class="public-notice">공개 샌드박스 · 가상 데이터 / Public sandbox · fictional data<br>아래 샌드박스에서 시나리오를 적용해 보세요. 실제 기록·Qwen 대화는 KHDP 서버에서 제공합니다. / Try the sandbox below. Source records and Qwen chat are available on KHDP.</div>')
s=s.replace('</body>','<dialog id="publicPatient"><button id="publicClose">✕ 닫기 / Close</button><div id="publicPatientBody"></div></dialog></body>')
s=s.replace('</head>','<meta name="icu-release-at" content="'+datetime.now(timezone.utc).isoformat()+'"></head>')
(dist/'index.html').write_text(s)
p=dist/'static/app-shell.css';p.write_text(p.read_text()+'''\n.public-notice{padding:12px 24px;background:#e9f2fc;color:#25476b;font-size:13px;line-height:1.7;border-bottom:1px solid #bdd2eb}#simulationControls,#bleedingCase,.compare-controls,.hospital-actions button:nth-child(2),.research-notes,.side button,.side .diagnostic-controls{display:none!important}#publicPatient{border:1px solid #ccd8e6;border-radius:14px;padding:24px;width:min(620px,90vw);max-height:85vh;color:#17334e}#publicPatient::backdrop{background:#102a45aa}#publicClose{position:sticky;top:0;z-index:2;float:right;min-height:44px;min-width:116px;font-weight:700;background:#eaf1fa;border:1px solid #a9bfd6}#publicPatientBody{clear:both;padding-top:15px;line-height:1.8}#publicPatientBody table{width:100%;margin:15px 0}#publicPatientBody td{padding:8px;border-bottom:1px solid #dbe4ee}#publicPatientBody .public-source{background:#eef4fa;border-radius:8px;padding:12px;font-size:13px}\n''')
manifest=json.loads((out/'.openai/hosting.json').read_text());manifest['static']={'directory':'dist'};(out/'.openai/hosting.json').write_text(json.dumps(manifest,indent=2))
(out/'README.md').write_text('Public fictional ICU sandbox and browser-local transport demonstrations. Built from the local dashboard. No patient records, API keys, runtime settings, backend or live inference are included. Hospital/ward navigation, bed icons, bilingual UI and patient summaries work locally in each visitor browser.\n')
print('Public snapshot built:',len(state['floors']),'floors; no real data, credentials or model calls')

with (dist/'static/app-shell.css').open('a') as f:f.write('''#publicSandbox{margin:18px 24px;padding:20px 24px;border:2px solid #507cac;border-radius:12px;background:#f2f7fc;color:#203c56}#publicSandbox h2{font-size:19px;margin:0 0 8px}#publicSandbox p{font-size:13px;line-height:1.7;margin:0 0 12px}.sandbox-controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.sandbox-controls button,.sandbox-controls select{min-height:42px;font:inherit;padding:8px 14px}.sandbox-controls input{width:200px}#sandboxMinute{font-weight:700;font-size:18px}#sandboxStatus{min-height:23px;margin-top:8px;font-size:12px}''')
