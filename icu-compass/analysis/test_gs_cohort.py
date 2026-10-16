"""Synthetic-only checks for GS intervals, conservative exclusions and output privacy."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('gs', Path(__file__).with_name('count_gs_cohort.py'))
gs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gs)


def time(hour):
    return gs.dt(f'2020-01-01 {hour:02d}:00:00')


class GSAttributionTests(unittest.TestCase):
    def setUp(self):
        # Default-mode regressions must stay strict even in a prefix-mode shell.
        strict_mode = patch.object(gs, 'PREFIX_MODE', False)
        strict_mode.start()
        self.addCleanup(strict_mode.stop)

    def test_service_change_and_half_open_boundary(self):
        result = gs.classify(time(1), time(3), {time(0): {'GS'}, time(2): {'NS'}})
        self.assertEqual(result, dict(zip(gs.CRITERIA, (True, True, False))))
        result = gs.classify(time(1), time(3), {time(0): {'NS'}, time(3): {'GS'}})
        self.assertEqual(result, dict.fromkeys(gs.CRITERIA, False))

    def test_unknown_initial_period_and_conflicting_timestamp(self):
        result = gs.classify(time(1), time(4), {time(2): {'GS'}})
        self.assertEqual(result, dict(zip(gs.CRITERIA, (None, True, None))))
        result = gs.classify(time(1), time(4), {time(0): {'GS', 'NS'}, time(3): {'GS'}})
        self.assertEqual(result, dict(zip(gs.CRITERIA, (None, True, None))))

    def test_invalid_time_excludes_entire_admission(self):
        result = gs.classify(time(1), time(4), {time(0): {'GS'}}, invalid_time=True)
        self.assertEqual(result, dict.fromkeys(gs.CRITERIA))

    def test_duplicate_event_and_literal_code(self):
        self.assertEqual(gs.ident('123.0'), '123')
        self.assertEqual(gs.ident('abc.0'), 'abc.0')
        self.assertEqual(gs.classify(time(1), time(4), {time(0): {'GS', 'GS'}}),
                         dict.fromkeys(gs.CRITERIA, True))
        self.assertEqual(gs.classify(time(1), time(4), {time(0): {'gs'}}),
                         dict.fromkeys(gs.CRITERIA, False))

    def test_prefix_mode_is_opt_in_and_retains_uncertainty(self):
        self.assertTrue(gs.is_gs('GS'))
        self.assertTrue(all(not gs.is_gs(code) for code in ('GSL', 'GSA', 'GSV', 'GSS', 'GSC', 'gs', 'AGS')))
        self.assertEqual(gs.classify(time(1), time(4), {time(0): {'GSL'}, time(2): {'GSA'}}),
                         dict.fromkeys(gs.CRITERIA, False))
        with patch.object(gs, 'PREFIX_MODE', True):
            self.assertTrue(all(gs.is_gs(code) for code in ('GS', 'GSL', 'GSA', 'GSV', 'GSS', 'GSC')))
            self.assertTrue(all(not gs.is_gs(code) for code in ('gs', 'AGS', 'NS', '')))
            # Last known family service extends to ICU exit; a family-to-family
            # change does not interrupt coverage in this explicitly broader mode.
            self.assertEqual(gs.classify(time(1), time(4), {time(0): {'GSL'}, time(2): {'GSA'}}),
                             dict.fromkeys(gs.CRITERIA, True))
            # A conflicting timestamp remains unknown, even within the GS family.
            self.assertEqual(gs.classify(time(1), time(4), {time(0): {'GS', 'GSL'}}),
                             dict.fromkeys(gs.CRITERIA))
            self.assertEqual(gs.classify(time(1), time(4), {time(0): {'NS'}, time(4): {'GSL'}}),
                             dict.fromkeys(gs.CRITERIA, False))
        self.assertFalse(gs.is_gs('GSL'))

    def test_incomplete_hospital_coverage_cannot_attribute(self):
        rows = [{'subject': 'synthetic', 'admission': 'a', 'start': time(1), 'end': time(4)}]
        result = gs.count(rows, {('synthetic', 'a'): {time(0): {'GS'}}}, set(), False)
        self.assertEqual(result['excluded_incomplete_coverage_stays'], 1)
        self.assertEqual(result['criteria']['gs_during_icu']['unknown']['icu_stays'], 1)

    def test_whole_script_dedup_counts_and_no_identifier_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, extraction, out = base / 'datasets', base / 'extraction', base / 'output'
            extraction.mkdir()
            cohort_rows, identifiers = [], []
            for hospital in gs.HOSPITALS:
                subject, admission = 'PRIVATE_PATIENT_' + hospital, 'PRIVATE_ADMISSION_' + hospital
                if hospital in ('003', '004'):
                    subject = 'PRIVATE_PATIENT_SAME_ID_DIFFERENT_HOSPITALS'
                identifiers.extend((subject, admission))
                cohort_rows.append({'hospital': hospital, 'SUBJECT_ID': subject, 'HADM_ID': admission,
                                    'STAY_ID': '1', 'icu_in': time(1).isoformat(), 'icu_out': time(4).isoformat()})
                folder = root / ('kmimic-emr-' + hospital) / '268'
                folder.mkdir(parents=True)
                code = {'001': 'GS', '003': 'GSL', '004': 'GSA', '005': 'AGS'}.get(hospital, 'NS')
                service_rows = [[subject, admission, time(0).isoformat(), '', code]]
                if hospital == '001':
                    service_rows *= 2
                    cohort_rows.append({**cohort_rows[-1], 'STAY_ID': '2'})
                    unknown_subject, unknown_admission = 'PRIVATE_UNKNOWN', 'PRIVATE_UNKNOWN_ADMISSION'
                    identifiers.extend((unknown_subject, unknown_admission))
                    cohort_rows.append({**cohort_rows[-1], 'SUBJECT_ID': unknown_subject,
                                        'HADM_ID': unknown_admission, 'STAY_ID': '3'})
                    service_rows.extend([[unknown_subject, unknown_admission, '', '', 'GS'],
                                         [unknown_subject, unknown_admission, time(0).isoformat(), '', 'GS']])
                if hospital != '006':  # Missing partition must not become a negative GS result.
                    with (folder / 'SERVICES.csv').open('w', newline='') as handle:
                        writer = csv.writer(handle)
                        writer.writerow(['SUBJECT_ID', 'HADM_ID', 'TRANSFERTIME', 'PREV_SERVICE', 'CURR_SERVICE'])
                        writer.writerows(service_rows)
                audit_dir = extraction / hospital
                audit_dir.mkdir()
                (audit_dir / 'audit.json').write_text(json.dumps({'files': [
                    {'file': f'kmimic-emr-{hospital}/268/ICUSTAYS.csv', 'status': 'ok'}]}))
            cohort = extraction / 'surgical_icu_stays.csv'
            with cohort.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(cohort_rows[0]))
                writer.writeheader()
                writer.writerows(cohort_rows)
            environment = {**os.environ, 'KMIMIC_ROOT': str(root), 'KMIMIC_COHORT': str(cohort),
                           'KMIMIC_GS_OUT': str(out), 'KMIMIC_GS_PREFIX': '0'}
            run = subprocess.run([sys.executable, str(Path(gs.__file__))], env=environment,
                                 text=True, capture_output=True, check=True)
            report = json.loads((out / 'summary.json').read_text())
            self.assertEqual(report['cohort_icu_stays'], 9)
            self.assertFalse(report['complete'])
            self.assertEqual(report['hospitals'][0]['duplicate_time_code_events'], 1)
            totals = report['totals']['criteria']['gs_at_icu_entry']
            self.assertEqual(totals['yes'], {'icu_stays': 2, 'distinct_hospital_subjects': 1})
            self.assertEqual(totals['no'], {'icu_stays': 5, 'distinct_hospital_subjects': 5})
            self.assertEqual(totals['unknown']['icu_stays'], 2)
            output = run.stdout + run.stderr + ''.join(path.read_text() for path in out.glob('*.json'))
            strict_summary = (out / 'summary.json').read_bytes()
            prefix_out = base / 'prefix-output'
            prefix_run = subprocess.run([sys.executable, str(Path(gs.__file__))],
                                        env={**environment, 'KMIMIC_GS_PREFIX': '1', 'KMIMIC_GS_OUT': str(prefix_out)},
                                        text=True, capture_output=True, check=True)
            prefix_report = json.loads((prefix_out / 'summary.json').read_text())
            self.assertEqual(prefix_report['service_code'], 'GS* (prefix candidates)')
            self.assertIn('NOT verified', prefix_report['definition'])
            self.assertEqual(prefix_report['totals']['criteria']['gs_at_icu_entry']['yes'],
                             {'icu_stays': 4, 'distinct_hospital_subjects': 3})
            self.assertEqual(prefix_report['totals']['criteria']['gs_at_icu_entry']['unknown']['icu_stays'], 2)
            self.assertEqual((out / 'summary.json').read_bytes(), strict_summary)
            output += prefix_run.stdout + prefix_run.stderr + ''.join(path.read_text() for path in prefix_out.glob('*.json'))
            self.assertTrue(all(identifier not in output for identifier in identifiers))
            self.assertEqual((out / 'summary.json').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
