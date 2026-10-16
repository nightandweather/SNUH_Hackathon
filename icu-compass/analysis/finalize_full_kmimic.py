"""Apply verified m_icu_name mapping and audit all expected core partitions."""
import csv,json,os,html,collections
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(os.getenv('KMIMIC_ROOT','/home/khdp-user/workspace/datasets'))
OUT=Path(os.getenv('KMIMIC_OUT','/home/khdp-user/workspace/icu-runtime/full-kmimic-extract'))
MAPPING={'001':{'SICU':'SICU','SICU3':'SICU'},'003':{'SICU':'SICU'},'004':{'SICU':'SICU'},'005':{'TSICU':'TICU'},'006':{'SICU':'SICU'},'009':{'2ICU':'SICU','GSICU':'SICU','SICU':'SICU'},'202':{'SICU':'SICU'}}
SOURCE_COUNTS={'001':(149760,149760),'003':(29038,28994),'004':(25085,25085),'005':(16910,16910),'006':(35367,35367),'009':(48867,48865),'202':(25312,25312)}
SQL="SELECT hospital_id, careunit, icu_category, icu_name FROM kmimic_voca.m_icu_name WHERE icu_category IN ('SICU','TICU') ORDER BY hospital_id, careunit LIMIT 100"
def dt(v):
 try:return datetime.fromisoformat(str(v)).replace(tzinfo=None)
 except:return None
def load(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writej(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2));p.chmod(0o600)
def main():
 report=json.loads((OUT/'summary.json').read_text());assert report.get('finished_at'),'Core extraction still running'
 writej(OUT/'icu_mapping_source.json',{'source':'https://khdp.ai/table/t/kmimic_voca','table':'kmimic_voca.m_icu_name','sql':SQL,'tool_result_rows':10,'mapping':MAPPING,'verified':'SQL tool expanded result, all 10 rows visible; not inferred from code strings'})
 rows=load(OUT/'all_icu_stays.csv');keys=set();byadm=collections.defaultdict(list)
 for r in rows:
  k=(r['hospital'],r['SUBJECT_ID'],r['HADM_ID'],r['STAY_ID']);assert k not in keys,'Duplicate composite stay key';keys.add(k)
  r['surgical_unit_evidence']='';r['standard_icu_category']='';r['surgical_unit_codes']=''
  cats=[];units=[]
  for col in ('FIRST_CAREUNIT','LAST_CAREUNIT'):
   unit=r[col];cat=MAPPING.get(r['hospital'],{}).get(unit)
   if cat:cats.append(cat);units.append(unit);r['surgical_unit_evidence']+=col+'='+unit+'; '
  r['_categories']=set(cats);r['_units']=set(units);r['_a']=dt(r['icu_in']);r['_b']=dt(r['icu_out']);byadm[(r['hospital'],r['SUBJECT_ID'],r['HADM_ID'])].append(r)
 transfer_receipts=[]
 # Search whole admission transfer history, including a surgical ICU in the middle of a stay.
 for h in MAPPING:
  fs=sorted((ROOT/('kmimic-emr-'+h)).glob('*/TRANSFERS.csv'));matched=0
  with ThreadPoolExecutor(max_workers=4) as pool:
   for i in range(0,len(fs),4):
    for p,rr in zip(fs[i:i+4],pool.map(load,fs[i:i+4])):
     for t in rr:
      unit=t.get('CAREUNIT','');cat=MAPPING[h].get(unit)
      if not cat:continue
      a,b=dt(t.get('INTIME')),dt(t.get('OUTTIME'))
      if not a:continue
      for r in byadm.get((h,t.get('SUBJECT_ID',''),t.get('HADM_ID','')),[]):
       if r['_a']<=a<r['_b'] or (b and a<r['_a']<b):
        r['_categories'].add(cat);r['_units'].add(unit)
        if 'TRANSFERS' not in r['surgical_unit_evidence']:r['surgical_unit_evidence']+='TRANSFERS interval overlap; '
        matched+=1
     transfer_receipts.append({'hospital':h,'file':str(p.relative_to(ROOT)),'rows':len(rr)})
  print('MAPPING_DONE',h,'transfer_files',len(fs),'interval_matches',matched,flush=True)
 for r in rows:
  r['standard_icu_category']=' | '.join(sorted(r.pop('_categories')));r['surgical_unit_codes']=' | '.join(sorted(r.pop('_units')));r.pop('_a');r.pop('_b')
  r['cohort_basis']='mapped_surgical_icu' if 'SICU' in r['standard_icu_category'].split(' | ') else 'mapped_trauma_icu' if r['standard_icu_category']=='TICU' else 'other_icu_with_surgery_evidence' if any(s in r['matched_evidence'] for s in ('operation_flag','surgery_ended_before','surgery_record_during')) else 'not_in_surgical_cohort'
 fields=list(rows[0]) if rows else []
 def save(name,selected):
  with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(selected)
  (OUT/name).chmod(0o600)
 groups={'surgical_icu_stays.csv':[r for r in rows if r['cohort_basis']=='mapped_surgical_icu'],'trauma_icu_stays.csv':[r for r in rows if r['cohort_basis']=='mapped_trauma_icu'],'other_icu_with_surgery_evidence.csv':[r for r in rows if r['cohort_basis']=='other_icu_with_surgery_evidence']}
 groups['surgical_scenario_candidates.csv']=[r for r in groups['surgical_icu_stays.csv'] if r['matched_evidence']]
 for name,rr in groups.items():save(name,rr)
 save('all_icu_stays_mapped.csv',rows)
 audits=[]
 for h in report['hospitals']:
  ident=h['hospital'];a=json.loads((OUT/ident/'audit.json').read_text());parts={Path(x['file']).parts[-2] for x in a['files'] if x['file'].endswith('/ICUSTAYS.csv')}
  coverage={}
  for t in ('ICUSTAYS','ADMISSIONS','PROCEDUREEVENTS','TRANSFERS'):
   ok={Path(x['file']).parts[-2] for x in a['files'] if x['file'].endswith('/'+t+'.csv') and x['status']=='ok'}
   coverage[t]={'read_files':len(ok),'missing_partitions':sorted(parts-ok)}
  h['sql_reference_raw_rows'],h['sql_reference_unique_keys']=SOURCE_COUNTS[ident];h['raw_count_matches_sql']=h['counts']['icu_raw_rows']==SOURCE_COUNTS[ident][0]
  h['coverage']=coverage;h['core_files_complete']=all(not v['missing_partitions'] for v in coverage.values()) and bool(parts)
  h['mapped_surgical_icu_stays']=sum(r['hospital']==ident for r in groups['surgical_icu_stays.csv']);h['mapped_trauma_icu_stays']=sum(r['hospital']==ident for r in groups['trauma_icu_stays.csv']);h['scenario_candidates']=sum(r['hospital']==ident for r in groups['surgical_scenario_candidates.csv'])
  audits.append(a)
 report['core_complete']=report['core_complete'] and all(h['core_files_complete'] and h['raw_count_matches_sql'] for h in report['hospitals'])
 report['sql_reconciliation_source']='KHDP.AI Tables: UNION ALL counts over seven kmimic_*.icustays, run_sql succeeded, 7 rows, 82 ms';report['source_total_raw_rows']=330339;report['source_total_unique_keys']=330293
 preliminary=OUT/'surgical_candidates.csv'
 if preliminary.exists():preliminary.replace(OUT/'preliminary_unmapped_candidates.csv')
 report['totals']['pre_mapping_surgery_screen_candidates']=report['totals'].pop('surgical_candidates',report['totals'].get('pre_mapping_surgery_screen_candidates',0))
 report['totals']['pre_mapping_candidate_subjects']=report['totals'].pop('distinct_candidate_subjects',report['totals'].get('pre_mapping_candidate_subjects',0))
 report['mapping_applied']=True;report['mapped_outputs']={k:len(v) for k,v in groups.items()};report['transfer_mapping_files']=len(transfer_receipts);report['validated_at']=datetime.now(timezone.utc).isoformat()
 report['distinct_surgical_subjects']=len({(r['hospital'],r['SUBJECT_ID']) for r in groups['surgical_icu_stays.csv']})
 report['scenario_evidence_counts']=dict(collections.Counter(e for r in groups['surgical_scenario_candidates.csv'] for e in r['matched_evidence'].split(' | ')))
 report['limitations']=[x for x in report['limitations'] if not x.startswith('SICU labels')]+['Hospital-specific SICU/TICU categories from m_icu_name applied to FIRST/LAST_CAREUNIT and TRANSFERS interval overlap. Trauma is a separate cohort.','Patients may have multiple ICU stays; hospital namespaces cannot be linked into cross-hospital people.','Patient-level chronological evidence only: an ICU bed layout, reservation, porter movement or staffing is simulated, not measured by K-MIMIC.']
 writej(OUT/'summary.json',report);writej(OUT/'transfer_mapping_audit.json',transfer_receipts)
 title='K-MIMIC 전체 외과 ICU 추출';header='<meta charset="utf-8"><title>'+title+'</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:36px auto;padding:0 24px;color:#18324a;background:#f5f8fc}h1{font-size:28px}.box{background:white;border:1px solid #d8e2ed;border-radius:12px;padding:22px;margin:18px 0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #e0e7ef}a{color:#0059b3}.warn{background:#fff3cf}.big{font-size:24px;font-weight:700}</style>'
 table='<table><tr><th>병원</th><th>ICU 파티션</th><th>유효 ICU 입실</th><th>외과 ICU</th><th>외상 ICU</th><th>시나리오 후보</th><th>파일 완결</th></tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (h['hospital'],h['inventory']['ICUSTAYS']['files'],h['counts']['valid_unique_icu_stays'],h['mapped_surgical_icu_stays'],h['mapped_trauma_icu_stays'],h['scenario_candidates'],h['core_files_complete']))+'</tr>' for h in report['hospitals'])+'</table>'
 page=header+'<h1>'+title+'</h1><p>KHDP 인증 서버 전용 · 실제 과거 기록 · 생성 '+html.escape(report['validated_at'])+'</p><div class="box"><div class="big">7개 병원 · '+str(sum(h['inventory']['ICUSTAYS']['files'] for h in report['hospitals']))+'개 파티션</div><p>환자 단위가 아닌 ICU 입실 단위입니다. 병원·환자·입원·ICU 입실 키로 중복을 검사하고 전체 파티션을 연결했습니다.</p>'+table+'</div><div class="box warn"><b>현재 완료 범위: 전체 입실·입원·수술·병동 이동 기록 연결 및 외과 ICU 후보 추출</b><p>CPR·ECMO·CRRT·인공호흡기·승압제의 관찰 기록 검증은 아직 완료되지 않았습니다. 엑셀의 모든 임상 조건을 충족하는 환자 목록으로 해석하지 마세요. 병상 예약·이송원·인력 배치는 시뮬레이션입니다.</p></div><div class="box"><h2>엑셀에서 열 수 있는 CSV</h2>'+''.join('<p><a href="'+name+'">'+label+'</a> — '+format(len(groups[name]),',')+' 입실</p>' for name,label in [('surgical_icu_stays.csv','외과 ICU 전체'),('surgical_scenario_candidates.csv','수술·응급실·사망 등 근거가 있는 외과 ICU 후보'),('trauma_icu_stays.csv','외상 ICU 별도 목록'),('other_icu_with_surgery_evidence.csv','다른 ICU의 수술 이력 후보')])+'<p><a href="summary.json">집계·한계·완결성 검사</a> · <a href="icu_mapping_source.json">병동 코드 매핑 근거</a></p></div>'
 (OUT/'preview.html').write_text(page);(OUT/'preview.html').chmod(0o600)
 print('FINAL_MAPPED',json.dumps({'core_complete':report['core_complete'],'totals':report['totals'],'mapped_outputs':report['mapped_outputs'],'evidence':report['scenario_evidence_counts']}),flush=True)
if __name__=='__main__':main()
