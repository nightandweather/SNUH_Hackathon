"""Exercise nurse sessions and patient boundaries without opening sockets."""
import copy
import io
import json
import os
import unittest
from unittest.mock import patch

from test_shifts import admit, advance, hospital

# Unit tests must also run from a clean checkout without patient caches or downloads.
os.environ["POOL"] = "synth"
os.environ["OFFLINE_DEMO"] = "1"
import server


class PortalRequests:
    def request(self, method, path, body=None, token=None):
        handler = object.__new__(server.H)
        handler.path = path
        data = json.dumps({} if body is None else body).encode()
        handler.headers = {"Content-Length": str(len(data))}
        if token is not None:
            handler.headers["Authorization"] = "Bearer " + token
        handler.rfile = io.BytesIO(data)
        result = {}

        def capture(code, payload, ctype="application/json; charset=utf-8"):
            result.update(code=code, body=payload, ctype=ctype)
            if not isinstance(payload, bytes):
                json.dumps(payload, ensure_ascii=False)

        handler._send = capture
        getattr(handler, "do_" + method)()
        return result

    def login(self, account="D-MICU-1"):
        result = self.request("POST", "/api/nurse/login", {"account_id": account, "pin": "2026"})
        self.assertEqual(result["code"], 200)
        return result["body"]["token"]

    def state(self, token):
        result = self.request("GET", "/api/nurse/state", token=token)
        self.assertEqual(result["code"], 200)
        return result["body"]

    def selection(self, bed="MICU-01", **extra):
        pt = server.sim["h"].beds[bed]["patient"]
        return dict(bed=bed, patient_key={"pid": pt["src"]["pid"], "admit_t": pt["admit_t"]}, **extra)


class NursePortalTests(PortalRequests, unittest.TestCase):
    def setUp(self):
        self.saved_sim = server.sim.copy()
        self.saved_sessions = server.portal.sessions.copy()
        server.portal.sessions.clear()
        server.sim.update(h=hospital(), seed=31, running=False)
        self.h = server.sim["h"]
        for bed in self.h.beds:
            admit(self.h, bed)

    def tearDown(self):
        server.sim.update(self.saved_sim)
        server.portal.sessions.clear()
        server.portal.sessions.update(self.saved_sessions)

    def test_public_accounts_contain_three_crews_and_head_nurse_only(self):
        result = self.request("GET", "/api/nurse/accounts")
        self.assertEqual(result["code"], 200)
        accounts = result["body"]["accounts"]
        self.assertEqual(len(accounts), 121)
        self.assertEqual(len({a["account_id"] for a in accounts}), 121)
        self.assertEqual(sum(a["on_duty"] for a in accounts), 41)
        self.assertEqual({a["shift_code"] for a in accounts if a["role"] != "head_nurse"}, {"D", "E", "N"})
        self.assertTrue(all(set(a) == {"account_id", "staff_id", "slot_id", "unit", "role", "shift_code",
                                      "shift_label", "on_duty"} for a in accounts))
        self.assertNotIn("patient", json.dumps(accounts))

    def test_login_rejects_unknown_account_bad_pin_and_malformed_inputs(self):
        for account, pin in (("HN02", "2026"), ("HN01", "wrong"), ("HN01", "비밀번호"),
                             ("HN01", 2026), (None, "2026"), (["HN01"], "2026")):
            with self.subTest(account=account, pin=pin):
                result = self.request("POST", "/api/nurse/login", {"account_id": account, "pin": pin,
                                                                    "role": "head_nurse"})
                self.assertEqual(result["code"], 401)
        self.assertEqual(server.portal.sessions, {})

    def test_auth_is_required_for_state_and_patient_operations(self):
        for token in (None, "invented"):
            self.assertEqual(self.request("GET", "/api/nurse/state", token=token)["code"], 401)
            self.assertEqual(self.request("POST", "/api/nurse/patient", self.selection(), token)["code"], 401)

    def test_same_board_data_is_scoped_to_two_assigned_beds(self):
        token = self.login()
        state = self.state(token)
        self.assertEqual({p["id"] for p in state["patients"]}, {"MICU-01", "MICU-02"})
        self.assertEqual(state["nurse"]["staff_id"], "D-MICU-1")
        self.assertTrue(all(p["assignment"] == "assigned" for p in state["patients"]))
        full = self.request("GET", "/api/state")["body"]
        board_patients = {b["id"]: b["patient"] for f in full["floors"] for u in f["units"] for b in u["beds"]}
        self.assertTrue(all(p["patient"] == board_patients[p["id"]] for p in state["patients"]))
        self.assertEqual((state["clock"], state["t"], state["shift"]),
                         (full["clock"], full["t"], full["shift"]))
        self.assertFalse(state["running"])

    def test_cover_and_response_expand_only_within_own_icu(self):
        token = self.login()
        self.h.nurses["MICU-1"]["cover"].extend(["MICU-03", "SICU1-01"])
        inc = self.h._new_incident(self.h.beds["MICU-04"], "det")
        inc["responders"] = ["MICU-1"]
        other = self.h._new_incident(self.h.beds["SICU1-02"], "det")
        other["responders"] = ["MICU-1"]  # corrupted metadata must still not cross the unit gate
        state = self.state(token)
        self.assertEqual({p["id"] for p in state["patients"]}, {"MICU-01", "MICU-02", "MICU-03", "MICU-04"})
        self.assertEqual(state["nurse"]["cover"], ["MICU-03"])
        self.assertEqual([a["bed"] for a in state["alerts"]], ["MICU-04"])
        self.assertEqual({p["id"]: p["assignment"] for p in state["patients"]}["MICU-03"], "cover")
        inc["end"] = 1
        self.assertNotIn("MICU-04", {p["id"] for p in self.state(token)["patients"]})

    def test_charge_sees_same_icu_and_head_sees_all_64(self):
        charge = self.state(self.login("D-MICU-C"))
        self.assertEqual(len(charge["patients"]), 8)
        self.assertEqual({p["unit"] for p in charge["patients"]}, {"MICU"})
        self.assertTrue(all(p["assignment"] == "unit" for p in charge["patients"]))
        head = self.state(self.login("HN01"))
        self.assertEqual(len(head["patients"]), 64)
        self.assertIsNone(head["nurse"])
        self.assertEqual(head["my_actions"], [])
        self.assertEqual(head["activities"], [])

    def test_forged_role_nurse_and_staff_cannot_expand_patient_access(self):
        token = self.login()
        for operation in ("patient", "care-log", "diagnostics", "consult", "handover"):
            for bed in ("MICU-03", "SICU1-01"):
                result = self.request("POST", "/api/nurse/" + operation,
                                      self.selection(bed, nurse_id="MICU-C", staff_id="HN01",
                                                     role="head_nurse", text="시연 기록", kind="blood_draw"), token)
                self.assertEqual(result["code"], 403, (operation, bed, result))
        self.assertEqual(self.h.care_actions, [])
        self.assertEqual(self.h.diagnostics, [])

    def test_authorized_mutations_always_use_canonical_login_staff(self):
        token = self.login()
        forged = self.selection(nurse_id="SICU1-C", staff_id="HN01", role="head_nurse", text="시연: 상태 확인")
        result = self.request("POST", "/api/nurse/care-log", forged, token)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["body"]["action"]["nurse_id"], "MICU-1")
        self.assertEqual(result["body"]["action"]["staff_id"], "D-MICU-1")
        self.assertEqual(result["body"]["account"]["account_id"], "D-MICU-1")
        diag = self.request("POST", "/api/nurse/diagnostics", dict(forged, kind="blood_draw"), token)
        self.assertEqual(diag["code"], 200)
        self.assertEqual(diag["body"]["task"]["requested_by_staff_id"], "D-MICU-1")
        self.assertEqual(self.request("POST", "/api/nurse/diagnostics", dict(forged, kind="blood_draw"), token)["code"], 409)

    def test_stale_patient_key_and_malformed_bed_are_rejected(self):
        token = self.login()
        result = self.request("POST", "/api/nurse/care-log", self.selection(text="시연 기록") |
                              {"patient_key": {"pid": "old", "admit_t": 0}}, token)
        self.assertEqual(result["code"], 409)
        for bed in ([], {}, None, "missing"):
            self.assertEqual(self.request("POST", "/api/nurse/patient", {"bed": bed}, token)["code"], 403)
        self.assertEqual(self.h.care_actions, [])

    def test_head_can_read_patient_and_draft_but_cannot_mutate(self):
        token = self.login("HN01")
        selection = self.selection("SICU1-01", nurse_id="MICU-1", staff_id="HN01")
        result = self.request("POST", "/api/nurse/patient", selection, token)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["body"]["account"]["staff_id"], "HN01")
        self.assertEqual(result["body"]["context_nurse"]["staff_id"], "D-SICU1-1")
        with patch.object(server.consult, "agent_turn_result", return_value={"text": "초안", "mode": "rules", "model": None}):
            result = self.request("POST", "/api/nurse/consult", dict(selection, task="sbar"), token)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["body"]["account"]["account_id"], "HN01")
        self.assertEqual(result["body"]["context_nurse"]["staff_id"], "D-SICU1-1")
        for operation in ("care-log", "diagnostics", "handover"):
            self.assertEqual(self.request("POST", "/api/nurse/" + operation, selection, token)["code"], 403)
        self.assertEqual(self.h.care_actions, [])
        self.assertEqual(self.h.diagnostics, [])

    def test_state_filters_tasks_own_records_and_simulated_activities(self):
        token = self.login()
        own = self.h.record_care_action("MICU-1", "MICU-01", "내 시연 수행")
        self.h.record_care_action("MICU-2", "MICU-03", "다른 담당자 수행")
        self.h._activity("MICU-1", "MICU-01", "arrival", "내 시연 도착")
        self.h._activity("MICU-2", "MICU-03", "arrival", "다른 담당자 도착")
        task = self.h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        self.h.request_diagnostic("MICU-2", "MICU-03", "blood_draw")
        self.h.request_diagnostic("SICU1-1", "SICU1-01", "blood_draw")
        state = self.state(token)
        self.assertEqual(state["my_actions"], [own])
        self.assertEqual([a["text"] for a in state["activities"]], ["내 시연 도착"])
        self.assertEqual([t["id"] for t in state["tasks"]], [task["id"]])

    def test_completed_xray_image_metadata_survives_state_poll(self):
        token = self.login()
        task = self.h.request_diagnostic("MICU-1", "MICU-01", "portable_xray")
        for _ in range(40):
            self.h.step()
            if self.h.diagnostic_task("MICU-01", task["id"])["status"] == "image_available":
                break
        self.assertEqual(self.h.diagnostic_task("MICU-01", task["id"])["status"], "image_available")
        image = server.consult.cxr_for(self.h.beds["MICU-01"]["patient"]["src"])
        with patch.object(server.Path, "is_file", return_value=True):
            state = self.state(token)
        result = next(t for t in state["tasks"] if t["id"] == task["id"])
        self.assertEqual(result["image_url"], "/static/cxr/" + image["file"])
        self.assertEqual(result["image_source"], "public_nih_example")
        self.assertIs(result["patient_linked"], False)

    def test_off_duty_account_logs_in_without_any_patient_data(self):
        token = self.login("E-MICU-1")
        state = self.state(token)
        self.assertFalse(state["account"]["on_duty"])
        for key in ("patients", "alerts", "tasks", "my_actions", "activities"):
            self.assertEqual(state[key], [])
        self.assertIsNone(state["nurse"])
        self.assertIsNone(state["handover"])
        for operation in ("patient", "care-log", "diagnostics", "handover", "consult"):
            self.assertEqual(self.request("POST", "/api/nurse/" + operation, self.selection(), token)["code"], 403)

    def test_shift_revokes_outgoing_patient_view_and_scopes_incoming_receipt(self):
        server.sim["h"] = self.h = hospital("14:59")
        for bed in self.h.beds:
            admit(self.h, bed)
        outgoing = self.login()
        incoming = self.login("E-MICU-1")
        self.h.step()
        self.assertEqual(self.state(outgoing)["patients"], [])
        self.assertEqual(self.request("POST", "/api/nurse/patient", self.selection(), outgoing)["code"], 403)
        state = self.state(incoming)
        self.assertEqual({r["bed"] for r in state["handover"]["patients"]}, {"MICU-01", "MICU-02"})
        self.assertTrue(all(r["to_staff_id"] == "E-MICU-1" for r in state["handover"]["patients"]))
        result = self.request("POST", "/api/nurse/handover",
                              self.selection(action="ack", handover_t=state["handover"]["t"],
                                             nurse_id="MICU-C", staff_id="HN01"), incoming)
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["body"]["receipt"]["received_by"], "E-MICU-1")
        self.assertEqual({r["bed"] for r in result["body"]["last_handover"]["patients"]}, {"MICU-01", "MICU-02"})
        charge = self.state(self.login("E-MICU-C"))
        self.assertEqual(len(charge["handover"]["patients"]), 8)
        self.assertEqual(len(self.state(self.login("HN01"))["handover"]["patients"]), 64)
        denied = self.request("POST", "/api/nurse/handover", self.selection(action="ack", handover_t=1),
                              self.login("E-MICU-C"))
        self.assertEqual(denied["code"], 403)

    def test_patient_replacement_removes_previous_admission_tasks_and_handover(self):
        server.sim["h"] = self.h = hospital("14:59")
        admit(self.h)
        self.h.request_diagnostic("MICU-1", "MICU-01", "blood_draw")
        self.h.step()
        token = self.login("E-MICU-1")
        self.assertTrue(self.state(token)["handover"]["patients"])
        admit(self.h)  # same source pid, new admission time
        state = self.state(token)
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["handover"]["patients"], [])

    def test_logout_invalidates_only_this_tabs_random_bearer(self):
        first, second = self.login(), self.login()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)
        self.assertEqual(self.request("POST", "/api/nurse/logout", token=first)["code"], 200)
        self.assertEqual(self.request("GET", "/api/nurse/state", token=first)["code"], 401)
        self.assertEqual(self.request("POST", "/api/nurse/logout", token=first)["code"], 401)
        self.assertEqual(self.state(second)["account"]["account_id"], "D-MICU-1")

    def test_consult_rechecks_shift_logout_reset_and_scope_after_model_call(self):
        for change, expected in (("shift", 409), ("logout", 401), ("reset", 409), ("scope", 409), ("patient", 409)):
            with self.subTest(change=change):
                server.sim["h"] = self.h = hospital("14:59")
                admit(self.h)
                token = self.login()
                selected = self.selection(task="sbar")

                def delayed_answer(*args, **kwargs):
                    if change == "shift":
                        self.h.step()
                    elif change == "logout":
                        server.portal.logout(token)
                    elif change == "reset":
                        server.sim["h"] = hospital()
                    elif change == "scope":
                        self.h.beds["MICU-01"]["nurse"] = "MICU-2"
                    else:
                        self.h.t += 1
                        admit(self.h)
                    return {"text": "오래된 환자 응답", "mode": "model", "model": "mock"}

                with patch.object(server.consult, "agent_turn_result", side_effect=delayed_answer):
                    result = self.request("POST", "/api/nurse/consult", selected, token)
                self.assertEqual(result["code"], expected, result)
                self.assertNotIn("오래된 환자 응답", json.dumps(result["body"], ensure_ascii=False))

    def test_unknown_portal_route_cannot_run_public_control_action(self):
        token = self.login()
        result = self.request("POST", "/api/nurse/reset", {"action": "play"}, token)
        self.assertEqual(result["code"], 404)
        self.assertFalse(server.sim["running"])
        self.assertEqual(self.request("POST", "/api/control", {"action": "play"})["code"], 200)
        self.assertTrue(server.sim["running"])

    def test_public_board_and_nurse_page_remain_available(self):
        self.assertEqual(self.request("GET", "/")["code"], 200)
        self.assertEqual(self.request("GET", "/api/state")["code"], 200)
        with patch.object(server.Path, "is_file", return_value=True), \
             patch.object(server.Path, "read_bytes", return_value=b"<html>nurse</html>"):
            result = self.request("GET", "/nurse")
        self.assertEqual(result["code"], 200)
        self.assertTrue(result["ctype"].startswith("text/html"))


if __name__ == "__main__":
    unittest.main()
