"""Model isolation, approval ownership, revision races and failure reporting."""
import json
import os
import unittest
from unittest.mock import patch

from planner_agent import PlannerService, model_config
from planner_core import PlannerError


def response(*names):
    calls = [{"id": f"call-{i}-{name}", "type": "function", "function": {
        "name": name, "arguments": json.dumps({} if name == "get_resources" else {"patient_id": "P003"})}}
        for i, name in enumerate(names)]
    return {"role": "assistant", "tool_calls": calls}, {"prompt_tokens": 2, "completion_tokens": 3}


class PlannerAgentTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LLM_BASE_URL": "http://127.0.0.1:9999/v1",
                                          "LLM_MODEL": "mock-test-model", "LLM_API_KEY": "TEST_SECRET"}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_offline_never_calls_model_and_requires_separate_approval(self):
        def fail(*args):
            self.fail("offline made a model request")
        service = PlannerService(request_fn=fail)
        reply = service.handle({"action": "propose", "patient_id": "P003", "mode": "offline"})
        self.assertTrue(reply["agent"]["success"])
        self.assertFalse(reply["agent"]["model_called"])
        self.assertFalse(reply["agent"]["live_verified"])
        self.assertEqual(reply["plan"]["status"], "proposed")
        self.assertFalse(any(r["patient_id"] == "P003" for r in service.state()["reservations"]))
        service.handle({"action": "approve", "plan_id": reply["plan"]["id"],
                        "expected_revision": reply["plan"]["revision"]})
        self.assertTrue(any(r["patient_id"] == "P003" for r in service.state()["reservations"]))

    def test_native_tools_create_only_a_proposal_and_record_usage(self):
        script = iter([response("get_patient", "get_resources"), response("propose_reservation")])
        service = PlannerService(request_fn=lambda *args: next(script))
        reply = service.handle({"action": "propose", "patient_id": "P003", "mode": "live"})
        self.assertTrue(reply["agent"]["success"])
        self.assertTrue(reply["agent"]["model_called"])
        self.assertEqual(reply["agent"]["calls"], 2)
        self.assertEqual(reply["agent"]["usage"], {"prompt_tokens": 4, "completion_tokens": 6})
        self.assertEqual(reply["plan"]["status"], "proposed")
        self.assertNotIn("TEST_SECRET", json.dumps(reply))
        self.assertFalse(any(r["patient_id"] == "P003" for r in reply["state"]["reservations"]))

    def test_model_cannot_approve_or_invent_unread_proposal(self):
        for name in ("approve", "propose_reservation"):
            with self.subTest(name=name):
                service = PlannerService(request_fn=lambda *args: response(name))
                before = service.state()["reservations"]
                with self.assertRaises(PlannerError):
                    service.handle({"action": "propose", "patient_id": "P003", "mode": "live"})
                self.assertEqual(service.state()["reservations"], before)
                self.assertEqual(service.state()["plans"], [])
                self.assertFalse(service.state()["agent_status"]["success"])

    def test_missing_configuration_fails_without_network_or_rule_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            service = PlannerService(request_fn=lambda *args: self.fail("missing config requested model"))
            with self.assertRaises(PlannerError) as caught:
                service.handle({"action": "propose", "patient_id": "P003", "mode": "live"})
            self.assertEqual(caught.exception.code, "MODEL_CONFIG")
            self.assertEqual(service.state()["plans"], [])
            self.assertFalse(service.state()["agent_status"]["model_called"])

    def test_failed_model_is_not_reported_as_success(self):
        def fail(*args):
            raise PlannerError("synthetic transport failure", "MODEL_UNAVAILABLE", 502)
        service = PlannerService(request_fn=fail)
        with self.assertRaises(PlannerError):
            service.handle({"action": "propose", "patient_id": "P003", "mode": "live"})
        meta = service.state()["agent_status"]
        self.assertFalse(meta["success"])
        self.assertFalse(meta["live_verified"])
        self.assertTrue(meta["model_called"])
        self.assertEqual(service.state()["plans"], [])

    def test_revision_changed_during_model_call_requires_fresh_reads(self):
        counter = 0
        service = PlannerService()
        def script(*args):
            nonlocal counter
            counter += 1
            if counter == 1:
                return response("get_patient", "get_resources")
            if counter == 2:
                service.handle({"action": "advance", "minutes": 1})
                return response("propose_reservation")
            if counter == 3:
                self.assertEqual(args[1][-1]["role"], "tool")
                self.assertIn("READ_REQUIRED", args[1][-1]["content"])
                return response("get_patient", "get_resources")
            return response("propose_reservation")
        service.request_fn = script
        reply = service.handle({"action": "propose", "patient_id": "P003", "mode": "live"})
        self.assertEqual(counter, 4)
        self.assertEqual(reply["plan"]["revision"], service.state()["revision"])
        self.assertTrue(any(e.get("error") for e in reply["agent"]["trace"]))

    def test_reset_during_call_does_not_attach_result_to_new_scenario(self):
        service = PlannerService()
        def script(*args):
            service.handle({"action": "reset", "seed": 2})
            return response("get_patient")
        service.request_fn = script
        with self.assertRaises(PlannerError) as caught:
            service.handle({"action": "propose", "patient_id": "P003", "mode": "live"})
        self.assertEqual(caught.exception.code, "SCENARIO_CHANGED")
        self.assertEqual(service.state()["plans"], [])
        self.assertFalse(service.state()["agent_status"]["model_called"])

    def test_khdp_configuration_and_explicit_llm_override(self):
        with patch.dict(os.environ, {"KHDP_BASE_URL": "https://pod.example/v1/", "KHDP_MODEL": "allowed-model",
                                     "KHDP_API_KEY": "SECRET"}, clear=True):
            self.assertEqual(model_config()["model"], "allowed-model")
            self.assertEqual(model_config()["base"], "https://pod.example/v1")
            with patch.dict(os.environ, {"LLM_MODEL": "explicit-model"}):
                self.assertEqual(model_config()["model"], "explicit-model")
        for base in ("", "file:///tmp/foo", "https://user:secret@pod.example/v1", "https://pod.example/v1?key=SECRET"):
            with self.subTest(base=base), patch.dict(os.environ, {"LLM_BASE_URL": base}, clear=True):
                with self.assertRaises(PlannerError):
                    model_config()

    def test_old_tab_approval_cannot_match_reused_plan_id_after_reset(self):
        service = PlannerService()
        old = service.handle({"action": "propose", "patient_id": "P003", "mode": "offline"})["plan"]
        service.handle({"action": "reset", "seed": 1})
        new = service.handle({"action": "propose", "patient_id": "P003", "mode": "offline"})["plan"]
        self.assertEqual(old["id"], new["id"])
        self.assertEqual(old["revision"], new["revision"])
        self.assertNotEqual(old["scenario_id"], new["scenario_id"])
        with self.assertRaises(PlannerError) as caught:
            service.handle({"action": "approve", "plan_id": old["id"], "expected_revision": old["revision"],
                            "scenario_id": old["scenario_id"]})
        self.assertEqual(caught.exception.status, 409)
        self.assertFalse(any(r["patient_id"] == "P003" for r in service.state()["reservations"]))


if __name__ == "__main__":
    unittest.main()
