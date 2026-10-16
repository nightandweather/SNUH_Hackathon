"""Non-socket checks for distinct crews, continuous care, and factual care logs."""
import copy
import unittest

import engine


def recorded_pool():
    return [{"pid": "case-1", "source": "test", "unit_type": "MICU", "dx": "Records 사례",
             "age": 50, "sex": "F", "vent": 0, "pressor": 0, "prior_risk": 10,
             "los_min": 6000, "step": 30, "cpr": [],
             "series": {"hr": [90] * 201, "map": [75] * 201,
                        "spo2": [99] * 201, "rr": [18] * 201}}]


def hospital(start="07:00", policy="fixed"):
    cfg = engine.load_config()
    cfg["start_clock"] = start
    return engine.Hospital(recorded_pool(), policy=policy, occupancy=0,
                           arrivals_per_unit_shift=0, cfg=cfg)


def admit(h, bed_id="MICU-01"):
    bed = h.beds[bed_id]
    bed["patient"] = h._pick_patient(h.units[bed["unit"]]["type"], False)
    h._update_patient(bed)
    return bed


def advance(h, minutes):
    for _ in range(minutes):
        h.step()


class ShiftTests(unittest.TestCase):
    def test_three_distinct_crews_keep_duty_slots(self):
        h = hospital()
        state = h.state()
        self.assertEqual(len(state["nurses"]), 40)
        self.assertEqual(len(state["roster"]), 120)
        self.assertEqual(len({n["staff_id"] for n in state["roster"]}), 120)
        self.assertEqual(sum(n["on_duty"] for n in state["roster"]), 40)
        self.assertEqual(state["shift"]["code"], "D")
        slots = set(h.nurses)
        day = {n["staff_id"] for n in h.nurses.values()}
        advance(h, 480)
        self.assertEqual(set(h.nurses), slots)
        self.assertTrue(day.isdisjoint({n["staff_id"] for n in h.nurses.values()}))
        self.assertEqual(h.state()["shift"]["code"], "E")
        self.assertTrue(all(n["fatigue"] == n["work"] == 0 for n in h.nurses.values()))
        self.assertEqual(len(h.last_shift["staff"]), 40)

    def test_handover_window_midnight_and_full_day(self):
        h = hospital()
        advance(h, 464)
        self.assertFalse(h.state()["shift"]["in_handover"])
        h.step()
        self.assertTrue(h.state()["shift"]["in_handover"])
        self.assertEqual(h.state()["shift"]["remaining_min"], 15)
        advance(h, 495)
        self.assertEqual((h.clock(), h.state()["shift"]["code"]), ("23:00", "N"))
        advance(h, 60)
        self.assertEqual((h.clock(), h.state()["shift"]["elapsed_min"]), ("00:00", 60))
        advance(h, 420)
        self.assertEqual((h.clock(), h.state()["shift"]["code"], h.state()["shift"]["cycle"]),
                         ("07:00", "D", 1))
        self.assertEqual([r["to_code"] for r in h.handover_history], ["E", "N", "D"])
        self.assertEqual(len(h.shift_history), 3)
        self.assertTrue(all(n["staff_id"].startswith("D-") for n in h.nurses.values()))

    def test_non_default_start_uses_wall_clock_boundaries(self):
        for start, initial, wait, following in (("14:50", "D", 10, "E"),
                                                ("03:00", "N", 240, "D"),
                                                ("23:00", "N", 480, "D")):
            with self.subTest(start=start):
                h = hospital(start)
                self.assertEqual(h.state()["shift"]["code"], initial)
                advance(h, wait - 1)
                self.assertEqual(h.state()["shift"]["code"], initial)
                h.step()
                self.assertEqual(h.state()["shift"]["code"], following)
                self.assertEqual(h.state()["shift"]["elapsed_min"], 0)
                self.assertEqual(h.last_shift["end_t"], wait)
                self.assertEqual(h.last_handover["from_code"], initial)

    def test_active_response_and_patient_state_survive_handover(self):
        h = hospital()
        bed = admit(h)
        advance(h, 470)
        h._new_incident(bed, "arrest")
        incident = h.incidents[-1]
        advance(h, 9)
        responders = list(incident["responders"])
        self.assertTrue(responders)
        before = copy.deepcopy(bed["patient"])
        h.step()
        self.assertIsNone(incident["end"])
        self.assertEqual(incident["responders"], responders)
        self.assertEqual(bed["patient"]["src"]["pid"], before["src"]["pid"])
        self.assertEqual(bed["patient"]["vitals"], before["vitals"])
        self.assertEqual(bed["patient"]["offset"], before["offset"] + 1)
        for nid in responders:
            self.assertEqual(h.nurses[nid]["incident"], incident["id"])
            self.assertTrue(h.nurses[nid]["staff_id"].startswith("E-"))
        handover = next(p for p in h.last_handover["patients"] if p["bed"] == bed["id"])
        self.assertEqual(handover["vitals"], bed["patient"]["vitals"])
        self.assertEqual(handover["from_staff_id"], "D-MICU-1")
        self.assertEqual(handover["to_staff_id"], "E-MICU-1")
        self.assertEqual(handover["open_events"][0]["responders"], responders)
        self.assertTrue(all(n.startswith("D-") for n in handover["open_events"][0]["from_responders"]))
        self.assertTrue(all(n.startswith("E-") for n in handover["open_events"][0]["to_responders"]))
        frozen = copy.deepcopy(handover)
        advance(h, 35)
        self.assertIsNotNone(incident["end"])
        self.assertEqual(h.last_handover["patients"][0], frozen)

    def test_stats_are_preserved_and_comparison_measures_remain_cumulative(self):
        h = hospital()
        advance(h, 479)
        nurse = h.nurses["MICU-1"]
        nurse.update(work=17.25, peak=88, over_warn=7, fatigue=80)
        before = h.metrics()
        h.step()
        after = h.metrics()
        archived = next(n for n in h.last_shift["staff"] if n["slot_id"] == "MICU-1")
        self.assertEqual(archived["work"], 17.25)
        self.assertEqual(archived["staff_id"], "D-MICU-1")
        self.assertGreaterEqual(after["fatigue_high_min"], before["fatigue_high_min"])
        self.assertEqual(after["fatigue_max"], 88)
        self.assertEqual(after["workload_sd"], before["workload_sd"])
        self.assertEqual(after["fatigue_current_mean"], 0)
        self.assertEqual(after["fatigue_mean_basis"], "last_completed_shift")
        self.assertEqual(after["fatigue_last_shift_label"], "Day")
        h.step()
        self.assertEqual(h.metrics()["fatigue_mean_basis"], "current_on_duty")
        self.assertEqual(h.last_shift["staff"], h.shift_history[0]["staff"])

    def test_eight_and_twenty_four_hour_comparisons_are_numeric(self):
        for policy in ("fixed", "auto"):
            for minutes in (480, 1440):
                with self.subTest(policy=policy, minutes=minutes):
                    result = engine.run(recorded_pool(), policy, 4, minutes)
                    self.assertEqual(result["minutes"], minutes)
                    self.assertEqual(result["fatigue_mean_basis"], "last_completed_shift")
                    for field in ("workload_sd", "fatigue_max", "fatigue_mean", "fatigue_high_min",
                                  "unattended_min", "unattended_high_min"):
                        self.assertIsInstance(result[field], (int, float))
                        self.assertGreaterEqual(result[field], 0)


class CareLogTests(unittest.TestCase):
    def setUp(self):
        self.h = hospital()
        self.bed = admit(self.h)

    def test_only_explicit_completed_care_is_recorded_with_current_staff(self):
        self.assertEqual(self.h.patient_actions("MICU-01"), [])
        record = self.h.record_care_action("MICU-1", "MICU-01", "  혈압 재측정 후 Assigned의에게 보고함  ")
        self.assertEqual(record["source"], "user_entered")
        self.assertEqual(record["staff_id"], "D-MICU-1")
        self.assertEqual(record["shift_code"], "D")
        self.assertEqual(record["text"], "혈압 재측정 후 Assigned의에게 보고함")
        self.assertEqual(record["admit_t"], self.bed["patient"]["admit_t"])
        self.assertEqual(record["pid"], self.bed["patient"]["src"]["pid"])
        returned = self.h.patient_actions("MICU-01")
        returned[0]["text"] = "modified"
        self.assertEqual(self.h.patient_actions("MICU-01")[0]["text"], record["text"])
        state = self.h.state()
        self.assertEqual(next(n for n in state["nurses"] if n["id"] == "MICU-1")["care_actions"], [record])
        self.assertEqual(self.h._bed_json(self.bed)["patient"]["admit_t"], record["admit_t"])

    def test_invalid_input_and_unrelated_nurse_are_rejected(self):
        for text in ("", "  ", "x" * 1001, None):
            with self.assertRaises(ValueError):
                self.h.record_care_action("MICU-1", "MICU-01", text)
        for nurse in ("MICU-2", "SICU1-C"):
            with self.assertRaises(PermissionError):
                self.h.record_care_action(nurse, "MICU-01", "Acknowledged함")
        with self.assertRaises(ValueError):
            self.h.record_care_action("MICU-1", "MICU-02", "Acknowledged함")
        self.assertEqual(self.h.care_actions, [])
        self.h.record_care_action("MICU-C", "MICU-01", "병동 ChargeNurse Acknowledged함")

    def test_same_unit_cover_and_responder_can_record_but_cross_unit_cannot(self):
        self.h.nurses["MICU-2"]["cover"].append("MICU-01")
        self.h.record_care_action("MICU-2", "MICU-01", "대신 관찰함")
        self.h._new_incident(self.bed, "arrest")
        self.h.incidents[-1]["responders"].append("MICU-3")
        self.h.record_care_action("MICU-3", "MICU-01", "Called받아 Arrived 후 Acknowledged함")
        self.h.incidents[-1]["responders"].append("SICU1-1")
        self.h.nurses["SICU1-1"]["cover"].append("MICU-01")
        with self.assertRaises(PermissionError):
            self.h.record_care_action("SICU1-1", "MICU-01", "다른 ICU에서 Records 시도")
        self.assertEqual(len(self.h.patient_actions("MICU-01")), 2)
        self.assertEqual(len(self.h.patient_actions("MICU-01", "MICU-2")), 1)

    def test_handover_keeps_actions_and_new_crew_records_under_new_person(self):
        original = self.h.record_care_action("MICU-1", "MICU-01", "Day에서 수행한 일")
        advance(self.h, 480)
        handover = next(p for p in self.h.last_handover["patients"] if p["bed"] == "MICU-01")
        self.assertEqual(handover["actions"], [original])
        self.assertEqual(self.h.last_shift["care_actions"], [original])
        current = self.h.record_care_action("MICU-1", "MICU-01", "Evening에서 수행한 일")
        self.assertEqual(current["staff_id"], "E-MICU-1")
        self.assertEqual(self.h.patient_actions("MICU-01"), [original, current])
        self.assertEqual(self.h.patient_actions("MICU-01", "MICU-1"), [current])
        self.assertEqual(handover["actions"], [original])
        n = next(n for n in self.h.state()["nurses"] if n["id"] == "MICU-1")
        self.assertEqual(n["care_actions"], [current])

    def test_reused_bed_and_patient_id_do_not_reuse_previous_admission_logs(self):
        self.h.record_care_action("MICU-1", "MICU-01", "이전 Admission Patient Care records")
        advance(self.h, 1)
        self.bed["patient"] = None
        self.assertEqual(self.h.patient_actions("MICU-01"), [])
        admit(self.h)
        self.assertEqual(self.h.patient_actions("MICU-01"), [])
        new = self.h.record_care_action("MICU-1", "MICU-01", "재Admission 후 Care records")
        self.assertEqual(new["admit_t"], 1)
        self.assertEqual(self.h.patient_actions("MICU-01"), [new])
        self.assertEqual(len(self.h.care_actions), 2)


if __name__ == "__main__":
    unittest.main()
