"""Inspect device dictionaries and selected-case source values inside KHDP.

Discovery keywords never become positive device mappings. Matched source rows
are cached mode-600 on the Pod for a subsequent reviewed mapping, not exported.
Stdout contains dictionary metadata and aggregate safe categorical counts only.
"""
import argparse
import collections
import json
import re
from pathlib import Path
import build_gs_board_pool as b

W=Path('/home/khdp-user/workspace/icu-runtime')
ROOT=W.parent/'datasets'
OUT=W/'gs-device-audit'
PATTERN=re.compile(r'ECMO|체외|CRRT|CVVH|CVVD|지속.*투석|혈액.*여과|인공호흡|ventilat|기관내|기관절개|\bETT\b|trach|foley|도뇨|중심정맥|central.?venous|\bCVC\b|\bPICC\b|arterial.?line|동맥관|a.?line|chest.?tube|흉관|배액관|\bdrain\b|hemovac|nasogastric|\bNGT\b|비위관|l.?tube|levin|\bCVP\b',re.I)
STATES={'on','off','yes','no','y','n','present','absent','in place','removed','inserted',
        '삽입','제거','유지','삽입됨','제거됨','유지 중','유지중','적용','미적용','없음','있음','유','무',
        '가동','중단','시행','미시행','true','false','none','0','1'}


def value_category(value):
    cleaned=b.norm(value)
    if cleaned in STATES:return cleaned
    numeric=b.number(value)
    if numeric is not None:return '<numeric-positive>' if numeric>0 else '<numeric-zero>' if numeric==0 else '<numeric-negative>'
    return '<other-text>' if cleaned else '<empty>'


def main(scan_values=False,hospital=None,limit=80):
    OUT.mkdir(parents=True,exist_ok=True);OUT.chmod(0o700)
    selection=json.loads((W/'gs-scenario-selection/selected_cases.json').read_text())
    pool=json.loads((W/'gs-board-pool/pool_gs.json').read_text())
    selected=[c for c in selection['cases'] if hospital is None or c['hospital']==hospital]
    poolmap={p['pid']:p for p in pool}
    dictionaries={};report={'scope':'Selected case source partitions only; discovery is not a device mapping','hospitals':{}}
    for h in sorted({c['hospital'] for c in selected}):
        parts={str(p) for c in selected if c['hospital']==h for p in c['source_partition_list']}
        found=collections.defaultdict(dict);headers=set();missing=[]
        for part in sorted(parts):
            try:
                for row in b.csv_rows(ROOT/('kmimic-emr-'+h)/part/'D_ITEMS.csv'):
                    headers.update(row)
                    iid=str(row.get('ITEMID') or '').strip()
                    searchable=' '.join(str(row.get(k) or '') for k in ('LABEL','CATEGORY','ITEMNAME','ITEM_NAME'))
                    if not iid or not (PATTERN.search(searchable) or iid in ('001C_1207_22360','001C_1093_22025')):continue
                    info={k:str(row.get(k) or '').strip() for k in ('LABEL','CATEGORY','UNITNAME','LINKSTO','ITEMNAME','ITEM_NAME')}
                    found[iid][json.dumps(info,sort_keys=True)]=info
            except Exception as error:missing.append({'partition':part,'error':type(error).__name__})
        dictionaries[h]={iid:next(iter(values.values())) for iid,values in found.items() if len(values)==1}
        candidates=[{'itemid':iid,**info} for iid,info in sorted(dictionaries[h].items())]
        report['hospitals'][h]={'partitions':sorted(parts),'headers':sorted(headers),'candidate_count':len(candidates),
                                 'conflicting_candidate_items':sum(len(v)>1 for v in found.values()),'errors':missing,
                                 'candidates':candidates}
    b.safe_write(OUT/'dictionary_candidates.json',report)
    for h,info in report['hospitals'].items():
        print('DEVICE_DICTIONARY',json.dumps({'hospital':h,**{k:v for k,v in info.items() if k!='candidates'},
              'candidates':info['candidates'][:limit]},ensure_ascii=False),flush=True)
    if not scan_values:return
    cache=[];summary=[]
    for h,items in dictionaries.items():
        cases=[c for c in selected if c['hospital']==h];targets={b.pair(c) for c in cases}
        parts=report['hospitals'][h]['partitions'];stats={};seen=set();file_receipts=[]
        for table in ('CHARTEVENTS','DATETIMEEVENTS'):
            for part in parts:
                receipt={'hospital':h,'table':table,'partition':part,'rows_in_selected_icu':0,'status':'ok'}
                try:
                    for row in b.selected_rows(ROOT/('kmimic-emr-'+h)/part/(table+'.csv'),targets,table,set(items)):
                        iid=str(row.get('ITEMID') or '').strip()
                        matching=[]
                        for c in cases:
                            if not b.own_record(row,c):continue
                            start,end=b.dt(c['icu_in']),b.dt(c['icu_out']);chart,store=b.available_times(row,start)
                            total=(end-start).total_seconds()/60
                            if chart is not None and 0<=chart<total and chart<=poolmap[c['case_alias']]['los_min']:
                                matching.append((c,chart,store))
                        if len(matching)!=1:continue
                        c,chart,store=matching[0]
                        identity=(h,table,json.dumps(row,sort_keys=True))
                        if identity in seen:continue
                        seen.add(identity);receipt['rows_in_selected_icu']+=1
                        available_reason='known' if store is not None else 'missing_storetime' if not str(row.get('STORETIME') or '').strip() else 'invalid_storetime' if b.dt(row.get('STORETIME')) is None else 'store_before_chart'
                        entry=stats.setdefault((table,iid),{'hospital':h,'table':table,'itemid':iid,**items[iid],
                                'selected_rows':0,'cases':set(),'value_categories':collections.Counter(),'units':collections.Counter(),
                                'availability':collections.Counter()})
                        entry['selected_rows']+=1;entry['cases'].add(c['case_alias'])
                        entry['value_categories'][value_category(row.get('VALUE') or row.get('VALUENUM') or '')]+=1
                        entry['units'][row.get('VALUEUOM') or items[iid].get('UNITNAME') or '<empty>']+=1
                        entry['availability'][available_reason]+=1
                        cache.append({'case_alias':c['case_alias'],'hospital':h,'partition':part,'table':table,
                                      'chart_minute':chart,'available_minute':store,'availability_reason':available_reason,
                                      'dictionary':items[iid],'row':row})
                except Exception as error:receipt.update(status='error',error=type(error).__name__)
                file_receipts.append(receipt)
                print('DEVICE_SOURCE_SCAN',json.dumps(receipt),flush=True)
        output=[]
        for item in sorted(stats.values(),key=lambda e:-e['selected_rows']):
            item={**item,'case_count':len(item['cases'])};item.pop('cases')
            output.append(item)
        summary.extend(output)
        print('DEVICE_SOURCE_VALUES',json.dumps({'hospital':h,'items_with_records':len(output),'items':output[:limit]},ensure_ascii=False),flush=True)
        b.safe_write(OUT/('files-'+h+'.json'),file_receipts)
    b.safe_write(OUT/'events.private.json',cache)
    b.safe_write(OUT/'selected_device_values.json',{'scope':'Selected historical source records; no current-attachment inference','items':summary})
    print('DEVICE_SOURCE_AUDIT_COMPLETE',json.dumps({'selected_cases':len(selected),'cached_source_rows':len(cache),'items_with_records':len(summary)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scan-values',action='store_true');parser.add_argument('--hospital');parser.add_argument('--limit',type=int,default=80)
    args=parser.parse_args();main(args.scan_values,args.hospital,args.limit)
