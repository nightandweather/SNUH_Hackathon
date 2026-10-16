import copy
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_full_gs_monthly as module


def plan(*days):
    return [{'day': index + 1, 'sourceRow': index + 2, 'beds':
             [{'status': value[0], 'event': value[1]} for value in day] +
             [{'status': 'empty', 'event': ''} for _ in range(8 - len(day))]}
            for index, day in enumerate(days)]


def patient(subject, los=2, kinds=('surgery_ended_before_icu_24h',), hospital='001', stay='1'):
    start = datetime(2020, 1, 2)
    tables = {'surgery_ended_before_icu_24h': 'PROCEDUREEVENTS', 'surgery_record_during_icu': 'PROCEDUREEVENTS',
              'death_during_icu': 'ADMISSIONS', 'ed_within_24h_before_icu': 'ADMISSIONS', 'cpr_start': 'DATETIMEEVENTS'}
    evidence = {kind: {'table': tables[kind], 'at': (start + timedelta(hours=1 if kind in ('death_during_icu', 'surgery_record_during_icu', 'cpr_start') else -1)).isoformat(),
                       'partition': '268', 'item': '001D_7284_11320'} for kind in kinds}
    return {'hospital': hospital, 'SUBJECT_ID': subject, 'HADM_ID': 'admission-' + subject, 'STAY_ID': stay,
            'icu_in': start.isoformat(), 'icu_out': (start + timedelta(days=los)).isoformat(), 'source_partitions': '268',
            'gs_entry_at': (start - timedelta(hours=2)).isoformat(), 'gs_entry_code': 'GS', 'gs_entry_source_partitions': '268',
            'gs_entry_evidence': {'table': 'SERVICES', 'code': 'GS', 'at': (start - timedelta(hours=2)).isoformat()},
            'evidence': evidence}


class FullMonthlyTest(unittest.TestCase):
    def test_los_preference_and_no_patient_reuse(self):
        rows = plan([('red', 'OP')], [('green', 'GW')], [('red', 'OP')], [('green', 'GW')])
        a, b = patient('private-A', 2), patient('private-B', 9)
        more_stay = patient('private-A', 2, stay='2')
        result, used = module.allocate_scope(module.prepare_candidates([b, a, more_stay]), rows, 'V')
        matches = result['episodes']
        self.assertEqual(matches[0]['source_identity']['SUBJECT_ID'], 'private-A')
        self.assertEqual(len(used), 2)
        self.assertEqual(len({e['source_identity']['SUBJECT_ID'] for e in matches}), 2)
        self.assertEqual(matches[0]['absolute_los_difference_days'], 0)
        self.assertFalse(matches[0]['plan_timing_verified'])

    def test_cpr_unknown_death_required_and_gw_incompatible(self):
        rows = plan([('red', 'CPR'), ('red', 'OP')], [('red', 'Death'), ('green', 'GW')])
        death = patient('D', kinds=('surgery_ended_before_icu_24h', 'death_during_icu', 'cpr_start'))
        surgery = patient('S')
        result, _ = module.allocate_scope(module.prepare_candidates([death, surgery]), rows, 'V')
        d = result['days'][0]['beds'][0]
        self.assertEqual(d['matched_criteria'], ['DEATH'])
        self.assertEqual(d['unconfirmed_criteria'], ['CPR'])
        self.assertFalse(d['event_verified'])
        self.assertEqual(result['episodes'][1]['source_identity']['SUBJECT_ID'], 'S')
        only_surgery, _ = module.allocate_scope(module.prepare_candidates([surgery]), rows, 'V')
        self.assertIsNone(only_surgery['days'][0]['beds'][0]['case_alias'])

    def test_unknown_only_no_matches_and_continuation_preserved(self):
        rows = plan([('red', 'AE'), ('red', 'OR'), ('red', 'CPR'), ('red', 'OP'), ('yellow', '')],
                    [('blue', ''), ('blue', ''), ('green', 'GW'), ('green', 'GW')])
        result, _ = module.allocate_scope(module.prepare_candidates([patient('A')]), rows, 'V')
        self.assertEqual(result['summary']['unlinked'], 3)
        self.assertEqual(result['days'][0]['beds'][3]['case_alias'], result['days'][1]['beds'][3]['case_alias'])
        self.assertEqual(result['days'][0]['beds'][4]['match_status'], 'reserved')
        self.assertEqual(result['days'][0]['beds'][5]['match_status'], 'empty')

    def test_global_disjoint_subjects_and_input_immutability(self):
        candidates = [patient('A'), patient('B'), patient('A', hospital='004'), patient('B', hospital='004')]
        rows = plan([('red', 'OP')])
        before = copy.deepcopy((candidates, rows))
        catalog = module.build_catalog(candidates, rows)
        identities = [(e['source_identity']['hospital'], e['source_identity']['SUBJECT_ID'])
                      for s in catalog['scopes'].values() for e in s['episodes'] if e['source_identity']]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual((candidates, rows), before)
        self.assertEqual(catalog['summary']['unique_patients'], 3)

    def test_cached_evidence_exact_join_and_strict_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = patient('A')
            source = {k: v for k, v in original.items() if k not in ('evidence', 'gs_entry_evidence')}
            path = root / 'cohort.csv'
            with path.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, source.keys())
                writer.writeheader()
                writer.writerow(source)
            loaded = module.load_cohort(path, 1)
            (root / '001').mkdir()
            (root / '001/candidate_evidence.json').write_text(json.dumps([
                {'hospital': '001', 'key': ['A', 'wrong-admission', '1'], 'evidence': {'death_during_icu': {'table': 'ADMISSIONS', 'at': '2020-01-02T01:00:00'}}},
                {'hospital': '001', 'key': ['A', 'admission-A', '1'], 'evidence': original['evidence']}]))
            module.selection.add_evidence(loaded, root, root / 'missing-cpr')
            self.assertNotIn('death_during_icu', loaded[0]['evidence'])
            self.assertIn('surgery_ended_before_icu_24h', loaded[0]['evidence'])
            with self.assertRaises(ValueError):
                module.load_cohort(path, 14321)

    def test_xlsx_template_unchanged_clones_keep_fill_and_no_raw_keys(self):
        rows = plan([('red', 'OP'), ('yellow', '')], [('green', 'GW')])
        rows.append({'day': None, 'sourceRow': 4, 'beds': [{'status': 'empty', 'event': ''}] * 8})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template, output = root / 'original.xlsx', root / 'out.xlsx'
            package = module.fallback_package(rows)
            with zipfile.ZipFile(template, 'w') as archive:
                for name, content in package.items():
                    archive.writestr(name, content)
            source_bytes = template.read_bytes()
            parsed = module.workbook_rows(template)
            self.assertEqual(parsed, rows)
            catalog = module.build_catalog([patient('SECRET-PATIENT'), patient('OTHER-PATIENT')], rows)
            module.export_xlsx(output, catalog, rows, template)
            self.assertEqual(template.read_bytes(), source_bytes)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with zipfile.ZipFile(output) as archive:
                self.assertIn(b'<Types xmlns=', archive.read('[Content_Types].xml'))
                self.assertIn(b'<Relationships xmlns=', archive.read('xl/_rels/workbook.xml.rels'))
                self.assertEqual(archive.read('xl/worksheets/sheet1.xml'), package['xl/worksheets/sheet1.xml'])
                all_text = b''.join(archive.read(name) for name in archive.namelist() if name.endswith('.xml'))
                self.assertNotIn(b'SECRET-PATIENT', all_text)
                self.assertNotIn(b'SUBJECT_ID', all_text)
                self.assertIn(b'VIRTUAL-P001', all_text)
                clone = ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
                style = int(clone.find('.//' + module.tag('c') + '[@r="B2"]').get('s'))
                xfs = ET.fromstring(archive.read('xl/styles.xml')).find(module.tag('cellXfs'))
                self.assertEqual(xfs[style].get('fillId'), '2')
            with self.assertRaises(ValueError):
                module.export_xlsx(template, catalog, rows, template)


if __name__ == '__main__':
    unittest.main()
