# Audited first-partition SICU replay with explicit ventilator ON/OFF records.
from pathlib import Path
import csv,json,os,math,collections
from datetime import datetime
root=Path(os.environ.get('KMIMIC_ROOT',str(Path.home()/'workspace/datasets')))
out=Path(os.environ.get('KMIMIC_OUTPUT',str(Path.home()/'workspace/icu-runtime/kmimic-board-cohort')))
out.mkdir(exist_ok=True);os.chmod(out,0o700)
d=root/'kmimic-emr-001';part=sorted(d.rglob('ICUSTAYS.csv'))[0].parent
dictionary_units={r['ITEMID']:r.get('UNITNAME','').strip() for r in csv.DictReader((part/'D_ITEMS.csv').open(encoding='utf-8-sig'))}
mapping={'001C_1021_25105':'hr','001C_1014_27095':'map','001C_1017_27095':'map','001C_1003_24480':'spo2','001C_1023_27310':'rr','001C_1012_24795':'sbp','001C_1015_24795':'sbp'}
limits={'hr':(1,300),'map':(1,250),'spo2':(1,100),'rr':(1,100),'sbp':(1,300)}
units={'hr':{'회/min','bpm','/min'},'map':{'mmHg'},'spo2':{'%'},'rr':{'회/min','/min'},'sbp':{'mmHg'}}
def stamp(s):
 try:return datetime.fromisoformat(s.strip()[:19])
 except:return None
stays={}
for r in csv.DictReader((part/'ICUSTAYS.csv').open(encoding='utf-8-sig')):
 if r['FIRST_CAREUNIT'].strip()!='SICU':continue
 t=stamp(r['INTIME']);end=stamp(r['OUTTIME'])
 if not t or not end or (end-t).total_seconds()<3600:continue
 key=tuple(r[k] for k in ['SUBJECT_ID','HADM_ID','STAY_ID'])
 stays[key]={'t0':t,'t1':end,'duration':min(1440,(end-t).total_seconds()/60),'obs':{},'vent_events':[],'raw_obs':[]}
 if len(stays)>=48:break
rejected=collections.Counter();count=0
for r in csv.DictReader((part/'CHARTEVENTS.csv').open(encoding='utf-8-sig')):
 var=mapping.get(r['ITEMID']);key=tuple(r.get(k,'') for k in ['SUBJECT_ID','HADM_ID','STAY_ID']);s=stays.get(key)
 if s is None:continue
 if r['ITEMID']=='001C_1207_22360':
  t=stamp(r.get('CHARTTIME',''));value=r.get('VALUE','').strip().upper()
  if t and value in ('ON','OFF'):
   minute=(t-s['t0']).total_seconds()/60
   if 0<=minute<s['duration']:s['vent_events'].append({'minute':minute,'active':value=='ON','raw':value,'itemid':r['ITEMID'],'table':'CHARTEVENTS'})
 if not var:continue
 unit=r.get('VALUEUOM','').strip() or dictionary_units.get(r['ITEMID'],'')
 if unit not in units[var]:rejected['unit:'+var+':'+unit]+=1;continue
 try:v=float(r.get('VALUENUM') or r['VALUE'])
 except:rejected['non_numeric']+=1;continue
 if not math.isfinite(v) or not limits[var][0]<=v<=limits[var][1]:rejected['invalid:'+var]+=1;continue
 t=stamp(r['CHARTTIME'])
 if not t:continue
 minute=(t-s['t0']).total_seconds()/60
 if 0<=minute<s['duration']:
  s['obs'].setdefault(var,{}).setdefault(minute,[]).append(v);count+=1
  s['raw_obs'].append({'minute':minute,'variable':var,'itemid':r['ITEMID'],'value':v,'unit':unit,'table':'CHARTEVENTS'})
procedure_rows={};procedure_conflicts=set()
procedure_path=part/'PROCEDUREEVENTS.csv'
if procedure_path.exists():
 for r in csv.DictReader(procedure_path.open(encoding='utf-8-sig')):
  key=tuple(r.get(k,'') for k in ['SUBJECT_ID','HADM_ID','STAY_ID']);stay=stays.get(key)
  if stay is None:continue
  start=stamp(r.get('STARTTIME',''));end=stamp(r.get('ENDTIME',''));rid=r.get('PROCEDUREEVENT_ID','').strip()
  if not rid or not start or not end or end<start:rejected['procedure_missing_or_invalid_time_id']+=1;continue
  sm=(start-stay['t0']).total_seconds()/60;em=(end-stay['t0']).total_seconds()/60
  if not (0<=sm<stay['duration']):continue
  event={'start_min':sm,'end_min':em,'itemid':r.get('ITEMID',''),'value':r.get('VALUE',''),'unit':r.get('VALUEUOM',''),'category':r.get('ORDERCATEGORYNAME',''),'table':'PROCEDUREEVENTS'}
  ident=(key,rid)
  if ident in procedure_rows and procedure_rows[ident]!=event:procedure_conflicts.add(ident)
  procedure_rows.setdefault(ident,event)
for (key,rid),event in procedure_rows.items():
 if (key,rid) not in procedure_conflicts:stays[key].setdefault('procedures',[]).append(event)
rejected['procedure_conflicting_ids']=len(procedure_conflicts)
pool=[]
for key,s in stays.items():
 if not all(s['obs'].get(v) for v in ['hr','map','spo2','rr']):continue
 n=int(s['duration']//5);series={};ages={}
 for var in ['hr','map','spo2','rr','sbp']:
  pts=sorted((t,sorted(vals)[len(vals)//2]) for t,vals in s['obs'].get(var,{}).items());j=0;last=None;arr=[];age=[]
  for i in range(n):
   while j<len(pts) and pts[j][0]<=i*5:last=pts[j];j+=1
   fresh=last is not None and i*5-last[0]<=30
   arr.append(round(last[1],1) if fresh else None);age.append(round(i*5-last[0],1) if fresh else None)
  series[var]=arr;ages[var]=age
 if sum(all(series[v][i] is not None for v in ['hr','map','spo2','rr']) for i in range(n))<12:continue
 pool.append({'pid':'KM001-S%03d'%(len(pool)+1),'unit_type':'SICU','careunit':'SICU','age':None,'sex':None,'dx':'SICU admission - diagnosis not mapped','vent':False,'pressor':False,'step':5,'los_min':n*5,'series':series,'measurement_age_min':ages,'cpr':[],'source':'K-MIMIC','bounded_carry_forward':True,'raw_observations':s['raw_obs'],'procedures':sorted(s.get('procedures',[]),key=lambda e:e['end_min']),'procedure_table_available':procedure_path.exists(),'device_events':{'ventilator':sorted(s['vent_events'],key=lambda e:e['minute'])},'provenance':{'source_identity':{'hospital':'001','SUBJECT_ID':key[0],'HADM_ID':key[1],'STAY_ID':key[2]},'icu_in':s['t0'].isoformat(),'icu_out':s['t1'].isoformat(),'dataset':'kmimic-emr-001','partition':part.name,'selection':'FIRST_CAREUNIT exactly SICU; unit-code candidate','support_status':'Ventilator: explicit ON/OFF record, at most 30 min carry; other devices and treatments unknown','max_carry_forward_min':30,'time':'Minutes from source ICU admission; no future observations','diagnosis':'Not mapped'}})
(out/'pool_kmimic.json').write_text(json.dumps(pool));os.chmod(out/'pool_kmimic.json',0o600)
report={'partition':part.name,'sampled_stays':len(stays),'usable_replay_stays':len(pool),'valid_observations':count,'rejections':dict(rejected),'item_mapping':mapping,'scope':'Convenience sample from first partition; not representative or clinically validated','procedure_records':sum(len(p['procedures']) for p in pool),'ventilator_records':sum(len(p['device_events']['ventilator']) for p in pool),'gcs':'Unavailable: coded text not decoded; qSOFA remains incomplete'}
(out/'replay_audit.json').write_text(json.dumps(report,indent=2));print('REPLAY_COMPLETE',json.dumps(report),flush=True)
