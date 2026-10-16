"""Select private, source-backed scenario cases from the strict GS-at-entry cohort.

Reuses the audited SERVICES reader/interval rule. Only aggregate progress is
printed; output CSV/JSON containing exact join keys stay in a private directory.
Scenario labels describe retrospective selection, never contemporaneous AI facts.
"""
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import count_gs_cohort as gs

gs.PREFIX_MODE = False  # Never inherit a previous GS* exploratory run.
SCENARIOS = {
    'cpr_start': 'cpr_during_icu',
    'death_during_icu': 'icu_death',
    'surgery_record_during_icu': 'surgery_during_icu',
    'ed_within_24h_before_icu': 'ed_within_24h_before_icu',
    'surgery_ended_before_icu_24h': 'postoperative_icu',
}


def key(row):
    return (str(row['hospital']), *(gs.ident(row.get(k)) for k in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID')))


def parts(value):
    return sorted({part.strip() for part in str(value or '').split('|') if part.strip()})


def verified_evidence(row, evidence):
    """Recheck event interval and source table; preserve only positive evidence."""
    start, end = gs.dt(row['icu_in']), gs.dt(row['icu_out'])
    result = {}
    for kind, event in evidence.items():
        if not isinstance(event, dict):
            continue
        at, table = gs.dt(event.get('at')), event.get('table')
        if not at:
            continue
        valid = (
            kind == 'ed_within_24h_before_icu' and table == 'ADMISSIONS' and start - timedelta(hours=24) <= at <= start
            or kind == 'surgery_ended_before_icu_24h' and table == 'PROCEDUREEVENTS' and start - timedelta(hours=24) <= at <= start
            or kind == 'surgery_record_during_icu' and table == 'PROCEDUREEVENTS' and start <= at < end
            or kind == 'death_during_icu' and table == 'ADMISSIONS' and start <= at < end
            or kind == 'cpr_start' and table == 'DATETIMEEVENTS' and row['hospital'] == '001'
            and event.get('item') == '001D_7284_11320' and start <= at < end
            or kind == 'operation_flag' and table == 'ICUSTAYS' and at == start
        )
        if valid:
            result[kind] = {**event, 'at': at.isoformat(),
                            'relative_minute': round((at - start).total_seconds() / 60, 3)}
    return result


def add_evidence(candidates, extraction, optional_path):
    by_key = {key(row): row for row in candidates}
    audits = []
    for hospital in gs.HOSPITALS:
        path = extraction / hospital / 'candidate_evidence.json'
        if not path.exists():
            audits.append({'hospital': hospital, 'status': 'evidence_file_missing'})
            continue
        entries = json.loads(path.read_text())
        matched = 0
        for entry in entries:
            identifiers = entry.get('key', [])
            if len(identifiers) != 3 or entry.get('hospital') != hospital:
                continue
            row = by_key.get((hospital, *(gs.ident(v) for v in identifiers)))
            if row is not None:
                row['evidence'] = verified_evidence(row, entry.get('evidence', {}))
                matched += 1
        audits.append({'hospital': hospital, 'status': 'ok', 'matched_stays': matched})
    optional = {'status': 'not_present', 'verified_cpr_stays': 0}
    if optional_path.exists():
        data = json.loads(optional_path.read_text())
        summary = data.get('summary', {})
        optional['status'] = 'read'
        # This cached extractor has a known hospital and exact join-key contract.
        if summary.get('dataset') == 'kmimic-emr-001' and str(summary.get('partition', '')).isdigit():
            for old in data.get('cases', []):
                row = by_key.get(('001', *(gs.ident(old.get(k)) for k in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID'))))
                if row is None or gs.dt(old.get('icu_in')) != gs.dt(row['icu_in']) or gs.dt(old.get('icu_out')) != gs.dt(row['icu_out']):
                    continue
                cpr = [e for e in old.get('events', []) if e.get('kind') == 'cpr_start']
                accepted = []
                for event in cpr:
                    ev = verified_evidence(row, {'cpr_start': {**event, 'partition': str(summary['partition']),
                                             'cached_source': 'surgical-scenario-extract/candidates.json'}})
                    if ev:
                        accepted.append(ev['cpr_start'])
                if accepted:
                    row.setdefault('evidence', {})['cpr_start'] = min(accepted, key=lambda e: e['at'])
                    optional['verified_cpr_stays'] += 1
        else:
            optional['status'] = 'unrecognized_source_skipped'
    for row in candidates:
        row.setdefault('evidence', {})
        row['scenario_labels'] = [SCENARIOS[kind] for kind in SCENARIOS if kind in row['evidence']]
    return audits, optional


def select_cases(candidates, limit=12):
    """Cover evidence types, then balance hospitals and reuse source partitions."""
    eligible = [row for row in candidates if row.get('scenario_labels')]
    chosen, seen, subjects, used_parts, hospital_counts = [], set(), set(), set(), Counter()

    def available():
        return [r for r in eligible if key(r) not in seen and (r['hospital'], r['SUBJECT_ID']) not in subjects]

    def rank(row):
        partitions = {(row['hospital'], p) for p in parts(row['source_partitions'])}
        # Prefer an existing coded-event partition only after hospital balance.
        useful_existing = int(('001', '268') in partitions)
        deterministic = hashlib.sha256('|'.join(key(row)).encode()).hexdigest()
        return (hospital_counts[row['hospital']], -len(partitions & used_parts),
                len(partitions - used_parts), -useful_existing, -len(row['scenario_labels']), deterministic)

    def choose(options, reason):
        if not options or len(chosen) >= limit:
            return
        row = min(options, key=rank)
        chosen.append({**row, 'selected_for': reason})
        seen.add(key(row))
        subjects.add((row['hospital'], row['SUBJECT_ID']))
        used_parts.update((row['hospital'], p) for p in parts(row['source_partitions']))
        hospital_counts[row['hospital']] += 1

    for scenario in SCENARIOS.values():
        if not any(scenario in row['scenario_labels'] for row in chosen):
            choose([r for r in available() if scenario in r['scenario_labels']], scenario)
    while len(chosen) < limit:
        options = available()
        if not options:
            break
        choose(options, 'hospital_balance_and_partition_reuse')
    for index, row in enumerate(chosen, 1):
        row['case_alias'] = f'GS-CASE-{index:03d}'
        row['dataset'] = 'kmimic-emr-' + row['hospital']
        row['source_partition_list'] = parts(row['source_partitions'])
        row['scenario_labels_retrospective'] = True
        required = defaultdict(set)
        required['ICUSTAYS'].update(row['source_partition_list'])
        required['SERVICES'].update(row['gs_entry_evidence']['source_partitions'])
        for event in row['evidence'].values():
            if event.get('partition'):
                required[event['table']].add(str(event['partition']))
        row['required_partitions'] = {table: sorted(values) for table, values in required.items()}
        preferred_kind = next((kind for kind, scenario in SCENARIOS.items() if scenario == row['selected_for']),
                              next(kind for kind in SCENARIOS if kind in row['evidence']))
        event_at = gs.dt(row['evidence'][preferred_kind]['at'])
        start, end = gs.dt(row['icu_in']), gs.dt(row['icu_out'])
        # Before death allows chart review without asserting a future outcome.
        at = max(start, event_at - timedelta(hours=1)) if preferred_kind == 'death_during_icu' else max(start, event_at)
        row['preferred_checkpoint'] = {'at': at.isoformat(), 'minute': round((at - start).total_seconds() / 60, 3),
                                       'evidence_kind': preferred_kind, 'within_icu': start <= at < end,
                                       'policy': 'Historical replay checkpoint; future selection outcomes must not enter AI context.'}
    return chosen


def private_csv(path, rows):
    fields = [name for name in rows[0] if name not in ('evidence', 'scenario_labels', 'gs_entry_evidence')]
    fields += ['gs_entry_at', 'gs_entry_code', 'gs_entry_source_partitions']
    temp = path.with_suffix('.tmp')
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            evidence = row['gs_entry_evidence']
            writer.writerow({**{k: row[k] for k in fields if k in row}, 'gs_entry_at': evidence['at'],
                             'gs_entry_code': 'GS', 'gs_entry_source_partitions': ' | '.join(evidence['source_partitions'])})
    temp.chmod(0o600)
    temp.replace(path)


def main():
    root = Path(os.getenv('KMIMIC_ROOT', '/home/khdp-user/workspace/datasets'))
    extraction = Path(os.getenv('KMIMIC_EXTRACTION', '/home/khdp-user/workspace/icu-runtime/full-kmimic-extract'))
    out = Path(os.getenv('KMIMIC_GS_SELECTION_OUT', '/home/khdp-user/workspace/icu-runtime/gs-scenario-selection'))
    optional = Path(os.getenv('KMIMIC_CPR_CANDIDATES', '/home/khdp-user/workspace/icu-runtime/surgical-scenario-extract/candidates.json'))
    expected = int(os.getenv('KMIMIC_EXPECTED_GS', '14321'))
    expected_cohort = int(os.getenv('KMIMIC_EXPECTED_COHORT', '68061'))
    expected_partitions = int(os.getenv('KMIMIC_EXPECTED_PARTITIONS', '920'))
    limit = max(8, min(16, int(os.getenv('KMIMIC_GS_CASES', '12'))))
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    with (extraction / 'surgical_icu_stays.csv').open(encoding='utf-8-sig', newline='') as handle:
        cohort = list(csv.DictReader(handle))
    if len(cohort) != expected_cohort or len({key(row) for row in cohort}) != len(cohort):
        raise ValueError('Existing surgical ICU cohort count or unique keys do not match')
    if any(row['hospital'] not in gs.HOSPITALS or not all(key(row)) or not gs.dt(row['icu_in'])
           or not gs.dt(row['icu_out']) or gs.dt(row['icu_out']) <= gs.dt(row['icu_in']) for row in cohort):
        raise ValueError('Existing cohort has invalid hospital, keys or ICU intervals')
    for row in cohort:
        for name in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID'):
            row[name] = gs.ident(row[name])
    selected_cohort, audits = [], []
    for hospital in gs.HOSPITALS:
        rows = [row for row in cohort if row['hospital'] == hospital]
        admissions = {(row['SUBJECT_ID'], row['HADM_ID']) for row in rows}
        audit = json.loads((extraction / hospital / 'audit.json').read_text())
        partitions = sorted({Path(r['file']).parent.name for r in audit['files']
                             if r['file'].endswith('/ICUSTAYS.csv') and r.get('status') == 'ok'})
        files = [root / ('kmimic-emr-' + hospital) / part / 'SERVICES.csv' for part in partitions]
        events, provenance = defaultdict(lambda: defaultdict(set)), defaultdict(set)
        invalid, receipts = set(), []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for offset in range(0, len(files), 4):
                batch = files[offset:offset + 4]
                for path, response in zip(batch, pool.map(lambda p: gs.read_services(p, admissions), batch)):
                    observed, bad, receipt = response
                    invalid.update(bad)
                    receipts.append({'partition': path.parent.name, **receipt})
                    for admission, when, code in observed:
                        events[admission][when].add(code)
                        provenance[(admission, when, code)].add(path.parent.name)
                    if len(receipts) % 10 == 0 or len(receipts) == len(files):
                        print('GS_SELECT_SCAN', hospital, len(receipts), '/', len(files), flush=True)
                gs.write_json(out / 'progress.json', {'at': gs.stamp(), 'hospital': hospital,
                              'files_read': len(receipts), 'files_total': len(files)})
        complete = bool(files) and all(receipt['status'] == 'ok' for receipt in receipts)
        matched = 0
        for row in rows:
            admission = row['SUBJECT_ID'], row['HADM_ID']
            start, end = gs.dt(row['icu_in']), gs.dt(row['icu_out'])
            if gs.classify(start, end, events.get(admission, {}), admission in invalid or not complete)['gs_at_icu_entry'] is not True:
                continue
            when = max(t for t in events[admission] if t <= start)
            selected_cohort.append({**row, 'gs_entry_evidence': {'table': 'SERVICES', 'at': when.isoformat(),
                                    'code': 'GS', 'source_partitions': sorted(provenance[(admission, when, 'GS')]),
                                    'relative_minute': round((when - start).total_seconds() / 60, 3),
                                    'rule': 'Latest nonconflicting valid CURR_SERVICE at or before ICU entry.'}})
            matched += 1
        audits.append({'hospital': hospital, 'coverage_complete': complete, 'files': receipts,
                       'source_partitions': len(partitions), 'gs_at_entry_stays': matched,
                       'invalid_service_time_admissions': len(invalid)})
        gs.write_json(out / 'scan_audit.json', {'hospitals': audits})
        print('GS_SELECT_HOSPITAL', hospital, 'matches', matched, 'complete', complete, flush=True)
    valid = (len(selected_cohort) == expected and sum(a['source_partitions'] for a in audits) == expected_partitions
             and all(a['coverage_complete'] for a in audits))
    if not valid:
        gs.write_json(out / 'validation_error.json', {'actual_gs_stays': len(selected_cohort), 'expected_gs_stays': expected,
                      'actual_partitions': sum(a['source_partitions'] for a in audits), 'expected_partitions': expected_partitions,
                      'all_hospitals_complete': all(a['coverage_complete'] for a in audits)})
        raise ValueError('Strict GS cohort count or full partition coverage mismatch; no final selection written')
    evidence_audits, cpr_audit = add_evidence(selected_cohort, extraction, optional)
    cases = select_cases(selected_cohort, limit)
    candidate_counts = Counter(scenario for row in selected_cohort for scenario in row['scenario_labels'])
    chosen_counts = Counter(scenario for row in cases for scenario in row['scenario_labels'])
    summary = {'generated_at': gs.stamp(), 'coverage_complete': True,
               'cohort_counts': {'surgical_icu_stays': len(cohort), 'gs_at_entry_stays': len(selected_cohort),
                                 'gs_distinct_hospital_subjects': len({(r['hospital'], r['SUBJECT_ID']) for r in selected_cohort}),
                                 'source_partitions': expected_partitions, 'matches_prior_strict_count': True},
               'candidate_scenarios': dict(candidate_counts), 'selected_scenarios': dict(chosen_counts),
               'selected_cases': len(cases), 'selected_hospitals': dict(Counter(r['hospital'] for r in cases)),
               'evidence_audits': evidence_audits, 'optional_cpr_audit': cpr_audit,
               'selection_policy': 'Literal GS at ICU entry only. Cover source-confirmed scenarios, then balance hospitals and reuse source partitions. No date/recency preference. Unique hospital-subject per selected case.',
               'limitations': ['ED in prior 24 hours does not establish a direct ED-to-ICU transfer.',
                              'Scenario labels are retrospective selection metadata; future events must not enter a frozen-time AI prompt.',
                              'Surgery and OP_FLAG do not establish postoperative instability.',
                              'No GW, AE, OR-death, current equipment support, discharge readiness or staff workload is inferred.',
                              'GS* aliases are excluded; this is the strict literal-GS cohort.']}
    private_csv(out / 'gs_at_entry_stays.csv', selected_cohort)
    gs.write_json(out / 'selected_cases.json', {'schema_version': 'gs-scenario-selection-v1', **summary, 'cases': cases})
    gs.write_json(out / 'summary.json', summary)
    gs.write_json(out / 'progress.json', {'at': gs.stamp(), 'status': 'finished', 'selected_cases': len(cases)})
    print('GS_SELECT_DONE', json.dumps({'gs_stays': len(selected_cohort), 'selected_cases': len(cases),
                                      'selected_hospitals': summary['selected_hospitals'], 'scenarios': dict(chosen_counts)}), flush=True)


if __name__ == '__main__':
    main()
