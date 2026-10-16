"""Private KHDP-only extraction. Positive evidence candidates, never inferred negatives."""
import csv,json,os,collections,hashlib,html
from pathlib import Path
from datetime import datetime,timedelta,timezone
root=Path(os.environ.get('KMIMIC_PARTITION','/home/khdp-user/workspace/datasets/kmimic-emr-001/268'))
out=Path('/home/khdp-user/workspace/icu-runtime/surgical-scenario-extract');out.mkdir(parents=True,exist_ok=True);out.chmod(0o700)
def rows(n):
 with (root/(n+'.csv')).open(encoding='utf-8-sig') as f:yield from csv.DictReader(f)
def dt(v):
 try:return datetime.fromisoformat(str(v).strip()[:19])
 except:return None
def pair(r):return (r.get('SUBJECT_ID',''),r.get('HADM_ID',''))
def key(r):return pair(r)+(r.get('STAY_ID',''),)
rejected=collections.Counter();adms=collections.defaultdict(list)
for r in rows('ADMISSIONS'):adms[pair(r)].append(r)
stays={};conflicts=set()
for r in rows('ICUSTAYS'):
 if r.get('FIRST_CAREUNIT','').strip()!='SICU':continue
 k=key(r);a,b=dt(r.get('INTIME')),dt(r.get('OUTTIME'))
 if not all(k) or not a or not b or b<=a:rejected['invalid_icu_key_time']+=1;continue
 if k in stays:
  if stays[k]['source']!=r:conflicts.add(k)
  else:rejected['duplicate_icu_row']+=1
  continue
 stays[k]={'source':r,'a':a,'b':b,'events':[]}
for k in conflicts:del stays[k]
rejected['conflicting_icu_keys']=len(conflicts)
byadm=collections.defaultdict(list)
for k,s in stays.items():byadm[k[:2]].append((k,s))
def add(s,kind,table,item,t,value=''):
 s['events'].append({'kind':kind,'table':table,'item':item,'at':t.isoformat(),'relative_minute':round((t-s['a']).total_seconds()/60,2),'value':value})
for k,s in stays.items():
 aa=adms[k[:2]]
 if len(aa)!=1:rejected['nonunique_admission_join']+=1;continue
 a=aa[0];d=dt(a.get('DEATHTIME'))
 if d and s['a']<=d<s['b']:add(s,'death_during_icu','ADMISSIONS','DEATHTIME',d)
 # Hospital ED timestamps prove ED exposure, not necessarily direct ED-to-ICU transfer.
 e=dt(a.get('EDREGTIME'));eo=dt(a.get('EDOUTTIME'))
 if e and eo and e<=eo<=s['a'] and s['a']-eo<=timedelta(hours=24):add(s,'ed_within_24h_before_icu','ADMISSIONS','EDREGTIME/EDOUTTIME',eo)
 if s['source'].get('OP_FLAG','').strip() in ('1','Y','True','true'):add(s,'operation_flag','ICUSTAYS','OP_FLAG',s['a'],'1')
seen=set()
for r in rows('PROCEDUREEVENTS'):
 if r.get('ORDERCATEGORYNAME','').strip()!='수술':continue
 a,b=dt(r.get('STARTTIME')),dt(r.get('ENDTIME'));rid=r.get('PROCEDUREEVENT_ID','')
 if not rid or not a or not b or b<a:rejected['invalid_surgery_time_or_id']+=1;continue
 fingerprint=tuple(sorted(r.items()))
 if fingerprint in seen:continue
 seen.add(fingerprint)
 for k,s in byadm.get(pair(r),[]):
  # Admission+temporal join accommodates procedures outside ICU STAY_ID.
  if s['a']-timedelta(hours=24)<=b<=s['a']:add(s,'surgery_ended_before_icu_24h','PROCEDUREEVENTS',r.get('ITEMID'),b)
  elif s['a']<=a<s['b']:add(s,'surgery_record_during_icu','PROCEDUREEVENTS',r.get('ITEMID'),a)
cpr='001D_7284_11320';ecmo='001C_1093_22025';vent='001C_1207_22360'
for r in rows('DATETIMEEVENTS'):
 if r.get('ITEMID')!=cpr:continue
 s=stays.get(key(r));t=dt(r.get('CHARTTIME')) if r.get('VALUE','').strip()=='심폐소생술 시작함' else dt(r.get('VALUE'))
 if not s:continue
 if t and s['a']<=t<s['b']:add(s,'cpr_start','DATETIMEEVENTS',cpr,t)
 else:rejected['cpr_value_time_not_confirmed_in_stay']+=1
for r in rows('CHARTEVENTS'):
 item=r.get('ITEMID');s=stays.get(key(r))
 if not s or item not in (ecmo,vent):continue
 t=dt(r.get('CHARTTIME'))
 if not t or not s['a']<=t<s['b']:continue
 v=r.get('VALUE','').strip()
 if item==vent and v.upper()=='ON':add(s,'ventilator_on','CHARTEVENTS',item,t,v)
 if item==ecmo:
  try:positive=0<float(r.get('VALUENUM') or v)<float('inf')
  except:positive=False
  if positive:add(s,'ecmo_positive_flow','CHARTEVENTS',item,t,v)
# Record next location as a candidate only: numeric ward codes are not declared general wards.
trans=collections.defaultdict(list)
for r in rows('TRANSFERS'):
 t=dt(r.get('INTIME'))
 if t:trans[pair(r)].append((t,r))
records=[];counts=collections.Counter()
for i,(k,s) in enumerate(sorted(stays.items(),key=lambda x:(x[1]['a'],x[0])),1):
 ev=list({json.dumps(e,sort_keys=True):e for e in s['events']}.values());ev.sort(key=lambda e:e['at']);kinds=sorted({e['kind'] for e in ev})
 after=sorted([(t,r) for t,r in trans[k[:2]] if s['b']<=t<=s['b']+timedelta(hours=24) and r.get('CAREUNIT')],key=lambda x:x[0]);nextunit=after[0][1]['CAREUNIT'] if after else ''
 rec={'case':f'SICU-{i:03d}','SUBJECT_ID':k[0],'HADM_ID':k[1],'STAY_ID':k[2],'icu_in':s['a'].isoformat(),'icu_out':s['b'].isoformat(),'icu_days':round((s['b']-s['a']).total_seconds()/86400,2),'matched_evidence':' | '.join(kinds),'next_unit_unclassified':nextunit,'crrt':'unknown_unmapped','AE_OR':'undefined','events':ev}
 if kinds:records.append(rec);counts.update(kinds)
summary={'dataset':'kmimic-emr-001','partition':root.name,'generated_at':datetime.now(timezone.utc).isoformat(),'eligible_sicu_stays':len(stays),'matched_candidates':len(records),'distinct_subjects':len({r['SUBJECT_ID'] for r in records}),'counts_by_evidence':dict(counts),'rejected':dict(rejected),'limitations':['Single partition convenience sample; not full K-MIMIC.','Counts overlap; rows are ICU stays, not distinct people.','Surgery category and OP_FLAG do not establish postoperative instability.','Missing matches mean unconfirmed, not absent.','GW cannot be assigned without ward code mapping; AE and OR undefined.','ECMO flow is event evidence, not persistent active support. CRRT remains unmapped.','Death requires DEATHTIME within ICU interval; no OR death inferred.','Workbook colors are planning categories, not inferred from these records.']}
(out/'candidates.json').write_text(json.dumps({'summary':summary,'cases':records},ensure_ascii=False,indent=2))
fields=[k for k in records[0] if k!='events'] if records else ['case']
with (out/'candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r[k] for k in fields} for r in records)
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
# Safe browser preview retained behind existing Jupyter authentication.
cols=['case','icu_days','matched_evidence','next_unit_unclassified']
page='<meta charset="utf-8"><title>SICU scenario candidates</title><style>body{font:15px/1.6 system-ui;margin:32px;color:#19324b}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccd6df;text-align:left}tr:nth-child(even){background:#f2f6fa}</style><h1>K-MIMIC SICU · 시나리오 후보</h1><p>실제 과거 입실 기록의 근거가 있는 후보입니다. 엑셀의 가상 병상 배치나 전실 가능 색상을 입증하지 않습니다.</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre><p><a href="candidates.csv">근거별 후보 CSV 다운로드</a></p><table><tr>'+''.join('<th>'+c+'</th>' for c in cols)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r[c]))+'</td>' for c in cols)+'</tr>' for r in records)+'</table>'
(out/'preview.html').write_text(page)
for p in out.iterdir():p.chmod(0o600)
print(json.dumps(summary,ensure_ascii=False,indent=2));print('PRIVATE_OUTPUT',out)
