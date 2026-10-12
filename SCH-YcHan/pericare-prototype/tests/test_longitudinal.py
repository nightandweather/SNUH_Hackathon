"""Longitudinal correctness: turnover, temporal isolation and recorded outcomes."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.engine import Engine, AppError
from app.importer import validate_dataset, export_canonical
from app.model import demo_predict, phase

ROOT = Path(__file__).resolve().parents[1]


class LongitudinalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.e = Engine(self.tmp.name + '/longitudinal.db')

    def tearDown(self):
        self.tmp.cleanup()

    def action(self, name, **body):
        return self.e.mutate(name, {'expected_revision': self.e.state['revision'], **body})

    def fixture(self):
        return json.loads((ROOT / 'examples/recorded-replay.json').read_text())

    def test_existing_census_and_scheduled_arrivals_are_separate(self):
        v = self.e.view()
        self.assertEqual(v['hospital']['current_census'], 60)
        self.assertEqual(v['hospital']['horizon_minutes'], 10080)
        self.assertEqual(len(self.e.state['arrival_queue']), 168)
        public = json.dumps(v)
        for key in ('arrival_queue', 'replay_events', 'trajectories', 'truth_icu', 'DEMO-061'):
            self.assertNotIn(key, public)
        self.assertTrue(any(p['phase'] == 'WARD' and p['admission_minute'] < -1440 for p in v['patients']))

    def test_initial_recovery_patients_leave_and_their_beds_are_cleaned(self):
        p = next(p for p in self.e.state['patients'] if p['id'] == 'DEMO-017')
        bid = p['ward_bed_id']
        self.action('advance', minutes=40)
        bed = next(b for b in self.e.state['ward_beds'] if b['id'] == bid)
        self.assertEqual(p['status'], 'active')  # Original reference cannot mutate a committed replacement.
        p = next(p for p in self.e.state['patients'] if p['id'] == 'DEMO-017')
        self.assertEqual(p['status'], 'discharged')
        self.assertIsNone(bed['occupant_id'])
        self.assertGreater(bed['available_minute'], self.e.state['minute'])
        self.assertFalse(any(a['patient_id'] == p['id'] for a in self.e.view()['alerts']))
        self.action('advance', minutes=60)
        self.assertFalse(any(x['id'] == p['id'] for x in self.e.view()['scene']['patients']))

    def test_short_forecast_is_not_a_discharge_order(self):
        original = demo_predict
        def very_short(f):
            pr = original(f)
            pr.update(hospital_los_days=.01, hospital_los_upper=.02)
            return pr
        with patch('app.model.demo_predict', side_effect=very_short):
            self.action('advance', minutes=60)
        p = next(p for p in self.e.state['patients'] if p['id'] == 'DEMO-023')
        self.assertEqual(p['status'], 'active')
        self.assertFalse(p['observations'][-1]['discharge_plan_confirmed'])

    def test_observed_recovery_progress_reduces_remaining_stay(self):
        p = next(p for p in self.e.view()['patients'] if p['id'] == 'DEMO-023')
        before = p['prediction']['hospital_los_days']
        self.action('advance', minutes=1440)
        p = next(p for p in self.e.view()['patients'] if p['id'] == 'DEMO-023')
        self.assertLess(p['prediction']['hospital_los_days'], before)

    def test_full_week_conserves_census_and_unique_physical_occupancy(self):
        self.action('play', running=True, speed=240)
        for _ in range(7):
            self.action('advance', minutes=1440)
            v = self.e.view()
            h = v['hospital']
            self.assertEqual(h['current_census'], h['initial_census'] + h['admissions'] - h['exits'])
            occupants = [b['occupant_id'] for b in self.e.state['beds'] + self.e.state['ward_beds'] if b['occupant_id']]
            self.assertEqual(len(occupants), len(set(occupants)))
            rooms = [p['location'] for p in self.e.state['patients'] if phase(p, self.e.state['minute']) == 'OR']
            self.assertEqual(len(rooms), len(set(rooms)))
            for p in v['patients']:
                self.assertLessEqual(p['prediction']['features']['minute'], v['minute'])
                self.assertTrue(all(o['minute'] <= v['minute'] for o in p['observations']))
        self.assertEqual(h['admissions'], 168)
        self.assertGreater(h['discharges'], 100)
        self.assertGreater(h['current_census'], 0)  # Unfinished stays remain censored at day seven.
        self.assertFalse(self.e.state['running'])
        self.assertTrue(h['ended'])
        self.assertLess(len(json.dumps(v)), 5 * 1024 * 1024)

    def test_recorded_arrival_and_off_grid_observation_are_not_visible_early(self):
        self.action('import', dataset=self.fixture())
        self.assertEqual(self.e.view()['hospital']['initial_census'], 1)
        self.assertNotIn('RECORDED-NEW', json.dumps(self.e.view()))
        self.action('advance', minutes=16)
        self.assertEqual(self.e.view()['patients'][0]['prediction']['features']['latest']['minute'], 0)
        self.action('advance', minutes=1)
        self.assertEqual(self.e.view()['patients'][0]['prediction']['features']['latest']['minute'], 17)
        self.action('advance', minutes=43)
        self.assertEqual(self.e.view()['hospital']['admissions'], 1)
        self.assertIn('RECORDED-NEW', [p['id'] for p in self.e.view()['patients']])
        self.assertFalse(self.e.state['automation']['enabled'])
        self.assertFalse(self.e.state['automation']['log'])

    def test_entry_and_exit_routes_name_the_actual_destination(self):
        self.action('advance', minutes=20)
        scene = self.e.view()['scene']
        self.assertTrue(any(p['motion'] and p['motion']['destination'] == 'EXIT' for p in scene['patients']))
        arrival = next(p for p in scene['patients'] if p['id'] == 'DEMO-061')
        self.assertEqual(arrival['motion']['destination'], 'PREOP')

    def test_observation_ingestion_cannot_skip_recorded_outcomes(self):
        self.action('import', dataset=self.fixture())
        self.action('observe', patient_id='RECORDED-NEW', as_of_minute=170,
                    observations=[{'minute':170,'map':80,'hr':77,'spo2':98,'norepi':0,'ventilation':False,'crrt':False}])
        self.assertEqual(self.e.view()['hospital']['discharges'],1)
        self.assertEqual(self.e.view()['hospital']['admissions'],1)
        self.assertTrue(all(e['minute']<=170 for e in self.e.state['replay_events'][:self.e.state['replay_cursor']]))
        self.assertEqual(self.e.state['replay_events'][self.e.state['replay_cursor']]['minute'],195)

    def test_recorded_discharge_is_an_outcome_not_a_prediction(self):
        self.action('import', dataset=self.fixture())
        self.action('advance', minutes=149)
        self.assertEqual(self.e.view()['hospital']['discharges'], 0)
        self.action('advance', minutes=1)
        p = next(p for p in self.e.view()['patients'] if p['id'] == 'DEMO-016')
        self.assertEqual(p['phase'], 'DISCHARGED')
        self.assertEqual(p['discharge_minute'], 150)
        self.assertEqual(p['prediction']['mode'], 'completed')

    def test_death_is_not_counted_as_home_discharge(self):
        data = self.fixture()
        event = next(e for e in data['replay_events'] if e['kind'] == 'hospital_discharge')
        event['outcome'] = 'death'
        self.action('import', dataset=data)
        self.action('advance', minutes=150)
        h = self.e.view()['hospital']
        self.assertEqual(h['deaths'], 1)
        self.assertEqual(h['discharges'], 0)
        self.assertEqual(h['exits'], 1)
        self.assertEqual(self.e.view()['patients'][0]['phase'], 'DECEASED')

    def test_snapshot_never_manufactures_missing_measurements_or_discharge(self):
        data = self.fixture()
        data['patients'] = data['patients'][:1]
        data['patients'][0]['observations'] = []
        data['replay_events'] = []
        self.action('import', dataset=data)
        self.action('advance', minutes=1440)
        p = self.e.view()['patients'][0]
        self.assertEqual(p['observations'], [])
        self.assertIsNone(p['prediction']['features']['latest'].get('minute'))
        self.assertEqual(p['phase'], 'WARD')
        self.assertEqual(self.e.view()['hospital']['discharges'], 0)

    def test_snapshot_export_does_not_leak_unreleased_replay_packets(self):
        self.action('import', dataset=self.fixture())
        exported = export_canonical(self.e.state)
        self.assertNotIn('replay_events', exported)
        self.assertNotIn('RECORDED-NEW', json.dumps(exported))
        validate_dataset(exported)

    def test_future_snapshot_values_still_rejected(self):
        data = self.fixture()
        data['patients'][0]['observations'][0]['minute'] = 1
        with self.assertRaises(AppError):
            validate_dataset(data)

    def test_future_patient_requires_a_matching_admission_packet(self):
        data = self.fixture()
        data['replay_events'] = [e for e in data['replay_events'] if e['kind'] != 'hospital_admission']
        with self.assertRaises(AppError):
            validate_dataset(data)

    def test_unknown_discharge_outcome_is_not_assumed_to_be_home(self):
        data = self.fixture()
        next(e for e in data['replay_events'] if e['kind'] == 'hospital_discharge').pop('outcome')
        with self.assertRaises(AppError):
            validate_dataset(data)

    def test_duplicate_packet_and_post_discharge_event_are_rejected(self):
        data = self.fixture()
        data['replay_events'].append(copy.deepcopy(data['replay_events'][0]))
        with self.assertRaises(AppError):
            validate_dataset(data)
        data = self.fixture()
        data['replay_events'].append({'minute':151,'patient_id':'DEMO-016','kind':'location','location':'WARD'})
        with self.assertRaises(AppError):
            validate_dataset(data)

    def test_relative_clock_or_missing_inventory_cannot_allocate_beds(self):
        data = self.fixture()
        data['clock_kind'] = 'case_relative'
        data['beds'] = []
        self.action('import', dataset=data)
        with self.assertRaises(AppError):
            self.action('reserve', patient_id='DEMO-016', bed_id='SICU-01', start=10, end=100, reason='test booking')
        self.assertEqual(self.e.view()['patients'][0]['recommendation']['status'], 'BLOCKED')

    def test_sparse_ward_measurements_have_phase_specific_freshness(self):
        p = self.e.state['patients'][-1]
        self.assertEqual(phase(p,0),'WARD')
        self.action('advance', minutes=35)
        pr = self.e.state['predictions'][p['id']]
        self.assertFalse(pr['features']['stale'])

    def test_restart_preserves_clock_arrivals_outcomes_and_pauses(self):
        self.action('play', running=True)
        self.action('advance', minutes=60)
        h = copy.deepcopy(self.e.state['hospital'])
        queue = copy.deepcopy(self.e.state['arrival_queue'])
        restarted = Engine(self.e.store.path)
        self.assertFalse(restarted.state['running'])
        self.assertEqual(restarted.state['minute'],60)
        self.assertEqual(restarted.state['hospital'],h)
        self.assertEqual(restarted.state['arrival_queue'],queue)


if __name__ == '__main__':
    unittest.main()
