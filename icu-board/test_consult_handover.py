"""Grounding checks use mock model responses; no server or network is started."""
import copy
import json
import unittest
from unittest.mock import patch

import consult


def record(text="MAP 재측정 58, 담당의 보고", **overrides):
    result = {"t": 35, "clock": "07:35", "staff_id": "D-MICU-1", "nurse_id": "MICU-1",
              "shift_code": "D", "cycle": 0, "bed": "MICU-01", "pid": "M-test",
              "admit_t": 0, "text": text, "source": "user_entered"}
    result.update(overrides)
    return result


class FakeHospital:
    def __init__(self):
        self.t = 60
        self.units = {"MICU": {"name": "내과 ICU"}}
        self.nurses = {"MICU-1": {"id": "MICU-1", "staff_id": "D-MICU-1", "shift_code": "D", "fatigue": 20},
                       "MICU-2": {"id": "MICU-2", "staff_id": "D-MICU-2", "shift_code": "D", "fatigue": 10}}
        src = {"pid": "M-test", "source": "MIMIC-IV demo", "age": 70, "sex": "F", "dx": "기록된 진단",
               "step": 5, "vent": True, "pressor": True,
               "series": {"hr": [110] * 60, "map": [58] * 60, "spo2": [91] * 60, "rr": [25] * 60}}
        patient = {"src": src, "offset": 60, "admit_t": 0, "risk": 78, "risk_hours": 4,
                   "vitals": {"hr": 110, "map": 58, "spo2": 91, "rr": 25}, "abn": ["MAP", "SpO2"]}
        self.beds = {"MICU-01": {"id": "MICU-01", "unit": "MICU", "nurse": "MICU-1", "patient": patient},
                     "MICU-02": {"id": "MICU-02", "unit": "MICU", "nurse": "MICU-2", "patient": None}}
        self.actions = [record()]
        self.incidents = [{"bed": "MICU-01", "end": None, "label": "급격한 악화", "start": 55},
                          {"bed": "MICU-02", "end": None, "label": "다른 환자 사건", "start": 52}]
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
        for fragment in ("07:35", "D-MICU-1", "MAP 재측정 58, 담당의 보고", "08:00", "MAP 58", "위험지표 78", "급격한 악화", "5분 경과"):
            self.assertIn(fragment, result["text"])
        self.assertNotIn("다른 환자 사건", result["text"])

    def test_history_claim_and_ai_advice_are_not_completed_records(self):
        self.hospital.actions = []
        history = [{"role": "nurse", "text": "비공식 대화: 펌프 투약 완료. 내가 여태 뭘 했고 이 환자 인계해줘"},
                   {"role": "agent", "text": "미기록 투약이 완료됐습니다."}]
        with patch.object(consult, "chat", return_value=None):
            text = consult.agent_turn(self.context(), history)
        self.assertIn("내 이번 근무 수행 기록 · D-MICU-1 (0건)", text)
        self.assertIn("기록 없음", text)
        self.assertNotIn("펌프 투약 완료", text)
        self.assertNotIn("미기록 투약", text)

    def test_current_person_is_separate_from_prior_shift_and_prior_cycle(self):
        self.hospital.actions += [record("이전 Night 간호사 확인", staff_id="N-MICU-1", shift_code="N", t=20),
                                  record("동료 간호사 관찰", staff_id="D-MICU-2", nurse_id="MICU-2", t=30),
                                  record("전날 같은 Day 근무 기록", cycle=-1, t=10)]
        ctx = self.context()
        self.assertEqual(len(ctx["handover"]["requester_actions"]), 1)
        # Serialization must not destroy separation between a nurse's actions
        # and other records (object identity is not an author identifier).
        ctx = json.loads(json.dumps(ctx))
        with patch.object(consult, "chat", return_value=None):
            text = consult.handover_turn(ctx)["text"]
        own, others = text.split("이전 조·동료 수행 기록", 1)
        self.assertNotIn("이전 Night", own)
        self.assertNotIn("전날 같은 Day", own)
        self.assertNotIn("동료 간호사", own)
        self.assertIn("N-MICU-1", others)
        self.assertIn("D-MICU-2", others)
        self.assertIn("전날 같은 Day", others)

    def test_only_current_patient_admission_user_records_are_used(self):
        self.hospital.actions += [record("다른 환자 비밀", pid="M-other"), record("이전 입원 기록", admit_t=-100),
                                  record("다른 병상 기록", bed="MICU-02"), record("AI 권고만", source="ai"),
                                  record("미래 기록", t=70)]
        ctx = self.context()
        self.assertEqual(len(ctx["actions"]), 1)
        self.assertEqual(ctx["patient_key"], {"pid": "M-test", "admit_t": 0})
        for fragment in ("다른 환자 비밀", "이전 입원 기록", "다른 병상 기록", "AI 권고만", "미래 기록"):
            self.assertNotIn(fragment, ctx["text"])

    def test_model_prompt_is_text_only_grounded_and_history_is_absent(self):
        ctx = self.context()
        history = [{"role": "nurse", "text": "대화에만 있는 거짓 투약완료, 인계해줘"}]
        with patch.object(consult, "chat", return_value="현재 MAP 재측정 결과를 다음 근무자에게 전달했나요?") as chat, \
                patch.object(consult, "model_name", return_value="GLM-local"), \
                patch.object(consult, "_img_part", side_effect=AssertionError("handover must be text only")):
            text = consult.agent_turn(ctx, history, task="handover")
        messages = chat.call_args.args[0]
        self.assertTrue(all(isinstance(row["content"], str) for row in messages))
        prompt = json.dumps(messages, ensure_ascii=False)
        self.assertIn("MAP 재측정 58, 담당의 보고", prompt)
        self.assertIn("일반 대화", prompt)
        self.assertNotIn("거짓 투약완료", prompt)
        self.assertNotIn("image_url", prompt)
        self.assertNotIn("Edema", prompt)
        self.assertIn("AI 검토 항목 초안 (수행 기록 아님", text)
        self.assertIn("[사용자 입력]", text)

    def test_model_mode_requires_actual_nonempty_response(self):
        for response, expected in ((None, "rules"), ("", "rules"), ("  ", "rules"), ("추가 수행 기록을 확인할까요?", "model")):
            with self.subTest(response=response), patch.object(consult, "chat", return_value=response), \
                    patch.object(consult, "model_name", return_value="GLM-local"):
                result = consult.handover_turn(self.context())
            self.assertEqual(result["mode"], expected)
            self.assertEqual(result["model"], "GLM-local" if expected == "model" else None)

    def test_new_context_includes_newly_recorded_work(self):
        first = self.context()
        self.hospital.actions.append(record("추가 관찰 기록", t=59, clock="07:59"))
        second = self.context()
        self.assertEqual(len(first["actions"]), 1)
        self.assertEqual(len(second["actions"]), 2)
        with patch.object(consult, "chat", return_value=None):
            self.assertIn("추가 관찰 기록", consult.handover_turn(second)["text"])

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
        self.hospital.actions = [record("수행 기록 " + "x" * 990, t=i, clock=f"07:{i:02d}") for i in range(60)]
        with patch.object(consult, "chat", return_value=None) as chat:
            result = consult.handover_turn(self.context())
        prompt = chat.call_args.args[0][1]["content"]
        data = json.loads(prompt.split("\n", 1)[1])
        self.assertGreater(data["actions_omitted_count"], 0)
        self.assertLess(len(prompt), 16000)
        self.assertIn("전체 60건 중 최근 40건 표시", result["text"])

    def test_xray_has_no_fictitious_time_and_sbar_uses_vitals_not_records(self):
        self.hospital.actions = [record("  기타 수행 기록: 예시와 무관")]
        ctx = self.context()
        self.assertNotIn("오늘 06:00", ctx["text"])
        self.assertIn("이 환자의 영상·판독문이 아니며", ctx["text"])
        with patch.object(consult, "chat", return_value=None):
            text = consult.agent_turn(ctx, [], task="sbar")
        self.assertIn("08:00: 110 / 58 / 91 / 25", text)
        self.assertNotIn("기타 수행 기록", text)

    def test_handover_request_detection(self):
        for text in ("이 환자 인계해줘", "내가 여태 뭘 했고 현재 상태 정리해줘", "내 수행 기록 보여줘"):
            self.assertTrue(consult.is_handover_request([{"role": "nurse", "text": text}]))
        for text in ("MAP 58인데 뭘 먼저 볼까요?", "투약 완료", "인계 말고 혈압만 봐줘"):
            self.assertFalse(consult.is_handover_request([{"role": "nurse", "text": text}]))
        self.assertTrue(consult.is_handover_request([], task="handover"))
        self.assertFalse(consult.is_handover_request([{"role": "nurse", "text": "인계해줘"}], task="sbar"))
        self.assertFalse(consult.is_handover_request([{"role": "agent", "text": "인계 요청하세요"}]))

    def test_emergency_injection_is_labeled_and_does_not_become_performed_work(self):
        self.hospital.actions = []
        patient = self.hospital.beds["MICU-01"]["patient"]
        patient["observed_vitals"] = copy.deepcopy(patient["vitals"])
        patient["vitals"].update(hr=20, map=25)
        patient["simulation_override"] = {"incident_id": 10, "scenario": "code_blue", "label": "코드블루",
                                           "source": "simulation_injected", "values": {"hr": 20, "map": 25}}
        self.hospital.incidents[0].update(label="심정지", scenario="code_blue", simulated=True, shortage=2,
                                          doctor_id="MICU-MD", doctor_called_t=56, doctor_arrived_t=None,
                                          doctor_waiting=True, doctor_status="waiting")
        ctx = self.context()
        self.assertEqual(ctx["handover"]["patient"]["vitals_origin"], "simulation_injected")
        self.assertEqual(ctx["handover"]["patient"]["observed_vitals"]["map"], 58)
        self.assertIn("원본 MIMIC 관측값이 아님", ctx["text"])
        self.assertIn("[응급 시연 주입]", ctx["latest_vitals_line"])
        with patch.object(consult, "chat", return_value=None):
            result = consult.handover_turn(ctx)
        text = result["text"]
        for value in ("현재 시연 상태", "MAP 25", "원본 MIMIC 관측값이 아닙니다", "간호 대응 인원 부족: 2명", "MD MICU-MD", "알림 07:56", "아직 도착 기록 없음", "같은 ICU 의사 응답 대기"):
            self.assertIn(value, text)
        self.assertIn("내 이번 근무 수행 기록 · D-MICU-1 (0건)", text)
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
            self.assertIn("도착 07:59 (시뮬레이션)", consult.handover_turn(current)["text"])

    def test_day_display_is_one_based_but_identity_cycle_is_unchanged(self):
        ctx = self.context()
        self.assertEqual(ctx["handover"]["shift"]["cycle"], 0)
        self.assertEqual(ctx["handover"]["requester"]["cycle"], 0)
        with patch.object(consult, "chat", return_value=None):
            text = consult.handover_turn(ctx)["text"]
        self.assertIn("현재 근무: Day · 1일차", text)
        self.assertIn("D조/1일차", text)
        self.assertNotIn("0일차", text)

    def test_simulation_activities_are_scoped_to_patient_and_person_not_care_actions(self):
        self.hospital.actions = []
        activities = [
            record("가상 간호사 침상 도착", t=40, source="simulation_activity", type="arrival", incident_id=1),
            record("이전 Night 가상 출동", t=30, staff_id="N-MICU-1", shift_code="N", source="simulation_activity", type="dispatch", incident_id=1),
            record("이전 입원 가상 활동", admit_t=-100, source="simulation_activity", type="arrival"),
            record("다른 환자 가상 활동", pid="M-other", source="simulation_activity", type="arrival"),
            record("MD 도착을 간호 수행으로 오인", source="simulation_activity", type="doctor_arrival"),
            record("AI의 가상 주장", source="ai", type="arrival"),
            record("미래 활동", t=70, source="simulation_activity", type="arrival"),
        ]
        self.hospital.patient_activities = lambda bed: copy.deepcopy(activities)
        ctx = self.context()
        self.assertEqual(ctx["actions"], [])
        self.assertEqual(len(ctx["activities"]), 2)
        self.assertEqual(len(ctx["handover"]["requester_activities"]), 1)
        with patch.object(consult, "chat", return_value=None) as chat:
            text = consult.handover_turn(json.loads(json.dumps(ctx)))["text"]
        completed, simulated = text.split("시뮬레이션 활동 기록 (실제처치 수행기록 아님):", 1)
        self.assertIn("내 이번 근무 수행 기록 · D-MICU-1 (0건)", completed)
        self.assertNotIn("침상 도착", completed)
        self.assertIn("내 이번 근무 시뮬레이션 활동 · D-MICU-1 (1건)", simulated)
        own, others = simulated.split("이전 조·동료 시뮬레이션 활동", 1)
        self.assertIn("가상 간호사 침상 도착", own)
        self.assertNotIn("이전 Night", own)
        self.assertIn("이전 Night 가상 출동", others)
        for excluded in ("이전 입원", "다른 환자 가상", "MD 도착을", "AI의 가상 주장", "미래 활동"):
            self.assertNotIn(excluded, text)
        prompt_data = json.loads(chat.call_args.args[0][1]["content"].split("\n", 1)[1])
        self.assertEqual(prompt_data["actions"], [])
        self.assertEqual(prompt_data["activities"][0]["source"], "simulation_activity")
        self.assertEqual(prompt_data["requester_activity_count"], 1)


if __name__ == "__main__":
    unittest.main()
