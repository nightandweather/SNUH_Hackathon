"""Reproducible synthetic resource-policy evaluation, without a live model.

python3 planner_evaluate.py --seeds 1 2 3 --output /tmp/planner-evaluation.json
Comma-separated seeds are also accepted. No network, clinical data or model API.
"""
import argparse
import json
from datetime import timedelta
from pathlib import Path

from planner_core import POLICIES, START, PlannerError, PlannerHospital


def validate_final_state(state):
    """Independent sweep over public resource reservations and known schedules."""
    reservations = [row for row in state["reservations"] if row["status"] != "cancelled"]
    beds = {row["id"] for row in state["beds"]}
    capacities = state["scenario"]["staff_capacity_by_shift"]
    violations = []
    for i, row in enumerate(reservations):
        if row["bed_id"] not in beds or row["end_t"] <= row["start_t"]:
            violations.append({"code": "invalid_reservation", "id": row["id"]})
        for other in reservations[i + 1:]:
            simultaneous = max(row["start_t"], other["start_t"]) < min(row["end_t"], other["end_t"])
            if simultaneous and (row["bed_id"] == other["bed_id"] or row["patient_id"] == other["patient_id"]):
                violations.append({"code": "overlap", "ids": [row["id"], other["id"]]})
    ends = [row["end_t"] for row in reservations]
    boundaries = {point for row in reservations for point in (row["start_t"], row["end_t"])}
    boundaries.update(range(0, int(max(ends, default=0)) + 1, 480))
    for point in boundaries:
        active = [row for row in reservations if row["start_t"] <= point < row["end_t"]]
        code = ("D", "E", "N")[int(point // 480) % 3]
        if len(active) > len(beds) or sum(row["nurse_units"] for row in active) > capacities[code]:
            violations.append({"code": "capacity", "t": point})
    for patient in state["patients"]:
        if patient["elective"] and (START + timedelta(minutes=patient["scheduled_start_t"])).weekday() >= 5:
            violations.append({"code": "weekend_elective", "patient_id": patient["id"]})
        if any(row["t"] > state["t"] for row in patient["observed_events"]):
            violations.append({"code": "future_clinical_event", "patient_id": patient["id"]})
    return {"ok": not violations, "violation_count": len(violations), "violations": violations}


def evaluate_policy(seed, policy):
    h = PlannerHospital(seed=seed)
    signature = h.fixture_signature()
    elective = sorted((row for row in h.state()["patients"] if row["elective"]),
                      key=lambda row: (row["scheduled_start_t"], row["id"]))
    requests, delay, weighted_delay = [], 0, 0
    for patient in elective:
        try:
            plan = h.propose(patient["id"], policy)
            approved = h.approve(plan["id"], plan["revision"])
            delay += plan["delay_minutes"]
            weighted_delay += plan["delay_minutes"] * patient["scenario_assumption"]["priority_weight"]
            requests.append({"patient_id": patient["id"], "status": "approved", "delay_minutes": plan["delay_minutes"],
                             "plan_id": plan["id"], "reservation_id": approved["reservation"]["id"]})
        except PlannerError as error:
            requests.append({"patient_id": patient["id"], "status": "not_completed", "code": error.code,
                             "error": error.message})
    booked_state = h.state()
    weekend_checks = []
    for target in (1440, 1920, 2400, 2880, 3360, 3840):
        h.advance(target - h.t)
        state = h.state()
        weekend_checks.append({"t": target, "datetime": state["calendar"]["datetime"],
                               "weekend": state["calendar"]["weekend"],
                               "elective_surgery_open": state["calendar"]["elective_surgery_open"],
                               "shift": state["calendar"]["shift"]["code"],
                               "observed_event_count": sum(len(p["observed_events"]) for p in state["patients"]),
                               "constraints_ok": validate_final_state(state)["ok"]})
    h.advance(6000 - h.t)
    final = h.state()
    approved_count = sum(row["status"] == "approved" for row in requests)
    return {"seed": seed, "policy": policy, "method": "deterministic_rule_no_solver_no_llm",
            "fixture_signature": signature, "requested_count": len(requests), "approved_count": approved_count,
            "not_completed_count": len(requests) - approved_count, "total_delay_minutes": delay,
            "priority_weighted_delay_minutes": weighted_delay,
            "booked_constraint_check": validate_final_state(booked_state),
            "final_constraint_check": validate_final_state(final), "requests": requests,
            "weekend_checks": weekend_checks, "final_state": final}


def _failure_scenarios(seed, policy):
    results = []
    h = PlannerHospital(seed=seed)
    old = h.propose("P003", policy)
    h.inject_conflict(old["id"])
    stale_code = None
    try:
        h.approve(old["id"], old["revision"])
    except PlannerError as error:
        stale_code = error.code
    fresh = h.replan(old["id"])
    still_unassigned = not any(row["patient_id"] == "P003" for row in h.state()["reservations"])
    h.approve(fresh["id"], fresh["revision"])
    final = h.state()
    results.append({"scenario": "conflict_then_replan", "passed": stale_code == "stale_revision"
                    and still_unassigned and validate_final_state(final)["ok"],
                    "stale_error_code": stale_code, "new_plan_requires_approval": still_unassigned, "final_state": final})
    for name in ("duplicate_approval", "clock_advance", "staffing_changed", "no_feasible"):
        h = PlannerHospital(seed=seed)
        rejection = None
        patient = "P006" if name == "no_feasible" else "P003"
        if name == "no_feasible":
            h.staff_capacity["N"] = 1  # Existing night census fits; another long booking does not.
        try:
            plan = h.propose(patient, "first_available" if name == "staffing_changed" else policy)
            if name == "duplicate_approval":
                h.approve(plan["id"], plan["revision"])
                h.approve(plan["id"], h.revision)
            elif name == "clock_advance":
                h.advance(1)
                h.approve(plan["id"], plan["revision"])
            elif name == "staffing_changed":
                h.staff_capacity["D"] = 2  # Fault fixture: resource condition changes before approval.
                h.approve(plan["id"], plan["revision"])
        except PlannerError as error:
            rejection = error.code
        expected = {"duplicate_approval": "already_approved", "clock_advance": "stale_revision",
                    "staffing_changed": "staff_capacity", "no_feasible": "no_feasible"}[name]
        final = h.state()
        results.append({"scenario": name, "passed": rejection == expected and validate_final_state(final)["ok"],
                        "error_code": rejection, "final_state": final})
    return results


def evaluate(seeds=(1, 2, 3)):
    seeds = list(seeds)
    if not seeds or any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds):
        raise ValueError("at least one integer seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be distinct")
    policies = [evaluate_policy(seed, policy) for seed in seeds for policy in POLICIES]
    failures = [{"seed": seed, "policy": policy, "scenarios": _failure_scenarios(seed, policy)}
                for seed in seeds for policy in POLICIES]
    paired = []
    for seed in seeds:
        left, right = [row for row in policies if row["seed"] == seed]
        paired.append({"seed": seed, "same_fixture": left["fixture_signature"] == right["fixture_signature"],
                       "optimized_minus_first_available_delay_minutes": right["total_delay_minutes"] - left["total_delay_minutes"],
                       "optimized_minus_first_available_weighted_delay_minutes": right["priority_weighted_delay_minutes"] - left["priority_weighted_delay_minutes"]})
    all_checks = all(row["booked_constraint_check"]["ok"] and row["final_constraint_check"]["ok"]
                     and all(check["constraints_ok"] for check in row["weekend_checks"]) for row in policies)
    return {"evaluation_type": "synthetic_operational_evaluation", "live_model_evaluated": False,
            "clinical_prediction_validated": False, "clinical_treatment_effect_evaluated": False,
            "note": "합성 가정·동일 fixture의 규칙 정책 비교. 실제 병원 효율·치료효과·에이전트 성능 평가가 아닙니다.",
            "seeds": seeds, "all_constraints_pass": all_checks,
            "all_failure_scenarios_pass": all(s["passed"] for row in failures for s in row["scenarios"]),
            "paired_comparisons": paired, "policy_results": policies, "failure_results": failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", default=["1", "2", "3"], help="integers, separated by spaces or commas")
    parser.add_argument("--output", type=Path, help="write complete evaluation JSON to this file")
    args = parser.parse_args(argv)
    try:
        seeds = [int(value) for group in args.seeds for value in group.split(",") if value.strip()]
        result = evaluate(seeds)
    except ValueError as error:
        parser.error(str(error))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
        print(json.dumps({key: result[key] for key in ("evaluation_type", "live_model_evaluated", "seeds",
                                                      "all_constraints_pass", "all_failure_scenarios_pass", "paired_comparisons")}, ensure_ascii=False))
    else:
        print(encoded)
    return 0 if result["all_constraints_pass"] and result["all_failure_scenarios_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
