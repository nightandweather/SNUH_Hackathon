"""Aggregate literal-GS service attribution within the existing surgical ICU cohort.

No patient identifiers or rows are written to output/logs. Unknown time/order,
incomplete hospital file coverage, and conflicting events prevent attribution.
"""
import csv
import json
import os
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOSPITALS = ('001', '003', '004', '005', '006', '009', '202')
CRITERIA = ('gs_at_icu_entry', 'gs_during_icu', 'exclusively_gs_whole_icu')
PREFIX_MODE = os.getenv('KMIMIC_GS_PREFIX') == '1'

def is_gs(code):
    return code.startswith('GS') if PREFIX_MODE else code == 'GS'


def ident(value):
    return re.sub(r'^([0-9]+)\.0$', r'\1', str(value or '').strip())


def dt(value):
    try:
        return datetime.fromisoformat(str(value).strip().replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def classify(start, end, events, invalid_time=False):
    """True/False/None per criterion; None means attribution is unknown."""
    unknown = dict.fromkeys(CRITERIA)
    if invalid_time or not events or not start or not end or end <= start:
        return unknown
    ordered = sorted(events.items())

    def state(codes):
        return next(iter(codes)) if len(codes) == 1 and '' not in codes else None

    prior = [codes for when, codes in ordered if when <= start]
    current = state(prior[-1]) if prior else None
    entry = None if current is None else is_gs(current)
    cursor = start
    segments = []
    for when, codes in ordered:
        if when <= start:
            continue
        if when >= end:
            break
        if when > cursor:
            segments.append(current)
        cursor, current = when, state(codes)
    if cursor < end:
        segments.append(current)
    has_gs = any(code is not None and is_gs(code) for code in segments)
    missing = None in segments
    other = any(code is not None and not is_gs(code) for code in segments)
    return {'gs_at_icu_entry': entry,
            'gs_during_icu': True if has_gs else None if missing else False,
            'exclusively_gs_whole_icu': False if other else None if missing else True}


def read_services(path, admissions):
    # Retry encoding from scratch; never include raw rows or identifiers in errors.
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            rows = Counter()
            events = []
            invalid = set()
            with path.open(encoding=encoding, newline='') as handle:
                reader = csv.DictReader(handle)
                required = {'SUBJECT_ID', 'HADM_ID', 'TRANSFERTIME', 'PREV_SERVICE', 'CURR_SERVICE'}
                if not required.issubset(reader.fieldnames or []):
                    return [], set(), {'status': 'error', 'error': 'missing_required_columns'}
                for row in reader:
                    rows['source_rows'] += 1
                    key = ident(row.get('SUBJECT_ID')), ident(row.get('HADM_ID'))
                    if key not in admissions:
                        continue
                    rows['matched_rows'] += 1
                    when = dt(row.get('TRANSFERTIME'))
                    code = str(row.get('CURR_SERVICE') or '').strip()
                    if code == 'GS':
                        rows['matched_literal_gs_rows'] += 1
                    if when is None:
                        invalid.add(key)
                        rows['matched_invalid_time_rows'] += 1
                    else:
                        events.append((key, when, code))
            return events, invalid, {'status': 'ok', 'encoding': encoding, **rows}
        except UnicodeDecodeError:
            if encoding == 'cp949':
                return [], set(), {'status': 'error', 'error': 'UnicodeDecodeError'}
        except (OSError, csv.Error) as error:
            return [], set(), {'status': 'error', 'error': type(error).__name__}


def count(rows, event_map, invalid, coverage_complete):
    result = {'icu_stays': len(rows), 'distinct_hospital_subjects': len({r['subject'] for r in rows}),
              'unlinked_stays': 0, 'invalid_service_time_stays': 0,
              'excluded_incomplete_coverage_stays': 0, 'criteria': {}}
    states = {key: {True: [], False: [], None: []} for key in CRITERIA}
    for row in rows:
        key = row['subject'], row['admission']
        events = event_map.get(key, {})
        if not events and key not in invalid:
            result['unlinked_stays'] += 1
        if key in invalid:
            result['invalid_service_time_stays'] += 1
        if not coverage_complete:
            result['excluded_incomplete_coverage_stays'] += 1
        values = classify(row['start'], row['end'], events, key in invalid or not coverage_complete)
        for criterion, value in values.items():
            states[criterion][value].append(row['subject'])
    for criterion in CRITERIA:
        result['criteria'][criterion] = {
            label: {'icu_stays': len(states[criterion][value]),
                    'distinct_hospital_subjects': len(set(states[criterion][value]))}
            for label, value in (('yes', True), ('no', False), ('unknown', None))}
    return result


def main():
    root = Path(os.getenv('KMIMIC_ROOT', '/home/khdp-user/workspace/datasets'))
    cohort = Path(os.getenv('KMIMIC_COHORT', '/home/khdp-user/workspace/icu-runtime/full-kmimic-extract/surgical_icu_stays.csv'))
    out = Path(os.getenv('KMIMIC_GS_OUT', '/home/khdp-user/workspace/icu-runtime/gs-cohort-count'))
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    by_hospital = defaultdict(list)
    keys = set()
    with cohort.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            hospital = str(row['hospital']).strip()
            subject, admission, stay = (ident(row.get(k)) for k in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID'))
            key = hospital, subject, admission, stay
            if hospital not in HOSPITALS or not all(key) or key in keys:
                raise ValueError('Cohort contains unknown hospital, missing key, or duplicate ICU stay')
            start, end = dt(row.get('icu_in')), dt(row.get('icu_out'))
            if not start or not end or end <= start:
                raise ValueError('Cohort contains invalid ICU interval')
            keys.add(key)
            by_hospital[hospital].append({'subject': subject, 'admission': admission, 'start': start, 'end': end})
    report = {'started_at': stamp(), 'cohort_icu_stays': len(keys), 'expected_existing_cohort_stays': 68061,
              'matches_expected_cohort': len(keys) == 68061, 'service_code': 'GS* (prefix candidates)' if PREFIX_MODE else 'GS',
              'definition': ('Trimmed CURR_SERVICE starts with GS; unvalidated code-family candidate count, NOT verified general-surgery mapping.' if PREFIX_MODE else 'Exact trimmed CURR_SERVICE GS; no inferred hospital-specific code expansion.'),
              'interval_policy': 'Service persists from TRANSFERTIME until next event; last event persists to ICU exit. Half-open intervals. Conflicting same-time codes are unknown until next event. Any linked invalid timestamp excludes entire admission.',
              'limitations': ['Counts represent stays in the existing surgical ICU cohort, not all GS admissions.',
                             'GS code meaning has not been verified in each hospital service vocabulary.',
                             'Distinct subjects are hospital-scoped; no cross-hospital identity linkage.',
                             'Subjects may appear in multiple yes/no/unknown categories across different ICU stays.',
                             'Missing/error service partitions make all attribution in that hospital unknown.'],
              'hospitals': []}
    write_json(out / 'summary.json', report)
    for hospital in HOSPITALS:
        directory = root / ('kmimic-emr-' + hospital)
        prior_audit = cohort.parent / hospital / 'audit.json'
        if prior_audit.exists():
            audited = json.loads(prior_audit.read_text())
            expected = {Path(r['file']).parent.name for r in audited['files']
                        if r['file'].endswith('/ICUSTAYS.csv') and r.get('status') == 'ok'}
            files = sorted(directory / part / 'SERVICES.csv' for part in expected)
            inventory_source = 'Existing complete core extraction ICUSTAYS partition audit; no NFS directory/stat scan'
        else:
            expected = {p.parent.name for p in directory.glob('*/ICUSTAYS.csv')}
            files = sorted(directory.glob('*/SERVICES.csv'))
            inventory_source = 'Mounted ICUSTAYS/SERVICES partition listing'
        found = {p.parent.name for p in files}
        admissions = {(r['subject'], r['admission']) for r in by_hospital[hospital]}
        event_map = defaultdict(lambda: defaultdict(set))
        invalid = set()
        receipts = []
        duplicates = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            for offset in range(0, len(files), 4):
                batch = files[offset:offset + 4]
                for path, response in zip(batch, pool.map(lambda p: read_services(p, admissions), batch)):
                    events, bad, receipt = response
                    receipts.append({'partition': path.parent.name, **receipt})
                    invalid.update(bad)
                    for key, when, code in events:
                        if code in event_map[key][when]:
                            duplicates += 1
                        event_map[key][when].add(code)
                    if len(receipts) % 10 == 0 or len(receipts) == len(files):
                        print('GS_SCAN', hospital, len(receipts), '/', len(files), flush=True)
                write_json(out / 'progress.json', {'at': stamp(), 'hospital': hospital,
                           'files_read': len(receipts), 'files_total': len(files)})
        missing = (expected - found) | {r['partition'] for r in receipts if r.get('error') == 'FileNotFoundError'}
        complete = bool(expected) and not missing and all(r['status'] == 'ok' for r in receipts)
        audit = {'hospital': hospital, 'icu_partitions': len(expected), 'service_files': len(files),
                 'missing_partitions': sorted(missing), 'inventory_source': inventory_source,
                 'extra_service_partitions': sorted(found - expected) if not prior_audit.exists() else 'not_enumerated_outside_existing_icu_partitions',
                 'coverage_complete': complete, 'duplicate_time_code_events': duplicates,
                 'conflicting_timestamps': sum(len(codes) > 1 for events in event_map.values() for codes in events.values()),
                 'invalid_time_admissions': len(invalid), 'files': receipts,
                 'counts': count(by_hospital[hospital], event_map, invalid, complete)}
        report['hospitals'].append(audit)
        write_json(out / 'summary.json', report)
        print('GS_HOSPITAL_DONE', hospital, 'coverage_complete', complete, 'cohort_stays', len(by_hospital[hospital]), flush=True)
    report['totals'] = {'criteria': {}}
    for criterion in CRITERIA:
        report['totals']['criteria'][criterion] = {
            label: {metric: sum(h['counts']['criteria'][criterion][label][metric] for h in report['hospitals'])
                    for metric in ('icu_stays', 'distinct_hospital_subjects')}
            for label in ('yes', 'no', 'unknown')}
    for metric in ('icu_stays', 'distinct_hospital_subjects', 'unlinked_stays',
                   'invalid_service_time_stays', 'excluded_incomplete_coverage_stays'):
        report['totals'][metric] = sum(h['counts'][metric] for h in report['hospitals'])
    report['finished_at'] = stamp()
    report['complete'] = all(h['coverage_complete'] for h in report['hospitals'])
    write_json(out / 'summary.json', report)
    write_json(out / 'progress.json', {'at': stamp(), 'status': 'finished', 'complete': report['complete']})
    print('GS_DONE', json.dumps({'complete': report['complete'], 'cohort_stays': len(keys), 'totals': report['totals']}), flush=True)


if __name__ == '__main__':
    main()
