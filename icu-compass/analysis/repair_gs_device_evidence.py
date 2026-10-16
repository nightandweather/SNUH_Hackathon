"""Apply reviewed device mappings to the private selected-case source cache.

Never infer attachment from an order, numeric device code, an unrelated result,
or a keyword match. Unknown-availability records are kept in a separate history
collection, excluded from current device flags and frozen-time AI facts.
"""
import collections
import hashlib
import json
import shutil
from pathlib import Path
import build_gs_board_pool as b

W=Path('/home/khdp-user/workspace/icu-runtime')
OUT=W/'gs-board-pool'
AUDIT=W/'gs-device-audit'
REPAIR_VERSION='v2'
NAMES={
    'ventilator':('인공호흡기','Ventilator'),'ecmo':('ECMO','ECMO'),
    'crrt':('CRRT','CRRT'),'urinary_catheter':('유치도뇨관','Urinary catheter'),
    'central_line':('중심정맥관','Central venous catheter'),'arterial_line':('동맥관','Arterial catheter'),
    'chest_drain':('흉관','Chest drain'),'surgical_drain':('수술 배액관','Surgical drain'),
    'nasogastric_tube':('비위관','Nasogastric tube'),'endotracheal_tube':('기관내관','Endotracheal tube'),
    'tracheostomy':('기관절개관','Tracheostomy tube')}
# Existing item-specific mappings previously audited in hospital 001. Additional
# mappings must be added only after reviewing the new dictionary/value audit.
MAPPINGS={
    ('001','001C_1207_22360'):{'device_type':'ventilator','kind':'explicit_device_state','positive':{'on'},'negative':{'off'},'review':'Previously audited literal ON/OFF ventilator source item'},
    ('001','001C_1093_22025'):{'device_type':'ecmo','kind':'positive_ecmo_flow','review':'Previously audited positive ECMO flow source item'},
}
# Exact hospital/item/label pairs inspected in the selected source partitions.
# These are documentary use/maintenance-status assertions, never orders or
# numeric device identifiers. For these exports VALUE is a recorded phrase,
# despite the DATETIMEEVENTS table name; it must match the positive label exactly.
DOCUMENTED_USE = [
    ('001','001D_1404_10900','urinary_catheter','Foley catheter 통해 소변 배출되고 있음'),
    ('001','001D_3339_10925','nasogastric_tube','Levin tube 통해 배액됨'),
    ('001','001D_9567_10110','ventilator','ventilator 적용 중임'),
    ('003','003D_7323_10523_01','ventilator','ventilator 적용 중임'),
    ('003','003D_3056_10126_01','urinary_catheter','Foley catheter 유지 중임'),
    ('003','003D1_20001075_01','arterial_line','A-line(arterial line)을 통해 지속적으로 혈압 monitor중임'),
    ('006','006D_3250','surgical_drain','Jackson Pratt drain 유지 중임'),
    ('006','006D_2445','central_line','중심정맥관 유지 중임'),
    ('006','006D_2900','urinary_catheter','Foley catheter 유지 중임'),
    ('006','006D_7045','arterial_line','arterial line 유지 중임'),
    ('006','006D_9235','endotracheal_tube','기관내관 유지 중임'),
    ('006','006D_9567','ventilator','ventilator 적용 중임'),
    ('009','009D_2900','urinary_catheter','Foley catheter 유지 중임'),
    ('009','009D_2445','central_line','중심정맥관 유지 중임'),
    ('009','009D_3250','surgical_drain','Jackson Pratt drain 유지 중임'),
    ('009','009D_3338','nasogastric_tube','Levin tube 유지 중임'),
    ('009','009D_9235','endotracheal_tube','기관내관 유지 중임'),
    ('009','009D_9567','ventilator','ventilator 적용 중임'),
]
for hospital,itemid,device_type,label in DOCUMENTED_USE:
    MAPPINGS[(hospital,itemid)]={'device_type':device_type,'kind':'documented_device_use','label':label,
        'review':'Exact selected-partition DATETIMEEVENTS dictionary and VALUE both explicitly document ongoing device use; CHARTTIME is the documentation time, not insertion time'}

# Exact VALUE/label agreement was confirmed by the cache-only transition audit.
# Circuit-water removal is equipment maintenance and is deliberately excluded.
# Extubation describes the endotracheal tube only; it does not establish that all
# mechanical respiratory support or a separate ventilator was stopped.
DOCUMENTED_REMOVAL = [
    ('006','006D_7046','arterial_line','arterial line 제거함'),
    ('001','001D_7412_12340','endotracheal_tube','기관내관 발관함'),
]
for hospital,itemid,device_type,label in DOCUMENTED_REMOVAL:
    MAPPINGS[(hospital,itemid)]={'device_type':device_type,'kind':'documented_device_removal','label':label,
        'review':'Exact selected-partition DATETIMEEVENTS dictionary and VALUE both explicitly document removal of this device only; no inference about other devices or subsequent re-insertion'}

DOCUMENTARY_KINDS={'documented_device_use','documented_device_removal'}


def mapped_state(hospital,row,dictionary):
    mapping=MAPPINGS.get((hospital,str(row.get('ITEMID') or '').strip()))
    if mapping is None:return None
    raw=str(row.get('VALUE') or row.get('VALUENUM') or '').strip()
    if mapping['kind'] in DOCUMENTARY_KINDS:
        label=str(dictionary.get('LABEL') or '').split('>')[0].strip()
        expected=''.join(b.norm(mapping['label']).split())
        if ''.join(b.norm(label).split())!=expected or ''.join(b.norm(raw).split())!=expected:return None
        return {'device_type':mapping['device_type'],'evidence_kind':mapping['kind'],
                'active':mapping['kind']=='documented_device_use',
                'time_basis':'documented_chart_time'}
    if mapping['kind']=='explicit_device_state':
        text=b.norm(raw)
        if text in mapping['positive']:active=True
        elif text in mapping['negative']:active=False
        else:return None
        return {'device_type':mapping['device_type'],'evidence_kind':mapping['kind'],
                'active':active,'raw':'ON' if active else 'OFF','source_value':raw}
    value=b.number(raw)
    if value is None or value<=0:return None
    return {'device_type':mapping['device_type'],'evidence_kind':mapping['kind'],
            'active':True,'raw':raw,'value':value,
            'unit':str(row.get('VALUEUOM') or dictionary.get('UNITNAME') or '').strip()}


def extract(entry,selected,patient):
    hospital=selected['hospital'];row=entry['row']
    table=entry.get('table')
    if entry.get('hospital')!=hospital or entry.get('case_alias')!=patient['pid'] or table not in ('CHARTEVENTS','DATETIMEEVENTS'):return None
    if not b.own_record(row,selected):return None
    start,end=b.dt(selected['icu_in']),b.dt(selected['icu_out'])
    total=(end-start).total_seconds()/60
    chart,available=b.available_times(row,start)
    if chart is None or not 0<=chart<total or chart>patient['los_min']:return None
    state=mapped_state(hospital,row,entry.get('dictionary',{}))
    if state is None:return None
    documented=state['evidence_kind'] in DOCUMENTARY_KINDS
    if documented!=(table=='DATETIMEEVENTS'):return None
    event=chart if documented else None
    kind=state['device_type'];ko,en=NAMES[kind]
    source_id=str(row.get(b.EVENT_IDS[table]) or json.dumps(row,sort_keys=True))
    reference=hashlib.sha256((hospital+':'+':'.join(b.key(selected))+':'+table+':'+source_id).encode()).hexdigest()[:16]
    evidence={'chart_minute':chart,'device_type':kind,'name':en,'name_ko':ko,'name_en':en,
              'itemid':row.get('ITEMID',''),'table':table,'record_ref':reference,**state}
    if documented:evidence['event_minute']=event
    if available is not None:
        if available>=total:return None
        if documented:
            evidence.update(available_minute=available,availability_status='known',historical_only=True)
            return 'historical_only',evidence
        evidence.update(minute=available,available_minute=available,availability_status='known',historical_only=False)
        return 'current_eligible',evidence
    reason='missing_storetime' if not str(row.get('STORETIME') or '').strip() else 'invalid_storetime' if b.dt(row.get('STORETIME')) is None else 'store_before_chart'
    # Deliberately omit an available_minute: the record is not admissible as a
    # fact that was known at this replay time.
    evidence.update(availability_status='unknown',availability_reason=reason,historical_only=True)
    return 'historical_only',evidence


def merge_records(existing,new):
    unique={}
    for source in existing+new:
        record={k:v for k,v in source.items() if k!='same_time_conflict'}
        unique.setdefault(json.dumps(record,sort_keys=True),record)
    records=list(unique.values());states=collections.defaultdict(set)
    for r in records:states[(r.get('device_type'),r['chart_minute'])].add(r['active'])
    for r in records:r['same_time_conflict']=len(states[(r.get('device_type'),r['chart_minute'])])>1
    return sorted(records,key=lambda r:(r['chart_minute'],r.get('device_type',''),r.get('record_ref','')))


def run():
    selection=json.loads((W/'gs-scenario-selection/selected_cases.json').read_text())
    selected={c['case_alias']:c for c in selection['cases']}
    for hospital in {c['hospital'] for c in selected.values()}:
        receipt_path=AUDIT/('files-'+hospital+'.json')
        if not receipt_path.is_file() or any(r.get('status')!='ok' for r in json.loads(receipt_path.read_text())):
            raise ValueError('Device source audit is incomplete; no pool changes written')
    source=json.loads((AUDIT/'events.private.json').read_text())
    pool=json.loads((OUT/'pool_gs.json').read_text());patients={p['pid']:p for p in pool}
    recovered=collections.defaultdict(lambda:collections.defaultdict(list));counts=collections.Counter()
    for entry in source:
        alias=entry.get('case_alias')
        if alias not in selected or alias not in patients:continue
        result=extract(entry,selected[alias],patients[alias])
        if result is None:counts['unmapped_or_invalid_source_rows']+=1;continue
        scope,evidence=result;recovered[alias][scope].append(evidence)
        counts[scope+'_rows']+=1
    # Commit only device fields on the latest pool to retain independent repairs.
    pool=json.loads((OUT/'pool_gs.json').read_text());case_summary=[]
    for p in pool:
        changes=recovered.get(p['pid'],{})
        history=changes.get('historical_only',[])
        p['historical_device_observations']=merge_records(p.get('historical_device_observations',[]),history)
        p['historical_device_scope']={'source':'Reviewed device-specific CHARTEVENTS states/flow and DATETIMEEVENTS documented use or removal',
            'use':'Documented use/removal at CHARTTIME may be displayed in historical replay. This does not establish continuous attachment between observations. Availability is separate; these records remain excluded from current status flags and frozen-time AI.'}
        for evidence in changes.get('current_eligible',[]):
            kind=evidence['device_type'];group='ventilator' if kind=='ventilator' else 'ecmo_crrt' if kind in ('ecmo','crrt') else 'accessories'
            event=dict(evidence)
            if group=='ecmo_crrt':event['subtype']=kind
            bucket=p.setdefault('device_events',{}).setdefault(group,[])
            if event not in bucket:bucket.append(event)
        for group,events in p.get('device_events',{}).items():events.sort(key=lambda e:e['minute'])
        case_summary.append({'case':p['pid'],'historical_device_records':len(p['historical_device_observations']),
            'historical_device_types':dict(collections.Counter(e['device_type'] for e in p['historical_device_observations'])),
            'availability_valid_device_records':{g:len(v) for g,v in p.get('device_events',{}).items()}})
    backup=OUT/('pool_gs.pre-device-repair-'+REPAIR_VERSION+'.json')
    if not backup.exists():shutil.copy2(OUT/'pool_gs.json',backup)
    b.safe_write(OUT/'pool_gs.json',pool)
    report={'repair_version':REPAIR_VERSION,'scope':'Selected cases only; original GS cohort is unchanged','source_cached_rows':len(source),'counts':dict(counts),
            'reviewed_mappings':[{'hospital':h,'itemid':iid,'device_type':m['device_type'],'evidence_kind':m['kind'],'review':m['review']} for (h,iid),m in MAPPINGS.items()],
            'case_summary':case_summary,'historical_unknown_used_in_current_or_ai':False}
    b.safe_write(AUDIT/'repair_audit.json',report)
    print('GS_DEVICE_REPAIR',json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':run()
