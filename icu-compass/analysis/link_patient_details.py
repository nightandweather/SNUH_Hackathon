"""Private KHDP-only linkage. Does not copy patient rows out of the Pod."""
from pathlib import Path
from datetime import datetime
import csv, json, os, collections, hashlib
import duckdb
W=Path('/home/khdp-user/workspace/icu-runtime')
ROOT=W.parent/'datasets/kmimic-emr-001'
FAST=os.environ.get('KMIMIC_LINK_SCOPE')=='source_partition'
OUT=W/'linked-pilot'
pool=json.loads((OUT/'pool_kmimic.json').read_text())
old=json.loads((W/'kmimic-board-cohort/pool_kmimic.json').read_text())
assert len(pool)==len(old) and all(a['pid']==b['pid'] and a['series']==b['series'] and a['measurement_age_min']==b['measurement_age_min'] and a['procedures']==b['procedures'] for a,b in zip(pool,old)), 'Rebuild does not preserve live cases'
pilots=pool[:8]
subjects={p['provenance']['source_identity']['SUBJECT_ID'] for p in pilots}
current={(p['provenance']['source_identity']['SUBJECT_ID'],p['provenance']['source_identity']['HADM_ID']) for p in pilots}
parts=sorted(x.parent for x in ROOT.rglob('ADMISSIONS.csv'))
audit={'hospital':'001','pilot_cases':len(pilots),'partition_count':len(parts),'tables':{},'identity_rebuild_verified':True}
def stamp(s):
 try:return datetime.fromisoformat(s.strip())
 except (ValueError,AttributeError):return None
def write(name,obj):
 p=OUT/name;p.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False));os.chmod(p,0o600)
def selected(table,fields):
 rows={}; conflicts=set(); scanned=0
 for d in parts:
  f=d/(table+'.csv')
  if not f.exists():raise RuntimeError('Missing '+table+' in '+d.name)
  with f.open(encoding='utf-8-sig') as stream:
   for r in csv.DictReader(stream):
    if r.get('SUBJECT_ID') not in subjects:continue
    k=tuple(r.get(x,'') for x in fields)
    if k in rows and rows[k]!=r:conflicts.add(k)
    rows.setdefault(k,r)
  scanned+=1
 audit['tables'][table]={'partitions':scanned,'matching_unique_rows':len(rows),'conflicts':len(conflicts)}
 return [r for k,r in rows.items() if k not in conflicts]
print('START core linkage',flush=True)
admissions=selected('ADMISSIONS',['SUBJECT_ID','HADM_ID'])
admit={(r['SUBJECT_ID'],r['HADM_ID']):r for r in admissions}
diagnoses=selected('DIAGNOSES_ICD',['SUBJECT_ID','HADM_ID','SEQ_NUM','ICD_CODE','ICD_VERSION','ITEMID'])
write('diagnosis_codes.json',sorted({(r['ICD_VERSION'],r['ICD_CODE']) for r in diagnoses}))
print('CORE_READY',json.dumps(audit),flush=True)
# Scan every hospital partition with exact subject+admission matching, no skip_errors.
con=duckdb.connect();con.execute("SET threads=2");con.execute("SET memory_limit='2GB'")
con.execute('CREATE TABLE target(subject VARCHAR, admission VARCHAR)')
con.executemany('INSERT INTO target VALUES (?,?)',list(current))
def scan_events(table,id_col):
 found={}; conflicts=set()
 scan_parts=[ROOT/pilots[0]['provenance']['partition']] if FAST else parts
 for i,d in enumerate(scan_parts):
  f=d/(table+'.csv')
  if not f.exists():raise RuntimeError('Missing '+table+' in '+d.name)
  cur=con.execute('SELECT e.* FROM read_csv(?, header=true, all_varchar=true) e JOIN target t ON e.SUBJECT_ID=t.subject AND e.HADM_ID=t.admission',[str(f)])
  names=[c[0] for c in cur.description]
  for values in cur.fetchall():
   r=dict(zip(names,values));r={k:v or '' for k,v in r.items()}
   key=(r['SUBJECT_ID'],r['HADM_ID'],r[id_col])
   if not r[id_col]:continue
   if key in found and found[key]!=r:conflicts.add(key)
   found.setdefault(key,r)
  if i%25==0:print(table,'partitions',i+1,'/',len(parts),flush=True)
 audit['tables'][table]={'partitions':len(scan_parts),'matching_unique_rows':len(found),'conflicts':len(conflicts),'scope':'source partition only' if FAST else 'all hospital partitions'}
 return [r for k,r in found.items() if k not in conflicts]
def vocab(table):
 found={}; conflicts=set()
 for d in ([ROOT/pilots[0]['provenance']['partition']] if FAST else parts):
  with (d/(table+'.csv')).open(encoding='utf-8-sig') as f:
   for r in csv.DictReader(f):
    key=r['ITEMID']
    if key in found and found[key]!=r:conflicts.add(key)
    found.setdefault(key,r)
 return {k:r for k,r in found.items() if k not in conflicts}
labs=scan_events('LABEVENTS','LABEVENT_ID'); labnames=vocab('D_LABITEMS')
tests=scan_events('TESTEVENTS','TESTEVENT_ID');testnames=vocab('D_TESTITEMS')
for p in pilots:
 identity=p['provenance']['source_identity']; key=(identity['SUBJECT_ID'],identity['HADM_ID']);a=admit.get(key)
 if not a:raise RuntimeError('Unresolved or conflicting admission identity')
 t0=stamp(p['provenance']['icu_in']);start=stamp(a['ADMITTIME'])
 if start is None or start>t0:raise RuntimeError('Invalid admission time')
 def minutes(s):
  t=stamp(s);return round((t-t0).total_seconds()/60,3) if t else None
 def is_key(r):return (r['SUBJECT_ID'],r['HADM_ID'])==key
 def dx(r):return {'code':r['ICD_CODE'],'version':r['ICD_VERSION'],'sequence':r['SEQ_NUM'],'table':'DIAGNOSES_ICD','name_status':'unmapped'}
 previous={k:r for k,r in admit.items() if k[0]==key[0] and k!=key and stamp(r.get('DISCHTIME')) and stamp(r.get('ADMITTIME')) and stamp(r['ADMITTIME'])<=stamp(r['DISCHTIME'])<start}
 history=[]
 for r in diagnoses:
  k=(r['SUBJECT_ID'],r['HADM_ID'])
  if k in previous:history.append({**dx(r),'prior_discharge_minute':minutes(previous[k]['DISCHTIME'])})
 clinical={'status':'linked','hospital':'001','admission':{'admit_minute':minutes(a['ADMITTIME']),'admission_type':a['ADMISSION_TYPE'],'admission_location':a['ADMISSION_LOCATION'],'table':'ADMISSIONS','summary_type':'structured source fields; no original narrative'},'current_diagnoses':[dx(r) for r in diagnoses if is_key(r)],'past_diagnoses':history,'labs':[],'imaging_tests':[],'coverage':audit,'diagnosis_time_policy':'Current admission diagnoses are retrospective, timestamp unknown; excluded from frozen-time AI. Previous admission codes are historical associations, not confirmed active conditions.'}
 for r in labs:
  if not is_key(r):continue
  chart=minutes(r['CHARTTIME']);store=minutes(r['STORETIME'])
  # Same admission; a mismatching explicit ICU stay is not silently relabeled as this stay.
  if r.get('STAY_ID') and r['STAY_ID']!=identity['STAY_ID']:continue
  if chart is None or chart<clinical['admission']['admit_minute'] or chart>p['los_min']:continue
  name=labnames.get(r['ITEMID'],{})
  clinical['labs'].append({'itemid':r['ITEMID'],'name':name.get('LABEL') or r['ITEMID'],'value':r['VALUE'] or r['VALUENUM'],'unit':r['VALUEUOM'],'reference_low':r['REF_RANGE_LOWER'],'reference_high':r['REF_RANGE_UPPER'],'flag':r['FLAG'],'chart_minute':chart,'available_minute':store if store is not None and store>=chart else None,'table':'LABEVENTS','dictionary':'D_LABITEMS','record_ref':hashlib.sha256(r['LABEVENT_ID'].encode()).hexdigest()[:12]})
 for r in tests:
  if not is_key(r):continue
  chart=minutes(r['CHARTTIME']);store=minutes(r['STORETIME'])
  if r.get('STAY_ID') and r['STAY_ID']!=identity['STAY_ID']:continue
  if chart is None or chart<clinical['admission']['admit_minute'] or chart>p['los_min']:continue
  name=testnames.get(r['ITEMID'],{})
  # Retain test category verbatim; do not call all tests radiology.
  clinical['imaging_tests'].append({'itemid':r['ITEMID'],'name':name.get('LABEL') or r['ITEMID'],'category':name.get('CATEGORY',''),'chart_minute':chart,'available_minute':store if store is not None and store>=chart else None,'table':'TESTEVENTS','dictionary':'D_TESTITEMS','report_status':'not_linked','file_reference_present':bool(r['FILE_PATH']),'record_ref':hashlib.sha256(r['TESTEVENT_ID'].encode()).hexdigest()[:12]})
 p['clinical_detail']=clinical
audit['scope']='admissions and diagnoses: all partitions; labs and tests: source partition only' if FAST else 'all hospital partitions'
write('pool_linked_preview.json' if FAST else 'pool_linked.json',pool)
audit['case_summary']=[{'case':f'CASE-{i+1:03d}','current_dx':len(p['clinical_detail']['current_diagnoses']),'past_dx':len(p['clinical_detail']['past_diagnoses']),'labs':len(p['clinical_detail']['labs']),'tests':len(p['clinical_detail']['imaging_tests'])} for i,p in enumerate(pilots)]
write('linkage_preview_audit.json' if FAST else 'linkage_audit.json',audit)
print('LINK_COMPLETE',json.dumps(audit),flush=True)
