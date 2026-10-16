from pathlib import Path
import os,json,shutil,sys,threading,copy,math
from http.server import ThreadingHTTPServer
base=Path.home()/'workspace/icu-runtime'; app=base/'kmimic-web'; original=Path.home()/'workspace/icu-board'
if not app.exists():shutil.copytree(original,app,ignore=shutil.ignore_patterns('data','__pycache__','*.log','verification'))
(app/'data').mkdir(exist_ok=True)
pool=json.loads((base/'kmimic-cohort/pool_kmimic.json').read_text());assert len(pool)>=8,'Need at least eight usable replay stays'
(app/'data/pool_kmimic.json').write_text(json.dumps(pool));os.chmod(app/'data/pool_kmimic.json',0o600)
sys.path.insert(0,str(app));os.environ['POOL']='kmimic';os.environ.pop('ICU_COHORT',None)
import engine
config=json.loads((app/'units.json').read_text());config['floors']=[{'floor':4,'units':[{'id':'SICU','name':'Surgical ICU - K-MIMIC replay','type':'SICU','beds':8}]}]
engine.load_config=lambda:copy.deepcopy(config)
def vital(self,src,var,idx):
 arr=src['series'].get(var,[]);return arr[idx] if 0<=idx<len(arr) else None
engine.Hospital._vital=vital
original_bed=engine.Hospital._bed_json
specs=[('hr','Heart rate','bpm','<',40,'Bradycardia'),('hr','Heart rate','bpm','>',140,'Tachycardia'),('map','Mean arterial pressure','mmHg','<',60,'Low MAP'),('spo2','Oxygen saturation','%','<',88,'Low oxygen saturation'),('rr','Respiratory rate','/min','>',35,'Tachypnea')]
def bed_json(self,bed):
 out=original_bed(self,bed);pt=bed.get('patient')
 if not pt:return out
 src=pt['src'];idx=int(pt['offset']//src['step']);p=out['patient'];v=p['vitals'];v['sbp']=vital(self,src,'sbp',idx)
 evidence=[]
 for key,name,unit,op,threshold,label in specs:
  value=v.get(key)
  if value is not None and (value<threshold if op=='<' else value>threshold):evidence.append({'key':key,'name':name,'unit':unit,'value':value,'threshold':threshold,'op':op,'label':label})
 rr=v.get('rr');sbp=v.get('sbp');parts=[{'rule':'RR >= 22/min','value':rr,'points':None if rr is None else int(rr>=22)},{'rule':'SBP <= 100 mmHg','value':sbp,'points':None if sbp is None else int(sbp<=100)},{'rule':'Altered mentation (GCS < 15)','value':None,'points':None}]
 lower=sum(x['points'] or 0 for x in parts);missing=sum(x['points'] is None for x in parts)
 p['clinical']={'title':' / '.join(dict.fromkeys(e['label'] for e in evidence)) or ('Incomplete observations' if any(v.get(k) is None for k in ['hr','map','spo2','rr']) else 'No configured threshold crossed'),'evidence':evidence,'qsofa':{'score':None,'range':[lower,lower+missing],'components':parts,'status':'Incomplete - GCS not mapped'},'provenance':src.get('provenance',{}),'source_offset_min':round(pt['offset'],1),'measurement_age_min':{k:a[idx] if idx<len(a) else None for k,a in src['measurement_age_min'].items()},'history':[{ 'minute':i*src['step'], **{k:a[i] if i<len(a) else None for k,a in src['series'].items()} } for i in range(max(0,idx-24),min(idx+1,len(src['series']['hr'])))]}
 return out
engine.Hospital._bed_json=bed_json
import server
server.sim['running']=False

def initial_windows():
 h=server.sim['h'];occupied=[b for b in h.beds.values() if b['patient']]
 def complete(p,i):return all(p['series'][k][i] is not None for k in ['hr','map','spo2','rr','sbp'])
 def alert(p,i):
  v={k:a[i] for k,a in p['series'].items()}
  return any(v.get(k) is not None and (v[k]<cut if op=='<' else v[k]>cut) for k,name,unit,op,cut,label in specs)
 for b in occupied:
  pt=b['patient'];p=pt['src'];indices=[i for i in range(len(p['series']['hr'])) if complete(p,i)]
  if indices:pt['offset']=indices[min(6,len(indices)-1)]*p['step'];pt.pop('_vital_history',None);h._update_patient(b)
 if occupied:
  used={b['patient']['src']['pid'] for b in occupied[1:]}
  example=next(((p,i) for p in pool if p['pid'] not in used for i in range(len(p['series']['hr'])) if complete(p,i) and alert(p,i)),None)
  if example:
   p,i=example;pt=occupied[0]['patient'];pt['src']=p;pt['offset']=i*p['step'];pt['hist']=[];pt.pop('_vital_history',None);h._update_patient(occupied[0])
initial_windows()


original_reset=server.reset
def reset_with_windows(*args,**kwargs):
 original_reset(*args,**kwargs);server.sim['running']=False;initial_windows()
server.reset=reset_with_windows
old_post=server.H.do_POST
def post(self):
 if self.path.split('?')[0] in ('/api/consult','/api/image-review'):
  self.rfile.read(int(self.headers.get('Content-Length') or 0))
  return self._send(503,{'error':'Qwen setup is deferred. No patient data was sent to a model.'})
 return old_post(self)
server.H.do_POST=post
import case_chat
case_conversations=case_chat.install(server,base)

summary=json.loads((base/'kmimic-cohort/cohort_summary.json').read_text());audit=json.loads((base/'kmimic-cohort/replay_audit.json').read_text())
old_get=server.H.do_GET
html=(base/'kmimic-evidence.html').read_bytes()
def get(self):
 path=self.path.split('?')[0]
 if path in ('/','/index.html'):return self._send(200,html,'text/html; charset=utf-8')
 if path=='/case-chat.js':return self._send(200,(base/'case-chat.js').read_bytes(),'application/javascript; charset=utf-8')
 if path=='/layout':return self._send(200,(app/'static/index.html').read_bytes(),'text/html; charset=utf-8')
 if path=='/api/evidence-summary':return self._send(200,{'cohort':summary,'replay':audit})
 return old_get(self)
server.H.do_GET=get
threading.Thread(target=server.ticker,daemon=True).start()
print('KMIMIC_WEB_READY',len(pool),'replay stays; listening on 127.0.0.1:8005',flush=True)
ThreadingHTTPServer(('127.0.0.1',8005),server.H).serve_forever()
