import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.demo import make_demo
from app.engine import Engine, AppError, overlap
from app.evaluation import compare, optimized_booking
from app.importer import export_canonical, validate_dataset
from app.model import extract_features, demo_predict, validate_prediction, predict


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + "/state.db"
        self.engine = Engine(self.path)
        # Existing operational tests exercise the retained manual-review mode.
        self.engine.state["automation"]["enabled"] = False

    def tearDown(self):
        self.tmp.cleanup()

    def action(self, name, **body):
        return self.engine.mutate(name, {"expected_revision": self.engine.state["revision"], **body})

    def reserve(self, pid="DEMO-001", bid="SICU-03", start=75, end=1800):
        return self.action("reserve", patient_id=pid, bed_id=bid, start=start, end=end, reason="테스트 임상 검토")

    def test_initial_cohort_and_private_future(self):
        view = self.engine.view()
        self.assertEqual(view["summary"]["patients"], 60)
        self.assertEqual(len(view["beds"]), 12)
        self.assertNotIn("trajectories", view)
        self.assertNotIn("truth_icu", json.dumps(view))
        for p in view["patients"]:
            self.assertTrue(all(o["minute"] <= view["minute"] for o in p["observations"]))
            self.assertTrue(p["actual_end_minute"] is None or p["actual_end_minute"] <= view["minute"])

    def test_future_information_excluded_in_model_contract(self):
        p = copy.deepcopy(self.engine.state["patients"][0])
        before = extract_features(p, 0, self.engine.state["policy"])
        p["observations"].append({"minute": 100, "map": 20, "hr": 220, "spo2": 60})
        p["treatments"].append({"minute": 100, "kind": "수혈", "label": "미래 처치"})
        after = extract_features(p, 0, self.engine.state["policy"])
        self.assertEqual(before, after)
        p["preop_labs_minute"] = 100
        self.assertEqual(extract_features(p, 0, self.engine.state["policy"])["preop_labs"], {})

    def test_closed_bed_rejected(self):
        with self.assertRaises(AppError):
            self.reserve(bid="SICU-08")

    def test_wrong_unit_rejected(self):
        with self.assertRaises(AppError):
            self.reserve(bid="CCU-03")

    def test_missing_required_equipment_rejected(self):
        self.engine.state["patients"][0]["capabilities_required"].append("crrt")
        with self.assertRaises(AppError):
            self.reserve(bid="SICU-07")

    def test_overlap_is_atomic_and_audited_only_on_success(self):
        self.reserve()
        previous = copy.deepcopy(self.engine.state)
        count = len(self.engine.store.audit())
        with self.assertRaises(AppError) as caught:
            self.reserve(pid="DEMO-004", start=45, end=2000)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.engine.state, previous)
        self.assertEqual(len(self.engine.store.audit()), count)

    def test_cleanup_gap_blocks_adjacent_reservation(self):
        self.reserve(start=75, end=135)
        with self.assertRaises(AppError):
            self.reserve(pid="DEMO-004", start=135, end=180)
        self.reserve(pid="DEMO-004", start=155, end=180)

    def test_same_patient_different_operation_not_double_booked(self):
        self.engine.state["patients"][3]["subject_id"] = self.engine.state["patients"][0]["subject_id"]
        self.reserve()
        with self.assertRaises(AppError):
            self.reserve(pid="DEMO-004", bid="SICU-06", start=75, end=1800)

    def test_optimistic_concurrency_rejects_stale_review(self):
        rev = self.engine.state["revision"]
        self.action("advance", minutes=5)
        with self.assertRaises(AppError) as caught:
            self.engine.mutate("reserve", {"expected_revision": rev, "patient_id": "DEMO-001", "bed_id": "SICU-03", "start": 75, "end": 1800, "reason": "오래된 검토"})
        self.assertEqual(caught.exception.status, 409)

    def test_required_revision_for_operational_change(self):
        with self.assertRaises(AppError):
            self.engine.mutate("reserve", {})

    def test_reservation_update_preserves_id(self):
        self.reserve()
        original = self.engine.state["reservations"][-1]["id"]
        self.reserve(bid="SICU-06")
        self.assertEqual(self.engine.state["reservations"][-1]["id"], original)
        self.assertEqual(self.engine.state["reservations"][-1]["previous"]["bed_id"], "SICU-03")

    def test_booking_forecast_records_prediction_available_at_reservation(self):
        rec = copy.deepcopy(self.engine.state["recommendations"]["DEMO-001"])
        prediction = copy.deepcopy(self.engine.state["predictions"]["DEMO-001"])
        self.reserve()
        snapshot = self.engine.state["reservations"][-1]["initial_booking_forecast"]
        self.assertEqual(snapshot["as_of_minute"], 0)
        self.assertEqual(snapshot["recommended_due_minute"], rec["due"])
        self.assertEqual(snapshot["expected_arrival_minute"], rec["start"])
        self.assertEqual(snapshot["need_score"], prediction["need_score"])
        self.assertEqual(snapshot["icu_probability"], prediction["icu_probability"])
        self.assertNotIn("truth", json.dumps(snapshot))

    def test_initial_booking_forecast_survives_later_updates_and_restart(self):
        self.reserve()
        initial = copy.deepcopy(self.engine.state["reservations"][-1]["initial_booking_forecast"])
        self.action("advance", minutes=10)
        self.reserve(bid="SICU-06")
        current = self.engine.state["reservations"][-1]
        self.assertEqual(current["created_minute"], 0)
        self.assertEqual(current["initial_booking_forecast"], initial)
        reloaded = Engine(self.path)
        self.assertEqual(reloaded.state["reservations"][-1]["initial_booking_forecast"], initial)

    def test_cancel_keeps_history(self):
        self.reserve()
        r = self.engine.state["reservations"][-1]
        self.action("cancel", reservation_id=r["id"], reason="임상 회복에 따른 취소")
        self.assertEqual(self.engine.state["reservations"][-1]["status"], "cancelled")
        self.assertEqual(len(self.engine.store.audit()), 2)

    def test_admit_requires_observed_end_of_operation(self):
        self.reserve()
        with self.assertRaises(AppError):
            self.action("admit", reservation_id=self.engine.state["reservations"][-1]["id"])

    def test_actual_admission_discharge_and_cleaning(self):
        self.reserve(pid="DEMO-008", start=0, end=120)
        r = self.engine.state["reservations"][-1]
        self.action("admit", reservation_id=r["id"])
        b = next(b for b in self.engine.state["beds"] if b["id"] == "SICU-03")
        self.assertEqual(b["occupant_id"], "DEMO-008")
        self.action("discharge", bed_id=b["id"], reason="실제 퇴실 확인")
        self.assertEqual(next(b for b in self.engine.state["beds"] if b["id"] == "SICU-03")["available_minute"], 20)
        with self.assertRaises(AppError):
            self.reserve(pid="DEMO-009", start=5, end=120)
        self.reserve(pid="DEMO-009", start=20, end=120)

    def test_stale_observation_blocks_advice(self):
        self.action("scenario", patient_id="DEMO-001", kind="stale")
        p = next(p for p in self.engine.view()["patients"] if p["id"] == "DEMO-001")
        self.assertTrue(p["prediction"]["features"]["stale"])
        self.assertEqual(p["recommendation"]["status"], "BLOCKED")
        self.assertFalse(p["recommendation"]["actionable"])

    def test_sensor_artifact_blocks_advice(self):
        self.action("scenario", patient_id="DEMO-001", kind="artifact")
        self.assertEqual(self.engine.state["recommendations"]["DEMO-001"]["status"], "BLOCKED")

    def test_worsening_increases_score_and_recovery_decreases_it(self):
        self.action("scenario", patient_id="DEMO-005", kind="bleeding")
        bad = self.engine.state["predictions"]["DEMO-005"]["need_score"]
        self.action("scenario", patient_id="DEMO-005", kind="improving")
        good = self.engine.state["predictions"]["DEMO-005"]["need_score"]
        self.assertGreater(bad, good)

    def test_apply_recommendation_and_overlap_recompute(self):
        self.action("apply_recommendation", patient_id="DEMO-007")
        r = next(r for r in self.engine.state["reservations"] if r["patient_id"] == "DEMO-007")
        self.assertEqual(r["bed_id"], "CCU-03")
        self.assertEqual(r["status"], "confirmed")

    def test_icu_use_not_equivalent_to_clinical_need(self):
        p = self.engine.state["predictions"]["DEMO-006"]
        self.assertGreater(p["icu_probability"], p["need_probability"])

    def test_restarting_preserves_data_and_invalidates_old_review(self):
        self.reserve()
        rev = self.engine.state["revision"]
        again = Engine(self.path)
        self.assertEqual(again.state["reservations"][-1]["bed_id"], "SICU-03")
        self.assertEqual(len(again.store.audit()), 1)
        self.assertGreater(again.state["revision"], rev)

    def test_relative_clocks_block_even_manual_booking(self):
        self.engine.state["clock_kind"] = "patient_relative"
        self.engine.refresh(self.engine.state)
        self.assertEqual(self.engine.state["recommendations"]["DEMO-001"]["status"], "BLOCKED")
        with self.assertRaises(AppError):
            self.reserve()

    def test_observation_ingestion_can_advance_as_of_time(self):
        self.action("observe", patient_id="DEMO-001", as_of_minute=5,
                    observations=[{"minute": 5, "map": 82, "hr": 80, "spo2": 98, "norepi": 0}])
        self.assertEqual(self.engine.state["minute"], 5)
        self.assertEqual(self.engine.state["predictions"]["DEMO-001"]["features"]["latest"]["map"], 82)

    def test_policy_hysteresis_must_be_valid(self):
        with self.assertRaises(AppError):
            self.action("policy", policy={"release_threshold": .5, "icu_threshold": .4})

    def test_no_preop_labs_is_valid_missing_data(self):
        data = export_canonical(make_demo())
        data["patients"][0]["preop_labs"] = {}
        data["patients"][0]["preop_labs_minute"] = None
        self.action("import", dataset=data)
        self.assertEqual(self.engine.state["predictions"]["DEMO-001"]["features"]["preop_labs"], {})

    def test_ward_deterioration_can_trigger_new_icu_reservation(self):
        self.action("scenario", patient_id="DEMO-016", kind="bleeding")
        self.assertEqual(self.engine.state["recommendations"]["DEMO-016"]["status"], "BOOK_NOW")

    def test_expired_occupied_forecast_is_not_free_bed(self):
        self.action("advance", minutes=120)
        with self.assertRaises(AppError):
            self.reserve(pid="DEMO-005", bid="SICU-05", start=130, end=1800)
        self.action("bed_forecast", bed_id="SICU-05", available_minute=140, reason="운영 검토에 따른 예상 조정")
        self.reserve(pid="DEMO-005", bid="SICU-05", start=145, end=1800)

    def test_occupied_forecast_change_flags_existing_booking(self):
        self.reserve(start=75, end=1800)
        self.engine.state["beds"][2]["occupant_id"] = "비수술 환자 B"
        self.action("bed_forecast", bed_id="SICU-03", available_minute=90, reason="기존 재실 연장 예상")
        self.assertTrue(any(a["kind"] == "reservation_conflict" for a in self.engine.state["alerts"]))

    def test_alert_ack_persists_while_episode_active(self):
        alert = self.engine.state["alerts"][0]
        self.action("ack", alert_id=alert["id"])
        self.action("advance", minutes=5)
        active = next(a for a in self.engine.state["alerts"] if a["id"] == alert["id"])
        self.assertTrue(active["acknowledged"])


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.data = export_canonical(make_demo())

    def test_canonical_roundtrip(self):
        self.assertEqual(len(validate_dataset(self.data)["patients"]), 60)

    def test_wrong_units_rejected(self):
        self.data["units"]["norepi"] = "mL/h"
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_future_observations_rejected(self):
        self.data["patients"][0]["observations"][-1]["minute"] = 100
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_duplicate_patient_rejected(self):
        self.data["patients"][1]["id"] = self.data["patients"][0]["id"]
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_duplicate_operation_rejected(self):
        self.data["patients"][1]["operation_id"] = self.data["patients"][0]["operation_id"]
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_impossible_vital_rejected(self):
        self.data["patients"][0]["observations"][-1]["spo2"] = 101
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_actual_end_must_be_observed(self):
        self.data["patients"][0]["actual_end_minute"] = 200
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_no_timezone_rejected(self):
        self.data["base_time"] = "2026-10-16T08:30:00"
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_wrong_prior_record_timestamp_rejected(self):
        self.data["patients"][0]["pre_admission"][0]["minute"] = -100
        with self.assertRaises(AppError):
            validate_dataset(self.data)

    def test_missing_support_is_unknown(self):
        self.data["patients"][0]["observations"][-1].pop("crrt")
        p = validate_dataset(self.data)["patients"][0]
        self.assertIsNone(p["observations"][-1]["crrt"])

    def test_model_nan_and_reversed_interval_rejected(self):
        p = demo_predict(extract_features(make_demo()["patients"][0], 0, make_demo()["policy"]))
        p["confidence"] = float("nan")
        with self.assertRaises(ValueError):
            validate_prediction(p)
        p["confidence"] = .9
        p["icu_los_upper"] = 0
        with self.assertRaises(ValueError):
            validate_prediction(p)

    def test_remote_failure_is_not_silently_demo(self):
        f = extract_features(make_demo()["patients"][0], 0, make_demo()["policy"])
        with patch.dict(os.environ, {"MODEL_URL": ""}):
            p = predict(f, "remote")
        self.assertEqual(p["mode"], "unavailable")
        self.assertEqual(p["confidence"], 0)

    def test_optimization_responds_to_cost_weights(self):
        policy = make_demo()["policy"]
        expensive = optimized_booking(0, 80, .9, {**policy, "delay_weight": 20})
        cheap = optimized_booking(0, 80, .9, {**policy, "delay_weight": .1})
        self.assertLessEqual(expensive["booking_minute"], cheap["booking_minute"])

    def test_replay_is_deterministic_and_not_always_superior(self):
        policy = make_demo()["policy"]
        first = compare(26, policy, 180)
        self.assertEqual(first, compare(26, policy, 180))
        self.assertFalse(first["clinical_validation"])
        self.assertEqual(len(first["results"]), 3)
        for r in first["results"]:
            self.assertGreaterEqual(r["bed_delay_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
