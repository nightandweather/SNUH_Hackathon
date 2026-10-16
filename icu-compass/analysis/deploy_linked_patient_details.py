"""Private Pod deployment after source linkage; never publishes to Sites."""
from pathlib import Path
import os, json, shutil, subprocess, sys, time, urllib.request, signal
W=Path('/home/khdp-user/workspace/icu-runtime');LIVE=W/'kmimic-board-v1';STAGE=W/'kmimic-linked-v4'
source=W/'linked-pilot/pool_linked.json'
if not source.exists():source=W/'linked-pilot/pool_linked_preview.json'
assert source.is_file(),'Linkage data not ready'
pool=json.loads(source.read_text());names=json.loads((STAGE/'verified_diagnosis_names.json').read_text())
lookup={(r['version'],r['code']):r for r in names['entries']}
for p in pool:
 for field in ('current_diagnoses','past_diagnoses'):
  for r in p.get('clinical_detail',{}).get(field,[]):
   match=lookup.get((r['version'],r['code']))
   if match:r.update(name_ko=match['name_ko'],name_en=match['name_en'],name_status='verified',name_source='KOICD · KCD5',name_source_url=names['source'])
active=W/'linked-pilot/pool_active.json'
# Keep raw source identities private; the API only emits aliases and approved fields.
active.write_text(json.dumps(pool,ensure_ascii=False,allow_nan=False));os.chmod(active,0o600)
files=['kmimic_board.py','grounded_chat.py','clinical_detail.py','static/grounded-chat.js','static/patient-detail.js','static/kmimic-board.html']
subprocess.run([sys.executable,'-m','unittest','test_grounded_chat','test_kmimic_board','test_clinical_detail'],cwd=STAGE,check=True)
proc=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=[x.decode() for x in p.read_bytes().split(b'\0') if x]
  if str(LIVE/'kmimic_board.py') in args:proc.append((int(p.parent.name),args))
 except (OSError,UnicodeError):pass
assert len(proc)==1,'Expected exactly one live board'
pid,args=proc[0]
env=dict(x.decode().split('=',1) for x in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0') if b'=' in x)
checklog=(W/'linked-stage.log').open('a')
tmp=subprocess.Popen([sys.executable,str(STAGE/'kmimic_board.py'),'--pool',str(active),'--port','8037'],env=env,stdout=checklog,stderr=checklog)
def get(path,port=8037):
 with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=10) as r:return json.load(r)
try:
 for _ in range(30):
  if tmp.poll() is not None:raise RuntimeError('Staged server stopped')
  try:public=get('/api/cases');break
  except OSError:time.sleep(.2)
 else:raise RuntimeError('Staged server did not start')
 assert len(public['cases'])==len(pool)
 assert all('_clinical' not in c and 'source_identity' not in c for c in public['cases'])
 report=[]
 for c in public['cases'][:8]:
  i=min(len(c['rows'])-1,72)
  d=get('/api/case-detail?case_id='+c['id']+'&row_index='+str(i))
  assert d['status']=='linked' and d['case_id']==c['id']
  assert all(r['chart_minute']<=r['available_minute']<=d['as_of_minute'] for r in d['labs'])
  report.append({'case':c['id'],'minute':d['as_of_minute'],'labs':d['laboratory_available_count'],'tests':d['test_available_count'],'dx':len(d['current_diagnoses_retrospective'])})
 print('STAGED_VALIDATION',json.dumps(report),flush=True)
finally:tmp.terminate();tmp.wait(timeout=15);checklog.close()
backup=W/('pre-linked-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(mode=0o700)
for name in files:
 old=LIVE/name
 if old.exists():
  b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,b)
 for_new=old.with_name(old.name+'.linked-new');for_new.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(STAGE/name,for_new);os.replace(for_new,old)
newargs=list(args)
newargs[newargs.index('--pool')+1]=str(active)
os.kill(pid,signal.SIGTERM)
for _ in range(100):
 if not (Path('/proc')/str(pid)).exists():break
 time.sleep(.1)
log=(W/'linked-live.log').open('a')
new=subprocess.Popen(newargs,cwd=LIVE,env=env,stdout=log,stderr=log,start_new_session=True)
try:
 for _ in range(50):
  if new.poll() is not None:raise RuntimeError('New live server stopped; backup at '+str(backup))
  try:
   x=get('/api/case-detail?case_id=CASE-001&row_index=12',8007)
   if x.get('status')=='linked':break
  except OSError:pass
  time.sleep(.2)
 else:raise RuntimeError('New live server health check failed; backup at '+str(backup))
except Exception:
 new.terminate()
 new.wait(timeout=15)
 for name in files:
  b=backup/name
  if b.exists():shutil.copy2(b,LIVE/name)
 restored=subprocess.Popen(args,cwd=LIVE,env=env,stdout=log,stderr=log,start_new_session=True)
 print('ROLLED_BACK',restored.pid,flush=True)
 raise
print('LINKED_DEPLOY_COMPLETE',json.dumps({'pid':new.pid,'source_file':source.name,'cases':len(pool),'linked_cases':8,'validation':report}),flush=True)
