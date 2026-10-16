"""Grounding checks use mock model responses; no server or network is started."""
import copy
import json
import unittest
from unittest.mock import patch

import consult


def record(text="MAP 재측정 58, Assigned의 보고", **overrides):
    result = {"t": 35, "clock": "07:35", "staff_id": "D-MICU-1", "nurse_id": "MICU-1",
              "shift_code": "D", "cycle": 0, "bed": "MICU-01", "pid": "M-test",
              "admit_t": 0, "text": text, "source": "user_entered"}
    result.update(overrides)
    return result


class FakeHospital:
    def __init__(self):
        self.t = 60
        self.units = {"MICU": {"name": "Medical ICU"}}
        self.nurses = {"MICU-1": {"id": "MICU-1", "staff_id": "D-MICU-1", "shift_code": "D", "fatigue": 20},
                       "MICU-2": {"id": "MICU-2", "staff_id": "D-MICU-2", "shift_code": "D", "fatigue": 10}}
        src = {"pid": "M-test", "source": "MIMIC-IV demo", "age": 70, "sex": "F", "dx": "Records된 Recorded diagnosis",
               "step": 5, "vent": True, "pressor": True,
               "series": {"hr": [110] * 60, "map": [58] * 60, "spo2": [91] * 60, "rr": [25] * 60}}
        patient = {"src": src, "offset": 60, "admit_t": 0, "risk": 78, "risk_hours": 4,
                   "vitals": {"hr": 110, "map": 58, "spo2": 91, "rr": 25}, "abn": ["MAP", "SpO2"]}
        self.beds = {"MICU-01": {"id": "MICU-01", "unit": "MICU", "nurse": "MICU-1", "patient": patient},
                     "MICU-02": {"id": "MICU-02", "unit": "MICU", "nurse": "MICU-2", "patient": None}}
        self.actions = [record()]
        self.incidents = [{"bed": "MICU-01", "end": None, "label": "Rapid deterioration", "start": 55},
                          {"bed": "MICU-02", "end": None, "label": "다른 Patient 사 events", "start": 52}]
        self.last_handover = None

    def _shift_at(self, time):
        return {"code": "D", "label": "Day", "cycle": 0, "elapsed_min": time, "remaining_min": 480 - time}

    def clock(self, time=None):
        time = self.t if time is None else time
        minute = 7 * 60 + int(time)
        return f"{minute // 60 % 24:02d}:{minute % 60:02d}"

    def _vital(self, source, key, index):
        return source["series"][key][index]

    def patient_actions(self, bed_id):
        return copy.deepcopy(self.actions)


class HandoverTests(unittest.TestCase):
    def setUp(self):
        self.hospital = FakeHospital()
        self.image = patch.object(consult, "cxr_for", return_value={"finding": "Edema", "file": "example.jpg", "image_id": "public-example"})
        self.image.start()
        self.addCleanup(self.image.stop)

    def context(self, nurse_id="MICU-1"):
        return consult.context(self.hospital, "MICU-01", nurse_id=nurse_id)

    def test_fallback_has_record_author_time_current_state_and_open_issue(self):
        with patch.object(consult, "chat", return_value=None), patch.object(consult, "model_name", side_effect=AssertionError("fallback must not advertise a model")):
            result = consult.handover_turn(self.context())
        self.assertEqual((result["mode"], result["model"]), ("rules", None))
        for fragment in ("07:35", "D-MICU-1", "MAP 재측정 58, Assigned의 보고", "08:00", "MAP 58", "Risk index 78", "Rapid deterioration", "5 min elapsed"):
            self.assertIn(fragment, result["text"])
        self.assertNotIn("다른 Patient 사 events", result["text"])

    def test_history_claim_and_ai_advice_are_not_completed_records(self):
        self.hospital.actions = []
        history = [{"role": "nurse", "text": "비공식 대화: 펌프 투약 완료. 내가 여태 뭘 했고 이 Patient Handover해줘"},
                   {"role": "agent", "text": "미Records 투약이 완료됐습니다."}]
        with patch.object(consult, "chat", return_value=None):
            text = consult.agent_turn(self.context(), history)
        self.assertIn("My care records this shift · D-MICU-1 (0 events)", text)
        self.assertIn("Not recorded", text)
        self.assertNotIn("펌프 투약 완료", text)
        self.assertNotIn("미Records 투약", text)

    def test_current_person_is_separate_from_prior_shift_and_prior_cycle(self):
        self.hospital.actions += [record("이전 Night Nurse Acknowledged", staff_id="N-MICU-1", shift_code="N", t=20),
                                  record("동료 Nurse 관찰", staff_id="D-MICU-2", nurse_id="MICU-2", t=30),
                                  record("전날 같은 Day shift Records", cycle=-1, t=10)]
        ctx = self.context()
        self.assertEqual(len(ctx["handover"]["requester_actions"]), 1)
        # Serialization must not destroy separation between a nurse's actions
        # and other records (object identity is not an author identifier).
        ctx = json.loads(json.dumps(ctx))
        with patch.object(consult, "chat", return_value=None):
            text = consult.handover_turn(ctx)["text"]
        own, others = text.split("Previous shift and colleague care records", 1)
        self.assertNotIn("이전 Night", own)
        self.assertNotIn("전날 같은 Day", own)
        self.assertNotIn("동료 Nurse", own)
        self.assertIn("N-MICU-1", others)
        self.assertIn("D-MICU-2", others)
        self.assertIn("전날 같은 Day", others)

    def test_only_current_patient_admission_user_records_are_used(self):
        self.hospital.actions += [record("다른 Patient 비밀", pid="M-other"), record("이전 입원 Records", admit_t=-100),
                                  record("다른 Bed Records", bed="MICU-02"), record("AI 권고만", source="ai"),
                                  record("미래 Records", t=70)]
        ctx = self.context()
        self.assertEqual(len(ctx["actions"]), 1)
        self.assertEqual(ctx["patient_key"], {"pid": "M-test", "admit_t": 0})
        for fragment in ("다른 Patient 비밀", "이전 입원 Records", "다른 Bed Records", "AI 권고만", "미래 Records"):
            self.assertNotIn(fragment, ctx["text"])

    def test_model_prompt_is_text_only_grounded_and_history_is_absent(self):
        ctx = self.context()
        history = [{"role": "nurse", "text": "대화에만 있는 거짓 투약완료, Handover해줘"}]
        with patch.object(consult, "chat", return_value="Current MAP 재측정 결과를 Next shift자에게 전달했나요?") as chat,\
                patch.object(consult, "model_name", return_value="GLM-local"),\
                patch.object(consult, "_img_part", side_effect=AssertionError("handover must be text only")):
            text = consult.agent_turn(ctx, history, task="handover")
        messages = chat.call_args.args[0]
        self.assertTrue(all(isinstance(row["content"], str) for row in messages))
        prompt = json.dumps(messages, ensure_ascii=False)
        self.assertIn("MAP 재측정 58, Assigned의 보고", prompt)
        self.assertIn("chat or AI recommendations", prompt)
        self.assertNotIn("거짓 투약완료", prompt)
        self.assertNotIn("image_url", prompt)
        self.assertNotIn("Edema", prompt)
        self.assertIn("AI review questions (not care records", text)
        self.assertIn("[User entry]", text)

    def test_model_mode_requires_actual_nonempty_response(self):
        for response, expected in ((None, "rules"), ("", "rules"), ("  ", "rules"), ("추가 Care records을 Acknowledged할까요?", "model")):
            with self.subTest(response=response), patch.object(consult, "chat", return_value=response),\
                    patch.object(consult, "model_name", return_value="GLM-local"):
                result = consult.handover_turn(self.context())
            self.assertEqual(result["mode"], expected)
            self.assertEqual(result["model"], "GLM-local" if expected == "model" else None)

    def test_new_context_includes_newly_recorded_work(self):
        first = self.context()
        self.hospital.actions.append(record("추가 관찰 Records", t=59, clock="07:59"))
        second = self.context()
        self.assertEqual(len(first["actions"]), 1)
        self.assertEqual(len(second["actions"]), 2)
        with patch.object(consult, "chat", return_value=None):
            self.assertIn("추가 관찰 Records", consult.handover_turn(second)["text"])

    def test_previous_handover_is_patient_and_admission_specific(self):
        self.hospital.last_handover = {"t": 40, "clock": "07:40", "from_code": "N", "to_code": "D",
                                       "from_label": "Night", "to_label": "Day", "patients": [
            {"bed": "MICU-01", "pid": "M-test", "admit_t": -100, "from_staff_id": "wrong-old-admission"},
            {"bed": "MICU-02", "pid": "M-other", "admit_t": 0, "from_staff_id": "wrong-other-patient"},
            {"bed": "MICU-01", "pid": "M-test", "admit_t": 0, "from_staff_id": "N-MICU-1", "to_staff_id": "D-MICU-1"}]}
        ctx = self.context()
        self.assertEqual(ctx["handover"]["last_handover"]["patient"]["from_staff_id"], "N-MICU-1")
        self.assertNotIn("wrong", json.dumps(ctx["handover"]))

    def test_record_prompt_is_bounded_and_omissions_are_explicit(self):
        self.hospital.actions = [record("Care records " + "x" * 990, t=i, clock=f"07:{i:02d}") for i in range(60)]
        with patch.object(consult, "chat", return_value=None) as chat:
            result = consult.handover_turn(self.context())
        prompt = chat.call_args.args[0][1]["content"]
        data = json.loads(prompt.split("\n", 1)[1])
        self.assertGreater(data["actions_omitted_count"], 0)
        self.assertLess(len(prompt), 16000)
        self.assertIn("Total 60 records; showing latest 40 records shown", result["text"])

    def test_xray_has_no_fictitious_time_and_sbar_uses_vitals_not_records(self):
        self.hospital.actions = [record("  기타 Care records: 예시와 무관")]
        ctx = self.context()
        self.assertNotIn("오늘 06:00", ctx["text"])
        self.assertIn("Not this patient's image or report", ctx["text"])
        with patch.object(consult, "chat", return_value=None):
            text = consult.agent_turn(ctx, [], task="sbar")
        self.assertIn("08:00: 110 / 58 / 91 / 25", text)
        self.assertNotIn("기타 Care records", text)

    def test_handover_request_detection(self):
        for text in ("Prepare a handover", "Show my care records", "Show my work history", "인계해줘", "내가 여태 뭘 했고 현재 상태 정리해줘"):
            self.assertTrue(consult.is_handover_request([{"role": "nurse", "text": text}]))
        for text in ("MAP is 58, what should I check?", "Medication given", "Do not prepare a handover", "인계 말고 혈압만 봐줘"):
            self.assertFalse(consult.is_handover_request([{"role": "nurse", "text": text}]))
        self.assertTrue(consult.is_handover_request([], task="handover"))
        self.assertFalse(consult.is_handover_request([{"role": "nurse", "text": "Prepare handover"}], task="sbar"))
        self.assertFalse(consult.is_handover_request([{"role": "agent", "text": "Prepare handover"}]))

    def test_emergency_injection_is_labeled_and_does_not_become_performed_work(self):
        self.hospital.actions = []
        patient = self.hospital.beds["MICU-01"]["patient"]
        patient["observed_vitals"] = copy.deepcopy(patient["vitals"])
        patient["vitals"].update(hr=20, map=25)
        patient["simulation_override"] = {"incident_id": 10, "scenario": "code_blue", "label": "Code blue",
                                           "source": "simulation_injected", "values": {"hr": 20, "map": 25}}
        self.hospital.incidents[0].update(label="Cardiac arrest", scenario="code_blue", simulated=True, shortage=2,
                                          doctor_id="MICU-MD", doctor_called_t=56, doctor_arrived_t=None,
                                          doctor_waiting=True, doctor_status="waiting")
        ctx = self.context()
        self.assertEqual(ctx["handover"]["patient"]["vitals_origin"], "simulation_injected")
        self.assertEqual(ctx["handover"]["patient"]["observed_vitals"]["map"], 58)
        self.assertIn("not original MIMIC observations", ctx["text"])
        self.assertIn("[Simulated emergency]", ctx["latest_vitals_line"])
        with patch.object(consult, "chat", return_value=None):
            result = consult.handover_turn(ctx)
        text = result["text"]
        for value in ("Current simulated state", "MAP 25", "not original MIMIC observations", "Nurse response shortage: 2 staff", "MD MICU-MD", "Notified 07:56", "Arrival not yet recorded", "Awaiting physician in the same ICU"):
            self.assertIn(value, text)
        self.assertIn("My care records this shift · D-MICU-1 (0 events)", text)
        self.assertEqual(ctx["actions"], [])

    def test_doctor_arrival_is_available_only_when_it_has_occurred(self):
        self.hospital.incidents[0].update(doctor_id="MICU-MD", doctor_called_t=56, doctor_arrived_t=70)
        future = self.context()["handover"]["open_events"][0]
        self.assertIsNone(future["doctor_arrived_t"])
        self.assertIsNone(future["doctor_arrived_clock"])
        self.hospital.incidents[0]["doctor_arrived_t"] = 59
        current = self.context()
        self.assertEqual(current["handover"]["open_events"][0]["doctor_arrived_clock"], "07:59")
        with patch.object(consult, "chat", return_value=None):
            self.assertIn("Arrived 07:59 (Simulation)", consult.handover_turn(current)["text"])

    def test_day_display_is_one_based_but_identity_cycle_is_unchanged(self):
        ctx = self.context()
        self.assertEqual(ctx["handover"]["shift"]["cycle"], 0)
        self.assertEqual(ctx["handover"]["requester"]["cycle"], 0)
        with patch.object(consult, "chat", return_value=None):
            text = consult.handover_turn(ctx)["text"]
        self.assertIn("Current shift: Day · 1day", text)
        self.assertIn("Dshift/1day", text)
        self.assertNotIn("0day", text)

    def test_simulation_activities_are_scoped_to_patient_and_person_not_care_actions(self):
        self.hospital.actions = []
        activities = [
            record("Synthetic Nurse 침상 Arrived", t=40, source="simulation_activity", type="arrival", incident_id=1),
            record("이전 Night Synthetic Dispatched", t=30, staff_id="N-MICU-1", shift_code="N", source="simulation_activity", type="dispatch", incident_id=1),
            record("이전 입원 Synthetic 활동", admit_t=-100, source="simulation_activity", type="arrival"),
            record("다른 Patient Synthetic 활동", pid="M-other", source="simulation_activity", type="arrival"),
            record("MD Arrived을 간호 수행으로 오인", source="simulation_activity", type="doctor_arrival"),
            record("AI의 Synthetic 주장", source="ai", type="arrival"),
            record("미래 활동", t=70, source="simulation_activity", type="arrival"),
        ]
        self.hospital.patient_activities = lambda bed: copy.deepcopy(activities)
        ctx = self.context()
        self.assertEqual(ctx["actions"], [])
        self.assertEqual(len(ctx["activities"]), 2)
        self.assertEqual(len(ctx["handover"]["requester_activities"]), 1)
        with patch.object(consult, "chat", return_value=None) as chat:
            text = consult.handover_turn(json.loads(json.dumps(ctx)))["text"]
        completed, simulated = text.split("Simulation activity records (not actual treatment records):", 1)
        self.assertIn("My care records this shift · D-MICU-1 (0 events)", completed)
        self.assertNotIn("침상 Arrived", completed)
        self.assertIn("My simulation activity this shift · D-MICU-1 (1 events)", simulated)
        own, others = simulated.split("Previous shift and colleague simulation activity", 1)
        self.assertIn("Synthetic Nurse 침상 Arrived", own)
        self.assertNotIn("이전 Night", own)
        self.assertIn("이전 Night Synthetic Dispatched", others)
        for excluded in ("이전 입원", "다른 Patient Synthetic", "MD Arrived을", "AI의 Synthetic 주장", "미래 활동"):
            self.assertNotIn(excluded, text)
        prompt_data = json.loads(chat.call_args.args[0][1]["content"].split("\n", 1)[1])
        self.assertEqual(prompt_data["actions"], [])
        self.assertEqual(prompt_data["activities"][0]["source"], "simulation_activity")
        self.assertEqual(prompt_data["requester_activity_count"], 1)


if __name__ == "__main__":
    unittest.main()
