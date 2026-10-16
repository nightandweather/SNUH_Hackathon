"""Cache-only transition discovery. No raw chart text or patient IDs on stdout.

This report proposes no new mappings and writes no patient-pool fields. Dictionary
labels are metadata; source VALUE is counted only as an exact label-phrase match,
a small explicit state vocabulary, or an undisclosed category.
"""
import argparse
import collections
import json
import re
from pathlib import Path
import build_gs_board_pool as b
import repair_gs_device_evidence as repair

W = Path('/home/khdp-user/workspace/icu-runtime')
AUDIT = W / 'gs-device-audit'
NEGATIVE = re.compile(r'제거|발관|중단|미적용|빠짐|빠져|탈관|\bOFF\b|remov|extubat|discontinu|not\s+in\s+place', re.I)
POSITIVE = re.compile(r'삽입|삽관|유지|적용|배출되고|통해\s*배액|통해.*monitor|insert|intubat|maintain|in\s+place', re.I)
ORDER = re.compile(r'예정|준비|계획|order|plan|prepar', re.I)
SAFE_STATES = {'on', 'off', 'present', 'absent', 'inserted', 'removed', 'extubated',
               'intubated', 'discontinued', 'maintained', 'in place', 'not in place',
               '있음', '없음', '삽입', '제거', '유지', '삽관', '발관', '중단',
               '삽입됨', '제거됨', '유지중', '유지 중', '적용', '미적용'}


def canonical(value):
    return ''.join(b.norm(value).split())


def phrase_class(label):
    if ORDER.search(label):
        return 'order_or_plan_candidate'
    if NEGATIVE.search(label):
        return 'removal_or_stop_candidate'
    if POSITIVE.search(label):
        return 'insertion_or_use_candidate'
    return 'other_device_metadata'


def value_class(value, label):
    text = str(value or '').strip()
    if text and canonical(text) == canonical(label.split('>')[0]):
        return 'exact_dictionary_phrase'
    normalized = b.norm(text)
    if normalized in SAFE_STATES:
        return 'explicit_state:' + normalized
    if b.dt(text) is not None:
        return 'datetime'
    if b.number(text) is not None:
        return 'numeric'
    return 'empty' if not text else 'undisclosed_text'


def accepted_time(entry, case, patient):
    if entry.get('hospital') != case['hospital'] or not b.own_record(entry['row'], case):
        return None
    start, end = b.dt(case['icu_in']), b.dt(case['icu_out'])
    chart, available = b.available_times(entry['row'], start)
    total = (end - start).total_seconds() / 60
    if chart is None or not 0 <= chart < total or chart > patient['los_min']:
        return None
    return chart, available, total


def main(limit=100):
    cached = json.loads((AUDIT / 'events.private.json').read_text())
    selected = {c['case_alias']: c for c in json.loads((W / 'gs-scenario-selection/selected_cases.json').read_text())['cases']}
    patients = {p['pid']: p for p in json.loads((W / 'gs-board-pool/pool_gs.json').read_text())}
    items = {}
    boundary = collections.Counter()
    per_case = collections.defaultdict(lambda: collections.Counter())
    for entry in cached:
        alias = entry.get('case_alias')
        if alias not in selected or alias not in patients:
            boundary['unknown_case'] += 1
            continue
        bounds = accepted_time(entry, selected[alias], patients[alias])
        if bounds is None:
            boundary['outside_own_stay_or_replay'] += 1
            continue
        chart, available, total = bounds
        boundary['accepted_chart_time'] += 1
        row = entry['row']; dictionary = entry.get('dictionary', {})
        label = str(dictionary.get('LABEL') or '')
        category = phrase_class(label)
        state = value_class(row.get('VALUE') or row.get('VALUENUM'), label)
        key = (entry['hospital'], entry['table'], row.get('ITEMID'))
        item = items.setdefault(key, {
            'hospital': key[0], 'table': key[1], 'itemid': key[2], 'label': label,
            'candidate_class': category, 'reviewed_mapping': key[::2] in repair.MAPPINGS,
            'rows': 0, 'cases': set(), 'value_classes': collections.Counter(),
            'availability': collections.Counter(), 'first_chart_minute': chart,
            'last_chart_minute': chart})
        item['rows'] += 1; item['cases'].add(alias)
        item['value_classes'][state] += 1
        availability = 'known_within_icu' if available is not None and available < total else 'store_at_or_after_exit' if available is not None else entry.get('availability_reason', 'unknown')
        item['availability'][availability] += 1
        item['first_chart_minute'] = min(item['first_chart_minute'], chart)
        item['last_chart_minute'] = max(item['last_chart_minute'], chart)
        if state == 'exact_dictionary_phrase':
            per_case[alias][category + ':exact_phrase'] += 1
    output = []
    for item in items.values():
        item['case_count'] = len(item.pop('cases'))
        output.append(item)
    priorities = {'removal_or_stop_candidate': 0, 'order_or_plan_candidate': 1,
                  'insertion_or_use_candidate': 2, 'other_device_metadata': 3}
    output.sort(key=lambda x: (priorities[x['candidate_class']], x['reviewed_mapping'], -x['rows'], x['itemid']))
    dictionary = json.loads((AUDIT / 'dictionary_candidates.json').read_text())
    unseen = []
    seen = {(h, iid) for h, _, iid in items}
    for hospital, info in dictionary['hospitals'].items():
        for item in info['candidates']:
            if (hospital, item['itemid']) not in seen and phrase_class(item.get('LABEL', '')) == 'removal_or_stop_candidate':
                unseen.append({'hospital': hospital, 'itemid': item['itemid'], 'label': item.get('LABEL', '')})
    report = {
        'scope': 'Selected private cache only; discovery candidates are not verified temporal state mappings',
        'cached_source_rows': len(cached), 'boundary_validation': dict(boundary),
        'candidate_item_count': len(output), 'items': output,
        'case_exact_phrase_counts': dict(per_case),
        'negative_dictionary_items_without_cached_rows': unseen,
        'coverage_limits': [
            'Only cached CHARTEVENTS and DATETIMEEVENTS device-keyword candidates within selected replay windows were examined',
            'A label containing only an unsearched synonym such as isolated extubation/발관 may not have been cached',
            'Absence of a removal candidate is not evidence of continuous device use',
            'A positive CHARTTIME assertion supports recorded use at that time, even when STORETIME is unknown; AI availability remains separate'
        ]}
    b.safe_write(AUDIT / 'cached_transition_audit.json', report)
    summary = {k: v for k, v in report.items() if k not in ('items', 'negative_dictionary_items_without_cached_rows')}
    summary['items'] = output[:limit]
    summary['negative_dictionary_items_without_cached_rows_count'] = len(unseen)
    summary['negative_dictionary_items_without_cached_rows'] = unseen[:30]
    print('GS_CACHED_DEVICE_TRANSITIONS', json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--limit', type=int, default=100)
    main(parser.parse_args().limit)
