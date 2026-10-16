"""Monthly scenario slots backed by unchanged real-case replay templates.

Despite the legacy module name, this helper generates no synthetic measurements,
devices, diagnoses, or source identities. ``scenario_cases`` contains compact
references to the separate, unchanged real ``cases`` collection. The browser
reuses those source arrays; scenario assignments are not real ICU occupancy.
"""
import copy
import hashlib
import math
from collections import Counter

from monthly_plan import segment_episodes, source_events

DAY = 1440


def _identity(hospital, episode):
    label = hashlib.sha256(str(hospital).encode('utf-8')).hexdigest()[:8].upper()
    return f"SCN-{label}-B{episode['bed']:02d}-D{episode['start_day']:02d}"


def _rows(case):
    rows = case.get('rows') or []
    if not rows or any(type(r.get('minute')) not in (int, float)
                       or not math.isfinite(r['minute']) or r['minute'] < 0 for r in rows):
        return []
    if any(a['minute'] >= b['minute'] for a, b in zip(rows, rows[1:])):
        return []
    return rows


def _initial(case):
    index = case.get('initial')
    return index if type(index) is int and 0 <= index < len(case['rows']) else 0


def _checkpoint(case, elapsed_days):
    rows = case['rows']
    target = rows[_initial(case)]['minute'] + elapsed_days * DAY
    index = max((i for i, row in enumerate(rows) if row['minute'] <= target), default=0)
    return {'row_index': index, 'checkpoint_minute': rows[index]['minute'],
            'source_range_exhausted': target > rows[-1]['minute'],
            'requested_source_minute': target,
            'checkpoint_basis': 'source_template_initial_plus_plan_elapsed_days',
            'checkpoint_outside_replay': target > rows[-1]['minute'],
            'checkpoint_clamped': target > rows[-1]['minute']}


def _choose_template(cases, hospital, episode, uses):
    tokens = {event['event'].strip().upper() for event in episode['events']}
    days = episode['end_day'] - episode['start_day'] + 1
    def score(case):
        events = source_events(case)
        matched = len(tokens & events.keys())
        contradiction = int('GW' in tokens and 'DEATH' in events)
        actual_days = (case['rows'][-1]['minute'] - case['rows'][_initial(case)]['minute']) / DAY
        return (contradiction, -matched, int(case.get('dataset') != hospital),
                abs(actual_days - days), uses[case['id']], case['id'])
    return min(cases, key=score) if cases else None


def augment_monthly_plan(payload):
    """Fill unlinked dated occupied episodes using compact real-case references.

    Returns a new payload and copied monthly plan. ``cases`` remains the exact
    same object. All real allocations, empty/reserved cells, and undated rows
    remain unchanged. Scenario episode identity persists across plan days.
    """
    result = dict(payload)
    original = payload.get('monthly_plan')
    if not isinstance(original, dict):
        result.setdefault('scenario_cases', [])
        return result
    plan = copy.deepcopy(original)
    result['monthly_plan'] = plan
    real_cases = payload.get('cases', [])
    templates = [c for c in real_cases if c.get('source') == 'K-MIMIC'
                 and isinstance(c.get('id'), str) and _rows(c)]
    real_ids = {c.get('id') for c in real_cases}
    previous = {c['id']: c for c in payload.get('scenario_cases', [])
                if isinstance(c, dict) and c.get('source') == 'ScenarioReplay'
                and c.get('source_case_id') in real_ids}
    scenarios = dict(previous)
    uses = Counter(c['source_case_id'] for c in previous.values())
    total = Counter()
    for hospital, scope in plan.get('by_hospital', {}).items():
        by_day = {row['day']: row for row in scope.get('days', [])
                  if type(row.get('day')) is int}
        dated = [by_day[day] for day in sorted(by_day)]
        units = Counter(c.get('unit') for c in real_cases if c.get('dataset') == hospital
                        and c.get('unit') in ('SICU', 'TSICU'))
        unit = 'SICU' if 'SICU' in units or not units else units.most_common(1)[0][0]
        counts = Counter()
        for episode in segment_episodes(dated):
            cells = [by_day[day]['beds'][episode['bed'] - 1] for day in episode['cell_days']]
            assigned = {cell.get('case_id') for cell in cells if cell.get('case_id')}
            if assigned:
                if all(ident in previous for ident in assigned):
                    counts['replay_episodes'] += 1
                    counts['replay_occupied_cells'] += len(cells)
                else:
                    counts['existing_assignment_episodes'] += 1
                continue
            template = _choose_template(templates, hospital, episode, uses)
            if template is None:
                counts['unfilled_episodes_no_source_template'] += 1
                continue
            alias = _identity(hospital, episode)
            if alias in real_ids:
                raise ValueError('Scenario alias collides with a source case alias')
            # No rows, demographics, diagnosis, or equipment are generated or
            # copied here. Hydrate this reference from the real-case collection.
            scenarios[alias] = {
                'id': alias, 'source': 'ScenarioReplay', 'source_case_id': template['id'],
                'dataset': hospital, 'unit': unit, 'initial': _initial(template),
                'ai_supported': False, 'clinical_linked': False,
                'scenario_replay': {
                    'episode_id': episode['episode_id'], 'bed': episode['bed'],
                    'start_day': episode['start_day'], 'end_day': episode['end_day'],
                    'source_dataset': template.get('dataset'), 'source_unit': template.get('unit'),
                    'template_record_count': len(template['rows']),
                    'time_policy': 'Replay the unchanged source timeline from its initial checkpoint, adding 1440 minutes per plan day and stopping at the last source row.',
                    'measurements_generated': False, 'device_states_generated': False,
                    'diagnoses_generated': False, 'actual_patient_assignment': False,
                    'source_outcomes_are_plan_outcomes': False,
                },
            }
            uses[template['id']] += 1
            for day, cell in zip(episode['cell_days'], cells):
                cell.update(source_match_status=cell.get('match_status', 'unmatched'),
                            case_id=alias, source='ScenarioReplay', scenario_replay=True,
                            match_status='scenario_replay', source_event_kind=None,
                            source_event_minute=None, cell_event_match_status='planned',
                            linked_checkpoint_for='source_template_replay',
                            plan_colors_verified=False, plan_timing_verified=False,
                            **_checkpoint(template, day - episode['start_day']))
            for item in scope.get('episodes', []):
                if item.get('bed') == episode['bed'] and item.get('start_day') == episode['start_day']:
                    item.update(source_match_status=item.get('match_status', 'unmatched'),
                                case_id=alias, source='ScenarioReplay', scenario_replay=True,
                                match_status='scenario_replay')
            counts['replay_episodes'] += 1
            counts['replay_occupied_cells'] += len(cells)
        scope['scenario_replay_summary'] = dict(counts)
        total.update(counts)
    result['scenario_cases'] = sorted(scenarios.values(), key=lambda c: c['id'])
    result['scenario_replay_summary'] = {
        'source': 'ScenarioReplay', 'real_cases_modified': False,
        'measurements_generated': False, 'grounded_ai_supported': False,
        'distinct_source_templates': len({c['source_case_id'] for c in scenarios.values()}),
        **dict(total),
    }
    return result
