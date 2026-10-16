"""Read-only scope checks against a running public ICU demo.

Starts and ends temporary login sessions. The one care-log attempt targets an
unrelated ICU and must be rejected; no care report should be created.
"""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def verify(base):
    tokens = []
    checks = []

    def request(path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request(base.rstrip("/") + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers=headers)
        try:
            with urlopen(req, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def login(account_id):
        code, result = request("/api/nurse/login", {"account_id": account_id, "pin": "2026"})
        assert code == 200, result
        tokens.append(result["token"])
        return result["token"]

    def state(token):
        code, result = request("/api/nurse/state", token=token)
        assert code == 200, result
        return result

    try:
        assert request("/api/nurse/state")[0] == 401
        assert request("/api/nurse/login", {"account_id": "HN01", "pin": "0000"})[0] == 401
        checks.append("authentication required and invalid PIN rejected")
        code, accounts = request("/api/nurse/accounts")
        assert code == 200 and len(accounts["accounts"]) == 121
        checks.append("120 shift accounts plus HN01")
        code, board = request("/api/state")
        assert code == 200 and not board["running"], "Pause the demo before scope verification"
        beds = {bed["id"]: dict(bed, unit=unit["id"])
                for floor in board["floors"] for unit in floor["units"] for bed in unit["beds"]}
        nurse = next(n for n in board["nurses"] if n["unit"] == "MICU" and n["role"] == "bedside")
        rn_token = login(nurse["staff_id"])
        rn = state(rn_token)
        incident_beds = {event["bed"] for event in board["incidents"] if nurse["id"] in event["responders"]}
        visible = {bid for bid, bed in beds.items() if bed["unit"] == nurse["unit"]
                   and (bed["nurse"] == nurse["id"] or bid in nurse["cover"] or bid in incident_beds)}
        expected = {bid for bid in visible if beds[bid].get("patient")}
        assert {row["id"] for row in rn["patients"]} == expected
        assert all(row["bed"] in visible for row in rn["alerts"] + rn["tasks"])
        checks.append("bedside scope matches current assignments, cover and response")
        target = next(bid for bid, bed in beds.items() if bed["unit"] != nurse["unit"])
        forged = {"bed": target, "role": "head_nurse", "account_id": "HN01",
                  "nurse_id": beds[target]["nurse"], "staff_id": "HN01",
                  "text": "scope test: this report must never be saved"}
        assert request("/api/nurse/patient", forged, rn_token)[0] == 403
        assert request("/api/nurse/care-log", forged, rn_token)[0] == 403
        checks.append("unrelated ICU and forged role/staff rejected")
        if expected:
            bid = next(iter(expected))
            patient = beds[bid]["patient"]
            selection = {"bed": bid, "patient_key": {"pid": patient["pid"], "admit_t": patient["admit_t"]}}
            assert request("/api/nurse/patient", selection, rn_token)[0] == 200
            stale = dict(selection, patient_key={"pid": "previous-patient", "admit_t": -1})
            assert request("/api/nurse/patient", stale, rn_token)[0] == 409
            checks.append("own patient history accessible and stale admission rejected")
        charge_id = next(n["staff_id"] for n in board["nurses"] if n["unit"] == "MICU" and n["role"] == "charge")
        charge = state(login(charge_id))
        assert {row["id"] for row in charge["patients"]} == {
            bid for bid, bed in beds.items() if bed["unit"] == "MICU" and bed.get("patient")}
        checks.append("charge account sees its ICU only")
        head_token = login("HN01")
        head = state(head_token)
        assert {row["id"] for row in head["patients"]} == {bid for bid, bed in beds.items() if bed.get("patient")}
        assert request("/api/nurse/care-log", {"bed": target, "text": "must not save"}, head_token)[0] == 403
        checks.append("head nurse sees all current patients and cannot impersonate a writer")
        off_id = next(a["account_id"] for a in accounts["accounts"] if not a["on_duty"])
        off_token = login(off_id)
        off = state(off_token)
        assert not off["patients"] and not off["alerts"] and not off["tasks"]
        assert request("/api/nurse/patient", {"bed": target}, off_token)[0] == 403
        checks.append("off-duty session has no current patient access")
        after = request("/api/state")[1]
        assert after["t"] == board["t"] and after["care_actions"] == board["care_actions"]
        checks.append("public board and care records unchanged")
        assert request("/api/nurse/logout", {}, rn_token)[0] == 200
        assert request("/api/nurse/state", token=rn_token)[0] == 401
        tokens.remove(rn_token)
        checks.append("logout invalidates the session")
        return {"status": "passed", "checks": checks, "clock": board["clock"],
                "accounts": len(accounts["accounts"]), "bedside_account": nurse["staff_id"],
                "bedside_patients": len(rn["patients"]), "charge_account": charge_id,
                "charge_patients": len(charge["patients"]), "head_patients": len(head["patients"])}
    finally:
        for token in tokens:
            request("/api/nurse/logout", {}, token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.url)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
