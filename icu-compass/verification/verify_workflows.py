"""Public-record replay regression; no listener or model is invoked."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def verify():
    pool = engine.load_pool("mimic")
    original = digest(pool)
    runs = []
    for policy in ("fixed", "auto"):
        for minutes in (480, 1440):
            h = engine.Hospital(pool, policy, seed=31)
            bed = next(b for b in h.beds.values() if b["patient"])
            h.request_diagnostic(bed["nurse"], bed["id"], "blood_draw")
            h.request_diagnostic(bed["nurse"], bed["id"], "portable_xray")
            for _ in range(minutes):
                h.step()
                for unit in h.units.values():
                    assert sum(h.nurses[nid]["on_break"] for nid in unit["nurse_ids"]) <= 1
                for nurse in h.nurses.values():
                    assert all(h.beds[bid]["unit"] == nurse["unit"] for bid in nurse["beds"] + nurse["cover"])
                for incident in h.incidents:
                    assert all(h.nurses[nid]["unit"] == incident["unit"] for nid in incident["responders"])
            state = h.state()
            assert len(state["nurses"]) == 40 and len(state["roster"]) == 120 and len(state["doctors"]) == 8
            assert len(state["completed_shifts"]) == minutes // 480
            assert not h.care_actions
            observed_beds = 0
            for current in h.beds.values():
                if current["patient"]:
                    history = h.patient_vital_history(current["id"])
                    assert history["points"]
                    assert all(max(current["patient"]["admit_t"], h.t - 120) <= row["t"] <= h.t
                               for row in history["points"])
                    assert history["points"][-1]["t"] == h.t
                    observed_beds += 1
            for task in h.diagnostics:
                assert task["source"] == "simulation_workflow" and task["simulated"]
                assert task["patient_linked"] is False
                assert all(event["t"] <= h.t for event in task["events"])
                assert task["review"] is None
            runs.append({"policy": policy, "minutes": minutes, "completed_shifts": len(h.shift_history),
                         "history_checked_for_occupied_beds": observed_beds,
                         "diagnostics": [{"kind": task["kind"], "status": task["status"]} for task in h.diagnostics],
                         "same_icu_scope": True, "one_break_per_icu": True})
    assert digest(pool) == original
    report = {"passed": True, "source_pool_sha256": original, "source_pool_unchanged": True,
              "runs": runs, "real_model_call_verified": False, "live_http_verified": False,
              "limits": ["Operational demonstration, no clinical outcome validation",
                         "Public X-ray examples are unrelated to the replayed patients",
                         "Blood workflow has no laboratory result data"]}
    (ROOT / "verification" / "workflows-offline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    verify()
