"""Workflow/image grounding checks; model responses and image bytes are mocked."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import consult
from test_consult_handover import FakeHospital


def diagnostic(**changes):
    task = {"id": "DX-1", "kind": "portable_xray", "bed": "MICU-01", "pid": "M-test", "admit_t": 0,
            "unit": "MICU", "nurse_id": "MICU-1", "requested_by_staff_id": "D-MICU-1",
            "requested_t": 20, "requested_clock": "07:20", "status": "image_available",
            "source": "simulation_workflow", "simulated": True, "image_source": "public_nih_example",
            "patient_linked": False, "review": None,
            "events": [{"t": 20, "clock": "07:20", "status": "requested", "text": "요청",
                        "staff_id": "D-MICU-1", "source": "simulation_activity"},
                       {"t": 30, "clock": "07:30", "status": "acquiring", "text": "촬영 단계",
                        "staff_id": "D-MICU-1", "source": "simulation_activity"},
                       {"t": 40, "clock": "07:40", "status": "image_available", "text": "예시 영상 준비",
                        "staff_id": "D-MICU-1", "source": "simulation_activity"}]}
    task.update(changes)
    return task


class ImagingTests(unittest.TestCase):
    def setUp(self):
        self.h = FakeHospital()
        self.tasks = [diagnostic()]
        self.h.patient_diagnostics = lambda bed: copy.deepcopy(self.tasks)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.sample = {"file": "edema_1.jpg", "image_id": "public-example", "view": "AP",
                       "finding": "Edema", "report": "PREEXISTING_REPORT_DO_NOT_SEND"}
        (self.directory / "index.json").write_text(json.dumps({"images": [self.sample]}))
        (self.directory / self.sample["file"]).write_bytes(b"mock-public-jpeg")
        for mocked in (patch.object(consult, "CXR_DIR", self.directory),
                       patch.object(consult, "cxr_for", return_value=self.sample)):
            mocked.start()
            self.addCleanup(mocked.stop)

    def ctx(self):
        return consult.context(self.h, "MICU-01", nurse_id="MICU-1")

    def test_success_has_actual_image_payload_and_no_label_or_previous_report(self):
        self.tasks[0]["review"] = {"t": 50, "clock": "07:50", "text": "OLD_REVIEW_DO_NOT_SEND", "mode": "model", "model": "old"}
        with patch.object(consult, "model_name", return_value="local-VL"), \
                patch.object(consult, "chat", return_value="영상 관찰: 우측 하부 음영이 보입니다.\n해석 한계: 공개 예시입니다.\n담당의 확인: 원본 영상 확인이 필요합니다.") as chat:
            result = consult.image_review_turn(self.ctx(), self.tasks[0])
        self.assertEqual((result["mode"], result["model"]), ("model", "local-VL"))
        self.assertEqual(result["source"]["image_id"], "public-example")
        self.assertIs(result["source"]["patient_linked"], False)
        messages = chat.call_args.args[0]
        image_parts = [part for row in messages if isinstance(row["content"], list)
                       for part in row["content"] if part["type"] == "image_url"]
        self.assertEqual(len(image_parts), 1)
        self.assertTrue(image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        prompt = json.dumps(messages, ensure_ascii=False)
        for forbidden in ("Edema", "edema_1.jpg", "PREEXISTING_REPORT_DO_NOT_SEND", "OLD_REVIEW_DO_NOT_SEND", "기록된 진단"):
            self.assertNotIn(forbidden, prompt)
        payload = json.loads(messages[1]["content"][0]["text"])
        self.assertEqual(payload["separate_patient_state"]["vitals"]["map"], 58)
        self.assertIn("현재 환자와 무관", result["text"])
        self.assertIn("담당의 판독·승인이 아닙니다", result["text"])

    def test_model_failure_and_missing_model_never_generate_rule_findings(self):
        for response in (None, "", "   ", OSError("model unavailable")):
            with self.subTest(response=response), patch.object(consult, "model_name", return_value="local-VL"), \
                    patch.object(consult, "chat", side_effect=response if isinstance(response, Exception) else None,
                                 return_value=response if not isinstance(response, Exception) else None):
                result = consult.image_review_turn(self.ctx(), self.tasks[0])
            self.assertEqual((result["mode"], result["model"]), ("unavailable", None))
            self.assertIn("미실행", result["text"])
            self.assertNotIn("폐부종", result["text"])
        with patch.object(consult, "model_name", return_value=None), patch.object(consult, "chat") as chat:
            result = consult.image_review_turn(self.ctx(), self.tasks[0])
        chat.assert_not_called()
        self.assertEqual(result["mode"], "unavailable")

    def test_future_unacquired_cancelled_blood_and_other_admission_never_call_model(self):
        future = diagnostic()
        future["events"][-1].update(t=70, clock="08:10")
        variants = [future, diagnostic(status="acquiring", events=diagnostic()["events"][:-1]),
                    diagnostic(status="cancelled"), diagnostic(kind="blood_draw", status="specimen_sent"),
                    diagnostic(pid="other"), diagnostic(admit_t=-1), diagnostic(bed="MICU-02"),
                    diagnostic(requested_t=70), diagnostic(events=[]), diagnostic(patient_linked=True),
                    diagnostic(image_source="private_patient_image")]
        for task in variants:
            with self.subTest(task=task), patch.object(consult, "model_name", side_effect=AssertionError("blocked before model discovery")), \
                    patch.object(consult, "chat", side_effect=AssertionError("blocked before inference")):
                self.tasks = [task]
                result = consult.image_review_turn(self.ctx(), task)
            self.assertEqual((result["mode"], result["model"]), ("unavailable", None))

    def test_missing_unregistered_or_escaped_image_never_calls_model(self):
        for sample in ({**self.sample, "file": "missing.jpg"}, {**self.sample, "image_id": "different"},
                       {**self.sample, "file": "../private.jpg"}):
            ctx = self.ctx()
            ctx["cxr"] = sample
            with self.subTest(sample=sample), patch.object(consult, "model_name", side_effect=AssertionError("no image")), \
                    patch.object(consult, "chat", side_effect=AssertionError("no image")):
                self.assertEqual(consult.image_review_turn(ctx, self.tasks[0])["mode"], "unavailable")

    def test_context_hides_future_acquisition_review_and_other_patients(self):
        future = diagnostic()
        future["events"][-1].update(t=70, clock="08:10", text="FUTURE_ACQUISITION")
        future["review"] = {"t": 80, "clock": "08:20", "mode": "model", "text": "FUTURE_REVIEW"}
        self.tasks = [future, diagnostic(id="OTHER_PATIENT", pid="other"),
                      diagnostic(id="OTHER_ADMISSION", admit_t=-100), diagnostic(id="FUTURE_REQUEST", requested_t=70)]
        ctx = self.ctx()
        self.assertEqual(len(ctx["diagnostics"]), 1)
        self.assertEqual(ctx["diagnostics"][0]["status"], "acquiring")
        self.assertIsNone(ctx["diagnostics"][0]["review"])
        for text in ("FUTURE_ACQUISITION", "FUTURE_REVIEW", "OTHER_PATIENT", "OTHER_ADMISSION", "FUTURE_REQUEST", "08:10", "08:20"):
            self.assertNotIn(text, json.dumps(ctx, ensure_ascii=False))

    def test_handover_keeps_workflow_result_and_model_draft_separate(self):
        self.h.actions = []
        blood = diagnostic(id="DX-2", kind="blood_draw", status="specimen_sent")
        blood["events"][-1].update(status="specimen_sent", text="검체 이송")
        self.tasks = [blood, diagnostic(review={"t": 50, "clock": "07:50", "mode": "model", "model": "local-VL",
                                              "text": "공개 예시 영상 관찰 초안", "source": {"kind": "public_nih_example"}})]
        with patch.object(consult, "chat", return_value=None):
            result = consult.handover_turn(self.ctx())
        text = result["text"]
        self.assertIn("내 이번 근무 수행 기록 · D-MICU-1 (0건)", text)
        self.assertIn("검체 이송 단계 완료", text)
        self.assertIn("검사 수치 결과는 제공되지 않았습니다", text)
        self.assertIn("예시 영상 표시 가능", text)
        self.assertIn("별도 영상 관찰 AI 초안", text)
        self.assertIn("실제 환자 판독·담당의 승인 아님", text)
        self.assertEqual(result["mode"], "rules")

    def test_normal_consult_and_sbar_do_not_send_images_before_or_after_acquisition(self):
        for task_name in (None, "sbar"):
            with self.subTest(task=task_name), patch.object(consult, "chat", return_value="텍스트 상담 초안") as chat, \
                    patch.object(consult, "model_name", return_value="local-text"), \
                    patch.object(consult, "_img_part", side_effect=AssertionError("dedicated image route only")):
                consult.agent_turn(self.ctx(), [{"role": "nurse", "text": "현재 MAP은요?"}], task=task_name)
            messages = chat.call_args.args[0]
            self.assertTrue(all(isinstance(row["content"], str) for row in messages))
            self.assertNotIn("image_url", json.dumps(messages))

    def test_recorded_vital_history_prevents_preadmission_and_future_series_leakage(self):
        self.h.beds["MICU-01"]["patient"]["admit_t"] = 40
        self.h.patient_vital_history = lambda bed, minutes: {"points": [
            {"t": 0, "clock": "07:00", "hr": 900, "map": 900, "spo2": 900, "rr": 900, "simulated": False},
            {"t": 40, "clock": "07:40", "hr": 20, "map": 10, "spo2": 40, "rr": 0, "simulated": True,
             "observed_vitals": {"hr": 110, "map": 58, "spo2": 91, "rr": 25}},
            {"t": 55, "clock": "07:55", "hr": 100, "map": 64, "spo2": 92, "rr": 22, "simulated": False},
            {"t": 80, "clock": "08:20", "hr": 999, "map": 999, "spo2": 999, "rr": 999, "simulated": False}]}
        with patch.object(self.h, "_vital", side_effect=AssertionError("use recorded history, not reconstructed series")):
            ctx = self.ctx()
        self.assertIn("07:40: 20 / 10 / 40 / 0 [응급 시연 주입]", ctx["text"])
        self.assertIn("별도 원본 기록 재생: 110 / 58 / 91 / 25", ctx["text"])
        self.assertIn("07:55", ctx["latest_vitals_line"])
        self.assertNotIn("07:00:", ctx["text"])
        self.assertNotIn("08:20", ctx["text"])
        self.assertNotIn("999", ctx["text"])

    def test_legacy_vital_fallback_stays_after_simulation_admission(self):
        self.h.beds["MICU-01"]["patient"]["admit_t"] = 45
        ctx = self.ctx()
        self.assertIn("08:00:", ctx["latest_vitals_line"])
        self.assertNotIn("07:00:", ctx["text"])
        self.assertNotIn("07:30:", ctx["text"])
        self.assertIn("새 측정 여부 미확인", ctx["text"])

    def test_handover_receipt_questions_are_time_scoped_and_not_answers_or_messages(self):
        self.h.last_handover = {"t": 40, "clock": "07:40", "from_code": "N", "to_code": "D", "patients": [
            {"bed": "MICU-01", "pid": "M-test", "admit_t": 0, "from_staff_id": "N-MICU-1", "to_staff_id": "D-MICU-1",
             "receipt": {"status": "question_open", "received_by": "D-MICU-1", "received_t": 50, "received_clock": "07:50",
                         "questions": [{"t": 55, "clock": "07:55", "staff_id": "D-MICU-1", "text": "검체 이송 기록을 확인할까요?", "source": "user_entered"},
                                       {"t": 80, "clock": "08:20", "staff_id": "D-MICU-1", "text": "FUTURE_QUESTION", "source": "user_entered"},
                                       {"t": 55, "clock": "07:55", "staff_id": "AI", "text": "AI_QUESTION_NOT_USER", "source": "ai"}]}}]}
        with patch.object(consult, "chat", return_value=None):
            result = consult.handover_turn(self.ctx())
        text = result["text"]
        self.assertIn("수신 확인: 07:50 · D-MICU-1", text)
        self.assertIn("질문 접수: 미해결 질문 기록 있음", text)
        self.assertIn("[사용자 입력 질문]", text)
        self.assertIn("답변·해결 완료는 확인되지 않았습니다", text)
        self.assertIn("이전 근무자에게 실제 메시지 발송 없음", text)
        self.assertNotIn("FUTURE_QUESTION", text)
        self.assertNotIn("AI_QUESTION_NOT_USER", text)
        receipt = self.h.last_handover["patients"][0]["receipt"]
        receipt.update(status="received", received_t=80, received_clock="08:20", questions=[])
        with patch.object(consult, "chat", return_value=None):
            future = consult.handover_turn(self.ctx())["text"]
        self.assertIn("수신 대기: 수신 확인 기록 없음", future)
        self.assertNotIn("08:20", future)

    def test_consult_metadata_uses_response_not_configured_model_and_keeps_text_wrappers(self):
        ctx = self.ctx()
        history = [{"role": "nurse", "text": "현재 MAP은요?"}]
        for helper, wrapper in ((consult.agent_turn_result, consult.agent_turn),
                                (consult.nurse_turn_result, consult.nurse_turn)):
            for response in (None, "", "   "):
                with self.subTest(helper=helper.__name__, response=response), \
                        patch.object(consult, "chat", return_value=response), \
                        patch.object(consult, "model_name", return_value="configured-but-failed"):
                    result = helper(ctx, history)
                    text = wrapper(ctx, history)
                self.assertEqual((result["mode"], result["model"]), ("rules", None))
                self.assertEqual(result["text"], text)
                self.assertTrue(text)
            with patch.object(consult, "chat", return_value="간호사: 실제 응답 한 줄"), \
                    patch.object(consult, "model_name", return_value="local-model"):
                result = helper(ctx, history)
                text = wrapper(ctx, history)
            self.assertEqual((result["mode"], result["model"]), ("model", "local-model"))
            self.assertEqual(result["text"], text)
        with patch.object(consult, "chat", return_value=None), patch.object(consult, "model_name", return_value="configured-but-failed"):
            routed = consult.agent_turn_result(ctx, [{"role": "nurse", "text": "이 환자 인계해줘"}])
        self.assertEqual((routed["mode"], routed["model"]), ("rules", None))
        self.assertIn("인계 ·", routed["text"])

    def test_handover_question_prompt_is_bounded_without_changing_saved_records(self):
        questions = [{"t": 55, "clock": "07:55", "staff_id": "D-MICU-1", "text": f"질문 {i}: " + "확인" * 400,
                      "source": "user_entered"} for i in range(90)]
        self.h.last_handover = {"t": 40, "clock": "07:40", "patients": [
            {"bed": "MICU-01", "pid": "M-test", "admit_t": 0, "receipt": {"status": "question_open", "questions": questions}}]}
        ctx = self.ctx()
        with patch.object(consult, "chat", return_value=None) as chat:
            result = consult.handover_turn(ctx)
        prompt = chat.call_args.args[0][1]["content"].split("\n", 1)[1]
        receipt = json.loads(prompt)["last_handover"]["patient"]["receipt"]
        self.assertLessEqual(len(json.dumps(receipt["questions"], ensure_ascii=False)), 6000)
        self.assertGreater(receipt["questions_omitted_count"], 0)
        self.assertIn("질문 89:", receipt["questions"][-1]["text"])
        self.assertEqual(len(ctx["handover"]["last_handover"]["patient"]["receipt"]["questions"]), 90)
        self.assertEqual(len(self.h.last_handover["patients"][0]["receipt"]["questions"]), 90)
        self.assertIn("전체 질문 90건 중 최근 40건 표시", result["text"])


if __name__ == "__main__":
    unittest.main()
