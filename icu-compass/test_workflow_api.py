"""Admission/shift-safe workflow and receipt requests, without a listener."""
import unittest
from unittest.mock import patch

import server
from test_shift_api import DirectRequests
from test_shifts import hospital, admit, advance


class WorkflowAPITests(DirectRequests, unittest.TestCase):
    def setUp(self):
        server.sim["h"] = hospital()
        self.h = server.sim["h"]
        self.bed = admit(self.h)
        self.selection = self.selection_for()

    def selection_for(self, nurse_id="MICU-1"):
        pt = self.bed["patient"]
        return {"bed": self.bed["id"], "nurse_id": nurse_id,
                "staff_id": self.h.nurses[nurse_id]["staff_id"],
                "patient_key": {"pid": pt["src"]["pid"], "admit_t": pt["admit_t"]}}

    def finish_xray(self):
        response = self.request("POST", "/api/diagnostics", dict(self.selection, kind="portable_xray"))
        self.assertEqual(response["code"], 200)
        task_id = response["body"]["task"]["id"]
        for _ in range(120):
            task = self.h.diagnostic_task(self.bed["id"], task_id)
            if task["status"] == "image_available":
                return task
            self.h.step()
        self.fail("Portable workflow did not complete")

    def test_history_contains_no_future_and_rejects_unrelated_and_stale_people(self):
        advance(self.h, 20)
        reply = self.request("POST", "/api/patient", self.selection)
        self.assertEqual(reply["code"], 200)
        points = reply["body"]["history"]["points"]
        self.assertTrue(points)
        self.assertTrue(all(0 <= row["t"] <= 20 for row in points))
        self.assertEqual(points[-1]["hr"], self.bed["patient"]["vitals"]["hr"])
        unrelated = self.selection_for("SICU1-1")
        self.assertEqual(self.request("POST", "/api/patient", unrelated)["code"], 403)
        self.assertEqual(self.request("POST", "/api/diagnostics", dict(unrelated, kind="blood_draw"))["code"], 403)
        stale = dict(self.selection, patient_key={"pid": "old", "admit_t": -1})
        self.assertEqual(self.request("POST", "/api/patient", stale)["code"], 409)

    def test_workflow_request_duplicate_and_unacquired_image(self):
        first = self.request("POST", "/api/diagnostics", dict(self.selection, kind="portable_xray"))
        self.assertEqual(first["code"], 200)
        self.assertEqual(self.request("POST", "/api/diagnostics", dict(self.selection, kind="portable_xray"))["code"], 409)
        with patch.object(server.consult, "image_review_turn") as model:
            pending = self.request("POST", "/api/image-review", dict(self.selection, task_id=first["body"]["task"]["id"]))
        self.assertEqual(pending["code"], 409)
        model.assert_not_called()
        self.assertEqual(self.h.care_actions, [])

    def test_image_preview_and_actual_model_metadata_only_after_acquisition(self):
        task = self.finish_xray()
        detail = self.request("POST", "/api/patient", self.selection)["body"]
        image = next(row for row in detail["diagnostics"] if row["id"] == task["id"])
        self.assertFalse(image["patient_linked"])
        self.assertEqual(image["image_source"], "public_nih_example")
        self.assertTrue(image["image_url"].startswith("/static/cxr/"))
        answer = {"text": "公開 Example image 검토 초안", "mode": "model", "model": "mock-vl",
                  "source": {"kind": "public_nih_example", "patient_linked": False}, "task_id": task["id"]}
        with patch.object(server.consult, "image_review_turn", return_value=answer):
            reply = self.request("POST", "/api/image-review", dict(self.selection, task_id=task["id"]))
        self.assertEqual(reply["code"], 200)
        self.assertEqual(reply["body"]["model"], "mock-vl")
        saved = self.h.diagnostic_task(self.bed["id"], task["id"])["review"]
        self.assertEqual(saved["t"], self.h.t)
        self.assertEqual(saved["mode"], "model")
        self.assertEqual(self.h.care_actions, [])

    def test_model_result_cannot_attach_to_a_reset_scenario(self):
        task = self.finish_xray()
        def result_after_reset(ctx, diagnostic):
            server.sim["h"] = hospital()
            admit(server.sim["h"])
            return {"text": "late", "mode": "model", "model": "mock-vl"}
        with patch.object(server.consult, "image_review_turn", side_effect=result_after_reset):
            reply = self.request("POST", "/api/image-review", dict(self.selection, task_id=task["id"]))
        self.assertEqual(reply["code"], 409)
        self.assertEqual(server.sim["h"].diagnostics, [])

    def test_model_failure_does_not_become_a_successful_review(self):
        task = self.finish_xray()
        answer = {"text": "영상 검토 not run: 모델 응답 None", "mode": "unavailable", "model": None,
                  "source": {"kind": "public_nih_example", "patient_linked": False}, "task_id": task["id"]}
        with patch.object(server.consult, "image_review_turn", return_value=answer):
            reply = self.request("POST", "/api/image-review", dict(self.selection, task_id=task["id"]))
        self.assertEqual(reply["code"], 200)
        self.assertEqual(reply["body"]["mode"], "unavailable")
        self.assertIsNone(reply["body"]["model"])

    def test_missing_image_task_returns_not_found_without_model_call(self):
        with patch.object(server.consult, "image_review_turn") as model:
            for task_id in (None, "missing", {"id": "bad"}):
                response = self.request("POST", "/api/image-review", dict(self.selection, task_id=task_id))
                self.assertEqual(response["code"], 404)
        model.assert_not_called()

    def test_model_result_rejects_shift_change_even_without_client_staff_key(self):
        task = self.finish_xray()
        def result_after_shift(ctx, diagnostic):
            advance(self.h, 480 - self.h.t)
            return {"text": "late", "mode": "model", "model": "mock-vl"}
        with patch.object(server.consult, "image_review_turn", side_effect=result_after_shift):
            response = self.request("POST", "/api/image-review", {"bed": self.bed["id"], "task_id": task["id"]})
        self.assertEqual(response["code"], 409)
        self.assertIsNone(self.h.diagnostic_task(self.bed["id"], task["id"])["review"])

    def test_receiver_ack_and_question_are_separate_from_care(self):
        advance(self.h, 480)
        incoming = self.selection_for()
        args = dict(incoming, handover_t=480)
        acknowledged = self.request("POST", "/api/handover", dict(args, action="ack"))
        self.assertEqual(acknowledged["code"], 200)
        receipt = acknowledged["body"]["receipt"]
        self.assertEqual(receipt["status"], "received")
        self.assertEqual(receipt["received_by"], "E-MICU-1")
        question = self.request("POST", "/api/handover", dict(args, action="question", text="Blood draw Requested은 아직 Active인가요?"))
        self.assertEqual(question["body"]["receipt"]["status"], "question_open")
        self.assertEqual(question["body"]["receipt"]["questions"][0]["source"], "user_entered")
        self.assertEqual(self.h.care_actions, [])
        # Repeated receipt retains its first time and cannot resolve an open question.
        self.h.step()
        repeated = self.request("POST", "/api/handover", dict(args, action="ack"))["body"]["receipt"]
        self.assertEqual(repeated["received_t"], receipt["received_t"])
        self.assertEqual(repeated["status"], "question_open")
        self.assertEqual(len(self.h.handover_receipts), 2)
        advance(self.h, 479)
        archived = self.request("GET", "/api/state")["body"]["handover_receipts"]
        self.assertEqual(archived[1]["text"], "Blood draw Requested은 아직 Active인가요?")
        self.assertEqual(archived[1]["handover_t"], 480)

    def test_receipt_rejects_wrong_receiver_old_snapshot_and_old_admission(self):
        advance(self.h, 480)
        args = dict(self.selection_for(), handover_t=480, action="ack")
        wrong = dict(args, nurse_id="MICU-2", staff_id="E-MICU-2")
        self.assertEqual(self.request("POST", "/api/handover", wrong)["code"], 403)
        self.assertEqual(self.request("POST", "/api/handover", dict(args, handover_t=0))["code"], 409)
        self.assertEqual(self.request("POST", "/api/handover", dict(self.selection, handover_t=480, action="ack"))["code"], 409)
        self.bed["patient"] = None
        admit(self.h)
        fresh_selection = self.selection_for()
        self.assertEqual(self.request("POST", "/api/handover", dict(fresh_selection, handover_t=480, action="ack"))["code"], 409)


if __name__ == "__main__":
    unittest.main()
