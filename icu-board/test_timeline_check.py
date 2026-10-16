import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from timeline_check import audit


class TimelineCheckTests(unittest.TestCase):
    def evaluate(self, admissions, events):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for name, fields, data in (("stays.csv", ["subject_id", "stay_id", "intime", "outtime"], admissions),
                                       ("events.csv", ["subject_id", "stay_id", "charttime"], events)):
                with (base / name).open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(fields)
                    writer.writerows(data)
            args = argparse.Namespace(admissions=base / "stays.csv", events=base / "events.csv",
                                      patient_column="subject_id", stay_column="stay_id", time_column="charttime",
                                      anchor_column="intime", end_column="outtime", max_rows=10000)
            return audit(args)

    def test_patient_shift_preserves_interval_counts_without_recovering_calendar(self):
        anchor = datetime(2100, 1, 1)
        reports = []
        for days in (0, 500):
            begin = anchor + timedelta(days=days)
            end = begin + timedelta(hours=8)
            report = self.evaluate([["PRIVATE_PATIENT", "PRIVATE_STAY", begin.isoformat(), end.isoformat()]],
                                   [["PRIVATE_PATIENT", "PRIVATE_STAY", (begin + timedelta(hours=2)).isoformat()]])
            self.assertFalse(report["cross_patient_calendar_verified"])
            self.assertNotIn("PRIVATE", str(report))
            reports.append(report["counts"])
        self.assertEqual(reports[0], reports[1])
        self.assertEqual(reports[0]["within_icu_interval"], 1)

    def test_mismatches_ambiguous_stays_and_invalid_times_are_not_silently_joined(self):
        report = self.evaluate([["p1", "s1", "2100-01-01 00:00", "2100-01-02 00:00"],
                                ["p2", "s2", "2100-01-01 00:00", "2100-01-02 00:00"],
                                ["p3", "s2", "2100-01-01 00:00", "2100-01-02 00:00"]],
                               [["wrong_patient", "s1", "2100-01-01 01:00"],
                                ["p2", "s2", "2100-01-01 01:00"],
                                ["p1", "s1", "not a timestamp"],
                                ["p1", "s1", "2100-01-01T01:00:00+09:00"]])
        counts = report["counts"]
        self.assertEqual(counts["duplicate_stay_keys"], 1)
        self.assertEqual(counts["patient_mismatch"], 1)
        self.assertEqual(counts["unmatched_stay"], 1)
        self.assertEqual(counts["invalid_event_time"], 1)
        self.assertEqual(counts["incomparable_timezone"], 1)
        self.assertEqual(counts["within_icu_interval"], 0)


if __name__ == "__main__":
    unittest.main()
