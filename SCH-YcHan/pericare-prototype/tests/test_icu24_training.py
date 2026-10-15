"""End-to-end software checks on generated data; no clinical performance claim."""
import argparse
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

try:
    import joblib
    import numpy as np
    import pandas as pd
    from ml.icu24.artifacts import calibrated_probability, model_frame
    from ml.icu24.evaluate import choose_threshold, operation_weights, threshold_metrics
    from ml.icu24.features import FEATURE_COLUMNS, NUMERIC_FEATURES, CATEGORICAL_FEATURES
    from ml.icu24.serve import Predictor, create_server
    from ml.icu24.train import patient_split, train
    HAS_ML = True
except ImportError:
    HAS_ML = False


def example_frame():
    rows = []
    for patient in range(120):
        label = patient % 2
        for operation in range(1 + (patient % 3 == 0)):
            for landmark in range(3):
                row = {name: None for name in FEATURE_COLUMNS}
                row.update({"subject_id": str(patient), "hadm_id": str(patient * 10 + operation),
                            "op_id": str(patient * 100 + operation), "landmark_minute": landmark * 30,
                            "label_status": "valid", "y_icu24": label, "phase": "PREOP",
                            "age": 30 + 25 * label + patient % 7, "asa": 1 + 2 * label,
                            "sex": "M" if patient % 3 else "F", "elapsed_operation_minutes": 0,
                            "department": "GS", "anesthesia_type": "General", "signal_count_30": 0})
                rows.append(row)
    return pd.DataFrame(rows)


@unittest.skipUnless(HAS_ML, "Install ml/requirements.txt to run ML tests")
class ICU24TrainingTests(unittest.TestCase):
    def test_patient_group_split_is_disjoint_deterministic(self):
        frame = example_frame()
        manifest = patient_split(frame, 26)
        self.assertTrue(manifest.equals(patient_split(frame, 26)))
        self.assertEqual(manifest.subject_id.nunique(), frame.subject_id.nunique())
        self.assertFalse(manifest.subject_id.duplicated().any())
        mapping = manifest.set_index("subject_id").split
        assigned = frame.assign(split=frame.subject_id.map(mapping))
        self.assertEqual(assigned.groupby("subject_id").split.nunique().max(), 1)
        self.assertEqual(set(manifest.split), {"train", "validation", "calibration", "test"})

    def test_operations_have_equal_total_weight(self):
        frame = example_frame()
        weighted = frame.assign(weight=operation_weights(frame))
        totals = weighted.groupby(["subject_id", "hadm_id", "op_id"]).weight.sum()
        np.testing.assert_allclose(totals, 1)

    def test_sensitivity_threshold_uses_at_least_target(self):
        y = np.array([0, 0, 0, 1, 1, 1])
        p = np.array([.1, .2, .8, .3, .6, .9])
        threshold = choose_threshold(y, p, np.ones(6), .9)
        self.assertAlmostEqual(threshold, .3)
        self.assertEqual(threshold_metrics(y, p, threshold)["sensitivity"], 1)

    def test_training_artifact_and_service_contract(self):
        frame = example_frame()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            path = base / "prepared.csv"
            frame.to_csv(path, index=False)
            args = argparse.Namespace(data=str(path), output_dir=str(base / "run"), dataset_kind="synthetic",
                                      metadata=None, seed=26, max_iter=15, candidates="logistic",
                                      target_sensitivity=.9, bootstrap=5, overwrite=False)
            report = train(args)
            self.assertEqual(report["dataset_kind"], "synthetic")
            self.assertEqual(report["candidate_selection"]["split"], "validation")
            self.assertEqual(report["threshold_selection"]["split"], "validation")
            self.assertGreater(report["partitions"]["test"]["patients"], 0)
            artifact = base / "run" / "model.joblib"
            with self.assertRaisesRegex(ValueError, "Synthetic"):
                Predictor(artifact)
            predictor = Predictor(artifact, allow_synthetic=True)
            payload = {"schema_version": "2.0", "features": {
                "minute": 0, "phase": "PREOP", "age": 65, "asa": 3,
                "sex": "M", "source_mode": "imported", "elapsed_operation_minutes": 0}}
            prediction = predictor.predict(payload)
            self.assertEqual(prediction["prediction_status"], "available")
            self.assertTrue(0 <= prediction["icu_probability"] <= 1)
            self.assertIsNone(prediction["icu_los_hours"])
            self.assertIsNone(prediction["confidence"])
            self.assertEqual(prediction["supported_outputs"], ["icu_probability"])
            payload["features"]["phase"] = "OR"
            self.assertEqual(predictor.predict(payload)["prediction_status"], "unsupported")
            payload["features"]["phase"] = "PREOP"
            payload["features"].pop("source_mode")
            self.assertEqual(predictor.predict(payload)["prediction_status"], "unsupported")
            payload["features"]["source_mode"] = "synthetic"
            self.assertEqual(predictor.predict(payload)["prediction_status"], "unsupported")
            payload["features"]["source_mode"] = "imported"
            server = create_server(predictor, "127.0.0.1", 0, api_key="test-only-key")
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(url + "/health") as response:
                    self.assertEqual(json.load(response)["status"], "ok")
                request = urllib.request.Request(url + "/predict", data=json.dumps(payload).encode(),
                                                 headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code, 401)
                request.add_header("Authorization", "Bearer test-only-key")
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response)["prediction_status"], "available")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)

    def test_test_features_cannot_change_fitted_preprocessing_or_calibration(self):
        frame = example_frame()
        manifest = patient_split(frame, 26)
        test_ids = set(manifest.loc[manifest.split == "test", "subject_id"])
        changed = frame.copy()
        changed.loc[changed.subject_id.isin(test_ids), "age"] = 100000
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            bundles = []
            for index, dataset in enumerate((frame, changed)):
                path = base / f"prepared{index}.csv"
                dataset.to_csv(path, index=False)
                args = argparse.Namespace(data=str(path), output_dir=str(base / str(index)), dataset_kind="synthetic",
                                          metadata=None, seed=26, max_iter=15, candidates="logistic",
                                          target_sensitivity=.9, bootstrap=0, overwrite=False)
                train(args)
                bundles.append(joblib.load(base / str(index) / "model.joblib"))
            unchanged = frame.loc[~frame.subject_id.isin(test_ids)]
            np.testing.assert_allclose(calibrated_probability(bundles[0], unchanged), calibrated_probability(bundles[1], unchanged))
            self.assertEqual(bundles[0]["decision_threshold"], bundles[1]["decision_threshold"])


if __name__ == "__main__":
    unittest.main()
