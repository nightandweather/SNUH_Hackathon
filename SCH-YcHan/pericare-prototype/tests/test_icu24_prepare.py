"""Endpoint boundaries and future-information leakage checks using fictional rows."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

try:
    import pandas as pd
    from ml.icu24.features import make_features
    from ml.icu24.prepare import classify_label, operation_landmarks, load_labs, prepare
    from ml.icu24.synthetic import generate
    HAVE_ML = True
except ImportError:
    HAVE_ML = False


@unittest.skipUnless(HAVE_ML, "Install ml/requirements.txt for optional ML tests")
class PrepareTests(unittest.TestCase):
    def row(self, **changes):
        result = dict(subject_id="1", hadm_id="2", op_id="4", age=65, asa=3,
                      orin_time=90, admission_time=0, opstart_time=100, opend_time=200,
                      discharge_time=3000, icuin_time=None, icuout_time=None, inhosp_death_time=None)
        result.update(changes)
        return result

    def test_inclusive_24h_boundary_and_not_lifetime_icu(self):
        self.assertEqual(classify_label(self.row(icuin_time=1640)), (1, "valid"))
        self.assertEqual(classify_label(self.row(icuin_time=1641)), (0, "valid"))
        self.assertIsNone(classify_label(self.row(icuin_time=199))[0])

    def test_death_missing_followup_and_icu_inconsistency_are_not_negatives(self):
        for changes in (dict(inhosp_death_time=300), dict(discharge_time=None), dict(icuout_time=500)):
            self.assertIsNone(classify_label(self.row(**changes))[0])
        self.assertEqual(classify_label(self.row(discharge_time=300)), (0, "valid"))
        self.assertIsNone(classify_label(self.row(), competing_operation=300)[0])

    def test_later_admission_icu_does_not_select_out_a_negative(self):
        self.assertEqual(classify_label(self.row(icuin_time=5000, icuout_time=6000)), (0, "valid"))
        # ICU exit timing is not a classification endpoint eligibility criterion.
        self.assertEqual(classify_label(self.row(icuin_time=300, icuout_time=4000)), (1, "valid"))

    def test_first_admission_operation_and_current_landmark_only(self):
        rows, audit = operation_landmarks(pd.DataFrame([
            self.row(), self.row(op_id="5", opstart_time=2000, opend_time=2100, orin_time=1990)
        ]), ["preop", 30, 100, 120])
        self.assertEqual({r["op_id"] for r in rows}, {"4"})
        self.assertEqual([r["landmark_minute"] for r in rows], [90, 130])
        self.assertEqual(audit["operations_after_first_in_admission"], 1)

    def test_future_labs_signals_and_outcomes_cannot_change_features(self):
        payload = dict(minute=60, phase="OR", age=65, asa=3, emergency=False,
                       signal_window=[dict(minute=50, map=70)],
                       preop_labs=dict(hemoglobin=11), preop_lab_times=dict(hemoglobin=20))
        before = make_features(payload)
        payload["signal_window"] += [dict(minute=80, map=30), dict(minute=55, available_minute=90, map=35)]
        payload.update(icuin_time=100, icuout_time=1000, opend_time=90, discharge_time=10000)
        self.assertEqual(before, make_features(payload))
        payload["preop_lab_times"]["hemoglobin"] = 80
        self.assertIsNone(make_features(payload)["lab_hemoglobin"])

    def test_asof_labs_use_patient_and_availability_not_future_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "labs.csv"
            path.write_text("subject_id,chart_time,item_name,value\n1,0,hb,10\n1,50,hb,20\n2,0,hb,18\n", encoding="utf-8")
            rows = [dict(subject_id="1", landmark_minute=60.0), dict(subject_id="2", landmark_minute=60.0)]
            result = load_labs(path, rows, delay_minutes=30, lookback_minutes=1000, chunksize=1)
            self.assertEqual(result[0]["hemoglobin"], (10, 0, 30))
            self.assertEqual(result[1]["hemoglobin"], (18, 0, 30))

    def test_synthetic_preparation_provenance_and_no_outcomes_in_feature_table(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "source", Path(temp) / "prepared"
            generate(source, patients=60, seed=26)
            audit = prepare(source, output, landmarks="preop,30", include_labs=True)
            self.assertEqual(audit["dataset_kind"], "synthetic")
            frame = pd.read_csv(output / "prepared.csv")
            self.assertGreater(frame.subject_id.nunique(), 40)
            self.assertEqual(set(frame.y_icu24), {0, 1})
            self.assertFalse({"opend_time", "icuin_time", "icuout_time", "discharge_time", "case_id"} & set(frame.columns))
            self.assertEqual(json.loads((output / "cohort_audit.json").read_text())["prepared_rows"], len(frame))
            with self.assertRaises(ValueError):
                prepare(source, output)
            with self.assertRaises(ValueError):
                prepare(source, source / "output")


if __name__ == "__main__":
    unittest.main()
