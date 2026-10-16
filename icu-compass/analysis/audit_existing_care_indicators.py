"""Read-only compact audit of five-icon source evidence already in the GS pool.

No source-data scan, raw patient identifiers, clinical free text, or credentials.
The report distinguishes source observation support from current/AI availability.
"""
import collections
import json
from pathlib import Path

W = Path('/home/khdp-user/workspace/icu-runtime')
SURGERY_KINDS = {'surgery_record_during_icu', 'surgery_ended_before_icu_24h'}
CPR_KINDS = {'cpr_start', 'cpr_recorded'}
SURGERY_CATEGORIES = {'수술', 'Surgery', 'Surgical', 'SURGERY'}


def main():
    pool = json.loads((W / 'gs-board-pool/pool_gs.json').read_text())
    result = []
    for p in pool:
        gs = p.get('gs_selection', {})
        offset = gs.get('icu_start_minute_of_day')
        checkpoint = p.get('initial_minute', 0)
        calendar = (offset + checkpoint) // 1440 if type(offset) is int else None
        events = []
        for e in gs.get('scenario_events', []):
            kind = e.get('kind')
            if kind not in SURGERY_KINDS | CPR_KINDS or e.get('evidence_status') != 'confirmed':
                continue
            expected = 'PROCEDUREEVENTS' if kind in SURGERY_KINDS else 'DATETIMEEVENTS'
            if e.get('table') != expected:
                continue
            minute = e.get('minute')
            if type(minute) not in (int, float):
                continue
            events.append({'kind': kind, 'table': expected, 'minute': minute,
                           'same_day_at_source_checkpoint': calendar is not None and minute <= checkpoint
                           and (offset + minute) // 1440 == calendar})
        history = collections.Counter((e.get('device_type'), e.get('active'))
                                      for e in p.get('historical_device_observations', []))
        result.append({
            'case': p['pid'], 'initial_minute': checkpoint,
            'calendar_offset_available': calendar is not None,
            'confirmed_cpr_surgery_events': events,
            'exact_surgery_procedure_rows': sum(e.get('category') in SURGERY_CATEGORIES for e in p.get('procedures', [])),
            'audited_device_event_counts': {k: len(v) for k, v in p.get('device_events', {}).items()},
            'historical_device_counts': [{'device_type': kind, 'active_at_observation': active, 'rows': count}
                                         for (kind, active), count in sorted(history.items())],
            'pressor_escalation_evidence_mapped': False,
            'operation_flag_used_for_surgery_today': False,
        })
    print('GS_EXISTING_CARE_EVIDENCE', json.dumps({'source': 'Existing selected pool only', 'cases': result}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
