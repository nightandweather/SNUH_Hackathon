"""Repair only failed procedure/lab partitions, preserving all other records."""
from pathlib import Path
import json,copy,shutil
import build_gs_board_pool as b
W=Path('/home/khdp-user/workspace/icu-runtime');OUT=W/'gs-board-pool';ROOT=W.parent/'datasets'
pool=json.loads((OUT/'pool_gs.json').read_text());audit=json.loads((OUT/'audit.json').read_text())
selection=json.loads((W/'gs-scenario-selection/selected_cases.json').read_text())
selected={(str(c['hospital']),)+b.key(c):c for c in selection['cases']}
repairs=[]
for h,ha in audit['hospitals'].items():
 for table,ta in ha['tables'].items():
  failed=[r['partition'] for r in ta.get('files',[]) if r.get('status')!='ok']
  if not failed:continue
  if table not in ('PROCEDUREEVENTS','LABEVENTS'):raise ValueError('Unexpected failed table requires review: '+h+' '+table)
  targets={b.pair(c) for c in selection['cases'] if c['hospital']==h};receipt={}
  records=b.scan(ROOT,h,table,failed,targets,receipt)
  assert receipt[table]['complete_for_selected_partition_set'],'Encoding repair failed'
  if table=='LABEVENTS':
   hospital_cases=[c for c in selection['cases'] if c['hospital']==h]
   admission_parts={str(part) for c in hospital_cases for part in c['source_partition_list']}
   admission_parts.update(str(part) for c in hospital_cases for part in c.get('required_partitions',{}).get('ADMISSIONS',[]))
   admissions=b.scan(ROOT,h,'ADMISSIONS',admission_parts,targets,receipt)
   assert receipt['ADMISSIONS']['complete_for_selected_partition_set'],'Admission repair linkage incomplete'
   dictionary=b.vocabulary(ROOT,h,'D_LABITEMS',set(failed)|admission_parts,receipt)
   assert receipt['D_LABITEMS']['missing_or_unreadable']==0,'Lab dictionary coverage incomplete'
  for p in pool:
   identity=p['provenance']['source_identity']
   if identity['hospital']!=h:continue
   c=selected[(h,)+b.key(identity)];start,end=b.dt(c['icu_in']),b.dt(c['icu_out']);total=(end-start).total_seconds()/60
   if table=='PROCEDUREEVENTS':
    new=[]
    for row in records:
     if not b.own_record(row,c):continue
     a,z=b.relative(row.get('STARTTIME'),start),b.relative(row.get('ENDTIME'),start)
     if a is None or z is None or not 0<=a<=z<total or z>p['los_min']:continue
     av=b.relative(row.get('STORETIME'),start)
     new.append({'start_min':a,'end_min':z,'itemid':row.get('ITEMID',''),'category':row.get('ORDERCATEGORYNAME',''),'table':table,'available_minute':av if av is not None and av>=z else None})
    unique={json.dumps(e,sort_keys=True):e for e in p.get('procedures',[])+new}
    p['procedures']=sorted(unique.values(),key=lambda e:e['end_min'])
    p['procedure_table_available']=True
   else:
    rebuilt=b.build_case(c,{'ADMISSIONS':admissions,'LABEVENTS':records},
      {'D_ITEMS':{},'D_LABITEMS':dictionary,'D_TESTITEMS':{}},{},receipt,p['gs_selection']['strict_cohort_stays'])
    combined={};conflicts=set()
    for lab in p['clinical_detail'].get('labs',[])+rebuilt['clinical_detail']['labs']:
     identity=lab['record_ref']
     if identity in combined and combined[identity]!=lab:conflicts.add(identity)
     combined.setdefault(identity,lab)
    p['clinical_detail']['labs']=sorted((r for k,r in combined.items() if k not in conflicts),key=lambda r:r['chart_minute'])
    p['clinical_detail']['coverage']['lab_encoding_repair_conflicting_refs']=len(conflicts)
  replacement={r['partition']:r for r in receipt[table]['files']}
  ta['files']=[replacement.get(r['partition'],r) for r in ta['files']]
  ta['complete_for_selected_partition_set']=all(r['status']=='ok' for r in ta['files'])
  ta['encoding_repair']='CP949 fallback; exact-key selected rows'
  ta['repair_matching_unique_rows']=receipt[table]['matching_unique_rows']
  ta['repair_conflicts']=receipt[table]['conflicts']
  if set(failed)=={r['partition'] for r in ta['files']}:
   ta['matching_unique_rows']=receipt[table]['matching_unique_rows'];ta['conflicts']=receipt[table]['conflicts']
  repairs.append({'hospital':h,'table':table,'partitions':failed,'matched_rows':len(records)})
for p in pool:p['clinical_detail']['coverage']['tables']=audit['hospitals'][p['provenance']['source_identity']['hospital']]['tables']
shutil.copy2(OUT/'pool_gs.json',OUT/'pool_gs.pre-encoding-repair.json')
b.safe_write(OUT/'pool_gs.json',pool);audit['encoding_repairs']=repairs
for row in audit.get('case_summary',[]):
 p=next((p for p in pool if p['pid']==row.get('case')),None)
 if p:row['labs']=len(p['clinical_detail']['labs'])
b.safe_write(OUT/'audit.json',audit)
print('GS_ENCODING_REPAIR_OK',json.dumps(repairs),flush=True)
