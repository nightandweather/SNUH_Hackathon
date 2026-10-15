"""A local PREOP viewer must not export labels or actual future surgery times."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from app.importer import validate_dataset
from app.model import extract_features
from ml.icu24.export_pericare import DISPLAY_ORIGIN, export_snapshot, make_snapshot
from ml.icu24.features import TASK, make_features


class PeriCareExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.raw, self.prepared_dir = root / "raw", root / "prepared"
        self.raw.mkdir()
        self.prepared_dir.mkdir()
        self.prepared = self.prepared_dir / "prepared.csv"
        self.operation = {
            "op_id": "4000001", "admission_time": 0,
            "opstart_time": 1030, "opend_time": 1234,
            "icuin_time": 1250, "discharge_time": 18000, "inhosp_death_time": 20000,
        }
        self.row = {
            "op_id": "4000001", "subject_id": "1000001", "hadm_id": "2000001",
            "landmark_minute": 1000, "phase": "PREOP", "label_status": "valid",
            "y_icu24": 1, "age": 65, "asa": 3, "sex": "M", "weight": 78,
            "height": 170, "department": "GS", "anesthesia_type": "General",
            "emergency": 0, "lab_hemoglobin": 12.5, "lab_hemoglobin_age_minutes": 120,
        }
        self.write_raw()
        self.write_prepared()

    def write_raw(self):
        with (self.raw / "operations.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.operation))
            writer.writeheader()
            writer.writerow(self.operation)

    def write_prepared(self):
        with self.prepared.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerow(self.row)
        meta = {"task": TASK, "dataset_kind": "synthetic", "lab_delay_minutes": 60,
                "prepared_sha256": hashlib.sha256(self.prepared.read_bytes()).hexdigest()}
        (self.prepared_dir / "cohort_audit.json").write_text(json.dumps(meta), encoding="utf-8")

    def snapshot(self, **kwargs):
        return make_snapshot(self.raw, self.prepared, 45, 150, **kwargs)

    def test_preop_import_and_known_lab_timing_match(self):
        snapshot = self.snapshot()
        state = validate_dataset(snapshot)
        patient = state["patients"][0]
        self.assertEqual(state["source"], "import")
        self.assertEqual(state["clock_kind"], "case_relative")
        self.assertEqual(state["beds"], [])
        self.assertEqual(snapshot["base_time"], DISPLAY_ORIGIN)
        self.assertEqual(patient["admission_minute"], -1000)
        self.assertEqual(patient["operation_start_minute"], 45)
        self.assertEqual(patient["estimated_end_minute"], 195)
        self.assertIsNone(patient["actual_end_minute"])
        values = make_features(extract_features(patient, 0, state["policy"]))
        self.assertEqual(values["phase"], "PREOP")
        self.assertEqual(values["elapsed_operation_minutes"], 0)
        self.assertEqual(values["lab_hemoglobin"], 12.5)
        self.assertEqual(values["lab_hemoglobin_age_minutes"], 120)
        self.assertEqual(patient["preop_lab_times"]["hemoglobin"], -60)

    def test_future_source_times_and_label_never_enter_snapshot(self):
        before = self.snapshot()
        self.operation.update(opstart_time=7000, opend_time=9000, icuin_time=9999,
                              discharge_time=25000, inhosp_death_time=30000)
        self.write_raw()
        self.row["y_icu24"] = 0
        self.write_prepared()
        self.assertEqual(before, self.snapshot())
        patient = before["patients"][0]
        for forbidden in ("y_icu24", "icuin_time", "icuout_time", "opstart_time", "opend_time",
                          "discharge_time", "discharge_minute", "inhosp_death_time", "case_id"):
            self.assertNotIn(forbidden, patient)
        self.assertNotIn("planned_icu", patient)
        self.assertEqual(before["replay_events"], [])

    def test_rejects_missing_plan_or_out_of_scope_row(self):
        for start, duration in ((0, 150), (-1, 150), (30, 0), (30, float("nan")), (9000, 2000)):
            with self.subTest(start=start, duration=duration), self.assertRaises(ValueError):
                make_snapshot(self.raw, self.prepared, start, duration)
        with self.assertRaises(ValueError):
            self.snapshot(op_id="missing")
        self.row["phase"] = "OR"
        self.write_prepared()
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_local_export_protects_sources_and_checks_provenance(self):
        with self.assertRaises(ValueError):
            export_snapshot(self.raw, self.prepared, self.raw / "forbidden.json", 30, 120)
        target = self.prepared_dir / "viewer.json"
        export_snapshot(self.raw, self.prepared, target, 30, 120)
        with self.assertRaises(FileExistsError):
            export_snapshot(self.raw, self.prepared, target, 30, 120)
        self.prepared.write_text(self.prepared.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.snapshot()


if __name__ == "__main__":
    unittest.main()
