"""End-to-end team workflows over observable synthetic patient courses."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.engine import Engine, AppError, overlap


class ClinicalTeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/team.db'
        self.engine = Engine(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def action(self, name, **body):
        return self.engine.mutate(name, {'expected_revision': self.engine.state['revision'], **body})

    def advance(self, minutes):
        while minutes:
            step = min(minutes, 120)
            self.action('advance', minutes=step)
            minutes -= step

    def log(self, pid=None, kind=None):
        return [e for e in self.engine.state['automation']['log']
                if (pid is None or e['patient_id'] == pid) and (kind is None or e['kind'] == kind)]

    def test_default_team_is_enabled_but_clock_is_paused(self):
        s = self.engine.view()
        self.assertTrue(s['automation']['eligible'])
        self.assertTrue(s['automation']['enabled'])
        self.assertFalse(s['running'])
        self.assertEqual(len(s['automation']['roles']), 6)
        self.assertTrue(all(p['workflow']['label'] for p in s['patients']))

    def test_complete_icu_workflow_without_user_admission_action(self):
        self.action('play', running=True)
        self.advance(120)
        kinds = [e['kind'] for e in self.log('DEMO-004')]
        expected = ['order', 'reservation', 'preparation', 'ready', 'transport', 'admission']
        positions = [kinds.index(k) for k in expected]
        self.assertEqual(positions, sorted(positions))
        admission = self.log('DEMO-004', 'admission')[0]
        patient = next(p for p in self.engine.state['patients'] if p['id'] == 'DEMO-004')
        self.assertGreaterEqual(admission['minute'], patient['actual_end_minute'])
        self.assertGreaterEqual(admission['minute'] - self.log('DEMO-004', 'preparation')[0]['minute'],
                                self.engine.state['policy']['prepare_minutes'])
        self.assertTrue(any(b['occupant_id'] == patient['id'] for b in self.engine.state['beds']))
        self.assertEqual(self.engine.state['automation']['workflows'][patient['id']]['stage'], 'icu_monitoring')
        audit = self.engine.store.audit(10000)
        self.assertTrue(any(a['action'] == 'team_admission' and a['actor'] == 'ICU 책임간호사' for a in audit))
        self.assertFalse(any(a['action'] == 'admit' for a in audit))

    def test_quality_failure_blocks_movement_and_requires_reassessment(self):
        self.action('play', running=True)
        self.advance(5)
        self.action('scenario', patient_id='DEMO-007', kind='artifact')
        self.advance(50)
        self.assertEqual(self.engine.state['automation']['workflows']['DEMO-007']['stage'], 'quality_hold')
        self.assertFalse(self.log('DEMO-007', 'admission'))
        self.assertTrue(self.log('DEMO-007', 'quality'))
        self.action('scenario', patient_id='DEMO-007', kind='clear')
        w = self.engine.state['automation']['workflows']['DEMO-007']
        # Clearing an injection does not erase a recent invalid signal window.
        self.assertEqual(w['stage'], 'quality_hold')
        self.advance(30)
        w = self.engine.state['automation']['workflows']['DEMO-007']
        self.assertEqual(w['stage'], 'doctor_review')
        self.assertTrue(self.log('DEMO-007', 'quality_resolved'))
        self.advance(60)
        self.assertTrue(self.log('DEMO-007', 'admission'))

    def test_bed_shortage_keeps_patient_under_observation(self):
        for bed in self.engine.state['beds']:
            if bed['unit'] == 'SICU' and not bed['occupant_id']:
                bed['enabled'] = False
            elif bed['unit'] == 'SICU':
                bed['available_minute'] = 10000
        self.action('play', running=True)
        self.advance(90)
        self.assertEqual(self.engine.state['automation']['workflows']['DEMO-004']['stage'], 'capacity_wait')
        self.assertTrue(self.log('DEMO-004', 'capacity'))
        self.assertFalse(self.log('DEMO-004', 'admission'))

    def test_actual_icu_discharge_precedes_cleaning_and_reuse(self):
        self.action('play', running=True)
        self.advance(140)
        event = self.log('DEMO-014', 'discharge')[0]
        bed = next(b for b in self.engine.state['beds'] if b['id'] == 'SICU-02')
        self.assertEqual(event['minute'], 140)
        self.assertIsNone(bed['occupant_id'])
        self.assertEqual(bed['available_minute'], 140 + self.engine.state['policy']['cleanup_minutes'])
        self.assertEqual(bed['available_basis'], '실제 퇴실 후 청소')
        self.assertFalse(any('SICU-02' in e['detail'] for e in self.log(kind='cleaned')))
        self.advance(self.engine.state['policy']['cleanup_minutes'])
        self.assertTrue(any('SICU-02' in e['detail'] for e in self.log(kind='cleaned')))

    def test_expired_forecast_never_evicts_unknown_occupant(self):
        bed = next(b for b in self.engine.state['beds'] if b['id'] == 'SICU-05')
        occupant = bed['occupant_id']
        bed['available_minute'] = 1
        self.action('play', running=True)
        self.advance(120)
        bed = next(b for b in self.engine.state['beds'] if b['id'] == 'SICU-05')
        self.assertEqual(bed['occupant_id'], occupant)
        self.assertFalse(any(r['bed_id'] == bed['id'] and r['status'] == 'occupied' for r in self.engine.state['reservations']))

    def test_nurse_reassigns_postoperative_patient_when_reserved_bed_is_blocked(self):
        self.action('play', running=True)
        self.advance(5)
        reservation = next(r for r in self.engine.state['reservations'] if r['patient_id'] == 'DEMO-007')
        blocked_bed = next(b for b in self.engine.state['beds'] if b['id'] == reservation['bed_id'])
        blocked_bed.update(occupant_id='외부 가상 재실 환자', available_minute=10000)
        self.advance(20)
        self.assertFalse(self.log('DEMO-007', 'admission'))
        self.action('bed', bed_id='CCU-04', enabled=True, reason='가상 인력·장비 확인 후 병상 추가 가동')
        self.advance(60)
        reservation = next(r for r in self.engine.state['reservations'] if r['patient_id'] == 'DEMO-007')
        self.assertNotEqual(reservation['bed_id'], blocked_bed['id'])
        self.assertTrue(next(b for b in self.engine.state['beds'] if b['id'] == reservation['bed_id'])['enabled'])
        self.assertEqual(reservation['status'], 'occupied')
        self.assertTrue(self.log('DEMO-007', 'admission'))

    def test_planned_icu_does_not_trigger_readmission_after_stable_discharge(self):
        self.action('play', running=True)
        self.advance(360)
        self.assertTrue(self.log('DEMO-010', 'discharge'))
        self.assertFalse(self.log('DEMO-010', 'admission'))
        patient = next(p for p in self.engine.view()['patients'] if p['id'] == 'DEMO-010')
        self.assertEqual(patient['phase'], 'WARD')
        self.assertFalse(patient['prediction']['features']['planned_icu'])

    def test_same_shift_admissions_never_share_or_overlap_beds(self):
        self.action('play', running=True)
        for _ in range(48):
            self.advance(5)
            s = self.engine.state
            active = [r for r in s['reservations'] if r['status'] in ('confirmed', 'occupied')]
            occupants = [b['occupant_id'] for b in s['beds'] if b['occupant_id']]
            self.assertEqual(len(occupants), len(set(occupants)))
            for i, left in enumerate(active):
                for right in active[i + 1:]:
                    if left['bed_id'] == right['bed_id']:
                        self.assertFalse(overlap(left['start'], left['end'] + s['policy']['cleanup_minutes'],
                                                 right['start'], right['end']))
            stages = [w['stage'] for w in s['automation']['workflows'].values()]
            self.assertLessEqual(stages.count('preparing'), 2)
            self.assertLessEqual(stages.count('transporting'), 2)

    def test_imported_data_cannot_enable_automatic_team(self):
        dataset = json.loads((Path(__file__).parent.parent / 'examples/canonical-data.json').read_text())
        self.action('import', dataset=dataset)
        self.assertFalse(self.engine.view()['automation']['eligible'])
        self.assertFalse(self.engine.state['automation']['enabled'])
        with self.assertRaises(AppError):
            self.action('automation', enabled=True)
        self.advance(5)
        self.assertFalse(self.log(kind='admission'))

    def test_restart_preserves_workflows_and_patient_handoff_records(self):
        self.action('play', running=True)
        self.advance(30)
        before = copy.deepcopy(self.engine.state['automation'])
        restarted = Engine(self.path)
        self.assertFalse(restarted.state['running'])
        self.assertEqual(restarted.state['automation'], before)
        self.assertTrue(any(a['action'].startswith('team_') for a in restarted.store.audit(10000)))

    def test_team_decisions_use_only_observed_evidence(self):
        self.action('play', running=True)
        self.advance(360)
        for event in self.log():
            evidence = event['evidence']
            if evidence:
                self.assertLessEqual(evidence['as_of_minute'], event['minute'])
                if evidence['observation_minute'] is not None:
                    self.assertLessEqual(evidence['observation_minute'], evidence['as_of_minute'])
        public = json.dumps(self.engine.view())
        self.assertNotIn('trajectories', public)
        self.assertNotIn('truth_icu', public)

    def test_batch_and_small_steps_produce_same_clinical_decisions(self):
        other = Engine(self.tmp.name + '/small.db')
        self.action('play', running=True)
        other.mutate('play', {'running': True})
        self.advance(120)
        for _ in range(24):
            other.mutate('advance', {'minutes': 5})
        self.assertEqual(self.engine.state['automation']['log'], other.state['automation']['log'])
        self.assertEqual(self.engine.state['automation']['counters'], other.state['automation']['counters'])

    def test_manual_mode_retains_control_and_can_be_reenabled(self):
        self.action('automation', enabled=False)
        self.advance(120)
        self.assertFalse(self.log(kind='admission'))
        self.assertEqual(self.engine.state['automation']['counters']['orders'], 0)
        self.action('automation', enabled=True)
        self.advance(60)
        self.assertTrue(self.log(kind='admission'))

    def test_planned_care_is_retained_when_model_threshold_is_high(self):
        self.action('policy', policy={'icu_threshold': .95})
        self.action('play', running=True)
        self.advance(90)
        self.assertTrue(self.log('DEMO-007', 'admission'))
        order = self.log('DEMO-007', 'order')[0]
        self.assertLess(order['evidence']['icu_probability'], .95)

    def test_failed_commit_does_not_partially_apply_team_events(self):
        self.action('play', running=True)
        before = copy.deepcopy(self.engine.state)
        audit = self.engine.store.audit(10000)
        with patch.object(self.engine.store, 'save', side_effect=RuntimeError('test failed commit')):
            with self.assertRaises(RuntimeError):
                self.advance(60)
        self.assertEqual(self.engine.state, before)
        self.assertEqual(self.engine.store.audit(10000), audit)
        self.assertNotIn('_audit_buffer', self.engine.state)


if __name__ == '__main__':
    unittest.main()
