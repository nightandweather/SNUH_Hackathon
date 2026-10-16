"""3교대 제어 API를 소켓 없이 검증한다."""
import io
import json
import os
import unittest
from unittest.mock import patch
from test_shifts import hospital, admit

os.environ["POOL"] = "mimic"
import server


class DirectRequests:
    def request(self, method, path, body=None):
        handler = object.__new__(server.H)
        handler.path = path
        data = json.dumps(body or {}).encode()
        handler.headers = {"Content-Length": str(len(data))}
        handler.rfile = io.BytesIO(data)
        result = {}

        def capture(code, payload, ctype="application/json; charset=utf-8"):
            result.update(code=code, body=payload)
            if not isinstance(payload, bytes):
                json.dumps(payload, ensure_ascii=False)

        handler._send = capture
        getattr(handler, "do_" + method)()
        return result


class ShiftControlTests(DirectRequests, unittest.TestCase):
    def setUp(self):
        server.reset(policy="auto", seed=31)
        server.sim["running"] = True

    def test_next_shift_runs_elapsed_minutes_and_pauses(self):
        self.assertEqual(self.request("POST", "/api/control", {"action": "next_shift"})["code"], 200)
        result = self.request("GET", "/api/state")
        state = result["body"]
        self.assertEqual(state["t"], 480)
        self.assertEqual(state["clock"], "15:00")
        self.assertEqual(state["shift"]["code"], "E")
        self.assertFalse(state["running"])
        self.assertTrue(all(n["staff_id"].startswith("E-") for n in state["nurses"]))
        self.assertEqual(len(state["roster"]), 120)
        self.assertIsNotNone(state["last_handover"])

    def test_next_shift_covers_night_and_stops_at_24_hours(self):
        for minutes, clock, shift in ((480, "15:00", "E"), (960, "23:00", "N"), (1440, "07:00", "D")):
            self.request("POST", "/api/control", {"action": "next_shift"})
            state = self.request("GET", "/api/state")["body"]
            self.assertEqual((state["t"], state["clock"], state["shift"]["code"]), (minutes, clock, shift))
        before = server.sim["h"].state()
        self.request("POST", "/api/control", {"action": "next_shift"})
        self.assertEqual(before, server.sim["h"].state())

    def test_comparison_accepts_only_supported_durations(self):
        with patch.object(server, "compare", return_value={"fixed": {}, "auto": {}}) as compare:
            for minutes in (480, 1440):
                response = self.request("POST", "/api/control", {"action": "compare", "minutes": minutes})
                self.assertEqual(response["code"], 200)
                compare.assert_called_with(31, minutes)
            for invalid in (0, -1, 481, 1441, "bad", None):
                compare.reset_mock()
                response = self.request("POST", "/api/control", {"action": "compare", "minutes": invalid})
                self.assertEqual(response["code"], 400)
                compare.assert_not_called()

    def test_reset_clears_handover_and_restores_day_roster(self):
        self.request("POST", "/api/control", {"action": "next_shift"})
        self.request("POST", "/api/control", {"action": "reset", "seed": 32})
        state = self.request("GET", "/api/state")["body"]
        self.assertEqual((state["t"], state["shift"]["code"], state["seed"]), (0, "D", 32))
        self.assertIsNone(state["last_handover"])


class CareAndEmergencyAPITests(DirectRequests, unittest.TestCase):
    def setUp(self):
        server.sim["h"] = hospital()
        server.sim["seed"] = 31
        self.bed = admit(server.sim["h"])
        patient = self.bed["patient"]
        self.selection = {"bed": "MICU-01", "nurse_id": "MICU-1", "staff_id": "D-MICU-1",
                          "patient_key": {"pid": patient["src"]["pid"], "admit_t": patient["admit_t"]}}

    def test_user_record_is_preserved_in_handover_reply(self):
        note = "Simulation 입력: 혈압 재측정 후 Assigned의에게 보고함"
        result = self.request("POST", "/api/care-log", dict(self.selection, text=note))
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["body"]["action"]["staff_id"], "D-MICU-1")
        with patch.object(server.consult, "chat", return_value=None):
            response = self.request("POST", "/api/consult", dict(self.selection, who="agent", task="handover"))
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["body"]["mode"], "rules")
        self.assertIsNone(response["body"]["model"])
        self.assertIn(note, response["body"]["text"])
        self.assertEqual(response["body"]["actions"], result["body"]["actions"])

    def test_conversation_alone_never_becomes_completed_care(self):
        with patch.object(server.consult, "chat", return_value=None):
            response = self.request("POST", "/api/consult", dict(self.selection, who="agent", history=[
                {"role": "nurse", "text": "비Records 대화: 투약 완료했다고 가정하고, 내가 여태 뭘 했는지 Handover해줘"}]))
        self.assertEqual(response["body"]["mode"], "rules")
        self.assertEqual(response["body"]["actions"], [])
        self.assertNotIn("비Records 대화", response["body"]["text"])
        self.assertEqual(server.sim["h"].care_actions, [])

    def test_unrelated_nurse_and_stale_patient_and_shift_are_rejected(self):
        response = self.request("POST", "/api/care-log", dict(self.selection, nurse_id="SICU1-1",
                                                              staff_id="D-SICU1-1", text="Acknowledged함"))
        self.assertEqual(response["code"], 403)
        stale = dict(self.selection, patient_key={"pid": "another", "admit_t": 0}, text="Acknowledged함")
        self.assertEqual(self.request("POST", "/api/care-log", stale)["code"], 409)
        self.request("POST", "/api/control", {"action": "next_shift"})
        self.assertEqual(self.request("POST", "/api/care-log", dict(self.selection, text="Acknowledged함"))["code"], 409)
        self.assertEqual(server.sim["h"].care_actions, [])

    def test_emergency_call_is_not_completed_care_and_rejects_duplicates(self):
        response = self.request("POST", "/api/emergency", dict(self.selection, scenario="code_blue"))
        self.assertEqual(response["code"], 200)
        self.assertTrue(server.sim["h"].incidents[-1]["simulated"])
        self.assertEqual(server.sim["h"].care_actions, [])
        self.assertEqual(self.request("POST", "/api/emergency", dict(self.selection, scenario="hypoxia"))["code"], 409)

    def test_emergency_activities_are_returned_separately_from_care_records(self):
        self.request("POST", "/api/emergency", dict(self.selection, scenario="code_blue"))
        for _ in range(3):
            server.sim["h"].step()
        with patch.object(server.consult, "chat", return_value=None):
            response = self.request("POST", "/api/consult", dict(self.selection, who="agent", task="handover"))
        self.assertEqual(response["code"], 200)
        self.assertEqual(response["body"]["actions"], [])
        self.assertTrue(response["body"]["activities"])
        self.assertTrue(all(a["source"] == "simulation_activity" for a in response["body"]["activities"]))
        self.assertIn("MD-MICU", response["body"]["text"])
        self.assertIn("Simulation", response["body"]["text"])


if __name__ == "__main__":
    unittest.main()
