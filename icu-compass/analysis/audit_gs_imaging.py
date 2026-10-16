"""Aggregate imaging-record coverage for exact GS-entry stays, inside KHDP only.
No row identifiers, file paths or images are exported. A test/file reference is
not proof that a radiology report or readable image is available.
"""
import csv, json, os, re, time
from pathlib import Path
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from count_gs_cohort import dt, ident, write_json, stamp
ROOT=Path(os.getenv('KMIMIC_ROOT','/home/khdp-user/workspace/datasets'))
W=Path('/home/khdp-user/workspace/icu-runtime')
OUT=W/'gs-imaging-audit'
CT=re.compile(r'(?<![A-Z0-9])CT(?![A-Z0-9])|전산화.*단층|컴퓨터.*단층',re.I)
CXR=re.compile(r'(?<![A-Z0-9])CXR(?![A-Z0-9])|CHEST\s*(?:[\(\-:]\s*)?(?:AP|PA|X.?RAY)(?![A-Z0-9])|흉부.*(?:단순|엑스|X.?선|촬영)',re.I)

def label_kind(label):
    if CT.search(label):return 'ct_related'
    if CXR.search(label):return 'cxr_related'
    return None

def read_file(hospital,part,admissions):
    p=ROOT/('kmimic-emr-'+hospital)/part
    vocab={}
    try:
        with (p/'D_TESTITEMS.csv').open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            reader.fieldnames=[name.lstrip('\ufeff').strip() for name in (reader.fieldnames or [])]
            for r in reader:
                kind=label_kind(r.get('LABEL',''))
                # Non-imaging labels participate in ambiguity detection too.
                # A CT label plus an unrelated label for one ITEMID is unknown.
                vocab.setdefault(r['ITEMID'],set()).add(kind)
        receipt={'hospital':hospital,'partition':part,'status':'ok','source_rows':0,'matched_rows':0,'unknown_time_rows':0,'ambiguous_stay_rows':0,'ambiguous_dictionary_items':sum(len(kinds)>1 for kinds in vocab.values())}
        matched=[]
        with (p/'TESTEVENTS.csv').open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            reader.fieldnames=[name.lstrip('\ufeff').strip() for name in (reader.fieldnames or [])]
            assert {'TESTEVENT_ID','SUBJECT_ID','HADM_ID','ITEMID','CHARTTIME','FILE_PATH'}.issubset(reader.fieldnames or [])
            for r in reader:
                receipt['source_rows']+=1
                candidates=admissions.get((ident(r.get('SUBJECT_ID')),ident(r.get('HADM_ID'))))
                if not candidates:continue
                kinds=vocab.get(r['ITEMID'],set())
                if len(kinds)!=1 or None in kinds:continue
                t=dt(r.get('CHARTTIME'))
                if not t:receipt['unknown_time_rows']+=1;continue
                stay=ident(r.get('STAY_ID')); own=[c for c in candidates if c[1]<=t<c[2] and (not stay or stay==c[0])]
                if len(own)!=1:
                    if len(own)>1:receipt['ambiguous_stay_rows']+=1
                    continue
                eid=ident(r.get('TESTEVENT_ID'))
                if not eid:continue
                key=(hospital,ident(r['SUBJECT_ID']),ident(r['HADM_ID']),own[0][0])
                # Retain actual path only as a hash for conflict detection, never display or expose it.
                import hashlib
                signature=(next(iter(kinds)),r['ITEMID'],t.isoformat(),bool(r.get('FILE_PATH','').strip()),hashlib.sha256(r.get('FILE_PATH','').encode()).hexdigest())
                matched.append(((hospital,ident(r['SUBJECT_ID']),ident(r['HADM_ID']),eid),key,signature))
                receipt['matched_rows']+=1
        return receipt,matched
    except Exception as e:
        return {'hospital':hospital,'partition':part,'status':'error','error':type(e).__name__},[]

def main():
    OUT.mkdir(exist_ok=True);OUT.chmod(0o700)
    inp=W/'gs-scenario-selection'/'gs_at_entry_stays.csv'
    by_hospital=defaultdict(lambda:defaultdict(list));allkeys=set()
    with inp.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            h=r['hospital'];key=tuple(ident(r[x]) for x in ('SUBJECT_ID','HADM_ID','STAY_ID'))
            assert (h,*key) not in allkeys
            allkeys.add((h,*key));by_hospital[h][key[:2]].append((key[2],dt(r['icu_in']),dt(r['icu_out'])))
    assert len(allkeys)==14321,'Unexpected GS denominator'
    jobs=[]
    for h in sorted(by_hospital):
        audit=json.loads((W/'full-kmimic-extract'/h/'audit.json').read_text())
        parts={Path(r['file']).parent.name for r in audit['files'] if r['file'].endswith('/ICUSTAYS.csv') and r.get('status')=='ok'}
        jobs.extend((h,p) for p in sorted(parts))
    receipts=[];events={};conflicts=set();started=stamp()
    def summary(complete):
        counts=Counter();sets=defaultdict(set)
        for eid,(stay,sig) in events.items():
            if eid in conflicts:continue
            kind,_,_,haspath,_=sig
            counts[kind+'_test_rows']+=1;sets[kind+'_stays'].add(stay)
            sets['any_imaging_related_stays'].add(stay)
            if haspath:counts[kind+'_rows_with_file_reference']+=1;sets[kind+'_stays_with_file_reference'].add(stay)
        return {'started_at':started,'updated_at':stamp(),'complete':complete,'gs_at_entry_icu_stays':len(allkeys),'scope':'Imaging-related TESTEVENTS with CHARTTIME inside each exact GS-at-entry ICU stay; not entire hospital admission. CT related labels may include contrast/procedure records.', 'files_read':len(receipts),'files_expected':len(jobs),'source_rows':sum(r.get('source_rows',0) for r in receipts),'error_files':sum(r['status']!='ok' for r in receipts),'conflicting_event_ids_excluded':len(conflicts),'counts':dict(counts)|{k:len(v) for k,v in sets.items()},'limitations':['No readable CT/CXR image, DICOM study or radiology report has been validated by this metadata audit.','FILE_PATH is only a source reference, not a verified accessible image.','Counts are ICU stays and test rows, not unique people or image/study counts.','Only CT/CXR-related dictionary labels are included; no-match is unconfirmed rather than no imaging.','Historical occurrence audit does not establish result availability at a selected replay time.'],'files':receipts}
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(read_file,h,p,by_hospital[h]):(h,p) for h,p in jobs}
        for fut in as_completed(pending):
            receipt,found=fut.result();receipts.append(receipt)
            for eid,key,sig in found:
                if eid in events and events[eid]!=(key,sig):conflicts.add(eid)
                events.setdefault(eid,(key,sig))
            if len(receipts)%10==0 or len(receipts)==len(jobs):
                write_json(OUT/'summary.json',summary(False));print('GS_IMAGING',len(receipts),'/',len(jobs),flush=True)
    result=summary(all(r['status']=='ok' for r in receipts));write_json(OUT/'summary.json',result)
    print('GS_IMAGING_DONE',json.dumps({k:v for k,v in result.items() if k!='files'}),flush=True)
if __name__=='__main__':main()
