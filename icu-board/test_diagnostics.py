"""Observed simulated workflows and vital history never become real test results."""
import copy
import unittest

import engine
from test_shifts import admit, advance, hospital


def finish(h, task_id, status, limit=100):
    for _ in range(limit):
        task = next(row for row in h.diagnostics if row["id"] == task_id)
        if task["status"] == status:
            return copy.deepcopy(task)
        h.step()
    raise AssertionError(f"task {task_id} did not reach {status}")


class DiagnosticTests(unittest.TestCase):
    def test_blood_draw_requires_arrival_and_records_only_simulated_specimen_delivery(self):
        h = hospital(policy="auto")
        bed = admit(h, "MICU-02")
        source = copy.deepcopy(bed["patient"]["src"])
        task = h.request_diagnostic("MICU-1", bed["id"], "blood_draw")
        self.assertEqual(task["status"], "requested")
        self.assertNotEqual(h.nurses["MICU-1"]["pos"], bed["pos"])
        h.step()
        live = h.diagnostic_task(bed["id"], task["id"])
        self.assertEqual(live["status"], "collecting")
        self.assertEqual(h.nurses["MICU-1"]["pos"], bed["pos"])
        done = finish(h, task["id"], "specimen_sent")
        begin = next(event for event in done["events"] if event["status"] == "collecting")
        self.assertTrue(2 <= done["events"][-1]["t"] - begin["t"] <= 4)
        self.assertEqual(done["source"], "simulation_workflow")
        self.assertIsNone(done["review"])
        self.assertNotIn("result", done)
        self.assertEqual(h.care_actions, [])
        self.assertEqual(bed["patient"]["src"], source)
        self.assertIsNone(h.nurses["MICU-1"]["diagnostic_id"])
        self.assertTrue(any(row["type"] == "diagnostic_complete" for row in h.patient_activities(bed["id"])))

    def test_xray_preparation_call_wait_and_acquisition_keep_example_provenance(self):
        h = hospital(policy="auto")
        admit(h)
        task = h.request_diagnostic("MICU-1", "MICU-01", "portable_xray")
        done = finish(h, task["id"], "image_available")
        self.assertEqual([event["status"] for event in done["events"]],
                         ["requested", "nurse_en_route", "preparing", "called", "acquiring", "image_available"])
        times = {event["status"]: event["t"] for event in done["events"]}
        self.assertTrue(2 <= times["called"] - times["preparing"] <= 4)
        self.assertTrue(4 <= times["acquiring"] - times["called"] <= 12)
        self.assertTrue(2 <= times["image_available"] - times["acquiring"] <= 4)
        self.assertEqual(done["image_source"], "public_nih_example")
        self.assertFalse(done["patient_linked"])
        self.assertIsNone(done["review"])
        self.assertTrue(all(event["source"] == "simulation_activity" for event in done["events"]))
        self.assertIsNone(done["events"][-1]["staff_id"])
        self.assertIsNone(done["events"][-2]["staff_id"])
        self.assertFalse({"image", "file", "finding", "report", "lab_values"}.intersection(done))

    def test_permissions_duplicate_and_invalid_requests_are_rejected(self):
        h = hospital()
        admit(h)
        for nurse in ("SICU1-C", "MICU-2"):
            with self.assertRaises(PermissionError):
                h.request_diagnostic(nurse, "MICU-01", "blood_draw")
        for nurse, bed, kind in ((None, "MICU-01", "blood_draw"), ("MICU-1", "MICU-02", "blood_draw"),
                                 ("MICU-1", "MICU-01", "MRI"), ("MICU-1", "MICU-01", {})):
            with self.assertRaises(ValueError):
                h.request_diagnostic(nurse, bed, kind)
        task = h.request_diagnostic("MICU-C", "MICU-01", "blood_draw")
        with self.assertRaises(ValueError):
            h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        returned = h.patient_diagnostics("MICU-01")
        returned[0]["status"] = "tampered"
        self.assertEqual(h.diagnostic_task("MICU-01", task["id"])["status"], "requested")

    def test_one_nurse_performs_one_task_and_keeps_later_request_queued(self):
        h = hospital()
        admit(h)
        admit(h, "MICU-02")
        first = h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        second = h.request_diagnostic("MICU-1", "MICU-02", "portable_xray")
        h.step()
        self.assertEqual(h.nurses["MICU-1"]["diagnostic_id"], first["id"])
        waiting = h.diagnostic_task("MICU-02", second["id"])
        self.assertEqual(waiting["status"], "requested")
        self.assertTrue(waiting["paused"])
        done = finish(h, first["id"], "specimen_sent")
        xray = finish(h, second["id"], "called")
        started = next(event["t"] for event in xray["events"] if event["status"] == "nurse_en_route")
        self.assertGreater(started, done["events"][-1]["t"])
        self.assertIsNone(h.nurses["MICU-1"]["diagnostic_id"])

    def test_emergency_immediately_preempts_collection_then_resumes_remaining_work(self):
        h = hospital(policy="fixed")
        admit(h)
        admit(h, "MICU-02")
        task = h.request_diagnostic("MICU-1", "MICU-02", "blood_draw")
        h.step()
        remaining = h._diagnostic_work[task["id"]]["remaining"]
        event = h.trigger_emergency("MICU-01", "hypoxia")
        self.assertIn("MICU-1", event["responders"])
        self.assertTrue(h.diagnostic_task("MICU-02", task["id"])["paused"])
        advance(h, 5)
        self.assertEqual(h._diagnostic_work[task["id"]]["remaining"], remaining)
        done = finish(h, task["id"], "specimen_sent")
        self.assertTrue(any("응급" in row["text"] for row in done["events"]))
        self.assertTrue(any("재개" in row["text"] for row in done["events"]))
        self.assertFalse(done["paused"])
        self.assertEqual(h.care_actions, [])

    def test_same_bed_emergency_pauses_the_separate_xray_technician_timer(self):
        h = hospital()
        admit(h)
        task = h.request_diagnostic("MICU-1", "MICU-01", "portable_xray")
        finish(h, task["id"], "called")
        remaining = h._diagnostic_work[task["id"]]["remaining"]
        h.trigger_emergency("MICU-01", "hypoxia")
        advance(h, 5)
        self.assertEqual(h._diagnostic_work[task["id"]]["remaining"], remaining)
        self.assertTrue(h.diagnostic_task("MICU-01", task["id"])["paused"])
        finish(h, task["id"], "image_available")

    def test_auto_diagnostic_resume_restores_other_patient_coverage_after_code_blue(self):
        for kind, phase, completed in (("blood_draw", "collecting", "specimen_sent"),
                                       ("portable_xray", "preparing", "called")):
            with self.subTest(kind=kind):
                h = hospital(policy="auto")
                for bid in h.units["MICU"]["bed_ids"]:
                    admit(h, bid)
                task = h.request_diagnostic("MICU-1", "MICU-02", kind)
                h.step()
                emergency = h.trigger_emergency("MICU-02", "code_blue")
                self.assertIn("MICU-1", emergency["responders"])
                while h.incidents[0]["end"] is None:
                    h.step()
                self.assertEqual(h.diagnostic_task("MICU-02", task["id"])["status"], phase)
                gap_at_resume = h.unattended["all"]
                while h.diagnostic_task("MICU-02", task["id"])["status"] == phase:
                    holders = [n for n in h.nurses.values() if "MICU-01" in n["cover"]]
                    self.assertEqual(len(holders), 1)
                    self.assertEqual(holders[0]["unit"], "MICU")
                    self.assertTrue(h._free(holders[0]["id"]))
                    h.step()
                    self.assertEqual(h.unattended["all"], gap_at_resume)
                self.assertEqual(h.diagnostic_task("MICU-02", task["id"])["status"], completed)

    def test_diagnostic_start_transfers_existing_cover_to_an_available_local_nurse(self):
        h = hospital(policy="auto")
        for bid in h.units["MICU"]["bed_ids"]:
            admit(h, bid)
        h.request_diagnostic("MICU-1", "MICU-02", "portable_xray")
        h.step()
        initial = [n for n in h.nurses.values() if "MICU-01" in n["cover"]]
        self.assertEqual(len(initial), 1)
        cover = initial[0]
        task = h.request_diagnostic(cover["id"], "MICU-03", "blood_draw")
        before_gap = h.unattended["all"]
        h.step()
        self.assertEqual(h.diagnostic_task("MICU-03", task["id"])["status"], "collecting")
        self.assertNotIn("MICU-01", cover["cover"])
        holders = [n for n in h.nurses.values() if "MICU-01" in n["cover"]]
        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0]["unit"], "MICU")
        self.assertTrue(h._free(holders[0]["id"]))
        self.assertEqual(h.unattended["all"], before_gap)
        cover_events = len([row for row in h.patient_activities("MICU-01") if row["type"] == "cover_start"])
        h._cover("MICU-1", exclude="MICU-02")
        h._cover("MICU-1", exclude="MICU-02")
        self.assertEqual(len([n for n in h.nurses.values() if "MICU-01" in n["cover"]]), 1)
        self.assertEqual(len([row for row in h.patient_activities("MICU-01") if row["type"] == "cover_start"]), cover_events)

    def test_no_available_local_replacement_removes_busy_cover_without_borrowing_staff(self):
        h = hospital(policy="auto")
        for bid in h.units["MICU"]["bed_ids"]:
            admit(h, bid)
        h.request_diagnostic("MICU-1", "MICU-02", "portable_xray")
        h.step()
        cover = next(n for n in h.nurses.values() if "MICU-01" in n["cover"])
        for nurse in h.nurses.values():
            if nurse["unit"] == "MICU" and nurse["id"] not in ("MICU-1", cover["id"]):
                nurse["incident"] = 999
        h.request_diagnostic(cover["id"], "MICU-03", "blood_draw")
        h.step()
        self.assertNotIn("MICU-01", cover["cover"])
        self.assertFalse(any("MICU-01" in n["cover"] for n in h.nurses.values()))
        self.assertTrue(all(n["diagnostic_id"] is None and not n["cover"]
                            for n in h.nurses.values() if n["unit"] != "MICU"))

    def test_rest_can_start_before_a_queued_task_and_task_waits_for_rest_end(self):
        h = hospital()
        admit(h)
        nurse = h.nurses["MICU-1"]
        advance(h, nurse["fixed_break_t"] - 1)
        task = h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        h.step()
        self.assertTrue(nurse["on_break"])
        pending = h.diagnostic_task("MICU-01", task["id"])
        self.assertEqual(pending["status"], "requested")
        self.assertTrue(pending["paused"])
        self.assertIsNone(nurse["diagnostic_id"])
        finish(h, task["id"], "specimen_sent")
        self.assertFalse(nurse["on_break"])

    def test_patient_replacement_cancels_work_without_contaminating_new_admission(self):
        h = hospital()
        bed = admit(h)
        task = h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        h.step()
        old_pid = bed["patient"]["src"]["pid"]
        bed["patient"] = None
        new = admit(h)
        self.assertEqual(new["patient"]["src"]["pid"], old_pid)
        self.assertEqual(h.patient_diagnostics("MICU-01"), [])
        with self.assertRaises(ValueError):
            h.diagnostic_task("MICU-01", task["id"])
        h.step()
        self.assertEqual(h.diagnostics[0]["status"], "cancelled")
        self.assertIsNone(h.nurses["MICU-1"]["diagnostic_id"])
        self.assertEqual(h.patient_activities("MICU-01"), [])
        self.assertTrue(all(point["t"] >= new["patient"]["admit_t"]
                            for point in h.patient_vital_history("MICU-01")["points"]))

    def test_discharge_cancels_pending_task(self):
        h = hospital()
        bed = admit(h)
        bed["patient"]["src"] = dict(copy.deepcopy(bed["patient"]["src"]), los_min=1)
        task = h.request_diagnostic("MICU-1", "MICU-01", "portable_xray")
        h.step()
        self.assertIsNone(bed["patient"])
        self.assertEqual(h.diagnostics[0]["id"], task["id"])
        self.assertEqual(h.diagnostics[0]["status"], "cancelled")

    def test_shift_handover_preserves_task_and_attributes_completion_to_incoming_staff(self):
        h = hospital("14:59")
        admit(h)
        task = h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        h.step()
        snapshot = h.last_handover["patients"][0]
        self.assertEqual(snapshot["diagnostics"][0]["id"], task["id"])
        self.assertEqual(snapshot["receipt"]["status"], "pending")
        self.assertEqual(h.nurses["MICU-1"]["diagnostic_id"], task["id"])
        done = finish(h, task["id"], "specimen_sent")
        self.assertEqual(done["requested_by_staff_id"], "D-MICU-1")
        self.assertEqual(done["events"][-1]["staff_id"], "E-MICU-1")
        self.assertEqual(h.patient_activities("MICU-01", "MICU-1")[-1]["staff_id"], "E-MICU-1")
        self.assertEqual(snapshot["diagnostics"][0]["status"], "collecting")
        self.assertTrue(any("수신확인 대기" in line for line in h.log))

    def test_review_requires_current_completed_image_and_preserves_unlinked_provenance(self):
        h = hospital()
        admit(h)
        task = h.request_diagnostic("MICU-1", "MICU-01", "portable_xray")
        with self.assertRaises(ValueError):
            h.save_image_review("MICU-01", task["id"], {})
        finish(h, task["id"], "image_available")
        saved = h.save_image_review("MICU-01", task["id"], {"status": "not_run", "patient_linked": True})
        self.assertFalse(saved["review"]["patient_linked"])
        self.assertEqual(saved["review"]["image_source"], "public_nih_example")
        self.assertEqual(saved["review"]["status"], "not_run")
        self.assertEqual(h.care_actions, [])
        h.beds["MICU-01"]["patient"] = None
        admit(h)
        with self.assertRaises(ValueError):
            h.save_image_review("MICU-01", task["id"], {})

    def test_task_durations_are_reproducible_and_do_not_consume_patient_rng(self):
        first, second = hospital(), hospital()
        for h in (first, second):
            admit(h)
            before = h.rng.getstate()
            h.request_diagnostic("MICU-1", "MICU-01", "portable_xray")
            self.assertEqual(h.rng.getstate(), before)
        advance(first, 30)
        advance(second, 30)
        self.assertEqual(first.diagnostics, second.diagnostics)


class VitalHistoryTests(unittest.TestCase):
    def test_initial_and_observed_points_do_not_expose_future_source_samples(self):
        h = hospital()
        bed = admit(h)
        bed["patient"]["src"] = copy.deepcopy(bed["patient"]["src"])
        bed["patient"]["src"]["series"]["hr"][1] = 220  # future record at minute 30
        self.assertEqual([point["t"] for point in h.patient_vital_history("MICU-01")["points"]], [0])
        advance(h, 5)
        result = h.patient_vital_history("MICU-01")
        self.assertEqual([point["t"] for point in result["points"]], list(range(6)))
        self.assertTrue(all(point["hr"] == 90 and point["t"] <= result["t"] for point in result["points"]))
        self.assertEqual(result["source"], "test")
        self.assertIn("이전 값 이월", result["source_description"])
        result["points"][0]["hr"] = 0
        self.assertEqual(h.patient_vital_history("MICU-01")["points"][0]["hr"], 90)
        self.assertNotIn("_vital_history", h._bed_json(bed)["patient"])

    def test_injected_points_label_simulation_and_keep_original_observations(self):
        h = hospital(policy="auto")
        admit(h)
        h.trigger_emergency("MICU-01", "code_blue")
        h.step()
        point = h.patient_vital_history("MICU-01")["points"][-1]
        self.assertTrue(point["simulated"])
        self.assertEqual(point["hr"], 0)
        self.assertEqual(point["observed_vitals"]["hr"], 90)
        advance(h, 40)
        last = h.patient_vital_history("MICU-01")["points"][-1]
        self.assertFalse(last["simulated"])
        self.assertEqual(last["hr"], 90)

    def test_history_retains_only_24_hours_and_query_window_is_bounded(self):
        h = hospital()
        bed = admit(h)
        advance(h, 1500)
        points = h.patient_vital_history("MICU-01", 1440)["points"]
        self.assertEqual((points[0]["t"], points[-1]["t"], len(points)), (60, 1500, 1441))
        recent = h.patient_vital_history("MICU-01", 120)["points"]
        self.assertEqual((recent[0]["t"], recent[-1]["t"], len(recent)), (1380, 1500, 121))
        self.assertEqual(len(bed["patient"]["_vital_history"]), 1441)
        for value in (0, 1441, True, "120"):
            with self.assertRaises(ValueError):
                h.patient_vital_history("MICU-01", value)


if __name__ == "__main__":
    unittest.main()
