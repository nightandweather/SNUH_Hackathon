"""Resource policy replay on a shared synthetic calendar, not clinical validation."""
import copy
from .demo import make_demo
from .model import extract_features, demo_predict, phase
from .engine import finite_number


def optimized_booking(now, arrival, probability, policy):
    """Finite candidate search under explicitly assumed arrival uncertainty.

The uncertainty is a scenario assumption, NOT a calibrated medical CI.
Cost = delay weight * expected needed-bed delay + idle weight * expected
unused hold + change weight * early-plan volatility. All inputs are forecasts.
"""
    remaining = max(0, arrival - now)
    uncertainty = max(5, min(40, remaining * 0.2))
    scenarios = [(max(now, arrival - uncertainty), 0.2), (arrival, 0.6), (arrival + uncertainty, 0.2)]
    prep = policy["prepare_minutes"]
    candidates = list(range(int(now), int(max(now, arrival)) + 1, 5))
    candidates += [max(now, arrival - prep), max(now, arrival - prep - uncertainty)]
    rows = []
    for booking in sorted(set(candidates)):
        delay = sum(w * max(0, booking + prep - a) for a, w in scenarios) * probability
        idle = sum(w * (probability * max(0, a - booking - prep) + (1 - probability) * max(0, a - booking)) for a, w in scenarios)
        change = policy["change_weight"] * min(1, max(0, arrival - booking - prep) / 120) * (1 - probability)
        cost = policy["delay_weight"] * delay + policy["idle_weight"] * idle + change
        rows.append({"minute": round(booking, 1), "cost": round(cost, 2), "expected_delay_minutes": round(delay, 1), "expected_idle_minutes": round(idle, 1)})
    best = min(rows, key=lambda v: (v["cost"], -v["minute"]))
    return {"booking_minute": best["minute"], "arrival_uncertainty_minutes": round(uncertainty, 1),
            "expected_cost": best["cost"], "expected_delay_minutes": best["expected_delay_minutes"],
            "expected_idle_minutes": best["expected_idle_minutes"], "candidates": rows[::max(1, len(rows) // 24)],
            "assumption": "3점 도착 시나리오와 운영 가중치에 대한 탐색 결과"}


def compare(seed, policy, horizon=360):
    horizon = int(finite_number(horizon, "평가기간", 120, 600))
    initial = make_demo(seed)
    candidates = [p for p in initial["patients"] if phase(p, 0) not in ("ICU", "WARD")]
    results = []
    for mode, label in (("fixed", "수술 종료 120분 전 일괄"), ("threshold", "위험 기준 도달 즉시"), ("dynamic", "위험·도착·준비시간 최적화")):
        beds = copy.deepcopy(initial["beds"])
        busy = {b["id"]: b["available_minute"] for b in beds}
        requests, booked, pending, allocations = {}, {}, {}, []
        completed_delays = 0.0
        idle, completed_false, missed, booking_count, revisions = 0.0, 0, 0, 0, 0
        for minute in range(0, horizon + 1, 5):
            for patient in candidates:
                pid = patient["id"]
                traj = initial["trajectories"][pid]
                p = copy.deepcopy(patient)
                p["observations"] = [o for o in traj["observations"] if o["minute"] <= minute]
                if traj["actual_end_minute"] <= minute:
                    p["actual_end_minute"] = traj["actual_end_minute"]
                features = extract_features(p, minute, policy)
                pred = demo_predict(features)
                arrival = max(0, patient["estimated_end_minute"]) + policy["transfer_minutes"]
                needed = traj["truth_icu"]
                if minute >= arrival and needed and pid not in allocations and pid not in pending:
                    pending[pid] = {"arrival": arrival, "patient": patient, "pred": pred}
                if pid in booked or pid in requests or pid in allocations:
                    continue
                if mode == "fixed":
                    trigger = minute >= max(0, arrival - 120)
                elif mode == "threshold":
                    trigger = pred["icu_probability"] >= policy["icu_threshold"]
                else:
                    opt = optimized_booking(minute, max(minute, arrival), pred["icu_probability"], policy)
                    trigger = pred["icu_probability"] >= policy["icu_threshold"] and pred["confidence"] >= policy["confidence_min"] and not features["stale"] and minute >= opt["booking_minute"]
                if trigger:
                    requests[pid] = {"patient": patient, "booking": minute, "arrival": arrival, "needed": needed, "pred": pred}
            for pid, req in sorted(list(requests.items()), key=lambda kv: -kv[1]["pred"]["need_score"]):
                patient = req["patient"]
                available = [b for b in beds if b["enabled"] and b["unit"] == patient["preferred_unit"] and busy[b["id"]] <= minute
                             and set(patient["capabilities_required"]).issubset(b["capabilities"])]
                if available:
                    bed = available[0]
                    booking_count += 1
                    ready = minute + policy["prepare_minutes"]
                    actual_start = max(req["arrival"], ready)
                    req.update(bed=bed["id"], ready=ready, actual_start=actual_start)
                    booked[pid] = req
                    busy[bed["id"]] = actual_start + (initial["trajectories"][pid]["truth_icu_hours"] * 60 if req["needed"] else 0) + policy["cleanup_minutes"]
                    requests.pop(pid)
            for pid, req in list(booked.items()):
                if minute >= req["actual_start"]:
                    idle += max(0, req["actual_start"] - req["ready"]) if req["needed"] else max(0, req["actual_start"] - req["booking"])
                    if req["needed"]:
                        completed_delays += max(0, req["actual_start"] - req["arrival"])
                        allocations.append(pid)
                        pending.pop(pid, None)
                    else:
                        completed_false += 1
                        allocations.append(pid)
                    booked.pop(pid)
        # Delays are evaluated against private synthetic outcomes only AFTER policy replay.
        delay = completed_delays
        needed_count = 0
        for pid, wait in pending.items():
            delay += max(0, horizon - wait["arrival"])
            missed += 1
        needed_count = sum(initial["trajectories"][p["id"]]["truth_icu"] and max(0, p["estimated_end_minute"]) + policy["transfer_minutes"] <= horizon for p in candidates)
        results.append({"policy": mode, "label": label, "bed_delay_minutes": round(delay, 1),
                        "idle_hold_minutes": round(idle, 1), "unnecessary_bookings": completed_false,
                        "unplaced_at_horizon": missed, "bookings": booking_count, "needed_patients": needed_count,
                        "weighted_cost": round(delay * policy["delay_weight"] + idle * policy["idle_weight"] + revisions * policy["change_weight"], 1)})
    return {"seed": seed, "horizon_minutes": horizon, "results": results,
            "scope": "고정 시드 기본 합성 경과 재생. 현재 화면의 수동 예약·추가 사건 주입은 제외.",
            "truth": "합성 시나리오의 지원 필요·ICU 기간을 평가 정답으로만 사용", "clinical_validation": False,
            "weights": {k: policy[k] for k in ("delay_weight", "idle_weight", "change_weight")}}
