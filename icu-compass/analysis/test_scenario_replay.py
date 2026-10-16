import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monthly_plan import build_monthly_plan, parse_workbook_plan
from synthetic_cases import augment_monthly_plan


def case(ident='CASE-001', hospital='H1', event=None):
    return {'id': ident, 'source': 'K-MIMIC', 'dataset': hospital, 'unit': 'SICU',
            'initial': 0, 'rows': [{'minute': minute, 'vitals': {'hr': 80 + i}, 'age': {'hr': 0}}
                                  for i, minute in enumerate((0, 10, 20, 1440, 1450, 2880))],
            'device_events': {'ventilator': [{'minute': 10, 'active': True}]},
            'gs_selection': {'scenario_events': [] if not event else [event]}}


def fixture():
    days = []
    for day in range(1, 5):
        beds = [{'status': 'empty', 'event': ''} for _ in range(8)]
        beds[0] = {'status': 'red' if day == 1 else 'blue', 'event': 'GW' if day == 4 else ''}
        beds[1] = {'status': 'yellow', 'event': 'OP'}
        beds[2] = {'status': 'blue', 'event': 'GW' if day in (2, 4) else ''}
        beds[3] = {'status': 'green', 'event': '', 'case_id': 'CASE-001'}
        days.append({'day': day, 'sourceRow': day + 3, 'beds': beds})
    return {'source': 'K-MIMIC', 'cases': [case()], 'gs_cohort': {'strict_cohort_stays': 14321},
            'monthly_plan': {'by_hospital': {'H1': {'days': days, 'episodes': []}},
                             'undated_rows': [{'day': None, 'beds': [{'status': 'red'}] * 8}]}}


class ScenarioReplayTests(unittest.TestCase):
    def test_real_arrays_and_inputs_unchanged_no_generated_measurements(self):
        payload = fixture(); before = copy.deepcopy(payload)
        result = augment_monthly_plan(payload)
        self.assertEqual(payload, before)
        self.assertIs(result['cases'], payload['cases'])
        self.assertIs(result['cases'][0]['rows'], payload['cases'][0]['rows'])
        self.assertEqual(result['gs_cohort']['strict_cohort_stays'], 14321)
        self.assertEqual(len(result['scenario_cases']), 3)
        for replay in result['scenario_cases']:
            self.assertEqual(replay['source'], 'ScenarioReplay')
            self.assertEqual(replay['source_case_id'], 'CASE-001')
            self.assertFalse(replay['ai_supported'])
            for forbidden in ('rows', 'vitals', 'device_events', 'diagnosis', 'simulated_detail', 'synthetic'):
                self.assertNotIn(forbidden, replay)

    def test_episode_identity_empty_reserved_undated_and_existing_preserved(self):
        payload = fixture(); result = augment_monthly_plan(payload)
        original = payload['monthly_plan']['by_hospital']['H1']['days']
        days = result['monthly_plan']['by_hospital']['H1']['days']
        self.assertEqual(len({row['beds'][0]['case_id'] for row in days}), 1)
        self.assertNotEqual(days[0]['beds'][2]['case_id'], days[2]['beds'][2]['case_id'])
        for old, new in zip(original, days):
            for index in (1, 3, 4, 5, 6, 7):
                self.assertEqual(old['beds'][index], new['beds'][index])
        self.assertEqual(result['monthly_plan']['undated_rows'], payload['monthly_plan']['undated_rows'])

    def test_actual_checkpoints_stop_at_source_end(self):
        result = augment_monthly_plan(fixture())
        days = result['monthly_plan']['by_hospital']['H1']['days']
        self.assertEqual([row['beds'][0]['row_index'] for row in days], [0, 3, 5, 5])
        self.assertEqual([row['beds'][0]['checkpoint_minute'] for row in days], [0, 1440, 2880, 2880])
        self.assertFalse(days[2]['beds'][0]['source_range_exhausted'])
        self.assertTrue(days[3]['beds'][0]['source_range_exhausted'])
        self.assertEqual(days[3]['beds'][0]['requested_source_minute'], 4320)

    def test_idempotence_and_hospital_identity(self):
        payload = fixture()
        payload['monthly_plan']['by_hospital']['H2'] = copy.deepcopy(payload['monthly_plan']['by_hospital']['H1'])
        result = augment_monthly_plan(payload)
        self.assertEqual(result, augment_monthly_plan(result))
        self.assertEqual(len({c['id'] for c in result['scenario_cases']}), 6)
        self.assertEqual(result['scenario_replay_summary']['distinct_source_templates'], 1)

    def test_no_source_means_no_fake_substitute(self):
        payload = fixture(); payload['cases'] = []
        result = augment_monthly_plan(payload)
        self.assertEqual(result['scenario_cases'], [])
        self.assertNotIn('case_id', result['monthly_plan']['by_hospital']['H1']['days'][0]['beds'][0])

    def test_original_workbook_plan_compact_references(self):
        source = (Path(__file__).resolve().parents[1] / 'static/workbook-plan.js').read_text()
        rows = parse_workbook_plan(source)
        template = case()
        payload = {'source': 'K-MIMIC', 'cases': [template], 'monthly_plan': build_monthly_plan([template], rows)}
        result = augment_monthly_plan(payload)
        occupied = [cell for row in result['monthly_plan']['by_hospital']['H1']['days']
                    for cell in row['beds'] if cell['status'] in ('red', 'blue', 'green')]
        self.assertTrue(all(cell.get('case_id') for cell in occupied))
        self.assertEqual(len(result['scenario_cases']), 48)
        self.assertLess(len(json.dumps(result['scenario_cases'])), 65000)
        self.assertEqual(result['cases'][0]['rows'], template['rows'])


if __name__ == '__main__':
    unittest.main()
