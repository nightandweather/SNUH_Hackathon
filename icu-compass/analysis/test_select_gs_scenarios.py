"""Synthetic source-only scenario selection checks; no clinical files required."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import select_gs_scenarios as selection


def case(hospital='001', index=1, partition='268', scenario='surgery_ended_before_icu_24h'):
    evidence = {
        'surgery_ended_before_icu_24h': {'table': 'PROCEDUREEVENTS', 'at': '2020-01-01T00:30:00', 'item': 'operation'},
        'ed_within_24h_before_icu': {'table': 'ADMISSIONS', 'at': '2020-01-01T00:00:00', 'item': 'EDREGTIME/EDOUTTIME'},
        'surgery_record_during_icu': {'table': 'PROCEDUREEVENTS', 'at': '2020-01-01T03:00:00', 'item': 'operation'},
        'death_during_icu': {'table': 'ADMISSIONS', 'at': '2020-01-01T07:00:00', 'item': 'DEATHTIME'},
    }
    event = {**evidence[scenario], 'partition': partition}
    return {'hospital': hospital, 'SUBJECT_ID': f'PRIVATE_SUBJECT_{hospital}_{index}',
            'HADM_ID': f'PRIVATE_ADMISSION_{hospital}_{index}', 'STAY_ID': str(index),
            'icu_in': '2020-01-01T01:00:00', 'icu_out': '2020-01-01T09:00:00',
            'source_partitions': partition, 'FIRST_CAREUNIT': 'SICU', 'LAST_CAREUNIT': 'SICU',
            'gs_entry_evidence': {'table': 'SERVICES', 'at': '2020-01-01T00:00:00',
                                  'code': 'GS', 'source_partitions': [partition]},
            'evidence': {scenario: event}, 'scenario_labels': [selection.SCENARIOS[scenario]]}


class GSScenarioTests(unittest.TestCase):
    def test_source_and_time_validation(self):
        row = case()
        evidence = {'surgery_ended_before_icu_24h': {'table': 'PROCEDUREEVENTS', 'at': '2019-12-31T00:59:59'},
                    'death_during_icu': {'table': 'ADMISSIONS', 'at': row['icu_out']},
                    'surgery_record_during_icu': {'table': 'LABEVENTS', 'at': row['icu_in']},
                    'ed_within_24h_before_icu': {'table': 'ADMISSIONS', 'at': '2020-01-01T00:00:00'}}
        validated = selection.verified_evidence(row, evidence)
        self.assertEqual(list(validated), ['ed_within_24h_before_icu'])
        self.assertEqual(validated['ed_within_24h_before_icu']['relative_minute'], -60)
        self.assertEqual(selection.SCENARIOS['ed_within_24h_before_icu'], 'ed_within_24h_before_icu')

    def test_representative_coverage_balance_unique_patients_and_determinism(self):
        kinds = list(selection.SCENARIOS)[1:]
        candidates = [case(hospital, index, scenario=kinds[(index - 1) % 4])
                      for hospital in ('001', '003', '009') for index in range(1, 9)]
        # A duplicate patient with a separate stay cannot consume another slot.
        duplicate = {**candidates[0], 'STAY_ID': '100'}
        candidates.append(duplicate)
        chosen = selection.select_cases(candidates, 12)
        reversed_chosen = selection.select_cases(list(reversed(candidates)), 12)
        self.assertEqual([selection.key(r) for r in chosen], [selection.key(r) for r in reversed_chosen])
        self.assertEqual(len({(r['hospital'], r['SUBJECT_ID']) for r in chosen}), 12)
        self.assertEqual({h: sum(r['hospital'] == h for r in chosen) for h in ('001', '003', '009')},
                         {'001': 4, '003': 4, '009': 4})
        self.assertEqual({s for row in chosen for s in row['scenario_labels']}, set(selection.SCENARIOS.values()) - {'cpr_during_icu'})
        death = next(row for row in chosen if row['selected_for'] == 'icu_death')
        self.assertEqual(death['preferred_checkpoint']['at'], '2020-01-01T06:00:00')
        self.assertTrue(death['scenario_labels_retrospective'])
        self.assertIn('future', death['preferred_checkpoint']['policy'])

    def test_no_evidence_is_not_invented(self):
        row = {**case(), 'evidence': {}, 'scenario_labels': []}
        self.assertEqual(selection.select_cases([row]), [])

    def test_optional_cpr_requires_exact_identity_interval_and_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for h in selection.gs.HOSPITALS:
                (root / h).mkdir()
                (root / h / 'candidate_evidence.json').write_text('[]')
            row = case()
            valid = {**row, 'events': [{'kind': 'cpr_start', 'table': 'DATETIMEEVENTS',
                     'item': '001D_7284_11320', 'at': '2020-01-01T02:00:00'}]}
            invalid = {**valid, 'HADM_ID': 'PRIVATE_WRONG_ADMISSION'}
            optional = root / 'optional.json'
            optional.write_text(json.dumps({'summary': {'dataset': 'kmimic-emr-001', 'partition': '268'},
                                            'cases': [valid, invalid]}))
            _, audit = selection.add_evidence([row], root, optional)
            self.assertEqual(audit['verified_cpr_stays'], 1)
            self.assertIn('cpr_start', row['evidence'])
            self.assertEqual(row['evidence']['cpr_start']['partition'], '268')

    def test_end_to_end_strict_count_private_outputs_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            datasets, extraction, out = base / 'datasets', base / 'extraction', base / 'out'
            extraction.mkdir()
            cohort, private_ids = [], []
            kinds = list(selection.SCENARIOS)[1:]
            for h_index, hospital in enumerate(selection.gs.HOSPITALS):
                directory = datasets / ('kmimic-emr-' + hospital) / '268'
                directory.mkdir(parents=True)
                hospital_extract = extraction / hospital
                hospital_extract.mkdir()
                (hospital_extract / 'audit.json').write_text(json.dumps({'files': [
                    {'file': f'kmimic-emr-{hospital}/268/ICUSTAYS.csv', 'status': 'ok'}]}))
                evidence, services = [], []
                for index in (1, 2):
                    row = case(hospital, index, scenario=kinds[(h_index + index) % 4])
                    private_ids.extend((row['SUBJECT_ID'], row['HADM_ID']))
                    evidence.append({'hospital': hospital, 'key': list(selection.key(row)[1:]), 'evidence': row['evidence']})
                    cohort.append({k: v for k, v in row.items() if k not in ('evidence', 'scenario_labels', 'gs_entry_evidence')})
                    services.append([row['SUBJECT_ID'], row['HADM_ID'], '2020-01-01T00:00:00', '',
                                     'GSL' if hospital == '004' else 'GS'])
                (hospital_extract / 'candidate_evidence.json').write_text(json.dumps(evidence))
                with (directory / 'SERVICES.csv').open('w', newline='') as handle:
                    writer = csv.writer(handle)
                    writer.writerow(['SUBJECT_ID', 'HADM_ID', 'TRANSFERTIME', 'PREV_SERVICE', 'CURR_SERVICE'])
                    writer.writerows(services)
            with (extraction / 'surgical_icu_stays.csv').open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(cohort[0]))
                writer.writeheader()
                writer.writerows(cohort)
            env = {**os.environ, 'KMIMIC_ROOT': str(datasets), 'KMIMIC_EXTRACTION': str(extraction),
                   'KMIMIC_GS_SELECTION_OUT': str(out), 'KMIMIC_CPR_CANDIDATES': str(base / 'missing.json'),
                   'KMIMIC_EXPECTED_GS': '12', 'KMIMIC_EXPECTED_COHORT': '14',
                   'KMIMIC_EXPECTED_PARTITIONS': '7', 'KMIMIC_GS_PREFIX': '1'}
            run = subprocess.run([sys.executable, selection.__file__], env=env, capture_output=True, text=True, check=True)
            selected = json.loads((out / 'selected_cases.json').read_text())
            self.assertEqual(selected['cohort_counts']['gs_at_entry_stays'], 12)
            self.assertEqual(len(selected['cases']), 12)
            self.assertNotIn('004', selected['selected_hospitals'])
            self.assertTrue(all(row['gs_entry_evidence']['code'] == 'GS' for row in selected['cases']))
            self.assertTrue(all(identifier not in run.stdout + run.stderr for identifier in private_ids))
            for name in ('gs_at_entry_stays.csv', 'selected_cases.json', 'summary.json'):
                self.assertEqual((out / name).stat().st_mode & 0o777, 0o600)
            with (out / 'gs_at_entry_stays.csv').open(encoding='utf-8-sig') as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 12)
            failed_out = base / 'mismatch'
            failed = subprocess.run([sys.executable, selection.__file__], env={**env,
                                     'KMIMIC_GS_SELECTION_OUT': str(failed_out), 'KMIMIC_EXPECTED_GS': '13'},
                                    capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse((failed_out / 'selected_cases.json').exists())
            self.assertFalse((failed_out / 'gs_at_entry_stays.csv').exists())


if __name__ == '__main__':
    unittest.main()
