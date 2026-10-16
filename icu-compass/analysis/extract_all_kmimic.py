"""Whole mounted K-MIMIC EMR cohort, private outputs only.
Scans ALL batches before joining; hospital is part of every patient/admission key.
Unmapped units and unqueried clinical signals are explicit, never false negatives.
"""
import csv,json,os,re,hashlib,collections,time,traceback
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(os.getenv('KMIMIC_ROOT','/home/khdp-user/workspace/datasets'))
OUT=Path(os.getenv('KMIMIC_OUT','/home/khdp-user/workspace/icu-runtime/full-kmimic-extract'))
EXPECTED={'001','003','004','005','006','009','202'}
FIELDS=['hospital','SUBJECT_ID','HADM_ID','STAY_ID','FIRST_CAREUNIT','LAST_CAREUNIT','icu_in','icu_out','icu_days','cohort_basis','matched_evidence','ed_24h','death_during_icu','surgery_before_24h','surgery_during_icu','operation_flag','next_unit_unclassified','ecmo_crrt','cpr','ventilation','AE_OR','source_partitions']
def stamp():return datetime.now(timezone.utc).isoformat()
def dt(v):
 try:return datetime.fromisoformat(str(v).strip().replace('Z','+00:00')).replace(tzinfo=None)
 except (ValueError,TypeError):return None
def ident(v):return re.sub(r'^([0-9]+)\.0$',r'\1',str(v or '').strip())
def pair(r):return (ident(r.get('SUBJECT_ID')),ident(r.get('HADM_ID')))
def writejson(p,data):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str));tmp.chmod(0o600);tmp.replace(p)
def readfile(p):
 start=time.time();rows=[]
 try:
  encoding='utf-8-sig'
  for encoding in ('utf-8-sig','cp949'):
   try:
    with p.open(encoding=encoding,newline='') as f:
     reader=csv.DictReader(f);header=reader.fieldnames
     if not header or 'SUBJECT_ID' not in header:raise ValueError('Missing SUBJECT_ID column')
     rows=list(reader)
    break
   except UnicodeDecodeError:
    if encoding=='cp949':raise
  return p,rows,{'file':str(p.relative_to(ROOT)),'rows':len(rows),'bytes':p.stat().st_size,'columns':header,'seconds':round(time.time()-start,2),'encoding':encoding,'status':'ok'}
 except Exception as e:return p,[],{'file':str(p.relative_to(ROOT)),'status':'error','error':str(e)}
def scan(d,table,audit):
 files=sorted(d.glob('*/'+table+'.csv'))
 audit['inventory'][table]={'files':len(files),'bytes':sum(p.stat().st_size for p in files)}
 # Bounded parallel reads. No scan of images, signals, or unrelated mounted datasets.
 with ThreadPoolExecutor(max_workers=4) as pool:
  for i,(p,rs,receipt) in enumerate(pool.map(readfile,files),1):
   audit['files'].append(receipt)
   if i%25==0 or i==len(files):
    writejson(OUT/'progress.json',{'at':stamp(),'hospital':d.name,'table':table,'files_read':i,'files_total':len(files)})
    print(d.name,table,i,'/',len(files),flush=True)
   yield p,rs

def hospital(d):
 h=d.name.rsplit('-',1)[-1];out=OUT/h;out.mkdir(exist_ok=True);out.chmod(0o700)
 audit={'hospital':h,'started_at':stamp(),'inventory':{},'files':[],'counts':collections.Counter(),'unit_counts':collections.Counter()}
 stays={};bad=set()
 for p,rows in scan(d,'ICUSTAYS',audit):
  for r in rows:
   audit['counts']['icu_raw_rows']+=1
   k=pair(r)+(ident(r.get('STAY_ID')),);a,b=dt(r.get('INTIME')),dt(r.get('OUTTIME'))
   if not all(k) or not a or not b or b<=a:audit['counts']['icu_invalid_key_time']+=1;continue
   # Ignore representational ID differences, but quarantine conflicting stay metadata.
   r={x:str(v or '').strip() for x,v in r.items()};r.update(SUBJECT_ID=k[0],HADM_ID=k[1],STAY_ID=k[2])
   fp=json.dumps(r,sort_keys=True)
   if k in stays:
    if stays[k]['fp']!=fp:bad.add(k)
    else:audit['counts']['icu_exact_duplicates']+=1
    stays[k]['parts'].add(p.parent.name);continue
   stays[k]={'r':r,'a':a,'b':b,'fp':fp,'parts':{p.parent.name},'ev':{},'next':None}
 for k in bad:stays.pop(k)
 audit['counts']['icu_conflicting_keys']=len(bad)
 byadm=collections.defaultdict(list)
 for k,s in stays.items():
  byadm[k[:2]].append((k,s));audit['unit_counts'][s['r'].get('FIRST_CAREUNIT','')]+=1
  if s['r'].get('OP_FLAG','').upper() in ('1','Y','TRUE'):s['ev']['operation_flag']={'table':'ICUSTAYS','at':s['a'].isoformat(),'item':'OP_FLAG'}
 admissions={};adm_bad=set()
 for p,rows in scan(d,'ADMISSIONS',audit):
  for r in rows:
   k=pair(r)
   if k not in byadm:continue
   fp=json.dumps(r,sort_keys=True)
   if k in admissions:
    if admissions[k][0]!=fp:adm_bad.add(k)
    else:audit['counts']['admission_exact_duplicates']+=1
   else:admissions[k]=(fp,r,p.parent.name)
 for k,ss in byadm.items():
  if k in adm_bad or k not in admissions:
   audit['counts']['stays_with_unresolved_admission']+=len(ss);continue
  _,r,part=admissions[k];death=dt(r.get('DEATHTIME'));er=dt(r.get('EDREGTIME'));eo=dt(r.get('EDOUTTIME'))
  for _,s in ss:
   if death and s['a']<=death<s['b']:s['ev']['death_during_icu']={'table':'ADMISSIONS','partition':part,'at':death.isoformat(),'item':'DEATHTIME'}
   if er and eo and er<=eo<=s['a'] and s['a']-eo<=timedelta(hours=24):s['ev']['ed_within_24h_before_icu']={'table':'ADMISSIONS','partition':part,'at':eo.isoformat(),'item':'EDREGTIME/EDOUTTIME'}
 audit['counts']['admission_conflicting_keys']=len(adm_bad)
 # Keep multiple rows per surgery as evidence only. Do not claim procedure counts.
 for p,rows in scan(d,'PROCEDUREEVENTS',audit):
  for r in rows:
   ss=byadm.get(pair(r))
   if not ss:continue
   category=str(r.get('ORDERCATEGORYNAME','')).strip()
   if category not in ('수술','Surgery','Surgical','SURGERY'):continue
   a,b=dt(r.get('STARTTIME')),dt(r.get('ENDTIME'))
   if not a or not b or b<a:audit['counts']['surgery_invalid_time']+=1;continue
   for _,s in ss:
    kind='surgery_ended_before_icu_24h' if s['a']-timedelta(hours=24)<=b<=s['a'] else 'surgery_record_during_icu' if s['a']<=a<s['b'] else None
    if kind:
     ev={'table':'PROCEDUREEVENTS','partition':p.parent.name,'at':(b if kind=='surgery_ended_before_icu_24h' else a).isoformat(),'item':r.get('ITEMID'),'event_id':r.get('PROCEDUREEVENT_ID'),'category':category}
     if kind not in s['ev'] or ev['at']<s['ev'][kind]['at']:s['ev'][kind]=ev
 for p,rows in scan(d,'TRANSFERS',audit):
  for r in rows:
   t=dt(r.get('INTIME'));unit=str(r.get('CAREUNIT','')).strip()
   if not t or not unit:continue
   for _,s in byadm.get(pair(r),[]):
    if s['b']<=t<=s['b']+timedelta(hours=24) and (s['next'] is None or t<s['next'][0]):s['next']=(t,unit,p.parent.name)
 records=[];evidence=[];counts=collections.Counter()
 for k,s in sorted(stays.items()):
  r=s['r'];unit=r.get('FIRST_CAREUNIT','').upper();ev=s['ev']
  # Literal SICU is a confirmed explicit surgical-unit label. Other codes need vocabulary.
  basis='explicit_SICU' if unit=='SICU' else 'surgery_evidence_unit_mapping_required' if any(x in ev for x in ('operation_flag','surgery_ended_before_icu_24h','surgery_record_during_icu')) else 'unit_mapping_required'
  rec=dict(zip(['SUBJECT_ID','HADM_ID','STAY_ID'],k));rec.update(hospital=h,FIRST_CAREUNIT=r.get('FIRST_CAREUNIT',''),LAST_CAREUNIT=r.get('LAST_CAREUNIT',''),icu_in=s['a'].isoformat(),icu_out=s['b'].isoformat(),icu_days=round((s['b']-s['a']).total_seconds()/86400,3),cohort_basis=basis,matched_evidence=' | '.join(sorted(ev)),ed_24h='confirmed' if 'ed_within_24h_before_icu' in ev else 'unconfirmed',death_during_icu='confirmed' if 'death_during_icu' in ev else 'unconfirmed',surgery_before_24h='confirmed' if 'surgery_ended_before_icu_24h' in ev else 'unconfirmed',surgery_during_icu='confirmed' if 'surgery_record_during_icu' in ev else 'unconfirmed',operation_flag='confirmed' if 'operation_flag' in ev else 'unconfirmed',next_unit_unclassified=s['next'][1] if s['next'] else '',ecmo_crrt='not_yet_queried',cpr='not_yet_queried',ventilation='not_yet_queried',AE_OR='undefined',source_partitions=' | '.join(sorted(s['parts'])))
  records.append(rec)
  if basis!='unit_mapping_required':
   counts[basis]+=1;counts.update(ev.keys());evidence.append({'hospital':h,'key':k,'evidence':ev})
 def csvout(name,rs):
  with (out/name).open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rs)
  (out/name).chmod(0o600)
 csvout('all_icu_stays.csv',records)
 candidates=[r for r in records if r['cohort_basis']!='unit_mapping_required'];csvout('surgical_candidates.csv',candidates)
 writejson(out/'candidate_evidence.json',evidence)
 audit['counts']['valid_unique_icu_stays']=len(records);audit['counts']['surgical_candidates']=len(candidates);audit['counts']['distinct_candidate_subjects']=len({r['SUBJECT_ID'] for r in candidates});audit['evidence_counts']=dict(counts)
 audit['finished_at']=stamp();audit['status']='complete_core' if not any(x['status']=='error' for x in audit['files']) else 'incomplete_read_errors'
 writejson(out/'audit.json',audit)
 print('HOSPITAL_RESULT',h,json.dumps(audit['counts']),json.dumps(audit['unit_counts']),flush=True)
 return audit

def main():
 OUT.mkdir(parents=True,exist_ok=True);OUT.chmod(0o700)
 datasets=sorted(ROOT.glob('kmimic-emr-*'));found={d.name.rsplit('-',1)[-1] for d in datasets}
 report={'started_at':stamp(),'scope':'All mounted K-MIMIC EMR hospitals and all batches; core cohort extraction','expected_hospitals':sorted(EXPECTED),'found_hospitals':sorted(found),'missing_hospitals':sorted(EXPECTED-found),'hospitals':[],'limitations':['Clinical observation tables have NOT been scanned: CPR, ECMO, CRRT, ventilation and vasopressors remain unconfirmed.','SICU labels are explicit. Other surgical candidates require hospital-specific ICU vocabulary review.','Only validated positive surgery/ED/death evidence is used. Missing evidence is not absence.','AE and OR workbook meanings remain undefined; no OR-death inference.','Numeric destination units are unclassified; no GW assertion.','Shifted dates do not represent real calendar dates. No transfer-readiness colors are inferred.','Conflicting ICU and admission keys are quarantined. All joins are hospital-scoped across ALL batches.']}
 writejson(OUT/'summary.json',report)
 for d in datasets:
  try:
   previous=OUT/d.name.rsplit('-',1)[-1]/'audit.json'
   cached=json.loads(previous.read_text()) if os.getenv('KMIMIC_RESUME')=='1' and previous.exists() else None
   audit=cached if cached and cached.get('status')=='complete_core' else hospital(d)
  except Exception as e:
   traceback.print_exc();audit={'hospital':d.name,'status':'error','error':str(e)}
  report['hospitals'].append({k:v for k,v in audit.items() if k!='files'});writejson(OUT/'summary.json',report)
 for name in ('all_icu_stays.csv','surgical_candidates.csv'):
  with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
   for h in sorted(found):
    p=OUT/h/name
    if p.exists():
     with p.open(encoding='utf-8-sig',newline='') as src:w.writerows(csv.DictReader(src))
  (OUT/name).chmod(0o600)
 report['finished_at']=stamp();report['core_complete']=not report['missing_hospitals'] and all(h.get('status')=='complete_core' for h in report['hospitals'])
 report['totals']={k:sum(h.get('counts',{}).get(k,0) for h in report['hospitals']) for k in ('icu_raw_rows','valid_unique_icu_stays','surgical_candidates','distinct_candidate_subjects','icu_exact_duplicates','icu_conflicting_keys')}
 writejson(OUT/'summary.json',report);writejson(OUT/'progress.json',{'at':stamp(),'status':'finished','core_complete':report['core_complete'],'totals':report['totals']});print('FINAL',json.dumps(report['totals']),flush=True)
if __name__=='__main__':main()
