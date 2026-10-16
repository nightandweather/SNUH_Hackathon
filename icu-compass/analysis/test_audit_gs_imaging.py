"""Synthetic imaging-label and dictionary-conflict regression tests."""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_gs_imaging as audit


def write_csv(path, columns, rows):
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


class ImagingAuditTests(unittest.TestCase):
    def test_cxr_projection_tokens_do_not_match_symptom_words(self):
        for label in ('CHEST PAIN', 'Chest apical examination', 'Chest PALPATION', 'CXRAY'):
            self.assertIsNone(audit.label_kind(label), label)
        for label in ('Chest PA', 'CHEST (AP)', 'Chest PA and lateral', 'Chest X-ray', 'CXR'):
            self.assertEqual(audit.label_kind(label), 'cxr_related', label)
        self.assertEqual(audit.label_kind('Chest CT with contrast'), 'ct_related')

    def test_dictionary_nonimaging_conflicts_excluded_and_stay_interval_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'kmimic-emr-001' / '268'
            folder.mkdir(parents=True)
            write_csv(folder / 'D_TESTITEMS.csv', ['ITEMID', 'LABEL', 'CATEGORY', 'EDI_CODE'], [
                ['A', 'Chest CT', '', ''], ['A', 'Unrelated chemistry test', '', ''],
                ['B', 'Chest CT', '', ''], ['B', 'Chest CT', '', ''],
                ['C', 'Chest PA', '', ''], ['D', 'Chest CT', '', ''], ['D', 'Chest PA', '', ''],
                ['E', 'CHEST PAIN', '', ''],
            ])
            columns = ['TESTEVENT_ID', 'SUBJECT_ID', 'HADM_ID', 'ITEMID', 'CHARTTIME', 'STORETIME', 'FILE_PATH', 'STAY_ID']
            rows = [[str(i), 'synthetic-patient', 'synthetic-admission', item, '2020-01-01T02:00:00',
                     '2020-01-01T03:00:00', 'synthetic-reference', '1'] for i, item in enumerate('ABCDE')]
            rows.extend([
                ['wrong-stay', 'synthetic-patient', 'synthetic-admission', 'B', '2020-01-01T02:00:00', '', '', '2'],
                ['at-exit', 'synthetic-patient', 'synthetic-admission', 'C', '2020-01-01T04:00:00', '', '', '1'],
            ])
            write_csv(folder / 'TESTEVENTS.csv', columns, rows)
            admissions = {('synthetic-patient', 'synthetic-admission'): [
                ('1', audit.dt('2020-01-01T01:00:00'), audit.dt('2020-01-01T04:00:00'))]}
            with patch.object(audit, 'ROOT', root):
                receipt, matched = audit.read_file('001', '268', admissions)
            self.assertEqual(receipt['status'], 'ok')
            self.assertEqual(receipt['ambiguous_dictionary_items'], 2)
            self.assertEqual(receipt['matched_rows'], 2)
            self.assertEqual({row[2][0] for row in matched}, {'ct_related', 'cxr_related'})
            self.assertEqual({row[2][1] for row in matched}, {'B', 'C'})
            self.assertTrue(all('synthetic-reference' not in str(row) for row in matched))


if __name__ == '__main__':
    unittest.main()
