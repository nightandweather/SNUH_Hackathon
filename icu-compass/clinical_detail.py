"""Filter linked records before they cross the UI / model boundary."""
import math
import re
from clinical_evidence import source_assessment

LAB_PAGE_SIZE = 120
LAB_INTERPOLATION_MAX_GAP = 360
TEST_PAGE_SIZE = 60


def imaging_kind(record):
    """Classify the recorded test label, never infer pixels or findings."""
    label = str(record.get('name') or '')
    if re.search(r'(?<![a-z0-9])CT(?![a-z0-9])|computed tomography|전산화\s*단층|컴퓨터\s*단층', label, re.I):
        return 'ct'
    chest = re.search(r'\bCXR\b|chest|흉부', label, re.I)
    portable = re.search(r'portable|portably|이동식|포터블|포타블', label, re.I)
    if chest and portable:
        return 'portable_cxr'
    if re.search(r'\bCXR\b|chest\s*[-(:]?\s*(?:AP|PA|x[ -]?ray)\b|흉부.*(?:단순|촬영|엑스|방사선|X.?선)', label, re.I):
        return 'cxr'
    return 'other'
# Interpolation requires a reviewed continuous quantity, not merely a numeric
# value with a unit: ordinal scores and coded qualitative results can have both.
QUANTITATIVE_LAB_NAMES = frozenset({
    'hemoglobin', 'haemoglobin', 'creatinine', 'sodium', 'potassium', 'chloride',
    'glucose', 'lactate', 'platelet count', 'platelets', 'wbc',
    'white blood cell count', 'white blood cells', 'rbc', 'red blood cell count',
    'red blood cells', 'hematocrit', 'haematocrit', 'bun', 'blood urea nitrogen',
    'calcium', 'total calcium', 'ionized calcium', 'magnesium', 'phosphorus',
    'phosphate', 'bilirubin', 'total bilirubin', 'direct bilirubin',
    'indirect bilirubin', 'albumin',
    # Exact labels from the private source-vocabulary audit. Do not strip
    # arbitrary annotations: they can change a measurement into a coded result.
    'glucose(정량)(현장검사)',
    'hb(hemoglobin)[spectrophotometry]:응급검사실',
    'hb(hemoblobin)[spectrophotometry]:응급검사실',
    'hct(hematocrit):응급검사실',
    'rbc count:응급검사실', 'wbc count:응급검사실',
    'platelet count:응급검사실',
    '[처방불가]glucose (em)', '[처방불가]creatinine (serum, em)',
    '[처방불가]potassium (serum, em)', '[처방불가]hb (em)',
    'hb(검사24시간가능)', 'glucose(검사24시간가능)',
})


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def reviewed_quantitative_name(record):
    name = record.get('name')
    if not isinstance(name, str):
        return False
    normalized = ' '.join(name.casefold().split())
    normalized = ':'.join(part.strip() for part in normalized.split(':'))
    return normalized in QUANTITATIVE_LAB_NAMES


def laboratory_interpolation(records, itemid, minute):
    """A separate retrospective simulation estimate, never a model input.

    Future source observations are deliberately confined to this opt-in channel.
    Missing brackets, incompatible units or ambiguous results never produce a value.
    """
    result = {'status': 'unavailable', 'method': 'linear', 'historical_only': True,
              'exclude_from_ai': True, 'max_gap_minutes': LAB_INTERPOLATION_MAX_GAP,
              'itemid': itemid, 'as_of_minute': minute, 'uses_future_observation': False}
    if not itemid:
        return {**result, 'reason': 'select_item'}
    groups = {}
    for r in records:
        c, a = r.get('chart_minute'), r.get('available_minute')
        if str(r.get('itemid', '')) == itemid and finite(c) and finite(a) and c <= a:
            groups.setdefault(c, []).append(r)
    before_times = [t for t in groups if t <= minute]
    after_times = [t for t in groups if t >= minute]
    if not before_times or not after_times:
        return {**result, 'reason': 'no_bracketing_observations'}
    left_time, right_time = max(before_times), min(after_times)
    if left_time == right_time and all(r['available_minute'] > minute for r in groups[left_time]):
        return {**result, 'reason': 'result_not_available'}
    if right_time - left_time > LAB_INTERPOLATION_MAX_GAP:
        return {**result, 'reason': 'gap_exceeds_limit'}
    endpoints = []
    for time in (left_time, right_time):
        rows = groups[time]
        fingerprints = {(repr(r.get('value')), repr(r.get('unit'))) for r in rows}
        if len(fingerprints) > 1 or any(r.get('same_time_conflict') for r in rows):
            return {**result, 'reason': 'conflicting_observations'}
        if any(any(word in str(r.get(field, '')).casefold()
                   for word in ('negative', 'reactive', 'positive'))
               for r in rows for field in ('value', 'reference_low', 'reference_high')):
            return {**result, 'reason': 'qualitative_result'}
        if not all(reviewed_quantitative_name(r) for r in rows):
            return {**result, 'reason': 'unreviewed_quantitative_item'}
        r = min(rows, key=lambda row: row['available_minute'])
        if not isinstance(r.get('unit'), str) or not r['unit'].strip():
            return {**result, 'reason': 'missing_unit'}
        try:
            value = float(r['value']) if not isinstance(r.get('value'), bool) else float('nan')
        except (KeyError, TypeError, ValueError):
            return {**result, 'reason': 'non_numeric_result'}
        if not math.isfinite(value):
            return {**result, 'reason': 'non_numeric_result'}
        endpoint = {key: r[key] for key in ('chart_minute', 'available_minute', 'value', 'unit')}
        endpoints.append((endpoint, value))
    before, first = endpoints[0]
    after, last = endpoints[1]
    if before['unit'] != after['unit']:
        return {**result, 'reason': 'unit_mismatch'}
    value = first if left_time == right_time else first + (last - first) * (minute - left_time) / (right_time - left_time)
    if not math.isfinite(value):
        return {**result, 'reason': 'non_numeric_result'}
    return {**result, 'status': 'observed' if left_time == right_time else 'estimated',
            'value': value, 'unit': before['unit'], 'before': before, 'after': after,
            'uses_future_observation': any(e['chart_minute'] > minute or e['available_minute'] > minute
                                           for e in (before, after)),
            'reason': 'exact_observation' if left_time == right_time else 'retrospective_linear_interpolation'}


def snapshot(case, row_index, *, lab_item='', lab_query='', lab_offset=0, lab_interpolate=False,
             test_kind='', test_query='', test_offset=0):
    if type(row_index) is not int or not 0 <= row_index < len(case['rows']):
        raise ValueError('Invalid observation index')
    if not isinstance(lab_item, str) or not isinstance(lab_query, str):
        raise ValueError('Invalid laboratory filter')
    if type(lab_offset) is not int or lab_offset < 0:
        raise ValueError('Invalid laboratory offset')
    if type(lab_interpolate) is not bool:
        raise ValueError('Invalid laboratory interpolation flag')
    if test_kind not in ('', 'cxr', 'portable_cxr', 'ct', 'other') or not isinstance(test_query, str):
        raise ValueError('Invalid test filter')
    if type(test_offset) is not int or test_offset < 0:
        raise ValueError('Invalid test offset')
    lab_item, lab_query = lab_item.strip(), lab_query.strip()
    minute = case['rows'][row_index]['minute']
    data = case.get('_clinical', {})
    result = {'case_id': case['id'], 'row_index': row_index, 'as_of_minute': minute,
              'status': data.get('status', 'unlinked'), 'assessment': source_assessment(case, row_index)}
    if data.get('status') != 'linked':
        return result
    def available(r):
        c, a = r.get('chart_minute'), r.get('available_minute')
        return finite(c) and finite(a) and c <= a <= minute
    def visible(r):
        return {k:v for k,v in r.items() if k not in ('file_path','SUBJECT_ID','HADM_ID','STAY_ID')}
    labs = sorted([visible(r) for r in data.get('labs', []) if available(r)], key=lambda r:r['chart_minute'], reverse=True)
    groups = {}
    for r in labs:
        groups.setdefault((r['itemid'],r['chart_minute']),set()).add((r.get('value'),r.get('unit')))
    for r in labs:
        r['same_time_conflict'] = len(groups[(r['itemid'],r['chart_minute'])]) > 1
    # Build the selector from all results available at this time, before paging.
    # Only vocabulary identity, display name and count cross this boundary.
    catalog = {}
    for r in labs:
        itemid = str(r['itemid'])
        name = r.get('name')
        name = name.strip() if isinstance(name, str) else ''
        entry = catalog.setdefault(itemid, {'itemid': itemid, 'name': name or itemid, 'count': 0})
        entry['count'] += 1
        if entry['name'] == itemid and name:
            entry['name'] = name
    query = lab_query.casefold()
    filtered_labs = [r for r in labs
                     if (not lab_item or str(r['itemid']) == lab_item)
                     and (not query or query in str(r.get('name') or '').casefold()
                          or query in str(r['itemid']).casefold())]
    tests = sorted([visible(r) for r in data.get('imaging_tests', []) if available(r)], key=lambda r:r['chart_minute'], reverse=True)
    # Explicit metadata allowlist: a source file reference is not a retrievable image.
    tests = [{**{k:r[k] for k in ('itemid', 'name', 'category', 'chart_minute', 'available_minute',
                                 'table', 'dictionary', 'record_ref', 'file_reference_present') if k in r},
              'imaging_kind': imaging_kind(r), 'image_status': 'not_linked', 'report_status': 'not_linked'} for r in tests]
    test_counts = {kind: sum(r['imaging_kind'] == kind for r in tests) for kind in ('cxr', 'portable_cxr', 'ct', 'other')}
    search = test_query.strip().casefold()
    selected_tests = [r for r in tests if (not test_kind or r['imaging_kind'] == test_kind
                                         or test_kind == 'cxr' and r['imaging_kind'] == 'portable_cxr')
                      and (not search or search in str(r.get('name', '')).casefold()
                           or search in str(r.get('itemid', '')).casefold())]
    admission = data.get('admission', {})
    result.update(admission=admission if finite(admission.get('admit_minute')) and admission['admit_minute'] <= minute else {},
                  current_diagnoses_retrospective=data.get('current_diagnoses', []),
                  past_diagnoses=[r for r in data.get('past_diagnoses', []) if finite(r.get('prior_discharge_minute')) and r['prior_discharge_minute'] < admission.get('admit_minute', -float('inf')) <= minute],
                  labs=filtered_labs[lab_offset:lab_offset + LAB_PAGE_SIZE],
                  laboratory_available_count=len(labs),
                  laboratory_filtered_count=len(filtered_labs),
                  lab_items=sorted(catalog.values(), key=lambda r: (r['name'].casefold(), r['itemid'])),
                  lab_item=lab_item, lab_query=lab_query, lab_offset=lab_offset,
                  lab_page_size=LAB_PAGE_SIZE,
                  tests=selected_tests[test_offset:test_offset + TEST_PAGE_SIZE], test_available_count=len(tests),
                  test_filtered_count=len(selected_tests), test_kind=test_kind, test_query=test_query,
                  test_offset=test_offset, test_page_size=TEST_PAGE_SIZE, test_counts=test_counts,
                  test_availability_unknown_count=sum(finite(r.get('chart_minute')) and r['chart_minute'] <= minute
                                                     and not finite(r.get('available_minute')) for r in data.get('imaging_tests', [])),
                  coverage=data.get('coverage', {}),
                  policy='Current-admission diagnosis timestamps unknown: retrospective display only, excluded from AI. Labs/tests require both observation and store time at or before selected time. No inferred radiology interpretation.')
    # A recorded collection with unknown availability is not a known result.
    result['lab_availability_unknown_count'] = sum(finite(r.get('chart_minute')) and r['chart_minute'] <= minute and not finite(r.get('available_minute')) for r in data.get('labs', []))
    if lab_interpolate:
        result['lab_interpolation'] = laboratory_interpolation(data.get('labs', []), lab_item, minute)
    return result


def model_facts(case, row_index):
    s = snapshot(case, row_index)
    if s['status'] != 'linked':
        return []
    result = [{'kind':'clinical_linkage_scope','source':'K-MIMIC','coverage':s.get('coverage',{}).get('tables',{}),'limitation':'Subset of available records. Current admission diagnoses are untimed and excluded. Original narrative and imaging reports are not linked. Only numeric, unit-bearing laboratory results without same-time value conflicts enter AI; qualitative encodings are not decoded.'}]
    if s.get('admission'):
        result.append({'kind':'admission', **s['admission']})
    for r in s['past_diagnoses'][:20]:
        # No unverified model code decoding; only mapped names may enter clinical context.
        if r.get('name_status') == 'verified':
            result.append({'kind':'past_admission_diagnosis', **r, 'limitation':'Historical diagnosis association, not confirmed active disease'})
    # Most recent result per item, with explicit times; no assumed persistence or normality.
    seen=set()
    for r in s['labs']:
        if r['itemid'] in seen:continue
        seen.add(r['itemid'])
        try: number=float(r['value'])
        except (TypeError,ValueError): continue
        if not math.isfinite(number) or not r.get('unit') or r.get('same_time_conflict'):
            continue
        if any(word in str(r.get('reference_low','')).lower() for word in ('negative','reactive','positive')):
            continue
        result.append({'kind':'laboratory', **r, 'age_minute':s['as_of_minute']-r['chart_minute']})
        if sum(f['kind']=='laboratory' for f in result)>=20:break
    for r in s['tests'][:8]:
        result.append({'kind':'test_record', **r, 'limitation':'Recorded test only. No image or report interpretation linked; do not infer findings.'})
    return result
