"""Deploy only the private presentation; preserve pool, LLM config and other services."""
from pathlib import Path
import os,sys,subprocess,shutil,time,json,urllib.request,signal,hashlib
W=Path('/home/khdp-user/workspace/icu-runtime');LIVE=W/'kmimic-board-v1';UPLOAD=W/'shared-clinical-upload';STAGE=W/'shared-clinical-stage'
files=['kmimic_board.py']+['static/'+x for x in ('shared-clinical.html','shared-presentation.css','shared-clinical.css','shared-care-icons.js','shared-clinical-controller.js','shared-shell-version.json')]
assert not STAGE.exists(),'Stage exists; inspect previous deployment before retrying'
shutil.copytree(LIVE,STAGE)
original={name:hashlib.sha256((LIVE/name).read_bytes()).hexdigest() if (LIVE/name).exists() else None for name in files}
for name in files:
 p=STAGE/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(UPLOAD/name,p)
proc=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=[x.decode() for x in p.read_bytes().split(b'\0') if x]
  if str(LIVE/'kmimic_board.py') in args:proc.append((int(p.parent.name),args))
 except (OSError,UnicodeError):pass
assert len(proc)==1,'Expected exactly one existing private board'
pid,args=proc[0];env=dict(x.decode().split('=',1) for x in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0') if b'=' in x)
log=(W/'shared-clinical-stage.log').open('a')
command=list(args);command[command.index(str(LIVE/'kmimic_board.py'))]=str(STAGE/'kmimic_board.py');command[command.index('--port')+1]='8037'
stage=subprocess.Popen(command,env=env,stdout=log,stderr=log)
def get(path,port=8037):
 with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=10) as r:return r.read()
try:
 for _ in range(50):
  if stage.poll() is not None:raise RuntimeError('Stage exited')
  try: payload=json.loads(get('/api/cases'));break
  except OSError:time.sleep(.2)
 else:raise RuntimeError('Stage unavailable')
 assert len(payload['cases'])==38
 assert all(not any(k.startswith('_') for k in c) for c in payload['cases'])
 assert sum(c['clinical_linked'] for c in payload['cases'])>=8
 for name in files[1:]:assert get('/'+Path(name).name)==(STAGE/name).read_bytes()
 assert b'shared-clinical-controller.js' in get('/')
 for c in payload['cases'][:8]:
  d=json.loads(get('/api/case-detail?case_id='+c['id']+'&row_index=0'))
  assert d['case_id']==c['id'] and d['status']=='linked'
  assert all(r['chart_minute']<=r['available_minute']<=d['as_of_minute'] for r in d['labs'])
 print('STAGE_OK cases=38 linked='+str(sum(c['clinical_linked'] for c in payload['cases'])),flush=True)
finally:stage.terminate();stage.wait(timeout=15)
# Avoid overwriting concurrent edits made after staging.
assert all((hashlib.sha256((LIVE/n).read_bytes()).hexdigest() if (LIVE/n).exists() else None)==h for n,h in original.items()),'Concurrent edit; deployment stopped'
backup=W/('pre-shared-shell-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(mode=0o700)
for n in files:
 old=LIVE/n
 if old.exists():
  b=backup/n;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,b)
 tmp=old.with_name(old.name+'.new-shell');shutil.copy2(STAGE/n,tmp);os.replace(tmp,old)
os.kill(pid,signal.SIGTERM)
for _ in range(100):
 if not (Path('/proc')/str(pid)).exists():break
 time.sleep(.1)
liveLog=(W/'shared-clinical-live.log').open('a');new=subprocess.Popen(args,cwd=LIVE,env=env,stdout=liveLog,stderr=liveLog,start_new_session=True)
try:
 for _ in range(50):
  if new.poll() is not None:raise RuntimeError('New server exited')
  try:
   if b'shared-clinical-controller.js' in get('/',8007):break
  except OSError:pass
  time.sleep(.2)
 else:raise RuntimeError('Health check failed')
except Exception:
 new.terminate();new.wait(timeout=15)
 for n in files:
  if (backup/n).exists():shutil.copy2(backup/n,LIVE/n)
 subprocess.Popen(args,cwd=LIVE,env=env,stdout=liveLog,stderr=liveLog,start_new_session=True)
 raise
print('SHARED_CLINICAL_DEPLOYED',new.pid,'backup',backup.name,flush=True)
