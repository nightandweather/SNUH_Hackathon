"""Synthetic fixtures exercise patient boundaries and temporal availability."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('gs_pool', Path(__file__).with_name('build_gs_board_pool.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class GsPoolTests(unittest.TestCase):
    def selected(self):
        return {'hospital': '001', 'SUBJECT_ID': '1', 'HADM_ID': '10', 'STAY_ID': '100',
                'icu_in': '2020-01-01T00:00:00', 'icu_out': '2020-01-03T00:00:00',
                'source_partition_list': ['1'], 'case_alias': 'GS-CASE-001',
                'gs_entry_evidence': {'table': 'SERVICES', 'at': '2019-12-31T23:00:00', 'code': 'GS'},
                'preferred_checkpoint': {'minute': 60}, 'scenario_labels': ['postoperative_icu'],
                'evidence': {'death_during_icu': {'at': '2020-01-02T00:00:00', 'table': 'ADMISSIONS', 'item': 'DEATHTIME'}}}

    def row(self, **changes):
        return {'SUBJECT_ID': '1', 'HADM_ID': '10', 'STAY_ID': '100', 'ITEMID': '001C_1021_25105',
                'CHARTTIME': '2020-01-01T00:05:00', 'STORETIME': '2020-01-01T00:10:00',
                'VALUE': '90', 'VALUEUOM': 'bpm', **changes}

    def build(self, tables=None, dictionaries=None):
        return m.build_case(self.selected(), tables or {}, dictionaries or {'D_ITEMS': {}, 'D_LABITEMS': {}, 'D_TESTITEMS': {}},
                            m.KNOWN_001, {}, 14321)

    def test_no_future_or_late_entry_carry(self):
        pool = self.build({'CHARTEVENTS': [self.row(), self.row(CHARTTIME='2020-01-01T00:06:00', STORETIME='2020-01-01T02:00:00', VALUE='120')]})
        self.assertIsNone(pool['series']['hr'][1])
        self.assertEqual(pool['series']['hr'][2], 90)
        self.assertIsNone(pool['series']['hr'][8])
        self.assertIsNone(pool['series']['hr'][24])

    def test_conflicting_same_time_is_unknown(self):
        pool = self.build({'CHARTEVENTS': [self.row(VALUE='90'), self.row(VALUE='120')]})
        self.assertIsNone(pool['series']['hr'][2])

    def test_cross_stay_and_admission_excluded(self):
        pool = self.build({'CHARTEVENTS': [self.row(STAY_ID='101'), self.row(HADM_ID='11')]})
        self.assertEqual(pool['raw_observations'], [])

    def test_missing_storetime_does_not_become_fact(self):
        pool = self.build({'CHARTEVENTS': [self.row(STORETIME=''), self.row(ITEMID='001C_1207_22360', VALUE='ON', STORETIME='')]})
        self.assertEqual(pool['raw_observations'], [])
        self.assertEqual(pool['device_events'], {})

    def test_positive_device_and_cpr_keep_chart_availability(self):
        pool = self.build({'CHARTEVENTS': [self.row(ITEMID='001C_1093_22025', VALUE='4.0', VALUEUOM='L/min')],
                          'DATETIMEEVENTS': [self.row(ITEMID='001D_7284_11320', VALUE='심폐소생술 시작함')]})
        self.assertEqual(pool['device_events']['ecmo_crrt'][0]['chart_minute'], 5)
        self.assertEqual(pool['device_events']['ecmo_crrt'][0]['available_minute'], 10)
        self.assertEqual(pool['device_events']['cpr'][0]['event_minute'], 5)

    def test_accessory_label_alone_is_not_presence(self):
        dictionaries = {'D_ITEMS': {'LINE': {'LABEL': 'central venous catheter'}}, 'D_LABITEMS': {}, 'D_TESTITEMS': {}}
        pool = self.build({'CHARTEVENTS': [self.row(ITEMID='LINE', VALUE='8'), self.row(ITEMID='LINE', VALUE='ON')]}, dictionaries)
        self.assertEqual(len(pool['device_events']['accessories']), 1)
        self.assertTrue(pool['device_events']['accessories'][0]['active'])

    def test_tests_are_metadata_not_images_or_reports(self):
        pool = self.build({'TESTEVENTS': [self.row(ITEMID='CT', TESTEVENT_ID='1', FILE_PATH='/private/scan')]},
                          {'D_ITEMS': {}, 'D_LABITEMS': {}, 'D_TESTITEMS': {'CT': {'LABEL': 'CT chest'}}})
        record = pool['clinical_detail']['imaging_tests'][0]
        self.assertTrue(record['file_reference_present'])
        self.assertFalse(record['file_access_verified'])
        self.assertEqual(record['report_status'], 'not_linked')
        self.assertNotIn('FILE_PATH', str(pool))
        self.assertNotIn('/private/scan', str(pool))

    def test_selection_rejects_gs_subcode(self):
        row = self.selected()
        row['gs_entry_evidence']['code'] = 'GSL'
        with self.assertRaises(ValueError):
            m.build_case(row, {}, {}, {}, {}, 14321)

    def test_chest_pain_and_apical_are_not_xrays(self):
        for label in ('Chest pain assessment', 'Chest apical pulse'):
            pool = self.build({'TESTEVENTS': [self.row(ITEMID='T', TESTEVENT_ID='1')]},
                              {'D_ITEMS': {}, 'D_LABITEMS': {}, 'D_TESTITEMS': {'T': {'LABEL': label}}})
            self.assertEqual(pool['clinical_detail']['imaging_tests'][0]['modality'], 'unclassified')

    def test_event_labels_remain_retrospective(self):
        pool = self.build()
        self.assertTrue(pool['gs_selection']['scenario_labels_retrospective'])
        self.assertEqual(pool['gs_selection']['scenario_events'][0]['availability_status'], 'source_event_time_only_not_model_fact')
        self.assertNotIn('death', str(pool['clinical_detail']))

    def test_selected_rows_exact_composite_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.csv'
            path.write_text('SUBJECT_ID,HADM_ID,ITEMID,VALUE\n1,10,X,1\n1,11,X,2\n2,10,X,3\n1.0,10.0,Y,4\n')
            rows = list(m.selected_rows(path, {('1', '10')}, 'CHARTEVENTS', {'X'}))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['VALUE'], '1')

    def test_grid_is_strictly_before_actual_icu_exit(self):
        points = [{'available_minute': 60, 'chart_minute': 60, 'value': 80, 'variable': 'hr'}]
        series, _ = m.resample(points, 61, 5, 61)
        self.assertEqual(len(series['hr']), 13)
        self.assertEqual(series['hr'][-1], 80)
        series, _ = m.resample(points, 60, 5, 60)
        self.assertEqual(len(series['hr']), 12)
        self.assertTrue(all(v is None for v in series['hr']))

    def test_replay_cap_endpoint_allowed_only_within_stay(self):
        series, _ = m.resample([], 1440, 5, 2880)
        self.assertEqual(len(series['hr']), 289)

    def test_exit_time_records_and_late_store_excluded(self):
        selected = self.selected()
        selected['icu_out'] = '2020-01-01T01:01:00'
        selected['preferred_checkpoint']['minute'] = 61
        at_exit = self.row(CHARTTIME=selected['icu_out'], STORETIME=selected['icu_out'], STAY_ID='')
        late = self.row(STORETIME=selected['icu_out'])
        tables = {'CHARTEVENTS': [at_exit, late], 'LABEVENTS': [at_exit], 'TESTEVENTS': [at_exit],
                  'DATETIMEEVENTS': [{**at_exit, 'ITEMID': '001D_7284_11320', 'VALUE': '심폐소생술 시작함'}]}
        pool = m.build_case(selected, tables, {'D_ITEMS': {}, 'D_LABITEMS': {}, 'D_TESTITEMS': {}}, m.KNOWN_001, {}, 14321)
        self.assertEqual(len(pool['series']['hr']), 13)
        self.assertEqual(pool['raw_observations'], [])
        self.assertEqual(pool['device_events'], {})
        self.assertEqual(pool['clinical_detail']['labs'], [])
        self.assertEqual(pool['clinical_detail']['imaging_tests'], [])
        self.assertEqual(pool['initial_minute'], 60)


if __name__ == '__main__':
    unittest.main()
