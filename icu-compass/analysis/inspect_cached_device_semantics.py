"""Cached source semantics only: no second dataset scan and no raw row output."""
import collections
import json
from pathlib import Path
import build_gs_board_pool as b
import repair_gs_device_evidence as device

W=Path('/home/khdp-user/workspace/icu-runtime')
AUDIT=W/'gs-device-audit'
ITEMS={'001D_1404_10900','001D_3339_10925','001D_9567_10110','001D_8201_10225',
       '001C_1564_24505','001C_1088_20245','001C_1966_24290','001C_1087_20250',
       '003D_7323_10523_01','003D_3056_10126_01','003D1_20001075_01',
       '006D_3250','006D_2445','006D_2900','006D_7045','006D_9235','006D_9567',
       '009D_2900','009D_2445','009D_3250','009D_3338','009D_9235','009D_9567'}
# Only known generic device-site/state vocabulary may be printed. Other values
# remain private and are counted without their actual contents.
SITE_WORDS={'rt','lt','right','left','radial','femoral','brachial','jugular','subclavian','ijv','scv','r','l',
            'naris','nostril','nose','oral','nasal','bilateral','intact','good','normal','patent',
            '우측','좌측','양측','우','좌','비강','비공','코','경정맥','쇄골하','쇄골하정맥','요골동맥','대퇴동맥',
            '양호','정상','유지','고정','있음','없음','제거','삽입','관찰','개방','작동','통과','무','유'}


def safe_categorical(value):
    text=b.norm(value)
    tokens=[s for s in __import__('re').split(r'[\s./_()\-]+',text) if s]
    return text if tokens and all(t in SITE_WORDS for t in tokens) else '<unclassified-text>'


def main():
    cached=json.loads((AUDIT/'events.private.json').read_text())
    selected={c['case_alias']:c for c in json.loads((W/'gs-scenario-selection/selected_cases.json').read_text())['cases']}
    report={}
    for entry in cached:
        row=entry['row'];iid=row.get('ITEMID')
        if iid not in ITEMS:continue
        item=report.setdefault(iid,{'table':entry['table'],'label':entry['dictionary'].get('LABEL',''),
                                   'rows':0,'value_types':collections.Counter(),'time_relations':collections.Counter(),
                                   'safe_categorical_values':collections.Counter(),'units':collections.Counter(),
                                   'positive_phrase_matches':collections.Counter()})
        item['rows']+=1
        value=str(row.get('VALUE') or row.get('VALUENUM') or '').strip();when=b.dt(value)
        mapping=device.MAPPINGS.get((entry['hospital'],iid),{})
        if mapping.get('kind')=='documented_device_use':
            expected=''.join(b.norm(mapping['label']).split())
            label=''.join(b.norm(entry['dictionary'].get('LABEL','').split('>')[0]).split())
            matches=(''.join(b.norm(value).split())==expected and label==expected)
            item['positive_phrase_matches']['exact_value_and_label' if matches else 'not_exact']+=1
        if when:
            item['value_types']['parseable_datetime']+=1
            c=selected[entry['case_alias']];start,end=b.dt(c['icu_in']),b.dt(c['icu_out'])
            chart,store=b.dt(row.get('CHARTTIME')),b.dt(row.get('STORETIME'))
            item['time_relations']['event_in_icu' if start<=when<end else 'event_outside_icu']+=1
            if chart:item['time_relations']['event_at_or_before_chart' if when<=chart else 'event_after_chart']+=1
            if store:item['time_relations']['event_at_or_before_store' if when<=store else 'event_after_store']+=1
        elif b.number(value) is not None:item['value_types']['numeric']+=1
        else:
            item['value_types']['categorical_or_text']+=1
            item['safe_categorical_values'][safe_categorical(value)]+=1
        item['units'][row.get('VALUEUOM') or entry['dictionary'].get('UNITNAME') or '<empty>']+=1
    b.safe_write(AUDIT/'reviewed_item_semantics.json',report)
    print('GS_DEVICE_CACHED_SEMANTICS',json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
