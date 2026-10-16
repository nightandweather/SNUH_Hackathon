import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monthly_plan import build_monthly_plan, checkpoint, parse_workbook_plan, segment_episodes, normalized_rows


def plan(*days):
    return [{'day': index + 1, 'sourceRow': index + 2,
             'beds': [{'status': value[0], 'event': value[1]} for value in day] +
                     [{'status': 'empty', 'event': ''} for _ in range(8 - len(day))]}
            for index, day in enumerate(days)]


def case(ident, *kinds, hospital='H1'):
    tables = {'ed_within_24h_before_icu': 'ADMISSIONS', 'death_during_icu': 'ADMISSIONS',
              'surgery_ended_before_icu_24h': 'PROCEDUREEVENTS', 'cpr_start': 'DATETIMEEVENTS'}
    return {'id': ident, 'dataset': hospital, 'initial': 1,
            'SUBJECT_ID': 'PRIVATE-SUBJECT', 'source_path': '/private/mount',
            'rows': [{'minute': 0}, {'minute': 5}, {'minute': 10}],
            'gs_selection': {'scenario_events': [{'kind': kind, 'table': tables[kind],
                              'minute': -10 if kind in ('ed_within_24h_before_icu', 'surgery_ended_before_icu_24h') else 7,
                              'evidence_status': 'confirmed'} for kind in kinds]}}


class MonthlyPlanTest(unittest.TestCase):
    def test_original_workbook_shape_and_no_eval(self):
        source = (Path(__file__).resolve().parents[1] / 'static/workbook-plan.js').read_text()
        result = build_monthly_plan([], parse_workbook_plan(source))
        self.assertEqual((result['day_count'], result['bed_count'], len(result['undated_rows'])), (31, 8, 4))
        self.assertEqual([r['sourceRow'] for r in result['undated_rows']], [33, 34, 35, 36])
        with self.assertRaises(ValueError):
            parse_workbook_plan('const rows=alert(1); function render(){')

    def test_continuity_terminal_and_empty_reserved(self):
        rows = plan([('red', 'OP'), ('yellow', '')], [('blue', '')], [('green', 'GW')],
                    [('red', 'ER')], [('empty', '')], [('red', 'OP')])
        episodes = segment_episodes(normalized_rows(rows)[0])
        self.assertEqual([(e['start_day'], e['end_day']) for e in episodes], [(1, 3), (4, 4), (6, 6)])
        result = build_monthly_plan([case('CASE-1', 'surgery_ended_before_icu_24h', 'ed_within_24h_before_icu')], rows)['by_hospital']['H1']
        cells = [r['beds'][0] for r in result['days']]
        self.assertEqual(len({c['case_id'] for c in cells[:3]}), 1)
        self.assertEqual(cells[2]['cell_event_match_status'], 'unconfirmed')
        self.assertEqual(cells[2]['linked_checkpoint_for'], 'episode_reference')
        self.assertEqual(result['days'][0]['beds'][1]['match_status'], 'reserved')
        self.assertIsNone(cells[4]['case_id'])

    def test_no_concurrent_reuse_and_later_reuse_flag(self):
        rows = plan([('red', 'OP'), ('red', 'OP')], [('green', 'GW'), ('green', 'GW')],
                    [('red', 'OP')])
        result = build_monthly_plan([case('CASE-1', 'surgery_ended_before_icu_24h')], rows)['by_hospital']['H1']
        self.assertEqual(sum(bool(c['case_id']) for c in result['days'][0]['beds']), 1)
        self.assertTrue(result['days'][2]['beds'][0]['reused_case'])

    def test_incompatible_death_and_partial_cpr(self):
        death = case('CASE-D', 'surgery_ended_before_icu_24h', 'death_during_icu')
        surgery = case('CASE-S', 'surgery_ended_before_icu_24h')
        rows = plan([('red', 'OP'), ('red', 'CPR')], [('green', 'GW'), ('red', 'Death')])
        result = build_monthly_plan([death, surgery], rows)['by_hospital']['H1']
        self.assertEqual(result['days'][0]['beds'][0]['case_id'], 'CASE-S')
        cpr = result['days'][0]['beds'][1]
        self.assertEqual(cpr['case_id'], 'CASE-D')
        self.assertEqual(cpr['matched_criteria'], ['DEATH'])
        self.assertEqual(cpr['unconfirmed_criteria'], ['CPR'])
        self.assertEqual(cpr['match_status'], 'partial')
        unmatched = build_monthly_plan([surgery], rows)['by_hospital']['H1']['days'][1]['beds'][1]
        self.assertIsNone(unmatched['case_id'])

    def test_unknown_labels_unconfirmed_and_alias_only(self):
        patient = case('CASE-1', 'surgery_ended_before_icu_24h')
        rows = plan([('red', 'AE'), ('red', 'OR'), ('red', 'OP')])
        original = copy.deepcopy((patient, rows))
        result = build_monthly_plan([patient], rows)
        self.assertEqual((patient, rows), original)
        cells = result['by_hospital']['H1']['days'][0]['beds']
        self.assertIsNone(cells[0]['case_id'])
        self.assertIsNone(cells[1]['case_id'])
        serialized = json.dumps(result)
        self.assertNotIn('PRIVATE-SUBJECT', serialized)
        self.assertNotIn('/private/mount', serialized)
        self.assertNotIn('SUBJECT_ID', serialized)

    def test_checkpoint_preserves_event_time_and_replay_bounds(self):
        patient = case('CASE-1')
        pre = checkpoint(patient, {'kind': 'surgery_ended_before_icu_24h', 'minute': -10})
        self.assertEqual((pre['row_index'], pre['checkpoint_minute'], pre['source_event_minute']), (1, 5, -10))
        cpr = checkpoint(patient, {'kind': 'cpr_start', 'minute': 7})
        self.assertEqual((cpr['row_index'], cpr['checkpoint_minute']), (2, 10))
        late = checkpoint(patient, {'kind': 'death_during_icu', 'minute': 12})
        self.assertIsNone(late['row_index'])
        self.assertIsNone(late['checkpoint_minute'])
        self.assertTrue(late['checkpoint_outside_replay'])
        self.assertEqual(late['source_event_minute'], 12)

    def test_hospitals_are_independent_and_unconfirmed_source_is_not_used(self):
        a, b = case('CASE-A', 'surgery_ended_before_icu_24h'), case('CASE-B', 'surgery_ended_before_icu_24h', hospital='H2')
        b['gs_selection']['scenario_events'][0]['evidence_status'] = 'unknown'
        result = build_monthly_plan([a, b], plan([('red', 'OP')]))['by_hospital']
        self.assertEqual(result['H1']['days'][0]['beds'][0]['case_id'], 'CASE-A')
        self.assertIsNone(result['H2']['days'][0]['beds'][0]['case_id'])


if __name__ == '__main__':
    unittest.main()
