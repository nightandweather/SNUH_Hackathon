"""Regression cases reproduced while reviewing real-input and replay paths."""
import copy
import tempfile
import unittest

from app.demo import make_demo
from app.engine import AppError, Engine, bed_fits
from app.importer import export_canonical, validate_dataset
from app.model import phase


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/review.db'
        self.e = Engine(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def action(self, name, **body):
        return self.e.mutate(name, {'expected_revision': self.e.state['revision'], **body})

    def dataset(self, ids=('DEMO-011', 'DEMO-014'), bed_ids=('SICU-01', 'SICU-02')):
        d = export_canonical(make_demo())
        d['patients'] = [p for p in d['patients'] if p['id'] in ids]
        d['beds'] = [b for b in d['beds'] if b['id'] in bed_ids]
        return d

    def obs(self, minute, map_value=85):
        return {'minute': minute, 'map': map_value, 'hr': 77, 'spo2': 98,
                'norepi': 0, 'ventilation': False, 'crrt': False}

    def patient(self, pid='DEMO-011'):
        return next(p for p in self.e.state['patients'] if p['id'] == pid)

    def test_known_patient_bed_cannot_be_reported_empty(self):
        d = self.dataset()
        d['beds'][0]['occupant_id'] = None
        with self.assertRaises(AppError):
            validate_dataset(d)

    def test_specific_patient_location_cannot_disagree_with_occupant_bed(self):
        d = self.dataset()
        d['patients'][0]['location'] = 'SICU-99'
        with self.assertRaises(AppError):
            validate_dataset(d)

    def test_generic_icu_unit_uses_the_supplied_bed_link(self):
        d = self.dataset()
        d['patients'][0]['location'] = 'SICU'
        imported = validate_dataset(d)
        self.assertEqual(imported['patients'][0]['location'], 'SICU-01')
        self.assertEqual(phase(imported['patients'][0], 0), 'ICU')

    def test_arbitrary_supplied_bed_id_is_recognized_as_icu(self):
        d = self.dataset(ids=('DEMO-011',), bed_ids=('SICU-01',))
        d['beds'][0]['id'] = 'BED-A01'
        d['patients'][0]['location'] = 'BED-A01'
        self.action('import', dataset=d)
        p = self.e.view()['patients'][0]
        self.assertEqual(p['phase'], 'ICU')
        self.assertEqual(p['recommendation']['status'], 'ADMITTED')
        self.assertEqual(self.e.view()['scene']['patients'][0]['home'], self.e.view()['scene']['beds'][0]['position'])

    def test_observed_icu_precedes_a_future_planned_operation(self):
        d = self.dataset(ids=('DEMO-011',), bed_ids=('SICU-01',))
        p = d['patients'][0]
        p.update(operation_start_minute=60, estimated_end_minute=180, actual_end_minute=None)
        self.action('import', dataset=d)
        self.assertEqual(self.e.view()['patients'][0]['phase'], 'ICU')
        self.assertEqual(self.e.view()['patients'][0]['recommendation']['status'], 'ADMITTED')

    def test_repeated_end_observation_does_not_move_icu_patient(self):
        self.action('observe', patient_id='DEMO-011', actual_end_minute=-220, observations=[self.obs(0)])
        self.assertEqual(self.patient()['location'], 'SICU-01')
        self.assertEqual(self.e.state['beds'][0]['occupant_id'], 'DEMO-011')
        self.assertEqual(phase(self.patient(), 0), 'ICU')

    def test_repeated_end_observation_does_not_move_ward_patient(self):
        p = self.patient('DEMO-017')
        end = p['actual_end_minute']
        self.action('observe', patient_id=p['id'], actual_end_minute=end, observations=[self.obs(0)])
        self.assertEqual(self.patient('DEMO-017')['location'], 'WARD')

    def test_first_received_operation_end_is_counted_only_once(self):
        self.action('observe', patient_id='DEMO-001', actual_end_minute=0, observations=[self.obs(0)])
        self.assertEqual(self.patient('DEMO-001')['location'], 'PACU')
        self.assertEqual(self.e.view()['hospital']['completed_operations'], 1)
        self.action('observe', patient_id='DEMO-001', actual_end_minute=0, observations=[self.obs(0)])
        self.assertEqual(self.e.view()['hospital']['completed_operations'], 1)

    def test_explicit_operation_end_updates_the_same_counter(self):
        self.action('end_operation', patient_id='DEMO-001', reason='관측된 실제 수술 종료')
        self.assertEqual(self.e.view()['hospital']['completed_operations'], 1)

    def test_same_timestamp_outgoing_and_incoming_are_order_independent(self):
        d = self.dataset()
        d['replay_events'] = [
            {'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'location', 'location': 'SICU-02'},
            {'minute': 10, 'patient_id': 'DEMO-014', 'kind': 'location', 'location': 'WARD'}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        self.assertEqual(self.e.state['beds'][1]['occupant_id'], 'DEMO-011')
        self.assertIsNone(self.e.state['beds'][0]['occupant_id'])
        self.assertEqual(self.patient('DEMO-014')['location'], 'WARD')

    def test_same_timestamp_discharge_releases_bed_for_observed_arrival(self):
        d = self.dataset()
        d['replay_events'] = [
            {'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'location', 'location': 'SICU-02'},
            {'minute': 10, 'patient_id': 'DEMO-014', 'kind': 'hospital_discharge', 'outcome': 'transfer'}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        self.assertEqual(self.e.state['beds'][1]['occupant_id'], 'DEMO-011')
        self.assertEqual(self.e.view()['hospital']['transfers'], 1)
        self.assertEqual(self.e.view()['hospital']['current_census'], 1)

    def test_simultaneous_bed_swap_has_no_duplicate_occupancy(self):
        d = self.dataset()
        d['replay_events'] = [
            {'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'location', 'location': 'SICU-02'},
            {'minute': 10, 'patient_id': 'DEMO-014', 'kind': 'location', 'location': 'SICU-01'}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        self.assertEqual([b['occupant_id'] for b in self.e.state['beds']], ['DEMO-014', 'DEMO-011'])

    def test_actual_bed_conflict_rolls_back_clock_cursor_and_census(self):
        d = self.dataset()
        d['replay_events'] = [{'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'location', 'location': 'SICU-02'}]
        self.action('import', dataset=d)
        before = copy.deepcopy(self.e.state)
        with self.assertRaises(AppError):
            self.action('advance', minutes=10)
        self.assertEqual(self.e.state, before)

    def test_icu_unit_only_update_does_not_release_known_bed(self):
        d = self.dataset()
        d['replay_events'] = [{'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'location', 'location': 'ICU'}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        self.assertEqual(self.patient()['location'], 'SICU-01')
        self.assertEqual(self.e.state['beds'][0]['occupant_id'], 'DEMO-011')

    def test_delayed_measurement_replaces_by_measurement_time_and_preserves_age(self):
        d = self.dataset(ids=('DEMO-017',), bed_ids=())
        d['replay_events'] = [{'minute': 10, 'patient_id': 'DEMO-017', 'kind': 'observation', 'observation': self.obs(0)}]
        self.action('import', dataset=d)
        self.action('advance', minutes=9)
        self.assertNotEqual(self.e.view()['patients'][0]['prediction']['features']['latest']['map'], 85)
        self.action('advance', minutes=1)
        self.assertEqual(sum(o['minute'] == 0 for o in self.patient('DEMO-017')['observations']), 1)
        f = self.e.view()['patients'][0]['prediction']['features']
        self.assertEqual(f['latest']['map'], 85)
        self.assertEqual(f['observation_age_minutes'], 10)

    def test_late_old_measurement_cannot_become_latest(self):
        d = self.dataset(ids=('DEMO-017',), bed_ids=())
        d['replay_events'] = [{'minute': 10, 'patient_id': 'DEMO-017', 'kind': 'observation', 'observation': self.obs(-60)}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        obs = self.patient('DEMO-017')['observations']
        self.assertEqual([o['minute'] for o in obs], sorted({o['minute'] for o in obs}))
        self.assertEqual(self.e.view()['patients'][0]['prediction']['features']['latest']['minute'], 0)

    def test_late_closed_encounter_observation_updates_history_without_reopening(self):
        d = self.dataset(ids=('DEMO-017',), bed_ids=())
        d['replay_events'] = [
            {'minute': 10, 'patient_id': 'DEMO-017', 'kind': 'hospital_discharge', 'outcome': 'home'},
            {'minute': 20, 'patient_id': 'DEMO-017', 'kind': 'observation', 'observation': self.obs(5)}]
        self.action('import', dataset=d)
        self.action('advance', minutes=20)
        p = self.e.view()['patients'][0]
        self.assertEqual(p['phase'], 'DISCHARGED')
        self.assertEqual(p['location'], 'DISCHARGED')
        self.assertTrue(any(o['minute'] == 5 for o in p['observations']))
        self.assertEqual(p['prediction']['mode'], 'completed')

    def test_measurement_after_discharge_is_rejected(self):
        d = self.dataset(ids=('DEMO-017',), bed_ids=())
        d['replay_events'] = [{'minute': 10, 'patient_id': 'DEMO-017', 'kind': 'hospital_discharge', 'outcome': 'home'}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        before = copy.deepcopy(self.e.state)
        with self.assertRaises(AppError):
            self.action('observe', patient_id='DEMO-017', as_of_minute=20, observations=[self.obs(20)])
        self.assertEqual(self.e.state, before)

    def test_v6_patch_upgrade_preserves_existing_progress(self):
        self.action('advance', minutes=40)
        self.e.state['runtime_version'] = '6.0'
        self.e.store.save(self.e.state)
        before = self.e.view()['hospital']
        new = Engine(self.path)
        self.assertEqual(new.state['minute'], 40)
        self.assertEqual(new.view()['hospital'], before)
        self.assertEqual(new.state['runtime_version'], '6.1')
        with new.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM archived_snapshot').fetchone()[0], 0)

    def test_delayed_operation_end_uses_actual_time_without_moving_icu_patient(self):
        d = self.dataset(ids=('DEMO-011',), bed_ids=('SICU-01',))
        d['patients'][0]['actual_end_minute'] = None
        d['replay_events'] = [{'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'operation_end', 'actual_end_minute': -220}]
        self.action('import', dataset=d)
        self.action('advance', minutes=9)
        self.assertIsNone(self.patient()['actual_end_minute'])
        self.action('advance', minutes=1)
        self.assertEqual(self.patient()['actual_end_minute'], -220)
        self.assertEqual(self.patient()['location'], 'SICU-01')
        self.assertEqual(self.e.state['beds'][0]['occupant_id'], 'DEMO-011')

    def test_actual_operation_end_time_and_receipt_time_are_distinct(self):
        d = self.dataset(ids=('DEMO-001',), bed_ids=())
        d['replay_events'] = [{'minute': 20, 'patient_id': 'DEMO-001', 'kind': 'operation_end', 'actual_end_minute': 10}]
        self.action('import', dataset=d)
        self.action('advance', minutes=19)
        self.assertIsNone(self.patient('DEMO-001')['actual_end_minute'])
        self.action('advance', minutes=1)
        p = self.e.view()['patients'][0]
        self.assertEqual(p['phase'], 'PACU')
        self.assertEqual(p['actual_end_minute'], 10)
        self.assertAlmostEqual(p['prediction']['features']['elapsed_postop_hours'], 10 / 60)

    def test_operation_end_without_start_packet_leaves_preop(self):
        d = self.dataset(ids=('DEMO-012',), bed_ids=())
        d['replay_events'] = [{'minute': 120, 'patient_id': 'DEMO-012', 'kind': 'operation_end', 'actual_end_minute': 110}]
        self.action('import', dataset=d)
        self.action('advance', minutes=120)
        self.assertEqual(self.e.view()['patients'][0]['phase'], 'PACU')

    def test_new_recorded_icu_occupant_has_no_inherited_exit_forecast(self):
        d = self.dataset()
        d['replay_events'] = [
            {'minute': 10, 'patient_id': 'DEMO-011', 'kind': 'location', 'location': 'SICU-02'},
            {'minute': 10, 'patient_id': 'DEMO-014', 'kind': 'location', 'location': 'WARD'}]
        self.action('import', dataset=d)
        self.action('advance', minutes=10)
        bed = self.e.state['beds'][1]
        self.assertFalse(bed['availability_forecast_known'])
        self.assertEqual(bed['available_minute'], 10)
        self.assertFalse(bed_fits(self.e.state, bed, self.patient('DEMO-014'), 60, 180))

    def test_unknown_forecast_cannot_become_bookable_from_numeric_placeholder(self):
        d = self.dataset()
        d['beds'][0]['availability_forecast_known'] = False
        self.action('import', dataset=d)
        bed = self.e.state['beds'][0]
        self.assertFalse(bed_fits(self.e.state, bed, self.patient('DEMO-014'), 1000, 1100))
        self.action('bed_forecast', bed_id='SICU-01', available_minute=100, reason='새로운 퇴실 전망을 관측·검토')
        self.assertTrue(self.e.state['beds'][0]['availability_forecast_known'])

    def test_missing_forecast_is_preserved_as_unknown_on_roundtrip(self):
        d = self.dataset()
        d['beds'][0].pop('available_minute')
        self.action('import', dataset=d)
        self.assertFalse(self.e.state['beds'][0]['availability_forecast_known'])
        again = validate_dataset(export_canonical(self.e.state))
        self.assertFalse(again['beds'][0]['availability_forecast_known'])
