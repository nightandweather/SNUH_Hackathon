"""Build private, source-bounded board cases from the audited literal-GS selection.

Run inside KHDP. Identifiers and source rows are written only to mode-600 private
pool files; console/progress output contains counts and source partition names.
The cohort selection is complete, while clinical observations are deliberately
limited to selected source partitions. Missing records never mean treatment absent.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

VITALS = ('hr', 'map', 'spo2', 'rr', 'sbp')
KNOWN_001 = {'001C_1021_25105': 'hr', '001C_1014_27095': 'map',
             '001C_1017_27095': 'map', '001C_1003_24480': 'spo2',
             '001C_1023_27310': 'rr', '001C_1012_24795': 'sbp',
             '001C_1015_24795': 'sbp'}
LABELS = {
    'hr': {'heart rate', 'hr', '심박수', '맥박수'},
    'map': {'mean arterial pressure', 'mean blood pressure', 'map', '평균동맥압'},
    'spo2': {'spo2', 'spo₂', '산소포화도'},
    'rr': {'respiratory rate', 'rr', '호흡수'},
    'sbp': {'systolic blood pressure', 'systolic arterial pressure', 'sbp', '수축기혈압'},
}
UNITS = {'hr': {'회/min', 'bpm', '/min', 'beats/min'}, 'map': {'mmhg'},
         'spo2': {'%'}, 'rr': {'회/min', '/min', 'breaths/min'}, 'sbp': {'mmhg'}}
LIMITS = {'hr': (1, 300), 'map': (1, 250), 'spo2': (1, 100), 'rr': (1, 100), 'sbp': (1, 300)}
# These exact device labels still require an explicit categorical state. A label
# mentioning a catheter, line site, drainage amount, or procedure is not enough.
ACCESSORY_LABELS = {'foley catheter': 'urinary_catheter', 'urinary catheter': 'urinary_catheter',
                    '유치도뇨관': 'urinary_catheter', 'central venous catheter': 'central_line',
                    '중심정맥관': 'central_line', 'arterial catheter': 'arterial_line',
                    '동맥관': 'arterial_line', 'chest tube': 'chest_drain',
                    '흉관': 'chest_drain', 'nasogastric tube': 'nasogastric_tube',
                    '비위관': 'nasogastric_tube'}
ON = {'on', 'present', 'in place', '삽입됨', '유지 중', '유지중'}
OFF = {'off', 'absent', 'removed', '제거됨'}
EVENT_IDS = {'CHARTEVENTS': 'CHARTEVENT_ID', 'DATETIMEEVENTS': 'DATETIMEEVENT_ID',
             'LABEVENTS': 'LABEVENT_ID', 'TESTEVENTS': 'TESTEVENT_ID',
             'PROCEDUREEVENTS': 'PROCEDUREEVENT_ID'}


def ident(value):
    return re.sub(r'^([0-9]+)\.0$', r'\1', str(value or '').strip())


def dt(value):
    try:
        return datetime.fromisoformat(str(value).strip().replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def norm(value):
    return ' '.join(str(value or '').strip().lower().split())


def pair(row):
    return tuple(ident(row.get(k)) for k in ('SUBJECT_ID', 'HADM_ID'))


def key(row):
    return pair(row) + (ident(row.get('STAY_ID')),)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def safe_write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def csv_rows(path):
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            with path.open(encoding=encoding, newline='') as stream:
                reader=csv.DictReader(stream)
                reader.fieldnames=[name.lstrip('\ufeff').strip() for name in (reader.fieldnames or [])]
                yield from reader
            return
        except UnicodeDecodeError:
            # Encoding retry would otherwise duplicate already emitted rows. The
            # caller deduplicates exact records and quarantines conflicts.
            if encoding == 'cp949':
                raise


def selected_rows(path, targets, table, itemids=None):
    """DuckDB streams the large CSV while retaining only selected admissions."""
    try:
        import duckdb
    except ImportError:
        for row in csv_rows(path):
            if pair(row) in targets and (itemids is None or row.get('ITEMID') in itemids):
                yield row
        return
    con = duckdb.connect()
    try:
        con.execute("SET threads=2")
        con.execute("SET memory_limit='1GB'")
        con.execute('CREATE TABLE selected(subject VARCHAR, admission VARCHAR)')
        con.executemany('INSERT INTO selected VALUES (?,?)', sorted(targets))
        condition = ''
        if itemids is not None:
            if not itemids:
                return
            con.execute('CREATE TABLE selected_items(itemid VARCHAR)')
            con.executemany('INSERT INTO selected_items VALUES (?)', [(x,) for x in sorted(itemids)])
            condition = ' JOIN selected_items i ON e.ITEMID=i.itemid'
        cursor = con.execute('SELECT e.* FROM read_csv(?, header=true, all_varchar=true) e '
                             'JOIN selected t ON regexp_replace(trim(e.SUBJECT_ID), \'\\.0$\', \'\')=t.subject '
                             'AND regexp_replace(trim(e.HADM_ID), \'\\.0$\', \'\')=t.admission' + condition, [str(path)])
        names = [c[0].lstrip('\ufeff').strip() for c in cursor.description]
        while True:
            batch = cursor.fetchmany(10000)
            if not batch:
                break
            for values in batch:
                yield {k: v or '' for k, v in zip(names, values)}
    except Exception:
        # Some hospital exports use CP949. The Python reader retries with the
        # documented alternate encoding; scan() deduplicates any earlier rows.
        for row in csv_rows(path):
            if pair(row) in targets and (itemids is None or row.get('ITEMID') in itemids):
                yield row
    finally:
        con.close()


def scan(root, hospital, table, partitions, targets, audit, itemids=None):
    rows, conflicts, receipts = {}, set(), []
    for part in sorted(partitions):
        path = root / ('kmimic-emr-' + hospital) / part / (table + '.csv')
        receipt = {'partition': part, 'matching_rows': 0, 'status': 'ok'}
        try:
            for raw in selected_rows(path, targets, table, itemids):
                row = {k: str(v or '').strip() for k, v in raw.items()}
                for field in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID'):
                    if field in row:
                        row[field] = ident(row[field])
                receipt['matching_rows'] += 1
                eid = row.get(EVENT_IDS.get(table, ''))
                if table == 'ADMISSIONS':
                    identity = pair(row)
                elif table == 'DIAGNOSES_ICD':
                    identity = pair(row) + tuple(row.get(k, '') for k in ('SEQ_NUM', 'ICD_CODE', 'ICD_VERSION', 'ITEMID'))
                elif eid:
                    identity = pair(row) + (eid,)
                else:
                    identity = (json.dumps(row, sort_keys=True),)
                if identity in rows and rows[identity] != row:
                    conflicts.add(identity)
                rows.setdefault(identity, row)
        except Exception as error:
            receipt.update(status='error', error=type(error).__name__)
        receipts.append(receipt)
        print('GS_POOL_SCAN', hospital, table, part, receipt['status'], receipt['matching_rows'], flush=True)
    audit[table] = {'scope': 'selected source partitions only', 'partitions': len(partitions),
                    'files': receipts, 'complete_for_selected_partition_set': all(r['status'] == 'ok' for r in receipts),
                    'matching_unique_rows': len(rows) - len(conflicts), 'conflicts': len(conflicts)}
    return [row for identity, row in rows.items() if identity not in conflicts]


def vocabulary(root, hospital, table, partitions, audit):
    rows, conflicts, missing = {}, set(), 0
    for part in sorted(partitions):
        try:
            for row in csv_rows(root / ('kmimic-emr-' + hospital) / part / (table + '.csv')):
                iid = str(row.get('ITEMID') or '').strip()
                if not iid:
                    continue
                # Differences in irrelevant administrative fields do not justify
                # conflicting clinical labels, units, or categories.
                info = {k: str(row.get(k) or '').strip() for k in ('LABEL', 'UNITNAME', 'CATEGORY')}
                if iid in rows and rows[iid] != info:
                    conflicts.add(iid)
                rows.setdefault(iid, info)
        except (OSError, UnicodeDecodeError, csv.Error):
            missing += 1
    audit[table] = {'partitions': len(partitions), 'missing_or_unreadable': missing, 'conflicting_items': len(conflicts)}
    return {iid: row for iid, row in rows.items() if iid not in conflicts}


def item_map(hospital, items):
    result = {}
    for iid, row in items.items():
        variable = KNOWN_001.get(iid) if hospital == '001' else None
        if variable is None:
            variable = next((v for v, names in LABELS.items() if norm(row.get('LABEL')) in names), None)
        if variable:
            result[iid] = variable
    # Verified codes may be used with an explicit observation unit even if a
    # dictionary row is absent; dictionary units are never invented.
    if hospital == '001':
        result.update(KNOWN_001)
    return result


def relative(value, start):
    point = dt(value)
    return round((point - start).total_seconds() / 60, 3) if point else None


def available_times(row, start):
    chart, store = relative(row.get('CHARTTIME'), start), relative(row.get('STORETIME'), start)
    return (chart, store) if chart is not None and store is not None and chart <= store else (chart, None)


def resample(observations, duration, step, actual_los=None):
    # A replay cap may be sampled inclusively, but actual ICU exit is exclusive.
    # Never round a 61-minute stay upward to a fictitious minute-65 observation.
    actual_los = duration if actual_los is None else actual_los
    if not 0 < actual_los or duration < 0 or step <= 0:
        raise ValueError('Invalid replay duration')
    n = int(math.floor(duration / step)) + 1
    while n > 0 and (n - 1) * step >= actual_los:
        n -= 1
    n = max(1, n)
    series, ages = {}, {}
    for variable in VITALS:
        points = sorted((r['available_minute'], r['chart_minute'], r['value']) for r in observations if r['variable'] == variable)
        values, age_values, known, cursor = [], [], {}, 0
        for i in range(n):
            minute = i * step
            while cursor < len(points) and points[cursor][0] <= minute:
                _, chart, value = points[cursor]
                known.setdefault(chart, set()).add(value)
                cursor += 1
            chart = max(known) if known else None
            fresh = chart is not None and 0 <= minute - chart <= 30 and len(known[chart]) == 1
            values.append(round(next(iter(known[chart])), 2) if fresh else None)
            age_values.append(round(minute - chart, 3) if fresh else None)
        series[variable], ages[variable] = values, age_values
    return series, ages


def own_record(row, selected):
    return pair(row) == pair(selected) and (not ident(row.get('STAY_ID')) or ident(row.get('STAY_ID')) == ident(selected['STAY_ID']))


def build_case(selected, tables, dictionaries, mapping, table_audit, cohort_count):
    hospital = str(selected['hospital'])
    start, end = dt(selected['icu_in']), dt(selected['icu_out'])
    entry = selected['gs_entry_evidence']
    if not start or not end or end <= start or entry.get('code') != 'GS' or not dt(entry.get('at')) or dt(entry['at']) > start:
        raise ValueError('Invalid strict-GS selection provenance')
    total = (end - start).total_seconds() / 60
    checkpoint = number(selected.get('preferred_checkpoint', {}).get('minute'))
    checkpoint = max(0, min(total, checkpoint if checkpoint is not None else 0))
    duration = min(total, max(1440, checkpoint + 60))
    # Preserve the important timepoint while bounding large JSONs for long stays.
    step = max(5, 5 * math.ceil(duration / (5 * 2016)))
    observations, devices, procedures = [], collections.defaultdict(list), []
    rejected = collections.Counter()
    for row in tables.get('CHARTEVENTS', []):
        if not own_record(row, selected):
            continue
        chart, store = available_times(row, start)
        if chart is None or not (0 <= chart <= duration and chart < total):
            continue
        if store is None or store >= total:
            rejected['chart_availability_unknown'] += 1
            continue
        iid = row.get('ITEMID', '')
        raw = row.get('VALUE') or row.get('VALUENUM') or ''
        info = dictionaries['D_ITEMS'].get(iid, {})
        unit = row.get('VALUEUOM') or info.get('UNITNAME', '')
        variable = mapping.get(iid)
        if variable:
            value = number(row.get('VALUENUM') or raw)
            if value is not None and norm(unit) in UNITS[variable] and LIMITS[variable][0] <= value <= LIMITS[variable][1]:
                observations.append({'minute': store, 'chart_minute': chart, 'available_minute': store,
                                     'variable': variable, 'itemid': iid, 'value': value, 'unit': unit, 'table': 'CHARTEVENTS'})
            else:
                rejected['vital_value_or_unit_unverified'] += 1
        base = {'minute': store, 'chart_minute': chart, 'available_minute': store, 'raw': raw,
                'itemid': iid, 'table': 'CHARTEVENTS'}
        if hospital == '001' and iid == '001C_1207_22360' and str(raw).upper() in ('ON', 'OFF'):
            devices['ventilator'].append({**base, 'raw': str(raw).upper(), 'active': str(raw).upper() == 'ON'})
        if hospital == '001' and iid == '001C_1093_22025' and number(raw) is not None and number(raw) > 0:
            devices['ecmo_crrt'].append({**base, 'subtype': 'ecmo', 'value': number(raw), 'unit': unit,
                                       'active': True, 'evidence_kind': 'positive_ecmo_flow'})
        accessory = ACCESSORY_LABELS.get(norm(info.get('LABEL')))
        if accessory and norm(raw) in ON | OFF:
            devices['accessories'].append({**base, 'name': info['LABEL'], 'device_type': accessory,
                                          'active': norm(raw) in ON, 'evidence_kind': 'explicit_device_state'})
    for row in tables.get('DATETIMEEVENTS', []):
        if hospital != '001' or not own_record(row, selected) or row.get('ITEMID') != '001D_7284_11320':
            continue
        chart, store = available_times(row, start)
        raw = row.get('VALUE', '')
        event = chart if raw == '심폐소생술 시작함' else relative(raw, start)
        if (chart is None or store is None or event is None or
                not (0 <= event <= duration and event < total and chart < total and store < total) or event > store):
            rejected['cpr_unknown_or_invalid_time'] += 1
            continue
        devices['cpr'].append({'minute': store, 'chart_minute': chart, 'available_minute': store,
                               'event_minute': event, 'active': True, 'raw': raw, 'itemid': row['ITEMID'],
                               'table': 'DATETIMEEVENTS', 'evidence_kind': 'cpr_start_record'})
    for row in tables.get('PROCEDUREEVENTS', []):
        if not own_record(row, selected):
            continue
        a, b = relative(row.get('STARTTIME'), start), relative(row.get('ENDTIME'), start)
        if a is not None and b is not None and 0 <= a <= b <= duration:
            available = relative(row.get('STORETIME'), start)
            procedures.append({'start_min': a, 'end_min': b, 'itemid': row.get('ITEMID', ''),
                               'category': row.get('ORDERCATEGORYNAME', ''), 'table': 'PROCEDUREEVENTS',
                               'available_minute': available if available is not None and available >= b else None})
    admissions = [row for row in tables.get('ADMISSIONS', []) if pair(row) == pair(selected)]
    admission = admissions[0] if len(admissions) == 1 else {}
    admit_minute = relative(admission.get('ADMITTIME'), start)
    if admit_minute is not None and admit_minute > 0:
        admit_minute = None
    clinical = {'status': 'linked', 'hospital': hospital,
                'admission': {'admit_minute': admit_minute, 'admission_type': admission.get('ADMISSION_TYPE', ''),
                              'admission_location': admission.get('ADMISSION_LOCATION', ''), 'table': 'ADMISSIONS',
                              'summary_type': 'Selected structured source fields; original admission narrative not linked'},
                'current_diagnoses': [], 'past_diagnoses': [], 'labs': [], 'imaging_tests': [],
                'coverage': {'scope': 'Selected source partitions only, not full-admission completeness', 'tables': table_audit},
                'diagnosis_time_policy': 'Current diagnosis codes are retrospective, timestamps unknown, excluded from frozen-time AI. Past diagnoses are not yet linked.'}
    for row in tables.get('DIAGNOSES_ICD', []):
        if pair(row) == pair(selected):
            clinical['current_diagnoses'].append({'code': row.get('ICD_CODE', ''), 'version': row.get('ICD_VERSION', ''),
                'sequence': row.get('SEQ_NUM', ''), 'table': 'DIAGNOSES_ICD', 'name_status': 'unmapped'})
    for table, dest, dictionary in (('LABEVENTS', 'labs', 'D_LABITEMS'), ('TESTEVENTS', 'imaging_tests', 'D_TESTITEMS')):
        for row in tables.get(table, []):
            if not own_record(row, selected):
                continue
            chart, store = available_times(row, start)
            if chart is None or not ((admit_minute if admit_minute is not None else 0) <= chart <= duration and chart < total):
                continue
            iid = row.get('ITEMID', '')
            info = dictionaries[dictionary].get(iid, {})
            ref = hospital + ':' + row.get(EVENT_IDS[table], json.dumps(row, sort_keys=True))
            result = {'itemid': iid, 'name': info.get('LABEL') or iid, 'chart_minute': chart,
                      'available_minute': store, 'table': table, 'dictionary': dictionary,
                      'record_ref': hashlib.sha256(ref.encode()).hexdigest()[:12]}
            if table == 'LABEVENTS':
                result.update(value=row.get('VALUE') or row.get('VALUENUM', ''), unit=row.get('VALUEUOM', ''),
                              reference_low=row.get('REF_RANGE_LOWER', ''), reference_high=row.get('REF_RANGE_UPPER', ''), flag=row.get('FLAG', ''))
            else:
                label = norm(info.get('LABEL'))
                modality = 'CT' if re.search(r'(^|[^a-z])ct([^a-z]|$)|computed tomography|전산화단층|컴퓨터단층', label) else 'CXR' if re.search(r'chest.*(x[- ]?ray|\bpa\b|\bap\b)|\bcxr\b|흉부.*(엑스|방사선)', label) else 'unclassified'
                result.update(category=info.get('CATEGORY', ''), modality=modality, report_status='not_linked',
                              file_reference_present=bool(row.get('FILE_PATH')), file_access_verified=False)
            clinical[dest].append(result)
    events = []
    for kind, ev in selected.get('evidence', {}).items():
        minute = relative(ev.get('at'), start)
        if minute is not None:
            events.append({'kind': kind, 'minute': minute, 'table': ev.get('table', ''),
                           'itemid': str(ev.get('item') or ''), 'category': str(ev.get('category') or ''),
                           'evidence_status': 'confirmed', 'time_scope': 'retrospective_source_event',
                           'availability_status': 'source_event_time_only_not_model_fact'})
    labels = selected.get('scenario_labels', [])
    gs = {'service_code': 'GS', 'criterion': 'gs_at_icu_entry', 'strict_cohort_stays': cohort_count,
          'selected_role': selected.get('selected_for') or (labels[0] if labels else 'gs_icu'), 'matched_scenarios': labels,
          'scenario_labels_retrospective': True, 'scenario_events': sorted(events, key=lambda e: e['minute']),
          'checkpoint_minute': checkpoint, 'icu_start_minute_of_day': start.hour * 60 + start.minute,
          'service_evidence': {'table': 'SERVICES', 'minute': relative(entry['at'], start), 'code': 'GS'},
          'cohort_basis': 'Surgical ICU + literal GS at ICU entry',
          'coverage': {'cohort': 'Full audited surgical ICU cohort; literal GS at ICU entry',
                       'observations': 'Selected source partitions only; missing means unknown',
                       'imaging': 'Test metadata only; pixels and radiology reports not verified'}}
    series, ages = resample(observations, duration, step, total)
    # Source checkpoints can fall between grid points; the UI cannot select an
    # observation at/after discharge. Preserve the source time separately.
    gs['source_checkpoint_minute'] = checkpoint
    checkpoint = min(checkpoint, (len(series['hr']) - 1) * step)
    gs['checkpoint_minute'] = checkpoint
    return {'pid': selected.get('case_alias', 'GS-' + hashlib.sha256(repr((hospital,) + key(selected)).encode()).hexdigest()[:10]),
            'source': 'K-MIMIC', 'unit_type': 'SICU', 'careunit': 'SICU', 'age': None, 'sex': None,
            'dx': 'Retrospective diagnosis codes; see source details', 'step': step, 'los_min': duration,
            'series': series, 'measurement_age_min': ages, 'bounded_carry_forward': True,
            'raw_observations': observations, 'device_events': {k: sorted(v, key=lambda e: e['minute']) for k, v in devices.items()},
            'procedures': sorted(procedures, key=lambda e: e['end_min']),
            'procedure_table_available': bool(table_audit.get('PROCEDUREEVENTS', {}).get('complete_for_selected_partition_set')),
            'clinical_detail': clinical, 'initial_minute': checkpoint, 'gs_selection': gs,
            'provenance': {'source_identity': {'hospital': hospital, **dict(zip(('SUBJECT_ID', 'HADM_ID', 'STAY_ID'), key(selected)))},
                           'icu_in': selected['icu_in'], 'icu_out': selected['icu_out'], 'dataset': 'kmimic-emr-' + hospital,
                           'partition': ' | '.join(selected['source_partition_list']), 'selection': gs['cohort_basis'],
                           'max_carry_forward_min': 30, 'support_status': 'Only explicit positive/state records; absence remains unknown',
                           'rejected_record_counts': dict(rejected)}}


def run(root, selection_path, output):
    selection = json.loads(selection_path.read_text())
    if selection.get('coverage_complete') is not True:
        raise ValueError('Refusing incomplete GS cohort selection')
    cases = selection.get('cases', [])
    if not cases or len(cases) > 32:
        raise ValueError('Expected 1–32 selected cases')
    identities = {(str(c['hospital']),) + key(c) for c in cases}
    if len(identities) != len(cases):
        raise ValueError('Duplicate selected ICU stay')
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    counts = selection.get('cohort_counts', {})
    cohort_count = counts.get('gs_at_entry_stays', counts.get('strict_gs_at_entry_stays', counts.get('gs_at_icu_entry', counts.get('strict_gs_stays'))))
    if isinstance(cohort_count, dict):
        cohort_count = cohort_count.get('icu_stays')
    if type(cohort_count) is not int or cohort_count < len(cases):
        raise ValueError('Missing verified strict-GS cohort count')
    audit = {'started_at': datetime.now(timezone.utc).isoformat(), 'selected_cases': len(cases), 'hospitals': {},
             'scope': 'Full-cohort GS selection; selected-partition clinical observations, not complete admission records',
             'imaging_limit': 'Selected-case TESTEVENTS metadata only. File references do not establish available CT/CXR pixels or reports.'}
    built = {}
    for hospital in sorted({str(c['hospital']) for c in cases}):
        selected = [c for c in cases if str(c['hospital']) == hospital]
        targets = {pair(c) for c in selected}
        parts = {str(part) for c in selected for part in c['source_partition_list']}
        requested = collections.defaultdict(set)
        for c in selected:
            for table, values in c.get('required_partitions', {}).items():
                requested[table].update(str(v) for v in values)
        receipts = {}
        dictionaries = {name: vocabulary(root, hospital, name, parts, receipts) for name in ('D_ITEMS', 'D_LABITEMS', 'D_TESTITEMS')}
        mapping = item_map(hospital, dictionaries['D_ITEMS'])
        chart_items = set(mapping) | {iid for iid, row in dictionaries['D_ITEMS'].items() if norm(row.get('LABEL')) in ACCESSORY_LABELS}
        if hospital == '001':
            chart_items.update(('001C_1207_22360', '001C_1093_22025'))
        tables = {}
        for table in ('ADMISSIONS', 'DIAGNOSES_ICD', 'PROCEDUREEVENTS', 'CHARTEVENTS', 'DATETIMEEVENTS', 'LABEVENTS', 'TESTEVENTS'):
            use_parts = parts | requested.get(table, set())
            if table == 'DIAGNOSES_ICD':
                use_parts |= requested.get('ADMISSIONS', set())
            items = chart_items if table == 'CHARTEVENTS' else {'001D_7284_11320'} if table == 'DATETIMEEVENTS' and hospital == '001' else set() if table == 'DATETIMEEVENTS' else None
            tables[table] = scan(root, hospital, table, use_parts, targets, receipts, items)
            safe_write(output / 'progress.json', {'at': datetime.now(timezone.utc).isoformat(), 'hospital': hospital, 'table': table, 'selected_cases': len(cases)})
        audit['hospitals'][hospital] = {'cases': len(selected), 'tables': receipts, 'verified_vital_items': len(mapping)}
        for c in selected:
            built[(hospital,) + key(c)] = build_case(c, tables, dictionaries, mapping, receipts, cohort_count)
        safe_write(output / 'audit.json', audit)
    pool = [built[(str(c['hospital']),) + key(c)] for c in cases]
    audit['case_summary'] = [{'case': p['pid'], 'hospital': p['provenance']['source_identity']['hospital'],
                              'scenarios': p['gs_selection']['matched_scenarios'], 'vital_observations': len(p['raw_observations']),
                              'device_records': {k: len(v) for k, v in p['device_events'].items()},
                              'diagnosis_codes': len(p['clinical_detail']['current_diagnoses']),
                              'labs': len(p['clinical_detail']['labs']), 'test_records': len(p['clinical_detail']['imaging_tests']),
                              'file_reference_records': sum(r['file_reference_present'] for r in p['clinical_detail']['imaging_tests'])} for p in pool]
    audit['finished_at'] = datetime.now(timezone.utc).isoformat()
    safe_write(output / 'pool_gs.json', pool)
    safe_write(output / 'audit.json', audit)
    safe_write(output / 'progress.json', {'status': 'finished', 'cases': len(pool), 'finished_at': audit['finished_at']})
    print('GS_POOL_COMPLETE', json.dumps({'cases': len(pool), 'vital_observations': sum(len(p['raw_observations']) for p in pool),
                                        'labs': sum(len(p['clinical_detail']['labs']) for p in pool),
                                        'test_records': sum(len(p['clinical_detail']['imaging_tests']) for p in pool)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('/home/khdp-user/workspace/datasets'))
    parser.add_argument('--selection', type=Path, default=Path('/home/khdp-user/workspace/icu-runtime/gs-scenario-selection/selected_cases.json'))
    parser.add_argument('--output', type=Path, default=Path('/home/khdp-user/workspace/icu-runtime/gs-board-pool'))
    args = parser.parse_args()
    run(args.root, args.selection, args.output)
