import csv,os,tempfile,importlib.util,json
from pathlib import Path
root=Path(tempfile.mkdtemp());os.environ['KMIMIC_ROOT']=str(root/'data');os.environ['KMIMIC_OUT']=str(root/'out')
spec=importlib.util.spec_from_file_location('ex',str(Path(__file__).with_name('extract_all_kmimic.py')));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
def save(h,p,t,rows):
 f=root/'data'/('kmimic-emr-'+h)/p/(t+'.csv');f.parent.mkdir(parents=True,exist_ok=True)
 with f.open('w',newline='') as o:w=csv.DictWriter(o,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
stay={'SUBJECT_ID':'P','HADM_ID':'H','STAY_ID':'1','FIRST_CAREUNIT':'SICU','LAST_CAREUNIT':'SICU','INTIME':'2450-01-02 12:00:00','OUTTIME':'2450-01-04 12:00:00','LOS':'2','OP_FLAG':'0'}
for h in ('001','009'):save(h,'a','ICUSTAYS',[stay]);save(h,'b','ICUSTAYS',[stay])
save('001','b','ADMISSIONS',[{'SUBJECT_ID':'P','HADM_ID':'H','DEATHTIME':'2450-01-03 00:00:00','EDREGTIME':'2450-01-01 12:00:00','EDOUTTIME':'2450-01-02 06:00:00'}])
save('001','c','PROCEDUREEVENTS',[{'SUBJECT_ID':'P','HADM_ID':'H','STARTTIME':'2450-01-02 08:00:00','ENDTIME':'2450-01-02 11:00:00','ORDERCATEGORYNAME':'수술','ITEMID':'surgery','PROCEDUREEVENT_ID':'e1'}])
save('001','d','TRANSFERS',[{'SUBJECT_ID':'P','HADM_ID':'H','INTIME':'2450-01-04 12:00:00','CAREUNIT':'123'}])
cpfile=root/'data/kmimic-emr-001/c/PROCEDUREEVENTS.csv';cpfile.write_bytes(cpfile.read_text().encode('cp949'))
ex.main()
rs=list(csv.DictReader((root/'out/surgical_candidates.csv').open(encoding='utf-8-sig')));assert len(rs)==2
r=next(r for r in rs if r['hospital']=='001');q=next(r for r in rs if r['hospital']=='009')
assert r['death_during_icu']==r['ed_24h']==r['surgery_before_24h']=='confirmed';assert q['death_during_icu']=='unconfirmed';assert r['next_unit_unclassified']=='123';assert r['ecmo_crrt']=='not_yet_queried'
assert json.loads((root/'out/001/audit.json').read_text())['counts']['icu_exact_duplicates']==1
assert not json.loads((root/'out/summary.json').read_text())['core_complete']
print('PASS: cross-batch joins, dedup, hospital isolation, shifted dates, unknown signals, missing-hospital coverage')
spec2=importlib.util.spec_from_file_location('fin',str(Path(__file__).with_name('finalize_full_kmimic.py')));fin=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(fin)
# Simulate a surgical ICU visited between identical non-surgical first/last units.
p=root/'out/all_icu_stays.csv';rs=list(csv.DictReader(p.open(encoding='utf-8-sig')));rs[0]['FIRST_CAREUNIT']=rs[0]['LAST_CAREUNIT']='MICU';rs[1]['FIRST_CAREUNIT']=rs[1]['LAST_CAREUNIT']='2ICU'
with p.open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
save('001','e','TRANSFERS',[{'SUBJECT_ID':'P','HADM_ID':'H','INTIME':'2450-01-03 12:00:00','OUTTIME':'2450-01-03 23:00:00','CAREUNIT':'SICU'}])
fin.main();rr=list(csv.DictReader((root/'out/surgical_icu_stays.csv').open(encoding='utf-8-sig')))
assert len(rr)==2 and all(r['cohort_basis']=='mapped_surgical_icu' for r in rr);assert any('TRANSFERS' in r['surgical_unit_evidence'] for r in rr)
assert not json.loads((root/'out/summary.json').read_text())['core_complete']
print('PASS: official 2ICU mapping, mid-stay surgical transfer, missing core files remain incomplete')
