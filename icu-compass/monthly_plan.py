"""Pure mapping of a fictional ICU.xlsx plan to source-evidenced case aliases.

Plan days, colors, occupancy and outcomes are never converted into patient facts.
Only verified event similarities select a case; unresolved criteria remain visible.
"""
import copy
import json
import math
import re
from collections import Counter, defaultdict

EVENTS = {
    'ER': {'ed_within_24h_before_icu': 'ADMISSIONS'},
    'OP': {'surgery_ended_before_icu_24h': 'PROCEDUREEVENTS', 'surgery_record_during_icu': 'PROCEDUREEVENTS'},
    'CPR': {'cpr_start': 'DATETIMEEVENTS', 'cpr_recorded': 'DATETIMEEVENTS'},
    'DEATH': {'death_during_icu': 'ADMISSIONS'},
}
STATUSES = {'red', 'blue', 'green', 'yellow', 'empty'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def parse_workbook_plan(source):
    match = re.search(r'const\s+rows\s*=\s*(\[.*?\])\s*;\s*function\s+render\s*\(', source, re.S)
    if not match:
        raise ValueError('Workbook plan JSON array not found')
    rows = json.loads(match[1])
    if not isinstance(rows, list):
        raise ValueError('Workbook plan must be a row list')
    return rows


def normalized_rows(rows):
    dated, undated = [], []
    for raw in rows:
        day = raw.get('day')
        if day is not None and (type(day) is not int or not 1 <= day <= 31):
            raise ValueError('Invalid plan day')
        beds = raw.get('beds', [])
        if len(beds) != 8:
            raise ValueError('Plan requires exactly eight beds per row')
        clean = []
        for bed in beds:
            status = str(bed.get('status', '')).lower()
            if status not in STATUSES:
                raise ValueError('Unknown plan color')
            event = str(bed.get('event') or '').strip()[:40]
            clean.append({'status': status, 'event': event})
        row = {'day': day, 'sourceRow': raw.get('sourceRow'), 'beds': clean}
        (dated if day is not None else undated).append(row)
    dated.sort(key=lambda row: row['day'])
    if [row['day'] for row in dated] != list(range(1, len(dated) + 1)):
        raise ValueError('Dated plan rows must be unique and contiguous from day one')
    return dated, undated


def segment_episodes(days):
    episodes = []
    for bed in range(8):
        current = None
        for row in days:
            cell, day = row['beds'][bed], row['day']
            if cell['status'] in ('empty', 'yellow'):
                current = None
                continue
            if current is None:
                current = {'episode_id': f'E{len(episodes) + 1:03d}', 'bed': bed + 1,
                           'start_day': day, 'end_day': day, 'events': [], 'cell_days': []}
                episodes.append(current)
            current['end_day'] = day
            current['cell_days'].append(day)
            if cell['event']:
                current['events'].append({'day': day, 'event': cell['event']})
            if cell['event'].upper() in ('GW', 'DEATH'):
                current = None
    return episodes


def source_events(case):
    grouped = defaultdict(list)
    for event in (case.get('gs_selection') or {}).get('scenario_events', []):
        if event.get('evidence_status') != 'confirmed' or not finite(event.get('minute')):
            continue
        for token, mapping in EVENTS.items():
            if mapping.get(event.get('kind')) == event.get('table'):
                grouped[token].append({'kind': event['kind'], 'minute': event['minute'], 'table': event['table']})
    for value in grouped.values():
        value.sort(key=lambda event: event['minute'])
    return grouped


def checkpoint(case, event):
    rows = [(index, row['minute']) for index, row in enumerate(case.get('rows', []))
            if finite(row.get('minute')) and row['minute'] >= 0]
    result = {'source_event_kind': event['kind'] if event else None,
              'source_event_minute': event['minute'] if event else None,
              'checkpoint_basis': 'source_record_time_not_fictional_plan_day',
              'checkpoint_clamped': False, 'checkpoint_outside_replay': False}
    if not rows:
        return dict(result, row_index=None, checkpoint_minute=None, checkpoint_outside_replay=True)
    rows.sort(key=lambda row: row[1])
    target = event['minute'] if event else None
    if target is None or target < 0:
        initial = case.get('initial', 0)
        index, minute = next(((index, minute) for index, minute in rows if index == initial), rows[0])
        return dict(result, row_index=index, checkpoint_minute=minute,
                    checkpoint_basis='initial_observation_after_preicu_event' if event else 'case_initial_observation')
    if target < rows[0][1] or target > rows[-1][1]:
        return dict(result, row_index=None, checkpoint_minute=None, checkpoint_outside_replay=True)
    index, minute = next((index, minute) for index, minute in rows if minute >= target)
    return dict(result, row_index=index, checkpoint_minute=minute)


def match_hospital(cases, original_days):
    days = copy.deepcopy(original_days)
    episodes = segment_episodes(days)
    cases = sorted(cases, key=lambda case: case['id'])
    evidence = {case['id']: source_events(case) for case in cases}
    assignments = defaultdict(list)
    by_id = {case['id']: case for case in cases}
    # Reserve scarce multi-event/CPR/death matches before ordinary OP episodes.
    def priority(episode):
        tokens = {event['event'].upper() for event in episode['events']}
        return (-len(tokens & EVENTS.keys()), -int('CPR' in tokens), -int('DEATH' in tokens), episode['start_day'], episode['bed'])
    for episode in sorted(episodes, key=priority):
        tokens = {event['event'].upper() for event in episode['events']}
        known, undefined = tokens & EVENTS.keys(), tokens - EVENTS.keys()
        options = []
        for case in cases:
            ident = case['id']
            # An ICU death is incompatible with a planned ward transfer. A
            # planned death likewise requires an actual ICU-death record.
            if ('GW' in tokens and 'DEATH' in evidence[ident]) or ('DEATH' in tokens and 'DEATH' not in evidence[ident]):
                continue
            if any(not (episode['end_day'] < other['start_day'] or episode['start_day'] > other['end_day']) for other in assignments[ident]):
                continue
            matched = known & evidence[ident].keys()
            if not matched:
                continue  # Do not invent a match for an undefined-only episode.
            mismatch = 'GW' in tokens and 'DEATH' in evidence[ident]
            score = (-int(matched == known), -len(matched), int(mismatch), len(assignments[ident]), ident)
            options.append((score, case, sorted(matched), mismatch))
        if options:
            _, case, matched, mismatch = min(options, key=lambda option: option[0])
            missing = sorted((known - set(matched)) | undefined)
            episode.update(case_id=case['id'], matched_criteria=matched, unconfirmed_criteria=missing,
                           match_status='partial' if missing or mismatch else 'matched_known_criteria',
                           case_mismatch_flags=['actual_icu_death_does_not_confirm_GW'] if mismatch else [])
            assignments[case['id']].append(episode)
        else:
            episode.update(case_id=None, matched_criteria=[], unconfirmed_criteria=sorted(tokens),
                           match_status='unmatched', case_mismatch_flags=[])
        episode.update(plan_colors_verified=False, plan_timing_verified=False,
                       plan_duration_days=episode['end_day'] - episode['start_day'] + 1)
    for history in assignments.values():
        history.sort(key=lambda episode: (episode['start_day'], episode['bed']))
        for index, episode in enumerate(history):
            episode['reused_case'] = index > 0
            episode['case_assignment_count'] = len(history)
    for episode in episodes:
        episode.setdefault('reused_case', False)
        episode.setdefault('case_assignment_count', 0)
        case = by_id.get(episode['case_id'])
        fallback = (min((event for token in episode['matched_criteria'] for event in evidence[case['id']][token]),
                        key=lambda event: event['minute']) if case else None)
        for row in days:
            if row['day'] not in episode['cell_days']:
                continue
            cell = row['beds'][episode['bed'] - 1]
            token = cell['event'].upper()
            event = evidence[case['id']][token][0] if case and token in episode['matched_criteria'] else fallback
            cell.update(bed=episode['bed'], episode_id=episode['episode_id'], case_id=episode['case_id'],
                        match_status=episode['match_status'], matched_criteria=episode['matched_criteria'],
                        unconfirmed_criteria=episode['unconfirmed_criteria'], reused_case=episode['reused_case'],
                        case_mismatch_flags=episode['case_mismatch_flags'], plan_day_has_no_source_time=True,
                        cell_event_match_status='matched' if token in episode['matched_criteria'] else 'unconfirmed' if token else 'continued_plan_cell',
                        linked_checkpoint_for='event' if token in episode['matched_criteria'] else 'episode_reference')
            cell.update(checkpoint(case, event) if case else {'row_index': None, 'checkpoint_minute': None})
    for row in days:
        for index, cell in enumerate(row['beds'], 1):
            if cell['status'] in ('empty', 'yellow'):
                cell.update(bed=index, episode_id=None, case_id=None, row_index=None, checkpoint_minute=None,
                            match_status='reserved' if cell['status'] == 'yellow' else 'empty',
                            matched_criteria=[], unconfirmed_criteria=[], reused_case=False)
    counts = Counter(episode['match_status'] for episode in episodes)
    return {'days': days, 'episodes': episodes,
            'summary': {'episodes': len(episodes), 'matched_known_criteria': counts['matched_known_criteria'],
                        'partial': counts['partial'], 'unmatched': counts['unmatched'],
                        'distinct_cases_assigned': len([v for v in assignments.values() if v]),
                        'reused_episodes': sum(episode['reused_case'] for episode in episodes)}}


def build_monthly_plan(cases, rows):
    days, undated = normalized_rows(rows)
    hospitals = sorted({case['dataset'] for case in cases if case.get('dataset')})
    aliases = [case.get('id') for case in cases]
    if len(set(aliases)) != len(aliases) or any(not isinstance(alias, str) or not alias for alias in aliases):
        raise ValueError('Case aliases must be present and unique')
    return {'version': 'gs-monthly-plan-v1', 'source': 'ICU.xlsx', 'day_count': len(days), 'bed_count': 8,
            'color_semantics': 'fictional_plan_not_clinical_readiness',
            'time_semantics': 'Plan day and length of stay are not actual patient dates or duration. Linked checkpoints use source event time.',
            'matching_semantics': 'Only verified event similarities; GW/AE/OR and missing criteria remain unconfirmed. No concurrent reuse of a case in one hospital.',
            'undated_rows': undated,
            'by_hospital': {hospital: match_hospital([case for case in cases if case['dataset'] == hospital], days)
                            for hospital in hospitals}}
