"""Read-only K-MIMIC case board. Real row-level input stays inside KHDP.

Bed slots are presentation slots, not reconstructed real occupancy.
Only audited bounded replay pools are accepted. LLM role discussions use frozen, source-bound evidence without synthetic fallbacks.
"""
import argparse
import json
import math
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from clinical_detail import snapshot
from grounded_chat import Discussions, ChatError
from vision_review import VisionReviews
from patient_imaging import ImageRegistry, binding as image_binding

VITALS = ('hr', 'map', 'spo2', 'rr', 'sbp')
SCENARIO_TABLES = {
    'ed_within_24h_before_icu': 'ADMISSIONS',
    'surgery_ended_before_icu_24h': 'PROCEDUREEVENTS',
    'surgery_record_during_icu': 'PROCEDUREEVENTS',
    'death_during_icu': 'ADMISSIONS',
    'operation_flag': 'ICUSTAYS',
    'next_unit_unclassified': 'TRANSFERS',
    'cpr_recorded': 'DATETIMEEVENTS',
    'cpr_start': 'DATETIMEEVENTS',
    'ecmo_flow_recorded': 'CHARTEVENTS',
    'ventilator_on': 'CHARTEVENTS', 'ventilator_off': 'CHARTEVENTS',
}
SCENARIO_LABELS = {'ed_to_icu', 'ed_within_24h_before_icu', 'postoperative_icu',
                   'surgery_during_icu', 'icu_death', 'cpr_during_icu'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def gs_selection(p):
    """Publish only reviewed metadata; never forward the private source identity."""
    raw = p.get('gs_selection', p.get('provenance', {}).get('gs_selection'))
    if raw is None:
        return None
    service = raw.get('service_evidence', {}) if isinstance(raw, dict) else {}
    if (not isinstance(raw, dict) or raw.get('service_code') != 'GS'
            or raw.get('criterion') != 'gs_at_icu_entry'
            or service.get('table') != 'SERVICES' or service.get('code') != 'GS'
            or not finite(service.get('minute')) or service['minute'] > 0
            or type(raw.get('strict_cohort_stays')) is not int or raw['strict_cohort_stays'] <= 0):
        raise ValueError('Unverified strict GS selection metadata')
    events = []
    for e in raw.get('scenario_events', []):
        kind = e.get('kind')
        if (kind not in SCENARIO_TABLES or e.get('table') != SCENARIO_TABLES[kind]
                or e.get('evidence_status') != 'confirmed' or not finite(e.get('minute'))):
            continue
        event = {'kind': kind, 'minute': e['minute'], 'table': e['table'],
                 'evidence_status': 'confirmed', 'time_scope': 'historical_event'}
        if finite(e.get('available_minute')) and e['available_minute'] >= e['minute']:
            event['available_minute'] = e['available_minute']
        # Item codes are source vocabulary keys, never source patient/admission keys.
        if isinstance(e.get('itemid'), str): event['itemid'] = e['itemid'][:100]
        events.append(event)
    labels = [v for v in raw.get('matched_scenarios', []) if v in SCENARIO_LABELS]
    result = {'service_code': 'GS', 'criterion': 'gs_at_icu_entry',
              'strict_cohort_stays': raw['strict_cohort_stays'],
              'matched_scenarios': list(dict.fromkeys(labels)),
              'selected_role': raw.get('selected_role') if raw.get('selected_role') in SCENARIO_LABELS else 'gs_icu',
              'service_evidence': {'table': 'SERVICES', 'code': 'GS', 'minute': service['minute']},
              'scenario_events': sorted(events, key=lambda e: e['minute']),
              'cohort_basis': 'Surgical ICU + literal GS at ICU entry'}
    checkpoint = raw.get('checkpoint_minute', p.get('initial_minute'))
    if finite(checkpoint) and checkpoint >= 0: result['checkpoint_minute'] = checkpoint
    offset = raw.get('icu_start_minute_of_day', p.get('icu_start_minute_of_day'))
    if type(offset) is int and 0 <= offset < 1440: result['icu_start_minute_of_day'] = offset
    return result


def audited_device_events(p):
    """Separate historical observations from current state; availability is mandatory for new mappings."""
    result = {'ventilator': [], 'ecmo_crrt': [], 'cpr': [], 'accessories': []}
    for group in result:
        for e in p.get('device_events', {}).get(group, []):
            minute = e.get('minute')
            if not finite(minute) or minute < 0 or type(e.get('active')) is not bool:
                continue
            if group == 'ventilator':
                if e.get('raw') not in ('ON', 'OFF') or e['active'] != (e['raw'] == 'ON'):
                    continue
                item = {'minute': minute, 'active': e['active'], 'raw': e['raw'],
                        'itemid': str(e.get('itemid', ''))[:100], 'table': 'CHARTEVENTS'}
                # Older audited pools predate the explicit availability fields.
                if not any(k in e for k in ('chart_minute', 'available_minute')):
                    result[group].append(item)
                    continue
            if not all(finite(e.get(k)) for k in ('chart_minute', 'available_minute')):
                continue
            chart, available = e['chart_minute'], e['available_minute']
            if not chart <= available == minute:
                continue
            expected = 'DATETIMEEVENTS' if group == 'cpr' else 'CHARTEVENTS'
            if e.get('table', expected) != expected:
                continue
            item = {'minute': minute, 'chart_minute': chart, 'available_minute': available,
                    'active': e['active'], 'itemid': str(e.get('itemid', ''))[:100], 'table': expected}
            if group == 'ecmo_crrt':
                if (e.get('subtype') != 'ecmo' or e.get('evidence_kind') != 'positive_ecmo_flow'
                        or e['active'] is not True or not finite(e.get('value')) or e['value'] <= 0):
                    continue
                item.update(subtype='ecmo', evidence_kind='positive_ecmo_flow', value=e['value'],
                            unit=str(e.get('unit', ''))[:40], raw=str(e['value']))
            elif group == 'cpr':
                if (e.get('evidence_kind') != 'cpr_start_record' or e['active'] is not True
                        or not finite(e.get('event_minute')) or not 0 <= e['event_minute'] <= available):
                    continue
                item.update(evidence_kind='cpr_start_record', event_minute=e['event_minute'])
            elif group == 'accessories':
                if e.get('evidence_kind') != 'explicit_device_state': continue
                token = str(e.get('raw', '')).strip().lower()
                on = {'on', 'present', 'in place', '삽입됨', '유지 중', '유지중'}
                off = {'off', 'absent', 'removed', '제거됨'}
                if token not in on | off or e['active'] != (token in on): continue
                item.update(evidence_kind='explicit_device_state', raw=e['raw'],
                            name=str(e.get('name', ''))[:100], device_type=str(e.get('device_type', ''))[:50])
            else:
                item['raw'] = e['raw']
            result[group].append(item)
        result[group].sort(key=lambda e: (e['minute'], e.get('chart_minute', e['minute'])))
    return result


def historical_vitals(p):
    """Retrospective chart-time points; never current-state or AI evidence."""
    units = {'hr': 'bpm', 'map': 'mmHg', 'spo2': '%', 'rr': '/min', 'sbp': 'mmHg'}
    limits = {'hr': (10, 300), 'map': (10, 250), 'spo2': (0, 100), 'rr': (0, 100), 'sbp': (20, 300)}
    duration = p.get('los_min')
    if not finite(duration) or duration <= 0:
        return []
    result = []
    for event in p.get('historical_vital_observations', []):
        key, minute, value = event.get('variable'), event.get('chart_minute'), event.get('value')
        if (key not in units or not finite(minute) or not 0 <= minute <= duration
                or not finite(value) or not limits[key][0] <= value <= limits[key][1]
                or event.get('unit') != units[key] or event.get('table') != 'CHARTEVENTS'
                or event.get('same_time_conflict') is True
                or event.get('historical_only') is not True or event.get('availability_status') != 'unknown'
                or event.get('availability_reason') not in ('missing_storetime', 'invalid_storetime', 'store_before_chart')):
            continue
        result.append({'chart_minute': minute, 'variable': key, 'value': value, 'unit': units[key],
                       'table': 'CHARTEVENTS', 'itemid': str(event.get('itemid', ''))[:100],
                       'availability_status': 'unknown', 'availability_reason': event['availability_reason'],
                       'historical_only': True})
    return sorted(result, key=lambda event: (event['chart_minute'], event['variable']))


HISTORICAL_DEVICE_NAMES = {
    'ventilator': ('인공호흡기', 'Ventilator'),
    'ecmo': ('ECMO', 'ECMO'),
    'crrt': ('CRRT', 'CRRT'),
    'urinary_catheter': ('도뇨관', 'Urinary catheter'),
    'central_line': ('중심정맥관', 'Central venous line'),
    'arterial_line': ('동맥관', 'Arterial line'),
    'chest_drain': ('흉관', 'Chest drain'),
    'surgical_drain': ('수술 배액관', 'Surgical drain'),
    'nasogastric_tube': ('비위관', 'Nasogastric tube'),
    'endotracheal_tube': ('기관내관', 'Endotracheal tube'),
    'tracheostomy': ('기관절개관', 'Tracheostomy tube'),
}


def historical_devices(p):
    """Reviewed chart observations, never current attachment or frozen-time AI facts."""
    duration = p.get('los_min')
    if not finite(duration) or duration <= 0:
        return []
    result = []
    for event in p.get('historical_device_observations', []):
        kind, minute = event.get('device_type'), event.get('chart_minute')
        evidence = event.get('evidence_kind')
        if (kind not in HISTORICAL_DEVICE_NAMES or not finite(minute) or not 0 <= minute < duration
                or event.get('table') not in ('CHARTEVENTS', 'DATETIMEEVENTS') or type(event.get('active')) is not bool
                or event.get('same_time_conflict') is True
                or event.get('historical_only') is not True
                or evidence not in ('explicit_device_state', 'positive_ecmo_flow', 'documented_device_use', 'documented_device_removal')):
            continue
        status = event.get('availability_status')
        if status == 'known':
            available = event.get('available_minute')
            if not finite(available) or not minute <= available < duration:
                continue
        elif status == 'unknown':
            if event.get('availability_reason') not in ('missing_storetime', 'invalid_storetime', 'store_before_chart'):
                continue
        else:
            continue
        if evidence in ('documented_device_use', 'documented_device_removal'):
            if (event.get('table') != 'DATETIMEEVENTS' or event['active'] is not (evidence == 'documented_device_use')
                    or not finite(event.get('event_minute')) or not 0 <= event['event_minute'] <= minute):
                continue
        elif event.get('table') != 'CHARTEVENTS':
            continue
        if evidence == 'positive_ecmo_flow' and (kind != 'ecmo' or event['active'] is not True
                or not finite(event.get('value')) or event['value'] <= 0):
            continue
        ko, en = HISTORICAL_DEVICE_NAMES[kind]
        item = {'chart_minute': minute, 'device_type': kind, 'name': en,
                       'name_ko': ko, 'name_en': en, 'active': event['active'],
                       'evidence_kind': evidence, 'table': event['table'],
                       'itemid': str(event.get('itemid', ''))[:100],
                       'availability_status': status, 'historical_only': True}
        if status == 'known':
            item['available_minute'] = event['available_minute']
        else:
            item['availability_reason'] = event['availability_reason']
        if evidence in ('documented_device_use', 'documented_device_removal'):
            item['event_minute'] = event['event_minute']
        result.append(item)
    return sorted(result, key=lambda event: (event['chart_minute'], event['device_type']))


def case_payload(pool):
    cases = []
    seen = set()
    for p in pool:
        if p.get('source') != 'K-MIMIC' or not p.get('bounded_carry_forward'):
            raise ValueError('Only audited bounded K-MIMIC replay records are accepted')
        if not p.get('pid') or p['pid'] in seen:
            raise ValueError('Missing or duplicate admission alias')
        seen.add(p['pid'])
        provenance = p.get('provenance', {})
        if p.get('careunit') not in ('SICU', 'TSICU'):
            raise ValueError('Unconfirmed surgical unit code')
        step = p.get('step')
        if not isinstance(step, (int, float)) or step <= 0:
            raise ValueError('Invalid observation step')
        series = p.get('series', {})
        n = len(series.get('hr', []))
        rows = []
        for i in range(n):
            values, ages = {}, {}
            for key in VITALS:
                a = series.get(key, [])
                b = p.get('measurement_age_min', {}).get(key, [])
                value = a[i] if i < len(a) else None
                age = b[i] if i < len(b) else None
                valid = (isinstance(value, (float, int)) and not isinstance(value, bool)
                         and math.isfinite(value) and isinstance(age, (float, int))
                         and math.isfinite(age) and 0 <= age <= 30)
                values[key] = value if valid else None
                ages[key] = age if valid else None
            rows.append({'minute': i * step, 'vitals': values, 'age': ages})
        complete = [i for i, row in enumerate(rows) if all(row['vitals'][key] is not None for key in VITALS)]
        initial = complete[min(6, len(complete)-1)] if complete else 0
        selection = gs_selection(p)
        if finite(p.get('initial_minute')) and rows:
            initial = min(len(rows)-1, max(0, math.ceil(p['initial_minute'] / step)))
        if selection and initial == 0:
            # Arrival/preoperative events often predate the first ICU observations.
            # Start at an explicitly labelled observed checkpoint, never fill minute 0
            # with a future measurement. Keep the source event's own time unchanged.
            observed = [i for i, row in enumerate(rows) if row['minute'] <= 360
                        and sum(row['vitals'][v] is not None for v in VITALS) >= 3]
            if observed:
                initial = observed[min(6, len(observed)-1)]
                selection['checkpoint_minute'] = rows[initial]['minute']
                selection['checkpoint_policy'] = 'Early ICU observation checkpoint; source event times unchanged'
        procedures = []
        for e in p.get('procedures', []):
            if not all(finite(e.get(k)) for k in ('start_min', 'end_min')) or not 0 <= e['start_min'] <= e['end_min']:
                continue
            event = dict(start_min=e['start_min'], end_min=e['end_min'], itemid=str(e.get('itemid', '')),
                         category=str(e.get('category', '')), table='PROCEDUREEVENTS')
            if selection:
                event['available_minute'] = e['available_minute'] if finite(e.get('available_minute')) and e['available_minute'] >= e['end_min'] else None
                event['time_scope'] = 'retrospective_event_time'
            procedures.append(event)
        # Legacy vent=False/pressor=False are importer placeholders, NOT negative evidence.
        cases.append({'id': f'CASE-{len(cases)+1:03d}', 'unit': p['careunit'],
                      'dataset': provenance.get('dataset'), 'partition': provenance.get('partition'),
                      'step': step, 'rows': rows, 'initial': initial,
                      'historical_vital_observations': historical_vitals(p),
                      'historical_device_observations': historical_devices(p),
                      'care_indicators': {}, 'devices': {},
                      'source': 'K-MIMIC', 'anatomy_findings': [],
                      'procedure_table_available': p.get('procedure_table_available') is True,
                      'procedures': procedures,
                      'device_events': audited_device_events(p),
                      'gs_selection': selection,
                      '_clinical': p.get('clinical_detail', {}),
                      '_image_binding': image_binding(provenance),
                      'clinical_linked': bool(p.get('clinical_detail')),
                      'mapping_status': ('Audited devices require observation and availability times. ECMO flow and CPR start are source records; unknown support is not absence. Procedure row counts are retrospective and not nursing workload.' if selection else 'Ventilator uses explicit ON/OFF; other support flags unmapped. Procedure row counts are not nursing workload.')})
    if not cases:
        raise ValueError('No audited replay admissions; synthetic substitution is disabled')
    gs = [c['gs_selection'] for c in cases if c['gs_selection']]
    if gs and (len(gs) != len(cases) or len({s['strict_cohort_stays'] for s in gs}) != 1):
        raise ValueError('Mixed or inconsistent GS cohort pool')
    result = {'source': 'K-MIMIC', 'mode': 'historical_case_replay', 'cases': cases,
            'count': len(cases), 'max_carry_forward_min': 30,
            'selection': 'First eligible SICU stays in one source partition; convenience sample, not representative.',
            'bed_semantics': 'Eight display slots per page; not actual simultaneous occupancy.'}
    if gs:
        result['selection'] = 'Scenario-matched historical cases from the full strict-GS-at-ICU-entry surgical ICU cohort; selected cases are not representative.'
        result['gs_cohort'] = {'criterion': 'gs_at_icu_entry', 'service_code': 'GS',
                               'strict_cohort_stays': gs[0]['strict_cohort_stays'],
                               'selected_stays': len(cases)}
    return result


def serve(pool_path, port):
    root = Path(__file__).parent
    payload = case_payload(json.loads(Path(pool_path).read_text()))
    if payload.get('gs_cohort'):
        from monthly_plan import parse_workbook_plan, build_monthly_plan
        plan_rows = parse_workbook_plan((root/'static/workbook-plan.js').read_text())
        payload['monthly_plan'] = build_monthly_plan(payload['cases'], plan_rows)
        from synthetic_cases import augment_monthly_plan
        payload = augment_monthly_plan(payload)
    discussions = Discussions(payload)
    image_registry = ImageRegistry(root.parent / 'patient-imaging')
    vision_reviews = VisionReviews(payload, image_registry)
    assets = {'/': ('text/html; charset=utf-8', root/'static/shared-clinical.html'),
              '/index.html': ('text/html; charset=utf-8', root/'static/shared-clinical.html'),
              '/evidence.html': ('text/html; charset=utf-8', root/'static/kmimic-board.html'),
              '/network.js': ('text/javascript; charset=utf-8', root/'static/network.js'),
              '/grounded-chat.js': ('text/javascript; charset=utf-8', root/'static/grounded-chat.js'),
              '/patient-detail.js': ('text/javascript; charset=utf-8', root/'static/patient-detail.js'),
              '/anatomy.js': ('text/javascript; charset=utf-8', root/'static/anatomy.js'),
              '/workbook.xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', root/'K-MIMIC_SICU_sample.xlsx'),
              '/workbook-preview.html': ('text/html; charset=utf-8', root/'workbook-preview.html')}
    for name in ('shared-clinical.html', 'shared-presentation.css', 'shared-clinical.css',
                 'shared-care-icons.js', 'shared-staff.js', 'shared-staff.css', 'record-visit-planner.js',
                 'replay-observations.js', 'vital-indicators.js', 'monthly-replay.js', 'eight-bed-labs.js',
                 'shared-clinical-controller.js', 'shared-shell-version.json'):
        mime = ('text/css; charset=utf-8' if name.endswith('.css') else
                'text/javascript; charset=utf-8' if name.endswith('.js') else
                'application/json; charset=utf-8' if name.endswith('.json') else 'text/html; charset=utf-8')
        assets['/' + name] = (mime, root/'static'/name)
    # Explicit allowlist only; files remain behind the existing KHDP authentication proxy.
    extraction = root.parent / 'full-kmimic-extract'
    for name in ('preview.html', 'surgical_icu_stays.csv', 'surgical_scenario_candidates.csv',
                 'trauma_icu_stays.csv', 'other_icu_with_surgery_evidence.csv',
                 'summary.json', 'icu_mapping_source.json'):
        mime = ('text/html; charset=utf-8' if name.endswith('.html') else
                'text/csv; charset=utf-8' if name.endswith('.csv') else 'application/json; charset=utf-8')
        assets['/cohort/' + name] = (mime, extraction / name)
    # Source files remain available only through the same authenticated private proxy.
    gs_root = root.parent / 'gs-scenario-selection'
    assets['/gs/summary.json'] = ('application/json; charset=utf-8', gs_root / 'summary.json')
    assets['/gs/stays.csv'] = ('text/csv; charset=utf-8', gs_root / 'gs_at_entry_stays.csv')
    assets['/gs/imaging-summary.json'] = ('application/json; charset=utf-8', root.parent / 'gs-imaging-audit' / 'summary.json')
    assets['/gs/monthly.xlsx'] = ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', root.parent / 'full-gs-monthly-allocation' / 'GS_monthly_plan.private.xlsx')
    assets['/gs/monthly-summary.json'] = ('application/json; charset=utf-8', root.parent / 'full-gs-monthly-allocation' / 'summary.json')
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def send_json(self, status, obj):
            body=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError): pass
        def do_POST(self):
            path=urlsplit(self.path).path
            if path not in ('/api/discussion/open','/api/discussion/turn','/api/cxr-review'):
                self.send_json(404,{'error':'Unknown endpoint.'}); return
            # JSON-only same-origin calls; no permissive CORS. KHDP proxy provides authentication.
            if self.headers.get('Sec-Fetch-Site')=='cross-site' or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.send_json(403,{'error':'Same-origin JSON requests required.'}); return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384: raise ChatError(413,'Request too large or empty.')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict): raise ChatError(400,'Invalid request.')
                result=vision_reviews.review(body) if path == '/api/cxr-review' else discussions.open(body) if path.endswith('/open') else discussions.turn(body)
                self.send_json(200,result)
            except ChatError as e: self.send_json(e.status,{'error':e.message})
            except (ValueError,TypeError): self.send_json(400,{'error':'Invalid request.'})
            except Exception: self.send_json(500,{'error':'Discussion unavailable; no reply was accepted.'})
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/api/case-images', '/api/case-image'):
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    self.send_json(403, {'error':'Same-origin requests required.'}); return
                try:
                    q = parse_qs(urlsplit(self.path).query)
                    case = next(c for c in payload['cases'] if c['id'] == q.get('case_id', [''])[0])
                    index = int(q.get('row_index', [''])[0])
                    if path == '/api/case-images':
                        self.send_json(200, image_registry.listing(case, index)); return
                    body, mime = image_registry.png(case, index, q.get('image_id', [''])[0]), 'image/png'
                except (StopIteration, FileNotFoundError):
                    self.send_json(404, {'error':'No linked image at this case and time.'}); return
                except (ValueError, TypeError, KeyError, OSError):
                    self.send_json(400, {'error':'Image unavailable.'}); return
            elif path == '/api/cases':
                body, mime = json.dumps({**payload, 'cases': [{k:v for k,v in c.items() if not k.startswith('_')} for c in payload['cases']]}, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8'
            elif path == '/api/case-detail':
                try:
                    query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    case = next(c for c in payload['cases'] if c['id'] == query.get('case_id', [''])[0])
                    interpolate = query.get('lab_interpolate', ['0'])[0]
                    if interpolate not in ('0', '1'):
                        raise ValueError('Invalid laboratory interpolation flag')
                    result = snapshot(case, int(query.get('row_index', [''])[0]),
                                      lab_item=query.get('lab_item', [''])[0],
                                      lab_query=query.get('lab_query', [''])[0],
                                      lab_offset=int(query.get('lab_offset', ['0'])[0]),
                                      lab_interpolate=interpolate == '1',
                                      test_kind=query.get('test_kind', [''])[0],
                                      test_query=query.get('test_query', [''])[0],
                                      test_offset=int(query.get('test_offset', ['0'])[0]))
                    self.send_json(200, result)
                except (StopIteration, ValueError, TypeError):
                    self.send_json(400, {'error': 'Invalid case, observation index, or laboratory filter.'})
                return
            elif path in assets:
                mime, file = assets[path]
                if not file.is_file(): self.send_error(404); return
                body = file.read_bytes()
            else:
                self.send_error(404); return
            self.send_response(200)
            for key, val in [('Content-Type', mime), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer')]:
                self.send_header(key, val)
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    print(f'KMIMIC_BOARD_READY cases={payload["count"]} port={port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()

if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--pool', required=True); a.add_argument('--port', type=int, default=8007)
    args = a.parse_args(); serve(args.pool, args.port)
