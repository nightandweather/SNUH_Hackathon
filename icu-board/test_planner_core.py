"""Synthetic reservation integrity and hidden-future tests; no network/model."""
import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

from planner_core import START, PlannerError, PlannerHospital
from planner_evaluate import evaluate, main, validate_final_state


class PlannerCoreTests(unittest.TestCase):
    def setUp(self):
        self.h = PlannerHospital(seed=1)

    def assert_error(self, code, function, *args):
        with self.assertRaises(PlannerError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_initial_calendar_and_explicit_assumptions(self):
        state = self.h.state()
        self.assertEqual(state["calendar"]["datetime"], "2026-10-16T07:00+09:00")
        self.assertEqual(state["calendar"]["weekday"], "Friday")
        self.assertFalse(state["calendar"]["weekend"])
        self.assertEqual(state["calendar"]["shift"]["code"], "D")
        self.assertEqual((len(state["patients"]), len(state["beds"])), (8, 3))
        for patient in state["patients"]:
            self.assertEqual(patient["id"], patient["patient_id"])
            self.assertEqual(patient["prediction"]["source"], "scenario_assumption")
            self.assertFalse(patient["prediction"]["validated"])
            self.assertFalse(patient["prediction"]["live_model"])
            self.assertTrue(all(event["t"] <= state["t"] for event in patient["observed_events"]))
        self.assertFalse(state["scenario"]["live_model_evaluated"])
        self.assertTrue(validate_final_state(state)["ok"])

    def test_known_schedule_is_visible_but_future_clinical_course_is_hidden(self):
        before = self.h.get_patient("P003")
        self.assertGreater(before["scheduled_end_t"], self.h.t)
        self.assertEqual(before["phase"], "preop")
        self.assertNotIn("recovery_started", json.dumps(before))
        self.assertNotIn("icu_exit", json.dumps(before))
        self.assertFalse(any(key.startswith("_") for key in before))
        self.h.advance(150)
        patient = self.h.get_patient("P003")
        self.assertEqual(patient["phase"], "intraop")
        self.assertTrue(all(event["t"] <= 150 for event in patient["observed_events"]))
        self.assertNotIn("icu_exit", json.dumps(patient))
        self.assertIn("intraop_observation", json.dumps(patient))

    def test_recommendation_does_not_depend_on_final_course_or_actual_los(self):
        other = PlannerHospital(seed=1)
        baseline = copy.deepcopy(other._patients["P003"]["_events"][0])
        other._patients["P003"]["_events"] = [baseline,
            {"t": 123456, "type": "PRIVATE_FINAL_OUTCOME", "text": "SECRET_REALIZED_LOS", "phase": "ward"}]
        for policy in ("first_available", "optimized"):
            left, right = self.h.propose("P003", policy), other.propose("P003", policy)
            self.assertEqual((left["bed_id"], left["start_t"], left["end_t"], left["score"]),
                             (right["bed_id"], right["start_t"], right["end_t"], right["score"]))
        self.assertNotIn("SECRET_REALIZED_LOS", json.dumps(other.state()))
        self.assertEqual(self.h.fixture_signature(), other.fixture_signature())

    def test_propose_changes_no_reservation_or_operational_revision(self):
        old = self.h.state()
        plan = self.h.propose("P003")
        new = self.h.state()
        self.assertEqual(plan["status"], "proposed")
        self.assertEqual(new["revision"], old["revision"])
        self.assertEqual(new["reservations"], old["reservations"])
        self.assertEqual(plan["revision"], new["revision"])
        # Return dictionaries are copies, not mutable authority to change plans.
        plan.update(bed_id="invented-bed", end_t=plan["end_t"] + 100000)
        approved = self.h.approve(plan["id"], plan["revision"])
        self.assertIn(approved["reservation"]["bed_id"], {"ICU-1", "ICU-2", "ICU-3"})
        self.assertTrue(validate_final_state(self.h.state())["ok"])

    def test_conflict_rejects_old_revision_even_when_current_revision_is_supplied(self):
        for policy in ("first_available", "optimized"):
            with self.subTest(policy=policy):
                h = PlannerHospital(seed=1)
                plan = h.propose("P003", policy)
                conflict = h.inject_conflict(plan["id"])
                self.assertGreater(conflict["revision"], plan["revision"])
                self.assert_error("stale_revision", h.approve, plan["id"], plan["revision"])
                self.assert_error("stale_revision", h.approve, plan["id"], h.revision)
                self.assertTrue(validate_final_state(h.state())["ok"])
                replacement = h.replan(plan["id"])
                self.assertNotEqual(replacement["id"], plan["id"])
                self.assertEqual(replacement["status"], "proposed")
                self.assertFalse(any(row["patient_id"] == "P003" for row in h.state()["reservations"]))
                self.assert_error("stale_revision", h.approve, plan["id"], h.revision)
                h.approve(replacement["id"], replacement["revision"])
                self.assertTrue(validate_final_state(h.state())["ok"])

    def test_approved_plan_cannot_receive_a_conflict_or_be_approved_twice(self):
        plan = self.h.propose("P003")
        self.h.approve(plan["id"], plan["revision"])
        previous = copy.deepcopy(self.h.state()["reservations"])
        self.assert_error("stale_revision", self.h.inject_conflict, plan["id"])
        self.assert_error("already_approved", self.h.approve, plan["id"], self.h.revision)
        self.assert_error("duplicate_reservation", self.h.propose, "P003")
        self.assertEqual(previous, self.h.state()["reservations"])

    def test_another_approval_invalidates_a_concurrent_proposal(self):
        first = self.h.propose("P003")
        second = self.h.propose("P004")
        self.h.approve(first["id"], first["revision"])
        self.assert_error("stale_revision", self.h.approve, second["id"], second["revision"])
        self.assertFalse(any(row["patient_id"] == "P004" for row in self.h.state()["reservations"]))

    def test_elapsed_time_and_shift_change_require_fresh_approval(self):
        plan = self.h.propose("P003")
        self.h.advance(1)
        self.assertEqual(self.assert_error("stale_revision", self.h.approve, plan["id"], plan["revision"]).status, 409)
        self.h.advance(479)
        self.assertEqual(self.h.state()["calendar"]["shift"]["code"], "E")
        self.h.advance(480)
        self.assertEqual(self.h.state()["calendar"]["shift"]["code"], "N")
        self.assert_error("stale_revision", self.h.approve, plan["id"], self.h.revision)

    def test_staff_and_calendar_are_checked_again_at_approval(self):
        plan = self.h.propose("P003", "first_available")
        self.h.staff_capacity["D"] = 2
        self.assert_error("staff_capacity", self.h.approve, plan["id"], plan["revision"])
        self.assertTrue(validate_final_state(self.h.state())["ok"])
        h = PlannerHospital(seed=1)
        plan = h.propose("P003")
        h._patients["P003"]["scheduled_start_t"] = 1440  # Saturday fixture update.
        self.assert_error("weekend_elective", h.approve, plan["id"], plan["revision"])
        self.assertFalse(any(row["patient_id"] == "P003" for row in h.state()["reservations"]))

    def test_weekend_has_no_elective_cases_but_patient_course_and_three_shifts_continue(self):
        self.h.advance(1440)
        saturday = self.h.state()
        self.assertTrue(saturday["calendar"]["weekend"])
        self.assertFalse(saturday["calendar"]["elective_surgery_open"])
        self.assertEqual(self.h.get_patient("P002")["phase"], "icu")
        self.assertEqual([self.h.advance(480)["calendar"]["shift"]["code"] for _ in range(3)], ["E", "N", "D"])
        sunday = self.h.state()
        self.assertTrue(sunday["calendar"]["weekend"])
        for patient in sunday["patients"]:
            if patient["elective"]:
                self.assertLess((START + timedelta(minutes=patient["scheduled_start_t"])).weekday(), 5)
            for event in patient["observed_events"]:
                if event["type"] == "anesthesia_started":
                    self.assertLess((START + timedelta(minutes=event["t"])).weekday(), 5)
        self.assertTrue(validate_final_state(sunday)["ok"])

    def test_infeasible_resource_request_and_missing_duration_are_not_invented(self):
        self.h.staff_capacity["N"] = 1
        self.assert_error("no_feasible", self.h.propose, "P006")
        self.assertFalse(any(row["patient_id"] == "P006" for row in self.h.state()["reservations"]))
        self.assertTrue(validate_final_state(self.h.state())["ok"])
        h = PlannerHospital(seed=1)
        del h._patients["P003"]["scenario_assumption"]["los_p90_min"]
        self.assertIsNone(h.get_patient("P003")["prediction"]["los_p90_min"])
        self.assert_error("missing_duration", h.propose, "P003")
        self.assertEqual(len(h.state()["reservations"]), 2)

    def test_all_booked_intervals_remain_feasible_across_weekend_and_release(self):
        for patient in self.h.state()["patients"]:
            if not patient["elective"]:
                continue
            try:
                plan = self.h.propose(patient["id"])
                self.h.approve(plan["id"], plan["revision"])
            except PlannerError as error:
                self.assertEqual(error.code, "no_feasible")
        for minutes in (1440, 1440, 1440, 1680):
            self.h.advance(minutes)
            self.assertTrue(validate_final_state(self.h.state())["ok"])
            self.assertTrue(self.h.constraint_report()["ok"])
            self.assertTrue(all(event["t"] <= self.h.t for p in self.h.state()["patients"] for event in p["observed_events"]))
        self.assertEqual(len(self.h.state()["beds"]), 3)

    def test_invalid_requests_are_structured_errors_and_public_values_are_copies(self):
        self.assert_error("patient_not_found", self.h.get_patient, "missing")
        self.assert_error("plan_not_found", self.h.approve, "missing", 1)
        self.assert_error("unknown_policy", self.h.propose, "P003", "solver")
        for bad in (-1, True, 10081, "60"):
            self.assert_error("invalid_minutes", self.h.advance, bad)
        patient = self.h.get_patient("P003")
        patient["prediction"]["icu_probability"] = 99
        patient["observed_events"].append({"t": 100000, "text": "forged"})
        fresh = self.h.get_patient("P003")
        self.assertLessEqual(fresh["prediction"]["icu_probability"], 1)
        self.assertNotIn("forged", json.dumps(fresh))


class PlannerEvaluationTests(unittest.TestCase):
    def test_paired_fixtures_failure_recovery_and_final_constraints(self):
        report = evaluate((1, 2, 3))
        self.assertFalse(report["live_model_evaluated"])
        self.assertFalse(report["clinical_prediction_validated"])
        self.assertFalse(report["clinical_treatment_effect_evaluated"])
        self.assertTrue(report["all_constraints_pass"])
        self.assertTrue(report["all_failure_scenarios_pass"])
        self.assertEqual(len(report["policy_results"]), 6)
        self.assertEqual(sum(len(row["scenarios"]) for row in report["failure_results"]), 30)
        self.assertTrue(all(row["same_fixture"] for row in report["paired_comparisons"]))
        # A weighted-objective improvement must not hide worse total waiting.
        for row in report["paired_comparisons"]:
            self.assertLess(row["optimized_minus_first_available_weighted_delay_minutes"], 0)
            self.assertGreater(row["optimized_minus_first_available_delay_minutes"], 0)
        for row in report["policy_results"]:
            self.assertEqual(row["approved_count"] + row["not_completed_count"], row["requested_count"])
            self.assertTrue(validate_final_state(row["final_state"])["ok"])

    def test_cli_outputs_full_reproducible_json_without_network_or_models(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            path = Path(directory) / "report.json"
            status = main(["--seeds", "1,2", "--output", str(path)])
            report = json.loads(path.read_text())
        self.assertEqual(status, 0)
        self.assertEqual(report["seeds"], [1, 2])
        self.assertEqual(report, evaluate((1, 2)))


if __name__ == "__main__":
    unittest.main()
