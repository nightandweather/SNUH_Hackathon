"""Run against the synthetic demo server; reset affects the demo only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8002")
    parser.add_argument("--output", default="verification/planning-http.json")
    args = parser.parse_args()

    def request(path, payload=None):
        raw = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(args.base.rstrip("/") + path, raw,
                                     {"Content-Type": "application/json"} if raw else {})
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            data = response.read()
            return response.status, json.loads(data) if "json" in response.headers.get("Content-Type", "") else data

    def action(name, state, **fields):
        return request("/api/planning/action", dict(action=name, scenario_id=state["scenario_id"], **fields))

    checks = []
    status, state = request("/api/planning/state")
    assert status == 200 and state["scope"] == "synthetic_operational_demo"
    _, reply = action("reset", state, seed=7)
    state = reply["state"]
    status, page = request("/planning")
    assert status == 200 and b"scenario_id" in page
    assert len(state["patients"]) == 8 and len(state["beds"]) == 3
    checks.append("synthetic_screen_and_scope")
    assert all(event["t"] <= state["t"] for patient in state["patients"] for event in patient["observed_events"])
    checks.append("future_clinical_events_hidden")
    status, reply = action("propose", state, patient_id="P003", mode="offline")
    assert status == 200 and reply["agent"]["model_called"] is False
    plan, state = reply["plan"], reply["state"]
    assert plan["status"] == "proposed" and not any(r["patient_id"] == "P003" for r in state["reservations"])
    checks.append("proposal_does_not_allocate")
    status, reply = action("conflict", state, plan_id=plan["id"])
    assert status == 200
    state = reply["state"]
    status, reply = action("approve", state, plan_id=plan["id"], expected_revision=plan["revision"])
    assert status == 409 and not any(r["patient_id"] == "P003" for r in reply["state"]["reservations"])
    checks.append("stale_approval_blocked")
    status, reply = action("replan", state, plan_id=plan["id"], mode="offline")
    assert status == 200
    new_plan, state = reply["plan"], reply["state"]
    status, reply = action("approve", state, plan_id=new_plan["id"], expected_revision=new_plan["revision"])
    assert status == 200 and len([r for r in reply["state"]["reservations"] if r["patient_id"] == "P003"]) == 1
    checks.append("replan_requires_and_accepts_new_approval")
    state = reply["state"]
    status, reply = action("propose", state, patient_id="P003", mode="offline")
    assert status == 409
    checks.append("duplicate_booking_blocked")
    _, reply = action("reset", state, seed=7)
    state = reply["state"]
    _, reply = action("propose", state, patient_id="P003", mode="offline")
    old_plan, old_state = reply["plan"], reply["state"]
    _, reply = action("reset", old_state, seed=7)
    state = reply["state"]
    _, reply = action("propose", state, patient_id="P003", mode="offline")
    assert reply["plan"]["id"] == old_plan["id"]
    status, reply = action("approve", old_state, plan_id=old_plan["id"], expected_revision=old_plan["revision"])
    assert status == 409 and reply["code"] == "SCENARIO_CHANGED"
    checks.append("cross_tab_reset_cannot_reuse_approval")
    state = reply["state"]
    _, reply = action("advance", state, minutes=1440)
    state = reply["state"]
    assert state["calendar"]["weekend"] and not state["calendar"]["elective_surgery_open"]
    assert state["calendar"]["shift"]["code"] == "D"
    assert any(p["observed_events"] for p in state["patients"])
    checks.append("weekend_replay_and_shifts_continue")
    _, reply = action("advance", state, minutes=2880)
    state = reply["state"]
    assert state["calendar"]["weekday"] == "Monday" and state["calendar"]["elective_surgery_open"]
    checks.append("monday_elective_schedule_resumes")
    status, reply = request("/api/planning/action", {"action": "approve", "plan_id": "PLAN-1", "expected_revision": 1})
    assert status == 400 and reply["code"] == "SCENARIO_REQUIRED"
    checks.append("scenario_identity_required")
    # Keep a fresh, legible initial state for the person opening the demo.
    action("reset", state, seed=7)
    report = {"status": "passed", "checks": checks, "check_count": len(checks),
              "scope": "synthetic_operational_demo", "real_model_call_verified": False,
              "clinical_prediction_validated": False, "verified_at": datetime.now(timezone.utc).isoformat()}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
