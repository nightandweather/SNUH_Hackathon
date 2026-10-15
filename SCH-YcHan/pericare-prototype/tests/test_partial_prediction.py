"""Probability-only models must be visible without inventing care/LOS outputs."""
import copy
import gc
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from app.demo import make_demo
from app.engine import AppError, Engine
from app.importer import export_canonical, validate_dataset
from app.model import ICU24_TASK, PARTIAL_NULL_OUTPUTS, extract_features, predict, validate_prediction


def partial(probability=0.82, available=True):
    return {**dict.fromkeys(PARTIAL_NULL_OUTPUTS), "schema_version": "2.0", "task": ICU24_TASK,
            "prediction_status": "available" if available else "unsupported",
            "supported_outputs": ["icu_probability"], "icu_probability": probability if available else None,
            "horizon_minutes": 1440, "interval_kind": "not_applicable", "contributions": [],
            "model_version": "test-icu24", "unsupported_reason": None if available else "학습한 단계가 아닙니다"}


class PartialContractTests(unittest.TestCase):
    def setUp(self):
        self.demo = make_demo()
        self.features = extract_features(self.demo["patients"][0], 0, self.demo["policy"])
        self.features["source_mode"] = "import"

    def remote(self, response, features=None):
        with patch.dict(os.environ, {"MODEL_URL": "http://local/predict", "MODEL_TASK": ICU24_TASK}), \
                patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result = predict(features or self.features, "remote")
            sent = json.loads(request.call_args.args[0].data)
            self.assertEqual(sent["schema_version"], "2.0")
        return result

    def test_probability_only_does_not_fill_unsupported_fields(self):
        p = self.remote(partial())
        self.assertEqual(p["mode"], "remote_partial")
        self.assertEqual(p["icu_probability"], .82)
        for key in PARTIAL_NULL_OUTPUTS:
            self.assertIsNone(p[key], key)

    def test_invalid_or_invented_outputs_fail_closed(self):
        for key, value in (("icu_probability", float("nan")), ("icu_probability", True),
                           ("icu_probability", 1.01), ("need_score", 82), ("confidence", .9),
                           ("icu_los_upper", 48), ("task", "other"), ("horizon_minutes", 60)):
            with self.subTest(key=key, value=value):
                p = partial()
                p[key] = value
                with self.assertRaises(ValueError):
                    validate_prediction(p)

    def test_unsupported_retains_nulls_and_reason(self):
        p = self.remote(partial(available=False))
        self.assertEqual(p["mode"], "unsupported")
        self.assertIn("단계", p["model_error"])
        self.assertIsNone(p["icu_probability"])

    def test_postop_and_synthetic_cannot_receive_valid_partial_prediction(self):
        for update in ({"phase": "PACU"}, {"phase": "ICU"}, {"phase": "WARD"}, {"source_mode": "synthetic"}):
            with self.subTest(update=update):
                p = self.remote(partial(), {**self.features, **update})
                self.assertEqual(p["mode"], "unavailable")
                self.assertIsNone(p["confidence"])
                self.assertIsNone(p["icu_probability"])

    def test_lab_times_and_body_fields_survive_import(self):
        data = export_canonical(self.demo)
        p = data["patients"][0]
        start = p["operation_start_minute"]
        p.update(weight=72, height=174, anesthesia_type="general", preop_labs_minute=None,
                 preop_labs={"hemoglobin": 11.2}, preop_lab_times={"hemoglobin": 0},
                 preop_lab_measurement_times={"hemoglobin": start - 90})
        imported = validate_dataset(data)["patients"][0]
        f = extract_features(imported, 0, self.demo["policy"])
        self.assertEqual(f["weight"], 72)
        self.assertEqual(f["height"], 174)
        self.assertEqual(f["anesthesia_type"], "general")
        self.assertEqual(f["preop_lab_times"], {"hemoglobin": 0})
        self.assertEqual(f["preop_lab_measurement_times"], {"hemoglobin": start - 90})
        imported["preop_lab_times"]["hemoglobin"] = 10
        self.assertEqual(extract_features(imported, 0, self.demo["policy"])["preop_labs"], {})

    def test_delayed_observation_is_not_visible_before_availability(self):
        p = copy.deepcopy(self.demo["patients"][0])
        p["observations"] = [{"minute": -5, "available_minute": 5, "map": 55, "hr": 120, "spo2": 95}]
        self.assertEqual(extract_features(p, 0, self.demo["policy"])["signal_window"], [])
        self.assertEqual(extract_features(p, 5, self.demo["policy"])["signal_window"][0]["map"], 55)


class PartialEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.tmp.name) / "partial.db")

    def tearDown(self):
        # SQLite connections in legacy Store are collected after their context.
        # Collect them before Windows removes the temporary database directory.
        gc.collect()
        self.tmp.cleanup()

    @staticmethod
    def result(features, backend):
        supported = features["phase"] in ("PREOP", "OR")
        return {**partial(available=supported), "mode": "remote_partial" if supported else "unsupported",
                "model_error": None if supported else "학습한 단계가 아닙니다"}

    def load_partial(self):
        self.engine.state["model_backend"] = "remote"
        with patch("app.engine.predict", side_effect=self.result):
            self.engine.refresh(self.engine.state)

    def test_partial_probability_never_creates_a_reservation_window(self):
        self.load_partial()
        recommendation = self.engine.state["recommendations"]["DEMO-001"]
        self.assertEqual(recommendation["status"], "BLOCKED")
        self.assertFalse(recommendation["actionable"])
        for key in ("start", "end", "due", "optimization"):
            self.assertIsNone(recommendation[key])
        with self.assertRaises(AppError):
            self.engine.mutate("apply_recommendation", {"patient_id": "DEMO-001", "expected_revision": self.engine.state["revision"]})

    def test_existing_confirmed_reservation_is_preserved(self):
        self.engine.reserve(self.engine.state, {"patient_id": "DEMO-001", "bed_id": "SICU-03", "start": 75,
                            "end": 1800, "reason": "담당자가 검토한 확정 예약"}, "tester")
        existing = copy.deepcopy(self.engine.state["reservations"])
        self.load_partial()
        self.assertEqual(self.engine.state["reservations"], existing)

    def test_team_holds_with_null_confidence_and_does_not_create_actions(self):
        from app.team import run_team
        self.load_partial()
        s = self.engine.state
        reservations = copy.deepcopy(s["reservations"])
        positions = [p["location"] for p in s["patients"]]
        run_team(self.engine, s)
        self.assertEqual(s["reservations"], reservations)
        self.assertEqual([p["location"] for p in s["patients"]], positions)
        self.assertEqual(s["automation"]["workflows"]["DEMO-001"]["stage"], "quality_hold")
        f = s["predictions"]["DEMO-001"]["features"]
        self.assertEqual(f["source_mode"], "synthetic")
        self.assertEqual(f["clock_kind"], "synthetic_shared")

    @unittest.skipUnless(shutil.which("node"), "Node is optional for UI rendering checks")
    def test_ui_renders_probability_with_correct_task_and_no_los(self):
        self.load_partial()
        state = self.engine.view()
        script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={console,Intl,Date,Math,Number,String,JSON,Set,Map,Error,URL,encodeURIComponent,decodeURIComponent,
 document:{addEventListener(){}},window:{addEventListener(){},innerWidth:1200},localStorage:{getItem(){return null;}}};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
context.fixture=JSON.parse(fs.readFileSync(0,'utf8'));
vm.runInContext("S=fixture;U.selected='DEMO-001';",context);
const html=vm.runInContext('patientView()',context);
assert.ok(html.includes('수술 후 24시간 이내 ICU 입실'));assert.ok(html.includes('82%'));
assert.ok(html.includes('이 모델에서 지원하지 않는 출력'));
assert.ok(!html.includes('예정 입실 반영'));assert.ok(!html.includes('NaN'));assert.ok(!html.includes('undefined'));
assert.equal(vm.runInContext('validPrediction(patient())',context),true);
assert.equal(vm.runInContext('validNeedPrediction(patient())',context),false);
'''
        result = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps(state),
                                text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
