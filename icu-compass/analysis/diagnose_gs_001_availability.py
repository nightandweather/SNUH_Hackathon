"""Count why selected hospital-001 observations are unavailable; no row values."""
import argparse
import collections
import hashlib
import json
import shutil
from pathlib import Path
import build_gs_board_pool as b

W=Path('/home/khdp-user/workspace/icu-runtime')
ROOT=W.parent/'datasets'
OUT=W/'gs-board-pool'


def main(rescan=False, recover_historical=False):
    pool=json.loads((OUT/'pool_gs.json').read_text())
    cases=[p for p in pool if p['provenance']['source_identity']['hospital']=='001']
    report={'hospital':'001','selected_cases':len(cases),'source_partition_scope_only':True,
            'cases':[{'case':p['pid'],'vital_observations':len(p['raw_observations']),
                      'rejections':p['provenance'].get('rejected_record_counts',{}),
                      'nonmissing_replay_values':{k:sum(v is not None for v in values) for k,values in p['series'].items()},
                      'device_records':{k:len(v) for k,v in p.get('device_events',{}).items()}}
                     for p in cases]}
    if rescan:
        selection=json.loads((W/'gs-scenario-selection/selected_cases.json').read_text())
        selected=[c for c in selection['cases'] if c['hospital']=='001']
        targets={b.pair(c) for c in selected}
        parts={part for c in selected for part in c['source_partition_list']}
        pbykey={b.key(p['provenance']['source_identity']):p for p in cases}
        receipts={}
        items=b.vocabulary(ROOT,'001','D_ITEMS',parts,receipts)
        mapping=b.item_map('001',items)
        wanted=set(mapping)|{'001C_1207_22360','001C_1093_22025'}
        counts=collections.Counter()
        bycase={c['case_alias']:collections.Counter() for c in selected}
        historical={c['case_alias']:{} for c in selected}
        for part in sorted(parts):
            for row in b.selected_rows(ROOT/'kmimic-emr-001'/part/'CHARTEVENTS.csv',targets,'CHARTEVENTS',wanted):
                counts['matched_admission_rows']+=1
                own=[c for c in selected if b.own_record(row,c)]
                if not own:counts['different_explicit_stay']+=1
                for c in own:
                    stats=bycase[c['case_alias']];stats['own_stay_rows']+=1
                    p=pbykey[b.key(c)];start=b.dt(c['icu_in']);total=(b.dt(c['icu_out'])-start).total_seconds()/60
                    chart,store=b.available_times(row,start)
                    if chart is None:stats['invalid_chart_time']+=1;continue
                    if chart<0:stats['chart_before_icu']+=1;continue
                    if chart>=total:stats['chart_at_or_after_icu_exit']+=1;continue
                    if chart>p['los_min']:stats['chart_after_selected_replay_window']+=1;continue
                    stats['chart_inside_replay']+=1
                    iid=row.get('ITEMID','');var=mapping.get(iid)
                    value=b.number(row.get('VALUENUM') or row.get('VALUE'))
                    unit=row.get('VALUEUOM') or items.get(iid,{}).get('UNITNAME','')
                    valid_vital=(var is not None and value is not None and b.norm(unit) in b.UNITS[var]
                                 and b.LIMITS[var][0]<=value<=b.LIMITS[var][1])
                    reason=None
                    if not str(row.get('STORETIME') or '').strip():reason='missing_storetime';stats['storetime_blank']+=1
                    if store is None:
                        raw_store=b.relative(row.get('STORETIME'),start)
                        if reason is None:
                            reason='store_before_chart' if raw_store is not None else 'invalid_storetime'
                            stats['store_before_chart' if raw_store is not None else 'storetime_unparseable']+=1
                        if valid_vital:
                            ref='001:'+':'.join(b.key(c))+':'+(row.get('CHARTEVENT_ID') or json.dumps(row,sort_keys=True))
                            record={'chart_minute':chart,'variable':var,'value':value,
                                    'unit':{'hr':'bpm','map':'mmHg','spo2':'%','rr':'/min','sbp':'mmHg'}[var],
                                    'source_unit':unit,'itemid':iid,
                                    'table':'CHARTEVENTS','availability_status':'unknown','availability_reason':reason,
                                    'historical_only':True,'record_ref':hashlib.sha256(ref.encode()).hexdigest()[:16]}
                            historical[c['case_alias']].setdefault(json.dumps(record,sort_keys=True),record)
                            stats['valid_retrospective_vital_rows']+=1
                        continue
                    if store>=total:stats['store_at_or_after_icu_exit']+=1;continue
                    stats['chart_and_availability_valid']+=1
                    if var:
                        if b.norm(unit) not in b.UNITS[var]:stats['vital_unit_unverified']+=1
                        elif value is None or not b.LIMITS[var][0]<=value<=b.LIMITS[var][1]:stats['vital_value_invalid']+=1
                        else:stats['valid_vital_source_rows']+=1
        report['targeted_rescan']={'aggregate':dict(counts),'cases':{k:dict(v) for k,v in bycase.items()}}
        if recover_historical:
            # Reload at commit time so independently repaired labs/procedures are
            # retained. Only this separate, explicitly retrospective field changes.
            latest=json.loads((OUT/'pool_gs.json').read_text())
            repaired=[]
            for p in latest:
                if p['pid'] not in historical:continue
                records=list(historical[p['pid']].values())
                same_time=collections.defaultdict(set)
                for r in records:same_time[(r['variable'],r['chart_minute'])].add((r['value'],r['unit']))
                for r in records:r['same_time_conflict']=len(same_time[(r['variable'],r['chart_minute'])])>1
                p['historical_vital_observations']=sorted(records,key=lambda r:(r['chart_minute'],r['variable'],r['record_ref']))
                p['historical_vital_scope']={'source':'K-MIMIC CHARTEVENTS','time_basis':'CHARTTIME only; record availability unknown',
                    'use':'Retrospective source review only. Excluded from current vitals, care indicators, transfer colors and frozen-time AI.',
                    'source_partitions_only':True,'icu_interval_policy':'0 <= CHARTTIME-relative minute < actual ICU length of stay'}
                repaired.append({'case':p['pid'],'historical_vital_rows':len(records),
                                 'same_time_conflict_rows':sum(r['same_time_conflict'] for r in records)})
            backup=OUT/'pool_gs.pre-historical-vitals.json'
            if not backup.exists():shutil.copy2(OUT/'pool_gs.json',backup)
            b.safe_write(OUT/'pool_gs.json',latest)
            report['historical_recovery']={'cases':repaired,'series_or_ai_facts_modified':False}
    b.safe_write(OUT/'hospital001_availability_diagnostic.json',report)
    print('GS_001_AVAILABILITY',json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rescan',action='store_true');parser.add_argument('--recover-historical',action='store_true')
    args=parser.parse_args();main(args.rescan or args.recover_historical,args.recover_historical)
