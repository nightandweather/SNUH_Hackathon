"""Demonstration emergencies keep real records and each ICU's staffing separate."""
import copy
import unittest

import engine
from test_shifts import admit, advance, hospital, recorded_pool


class EmergencyTests(unittest.TestCase):
    def test_overlay_follows_current_observations_and_restores_them_on_resolution(self):
        pool = recorded_pool()
        pool[0]["step"] = 1
        pool[0]["series"]["hr"] = [90 + i // 10 for i in range(201)]
        pool[0]["series"]["map"] = [75 - i // 20 for i in range(201)]
        source = copy.deepcopy(pool[0])
        h = engine.Hospital(pool, policy="auto", occupancy=0,
                            arrivals_per_unit_shift=0)
        bed = admit(h)
        h.trigger_emergency("MICU-01", "hypoxia")
        advance(h, 10)
        patient = h._bed_json(bed)["patient"]
        self.assertEqual(patient["observed_vitals"]["hr"], 91)
        self.assertEqual(patient["vitals"]["hr"], 91)
        self.assertEqual(patient["observed_vitals"]["spo2"], 99)
        self.assertEqual(patient["vitals"]["spo2"], 82)
        advance(h, 30)
        patient = h._bed_json(bed)["patient"]
        self.assertIsNone(patient["simulation_override"])
        self.assertEqual(patient["vitals"], patient["observed_vitals"])
        self.assertEqual((patient["vitals"]["hr"], patient["vitals"]["map"]), (94, 73))
        self.assertEqual(patient["risk"], 6)
        self.assertEqual(bed["patient"]["src"], source)

    def test_three_scenarios_overlay_observations_without_changing_source(self):
        for scenario, kind, need in (("code_blue", "arrest", 3), ("hypoxia", "det", 1),
                                      ("hypotension", "det", 1)):
            with self.subTest(scenario=scenario):
                h = hospital(policy="auto")
                bed = admit(h)
                source = copy.deepcopy(bed["patient"]["src"])
                observed = copy.deepcopy(bed["patient"]["vitals"])
                event = h.trigger_emergency("MICU-01", scenario)
                self.assertEqual((event["type"], event["need"]), (kind, need))
                self.assertTrue(event["simulated"])
                self.assertIn("simulation", event["label"].lower())
                patient = h._bed_json(bed)["patient"]
                self.assertEqual(patient["observed_vitals"], observed)
                self.assertEqual(patient["simulation_override"]["source"], "simulation_injected")
                for name, value in engine.EMERGENCY_SCENARIOS[scenario]["values"].items():
                    self.assertEqual(patient["vitals"][name], value)
                self.assertEqual(bed["patient"]["src"], source)
                self.assertEqual(h.care_actions, [])
                h.step()
                self.assertIsNotNone(bed["patient"]["simulation_override"])
                advance(h, 40)
                self.assertIsNotNone(h.incidents[0]["end"])
                patient = h._bed_json(bed)["patient"]
                self.assertIsNone(patient["simulation_override"])
                self.assertEqual(patient["vitals"], observed)
                self.assertEqual(bed["patient"]["src"], source)

    def test_busy_and_empty_beds_and_invalid_scenarios_are_rejected(self):
        h = hospital()
        admit(h)
        for scenario in ("unsupported", None, {}):
            with self.assertRaises(ValueError):
                h.trigger_emergency("MICU-01", scenario)
        with self.assertRaises(ValueError):
            h.trigger_emergency("MICU-02", "code_blue")
        h.trigger_emergency("MICU-01", "hypoxia")
        with self.assertRaises(ValueError):
            h.trigger_emergency("MICU-01", "hypotension")
        self.assertEqual(len(h.incidents), 1)

    def test_all_nursing_policies_dispatch_and_cover_only_within_the_same_icu(self):
        for policy in ("fixed", "auto"):
            with self.subTest(policy=policy):
                h = hospital(policy=policy)
                admit(h)
                admit(h, "MICU-02")
                h.trigger_emergency("MICU-01", "code_blue")
                advance(h, 6)
                event = h.incidents[0]
                self.assertEqual(len(event["responders"]), 3)
                self.assertTrue(all(h.nurses[nid]["unit"] == "MICU" for nid in event["responders"]))
                self.assertEqual(event["helpers"], 0)
                for n in h.nurses.values():
                    self.assertTrue(all(h.beds[bid]["unit"] == n["unit"] for bid in n["beds"] + n["cover"]))

    def test_unavailable_local_nurses_leave_a_shortage_despite_idle_other_icus(self):
        for policy in ("fixed", "auto"):
            with self.subTest(policy=policy):
                h = hospital(policy=policy)
                admit(h)
                for nurse in h.nurses.values():
                    if nurse["unit"] == "MICU":
                        nurse["incident"] = 999
                h.trigger_emergency("MICU-01", "code_blue")
                advance(h, 40)
                event = h.state()["incidents"][0]
                self.assertEqual(event["responders"], [])
                self.assertEqual(event["shortage"], 3)
                self.assertEqual(event["doctor_id"], "MD-MICU")
                self.assertIsNotNone(event["doctor_arrived_t"])
                self.assertIsNone(h.incidents[0]["end"])
                self.assertTrue(all(n["incident"] is None for n in h.nurses.values() if n["unit"] != "MICU"))

    def test_each_icu_has_an_independent_md_and_a_busy_md_waits_locally(self):
        h = hospital(policy="auto")
        admit(h)
        admit(h, "MICU-05")
        first = h.trigger_emergency("MICU-01", "code_blue")
        waiting = h.trigger_emergency("MICU-05", "hypoxia")
        self.assertEqual(len(h.state()["doctors"]), 8)
        self.assertEqual(first["doctor_id"], waiting["doctor_id"])
        self.assertTrue(waiting["doctor_waiting"])
        self.assertEqual(h.doctors["MD-MICU"]["incident"], first["id"])
        advance(h, 20)
        event = next(i for i in h.state()["incidents"] if i["id"] == waiting["id"])
        self.assertTrue(event["doctor_waiting"])
        self.assertIsNone(event["doctor_arrived_t"])
        self.assertTrue(all(d["status"] == "available" for d in h.doctors.values() if d["unit"] != "MICU"))
        advance(h, 20)
        second = next(i for i in h.incidents if i["id"] == waiting["id"])
        self.assertIsNotNone(second["doctor_arrived_t"])
        self.assertIsNone(second["end"])
        self.assertEqual(h.doctors["MD-MICU"]["incident"], waiting["id"])
        advance(h, 20)
        self.assertIsNotNone(second["end"])
        self.assertEqual(h.doctors["MD-MICU"]["status"], "available")

    def test_emergency_metadata_and_md_persist_across_nursing_handover(self):
        h = hospital(policy="auto")
        bed = admit(h)
        advance(h, 479)
        before = h.record_care_action("MICU-1", "MICU-01", "Records Acknowledged 후 ChargeNurse에게 보고함")
        event = h.trigger_emergency("MICU-01", "code_blue")
        md = h.doctors["MD-MICU"]
        h.step()
        self.assertEqual(h.state()["shift"]["code"], "E")
        self.assertIs(h.doctors["MD-MICU"], md)
        self.assertEqual(md["incident"], event["id"])
        patient = next(p for p in h.last_handover["patients"] if p["bed"] == "MICU-01")
        handed_event = patient["open_events"][0]
        self.assertEqual(handed_event["scenario"], "code_blue")
        self.assertTrue(handed_event["simulated"])
        self.assertEqual(handed_event["doctor_id"], "MD-MICU")
        self.assertIsNotNone(handed_event["doctor_arrived_t"])
        self.assertEqual(patient["vitals"]["hr"], 0)
        self.assertEqual(patient["observed_vitals"]["hr"], 90)
        self.assertEqual(patient["actions"], [before])
        self.assertTrue(any(a["type"] == "dispatch" for a in patient["activities"]))
        self.assertTrue(all(a["source"] == "simulation_activity" for a in patient["activities"]))
        self.assertEqual(len(h.care_actions), 1)
        self.assertEqual(h.patient_actions("MICU-01", "MICU-1"), [])
        self.assertEqual(h.patient_activities("MICU-01", "MICU-1"), [])
        self.assertEqual(bed["patient"]["simulation_override"]["scenario"], "code_blue")

    def test_simulator_activities_are_separate_factual_hooks_for_current_admission(self):
        h = hospital(policy="auto")
        bed = admit(h)
        admit(h, "MICU-02")
        h.trigger_emergency("MICU-01", "code_blue")
        self.assertTrue(any(a["type"] == "dispatch" for a in h.patient_activities("MICU-01")))
        self.assertFalse(any(a["type"] == "arrival" for a in h.patient_activities("MICU-01")))
        self.assertTrue(any(a["type"] == "cover_start" for a in h.patient_activities("MICU-02")))
        advance(h, 40)
        entries = h.patient_activities("MICU-01")
        self.assertTrue({"dispatch", "arrival", "response_end"}.issubset({a["type"] for a in entries}))
        self.assertTrue(all(a["source"] == "simulation_activity" and a["staff_id"].startswith("D-MICU") for a in entries))
        self.assertEqual(h.care_actions, [])
        self.assertEqual(len([a for a in entries if a["type"] == "arrival"]), 3)
        self.assertEqual(len([a for a in entries if a["type"] == "response_end"]), 3)
        old_count = len(h.activities)
        bed["patient"] = None
        admit(h)
        self.assertEqual(h.patient_activities("MICU-01"), [])
        self.assertEqual(len(h.activities), old_count)


if __name__ == "__main__":
    unittest.main()
