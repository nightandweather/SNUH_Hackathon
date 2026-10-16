"""Stage GS selection + private UI, then atomically switch port 8007 only."""
from pathlib import Path
import os,sys,subprocess,shutil,time,json,urllib.request,signal,hashlib
W=Path('/home/khdp-user/workspace/icu-runtime');LIVE=W/'kmimic-board-v1';UPLOAD=W/'gs-board-upload'
POOL=W/'gs-board-pool'/'pool_gs.json';tag=time.strftime('%Y%m%d-%H%M%S')
STAGE=W/('gs-board-stage-'+tag)
files=['patient_imaging.py','kmimic_board.py','grounded_chat.py','clinical_detail.py','clinical_evidence.py','monthly_plan.py','synthetic_cases.py']+['static/'+x for x in ('shared-clinical.html','shared-presentation.css','shared-clinical.css','shared-care-icons.js','shared-staff.js','shared-staff.css','record-visit-planner.js','replay-observations.js','vital-indicators.js','monthly-replay.js','eight-bed-labs.js','shared-clinical-controller.js','shared-shell-version.json','patient-detail.js','grounded-chat.js','workbook-plan.js')]
assert POOL.is_file(),'GS pool not ready'
raw=json.loads(POOL.read_text());assert 8<=len(raw)<=16
assert all(p.get('gs_selection',{}).get('service_code')=='GS' or p.get('provenance',{}).get('gs_selection',{}).get('service_code')=='GS' for p in raw),'GS metadata missing'
shutil.copytree(LIVE,STAGE)
original={n:hashlib.sha256((LIVE/n).read_bytes()).hexdigest() if (LIVE/n).exists() else None for n in files}
for n in files:
 p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(UPLOAD/n,p)
proc=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=[x.decode() for x in p.read_bytes().split(b'\0') if x]
  if str(LIVE/'kmimic_board.py') in args and '--port' in args and args[args.index('--port')+1]=='8007':proc.append((int(p.parent.name),args))
 except (OSError,UnicodeError):pass
assert len(proc)==1,'Expected exactly one private 8007 board'
pid,args=proc[0];env=dict(x.decode().split('=',1) for x in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0') if b'=' in x)
newargs=list(args);newargs[newargs.index('--pool')+1]=str(POOL)
command=list(newargs);command[command.index(str(LIVE/'kmimic_board.py'))]=str(STAGE/'kmimic_board.py');command[command.index('--port')+1]='8037'
log=(W/'gs-board-stage.log').open('a');stage=subprocess.Popen(command,env=env,cwd=STAGE,stdout=log,stderr=log)
def get(path,port=8037):
 with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=15) as r:return r.read()
def validate(port):
 payload=json.loads(get('/api/cases',port));assert len(payload['cases'])==len(raw)
 assert all(not any(k.startswith('_') for k in c) for c in payload['cases'])
 for token in ('SUBJECT_ID','HADM_ID','STAY_ID','khdp_pat_'):
  assert token.encode() not in get('/api/cases',port),'Identifier leaked in API'
 for c in payload['cases']:
  assert c['rows'];assert c['clinical_linked'];assert 0<=c['initial']<len(c['rows'])
  d=json.loads(get('/api/case-detail?case_id='+c['id']+'&row_index='+str(c['initial']),port))
  assert d['case_id']==c['id'] and d['status']=='linked'
  assert d['assessment']['calculator']['name']=='qSOFA'
  assert d['assessment']['clinical_decision'] is False
  if d['assessment']['calculator']['missing']:assert d['assessment']['calculator']['score'] is None
  assert all(r['chart_minute']<=r['available_minute']<=d['as_of_minute'] for r in d['labs'])
 assert b'shared-clinical-controller.js' in get('/',port)
 assert b'shared-staff.js' in get('/',port) and b'recordPlayback' in get('/',port)
 assert b'setReplayFrame' in get('/shared-staff.js',port)
 if any(p.get('historical_device_observations') for p in raw):
  history=[e for c in payload['cases'] for e in c.get('historical_device_observations',[])]
  assert history,'Reviewed device history was dropped from the API'
  assert all(e['historical_only'] is True for e in history)
  assert all(e['chart_minute']<=e['available_minute'] for e in history if e['availability_status']=='known')
 assert payload.get('monthly_plan',{}).get('day_count')==31
 real_ids={c['id'] for c in payload['cases']}
 replay=payload.get('scenario_cases',[])
 assert replay and all(c['source']=='ScenarioReplay' and c['source_case_id'] in real_ids and c['ai_supported'] is False for c in replay)
 assert all('rows' not in c and 'devices' not in c for c in replay),'Replay slots must reuse source arrays, not invent measurements'
 all_ids=real_ids|{c['id'] for c in replay}
 for scope in payload['monthly_plan']['by_hospital'].values():
  for day in scope['days']:
   for cell in day['beds']:
    if cell['status'] in ('red','blue','green'):assert cell.get('case_id') in all_ids,'Unfilled occupied monthly slot'
    elif cell['status'] in ('empty','yellow'):assert not cell.get('case_id'),'Empty/reserved slot was filled'
 assert b'RecordVisitPlanner' in get('/record-visit-planner.js',port)
 assert b'ReplayObservations' in get('/replay-observations.js',port)
 assert b'eightBedSummary' in get('/',port)
 assert b'VitalIndicators' in get('/vital-indicators.js',port)
 assert b'data-lab-item' in get('/patient-detail.js',port)
 for c in payload['cases']:
  detailpath='/api/case-detail?case_id='+c['id']+'&row_index='+str(len(c['rows'])-1)
  d=json.loads(get(detailpath,port))
  assert 'lab_items' in d and d['laboratory_available_count']==sum(i['count'] for i in d['lab_items'])
  if d['lab_items']:
   item=d['lab_items'][-1]
   from urllib.parse import quote
   selected=json.loads(get(detailpath+'&lab_item='+quote(item['itemid']),port))
   assert selected['laboratory_filtered_count']==item['count']
   assert all(str(r['itemid'])==item['itemid'] for r in selected['labs'])
   simulated=json.loads(get(detailpath+'&lab_item='+quote(item['itemid'])+'&lab_interpolate=1',port))
   assert simulated['labs']==selected['labs'] and simulated['lab_interpolation']['exclude_from_ai'] is True

 assert get('/gs/monthly.xlsx',port)[:2]==b'PK'
 allocation=json.loads(get('/gs/monthly-summary.json',port))
 assert allocation['cohort_stays']==14321 and allocation['by_scope']['VIRTUAL']['episodes']==48
 return payload
try:
 for _ in range(100):
  if stage.poll() is not None:raise RuntimeError('Stage exited; inspect gs-board-stage.log')
  try: get('/api/cases');break
  except OSError:time.sleep(.2)
 else:raise RuntimeError('Stage unavailable')
 payload=validate(8037)
 for n in files:
  if n.startswith('static/') and n!='static/workbook-plan.js':assert get('/'+Path(n).name)==(STAGE/n).read_bytes()
 print('GS_STAGE_OK',len(payload['cases']),flush=True)
finally:stage.terminate();stage.wait(timeout=15)
assert all((hashlib.sha256((LIVE/n).read_bytes()).hexdigest() if (LIVE/n).exists() else None)==h for n,h in original.items()),'Concurrent code edit; stopped'
backup=W/('pre-gs-board-'+tag);backup.mkdir(mode=0o700)
(backup/'launch_args.json').write_text(json.dumps(args));(backup/'launch_args.json').chmod(0o600)
for n in files:
 old=LIVE/n
 if old.exists():
  b=backup/n;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,b)
 tmp=old.with_name(old.name+'.gs-new');shutil.copy2(STAGE/n,tmp);os.replace(tmp,old)
os.kill(pid,signal.SIGTERM)
for _ in range(100):
 if not (Path('/proc')/str(pid)).exists():break
 time.sleep(.1)
liveLog=(W/'gs-board-live.log').open('a');new=subprocess.Popen(newargs,cwd=LIVE,env=env,stdout=liveLog,stderr=liveLog,start_new_session=True)
try:
 for _ in range(100):
  if new.poll() is not None:raise RuntimeError('New server exited')
  try:validate(8007);break
  except OSError:pass
  time.sleep(.2)
 else:raise RuntimeError('Live health check failed')
except Exception:
 new.terminate();new.wait(timeout=15)
 for n in files:
  if (backup/n).exists():shutil.copy2(backup/n,LIVE/n)
 subprocess.Popen(args,cwd=LIVE,env=env,stdout=liveLog,stderr=liveLog,start_new_session=True)
 raise
result={'deployed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'port':8007,'cases':len(raw),'scenario_replay_cases':len(payload.get('scenario_cases',[])),'pid':new.pid,'backup':backup.name,'pool':str(POOL),'public_changed':False,'source_ids_exposed':False}
(W/'gs-board-deployment.json').write_text(json.dumps(result,indent=2));print('GS_BOARD_DEPLOYED',json.dumps(result),flush=True)
