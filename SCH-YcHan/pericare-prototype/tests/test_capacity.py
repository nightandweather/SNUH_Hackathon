"""Bed mix, safe scenario upgrades and supplied-inventory boundaries."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.capacity import BED_REFERENCE
from app.demo import make_demo
from app.engine import Engine
from app.hospital import ensure_hospital
from app.store import Store

ROOT = Path(__file__).resolve().parents[1]


class CapacityTests(unittest.TestCase):
    def test_adult_general_icu_mix_matches_scaled_reference(self):
        s = make_demo()
        self.assertEqual(len(s['ward_beds']), 128)
        self.assertEqual(len(s['beds']), 12)
        self.assertEqual(sum(b['unit'] == 'SICU' for b in s['beds']), 8)
        self.assertEqual(sum(b['unit'] == 'CCU' for b in s['beds']), 4)
        reference_share = BED_REFERENCE['adult_icu_beds'] / (
            BED_REFERENCE['general_beds'] + BED_REFERENCE['adult_icu_beds'])
        self.assertAlmostEqual(len(s['beds']) / (len(s['beds']) + len(s['ward_beds'])), reference_share, places=3)
        self.assertEqual(sum(b['enabled'] for b in s['beds']), 10)
        self.assertEqual(next(b for b in s['beds'] if b['id'] == 'SICU-05')['occupant_id'], '비수술 환자 A')

    def test_supplied_data_without_ward_inventory_does_not_get_default_beds(self):
        s = make_demo()
        s['source'] = 'import'
        s.pop('ward_beds')
        original = copy.deepcopy(s['beds'])
        ensure_hospital(s)
        self.assertEqual(s['ward_beds'], [])
        self.assertEqual(s['beds'], original)

    def test_v5_synthetic_upgrade_archives_occupied_resources_before_new_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + '/migration.db'
            old = make_demo()
            old['runtime_version'] = '5.0'
            old['minute'] = 35
            old['beds'].append({**old['beds'][0], 'id': 'SICU-16', 'occupant_id': 'legacy-occupant'})
            Store(path).save(old)
            e = Engine(path)
            self.assertEqual(len(e.state['beds']), 12)
            self.assertEqual(len(e.state['ward_beds']), 128)
            self.assertEqual(e.state['minute'], 0)
            with e.store.connect() as db:
                archive = json.loads(db.execute('SELECT payload FROM archived_snapshot').fetchone()['payload'])
            self.assertEqual(archive['minute'], 35)
            self.assertTrue(any(b['occupant_id'] == 'legacy-occupant' for b in archive['beds']))

    def test_current_restart_preserves_census_clock_and_occupancy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + '/restart.db'
            e = Engine(path)
            e.mutate('advance', {'minutes': 40})
            before = e.view()
            after = Engine(path).view()
            self.assertEqual(after['minute'], before['minute'])
            self.assertEqual(after['hospital'], before['hospital'])
            self.assertEqual([b['occupant_id'] for b in after['beds']], [b['occupant_id'] for b in before['beds']])

    def test_imported_old_runtime_keeps_its_supplied_inventory_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + '/actual.db'
            e = Engine(path)
            fixture = json.loads((ROOT / 'examples/recorded-replay.json').read_text())
            e.mutate('import', {'dataset': fixture, 'expected_revision': e.state['revision']})
            e.state['runtime_version'] = '5.0'
            supplied = copy.deepcopy(e.state['beds'])
            e.store.save(e.state)
            after = Engine(path)
            self.assertEqual(after.state['source'], 'import')
            self.assertEqual(after.state['beds'], supplied)
            self.assertEqual(after.state['ward_beds'], [])
            with after.store.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM archived_snapshot').fetchone()[0], 0)
