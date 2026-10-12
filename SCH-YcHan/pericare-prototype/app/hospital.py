"""Hospital flow, observed recovery and recorded-event playback.

Synthetic generation is deliberately separate from decisions. Clinical team
code never reads a future trajectory or uses predicted LOS as an exit event.
Real inputs get no manufactured observations, milestones or departures.
"""
import copy
import math
from .capacity import WARD_BEDS

TERMINAL = {"discharged", "deceased", "transferred"}
RECOVERY_DAYS = {"minor": .8, "standard": 3, "major": 5, "complex": 8}


def ensure_hospital(s):
    h = s.setdefault("hospital", {})
    h.setdefault("initial_census", sum(active(p) and p["admission_minute"] <= s["minute"] for p in s["patients"]))
    h.setdefault("admissions", 0)
    h.setdefault("discharges", 0)
    h.setdefault("exits", 0)
    h.setdefault("deaths", 0)
    h.setdefault("transfers", 0)
    h.setdefault("icu_transfers", 0)
    h.setdefault("completed_operations", 0)
    h.setdefault("events", [])
    h.setdefault("daily", {})
    s.setdefault("horizon_minutes", s["minute"] + 10080)
    s.setdefault("arrival_queue", [])
    s.setdefault("replay_events", [])
    s.setdefault("replay_cursor", 0)
    # Only synthetic operations have a fabricated ward inventory.
    if "ward_beds" not in s:
        s["ward_beds"] = [{"id": f"WARD-{n:03d}", "unit": "WARD", "enabled": True,
            "occupant_id": None, "available_minute": 0} for n in range(1, WARD_BEDS + 1)] if s["source"] == "synthetic" else []
    for p in s["patients"]:
        p.setdefault("status", "active")
        p.setdefault("discharge_minute", None)
    return h


def active(p):
    return p.get("status", "active") not in TERMINAL | {"scheduled"}


def record(s, pid, kind, label, detail=""):
    h = ensure_hospital(s)
    e = {"minute": s["minute"], "patient_id": pid, "kind": kind, "label": label, "detail": detail}
    h["events"].append(e)
    h["events"] = h["events"][-1000:]
    s["events"].append(copy.deepcopy(e))
    day = str(s["minute"] // 1440)
    d = h["daily"].setdefault(day, {"admissions": 0, "discharges": 0, "operations": 0, "icu_admissions": 0})
    counter = {"hospital_admission": "admissions", "hospital_discharge": "discharges",
               "operation_end": "operations", "icu_admission": "icu_admissions"}.get(kind)
    if counter:
        d[counter] += 1
    s.setdefault("_audit_buffer", []).append({"minute": s["minute"], "action": kind,
        "actor": "병원 운영 시뮬레이션" if s["source"] == "synthetic" else "기록 재생",
        "payload": copy.deepcopy(e)})


def claim_ward_bed(s, p):
    existing = next((b for b in s["ward_beds"] if b["occupant_id"] == p["id"]), None)
    if existing:
        p["ward_bed_id"] = existing["id"]
        return existing
    bed = next((b for b in s["ward_beds"] if b["enabled"] and not b["occupant_id"]
                and b["available_minute"] <= s["minute"]), None)
    if bed:
        bed["occupant_id"] = p["id"]
        p["ward_bed_id"] = bed["id"]
    return bed


def release_ward_bed(s, p):
    for b in s["ward_beds"]:
        if b["occupant_id"] == p["id"]:
            b.update(occupant_id=None, available_minute=s["minute"] + s["policy"].get("ward_cleanup_minutes", 30))
    p.pop("ward_bed_id", None)


def synthetic_observation(p, minute, tr):
    """A deterministic observation emitted *at* this minute, not a forecast.

    Recovery group and physiology are fictional. Sparse ward observations are
    kept sparse; they are not interpolated into purported measured vital signs.
    """
    end = tr["actual_end_minute"]
    postop = max(0, minute - end)
    in_or = p["operation_start_minute"] <= minute < end
    course = tr.get("course", p.get("course", "stable"))
    noise = math.sin((minute + int(p["id"].split("-")[-1]) * 13) / 23) * 1.8
    severity = max(0, 1 - postop / {"shock": 2880, "cardiac": 1440, "hypoxia": 720,
        "hypotension": 480, "bleeding": 1080, "moderate": 180}.get(course, 60))
    burden = course in ("shock", "cardiac", "hypotension", "bleeding") and minute >= p["operation_start_minute"]
    mapv = 79 + noise - (20 * severity if burden else 0)
    norepi = (0.18 if course == "shock" else .08) * severity if burden else 0
    spo2 = 98 - (8 * severity if course == "hypoxia" and minute >= end else 0)
    lactate = 1.2 + (3.4 * severity if burden else 0)
    recovered = postop / (RECOVERY_DAYS.get(p.get("procedure_group"), 5) * 1440)
    return {"minute": minute, "map": round(mapv, 1), "hr": round(78 + noise + 26 * severity if burden else 78 + noise, 1),
        "spo2": round(spo2, 1), "lactate": round(lactate, 2), "hemoglobin": 12.1,
        "norepi": round(norepi, 3), "urine_ml_kg_h": .8, "ventilation": in_or or (course in ("shock", "cardiac") and postop < 480 and minute >= end),
        "crrt": p["id"] == "DEMO-011" and minute < end + 1440, "source": "synthetic-recovery",
        "oral_intake": recovered >= .4, "ambulating": recovered >= .65,
        "pain_score": 2 if recovered >= .8 else 5, "wound_ok": recovered >= .7,
        "discharge_plan_confirmed": recovered >= 1}


def update_synthetic(s):
    """Release arrivals and newly observed events. Never consult predictions."""
    if s["source"] != "synthetic":
        return
    now = s["minute"]
    ready = [q for q in s["arrival_queue"] if q["minute"] <= now]
    s["arrival_queue"] = [q for q in s["arrival_queue"] if q["minute"] > now]
    for q in ready:
        p = copy.deepcopy(q["patient"])
        p["admission_minute"] = now
        p["admission_handoff_due"] = now + 10
        if not claim_ward_bed(s, p):
            p["admission_wait"] = True
        s["patients"].append(p)
        s["trajectories"][p["id"]] = copy.deepcopy(q["trajectory"])
        s["hospital"]["admissions"] += 1
        record(s, p["id"], "hospital_admission", "신규 환자 접수 · 입원 인계", p["surgery"])
    room_ids = [f"OR-{n:02d}" for n in range(1, 9)]
    for p in s["patients"]:
        if not active(p):
            continue
        tr = s["trajectories"].get(p["id"], {})
        if not tr:
            continue
        if p["location"] == "ENTRY":
            if p.get("admission_wait"):
                if claim_ward_bed(s, p):
                    p.pop("admission_wait", None)
                    p["admission_handoff_due"] = now + 10
                else:
                    continue
            if now >= p.get("admission_handoff_due", now):
                p["location"] = "PREOP"
                record(s, p["id"], "admission_handoff", "입원 인계 완료 · 수술 전 준비")
        if p["location"].startswith("PREOP") and now >= p["operation_start_minute"]:
            occupied = {q["location"] for q in s["patients"] if active(q) and q.get("actual_end_minute") is None and q["location"].startswith("OR-")}
            room = next((r for r in room_ids if r not in occupied), None)
            if room:
                shift = max(0, now - p["operation_start_minute"])
                if shift:
                    p["operation_start_minute"] = now
                    p["estimated_end_minute"] += shift
                    tr["actual_end_minute"] += shift
                p["location"] = room
                record(s, p["id"], "operation_start", "수술실 도착 · 수술 시작", room)
        end = tr.get("actual_end_minute")
        if p["location"].startswith("OR") and end is not None and now >= end and p.get("actual_end_minute") is None:
            p.update(actual_end_minute=end, location="PACU")
            s["hospital"]["completed_operations"] += 1
            record(s, p["id"], "operation_end", "수술 종료 관측 · 회복실 인계")
        from .model import phase
        current = phase(p, now)
        cadence = 60 if current == "WARD" else 15 if current in ("PREOP", "ADMITTING") else 5
        # Existing sparse measurements are retained without making them fresh.
        if now % cadence and p["observations"]:
            continue
        exact = next((o for o in tr.get("observations", []) if o["minute"] == now), None)
        obs = copy.deepcopy(exact) if exact else synthetic_observation(p, now, tr)
        # Recovery milestones are observed only in the ward and never copied
        # from a future discharge time or a predicted duration.
        if current == "WARD":
            obs.update({k: v for k, v in synthetic_observation(p, now, tr).items()
                        if k in ("oral_intake", "ambulating", "pain_score", "wound_ok", "discharge_plan_confirmed")})
        scenario = s["active_scenarios"].get(p["id"])
        if scenario and now > scenario["end"]:
            s["active_scenarios"].pop(p["id"], None)
            scenario = None
        if scenario and scenario["kind"] == "stale":
            continue
        if scenario:
            from .engine import Engine
            Engine.apply_effect(obs, scenario["kind"])
        p["observations"] = [o for o in p["observations"] if o["minute"] != now][-479:] + [obs]
        for t in tr.get("treatments", []):
            if now - 5 < t["minute"] <= now and not any(v["minute"] == t["minute"] and v["label"] == t["label"] for v in p["treatments"]):
                p["treatments"].append(copy.deepcopy(t))


def can_review_discharge(p, now):
    from .team import stable_observation
    observed = [o for o in p["observations"] if now - 360 <= o["minute"] <= now]
    if len(observed) < 3 or observed[-1]["minute"] < now - 120:
        return False
    latest = observed[-1]
    return (all(stable_observation(o, strict=True) for o in observed[-3:])
            and all(latest.get(k) is True for k in ("oral_intake", "ambulating", "wound_ok", "discharge_plan_confirmed"))
            and isinstance(latest.get("pain_score"), (int, float)) and latest["pain_score"] <= 3)


def hospital_discharge(s, p, outcome="home"):
    """An observed event, not expiration of hospital_los_days."""
    if not active(p):
        return
    now = s["minute"]
    release_ward_bed(s, p)
    for bed in s["beds"]:
        if bed["occupant_id"] == p["id"]:
            bed.update(occupant_id=None, available_minute=now + s["policy"]["cleanup_minutes"], available_basis="실제 퇴실 후 청소", availability_forecast_known=True)
    for r in s["reservations"]:
        if r["patient_id"] == p["id"] and r["status"] in ("confirmed", "occupied"):
            r.update(status="completed" if r["status"] == "occupied" else "cancelled", end=now)
    p.update(status={"home": "discharged", "death": "deceased", "transfer": "transferred"}[outcome],
             location={"home": "DISCHARGED", "death": "DECEASED", "transfer": "TRANSFERRED"}[outcome],
             discharge_minute=now, discharge_outcome=outcome)
    s["hospital"]["discharges"] += int(outcome == "home")
    s["hospital"]["exits"] += 1
    s["hospital"]["deaths"] += int(outcome == "death")
    s["hospital"]["transfers"] += int(outcome == "transfer")
    record(s, p["id"], "hospital_discharge" if outcome == "home" else "hospital_exit",
           {"home": "병원 퇴원 완료", "death": "사망 기록", "transfer": "다른 기관 전원"}[outcome])
    s["active_scenarios"].pop(p["id"], None)


def recorded_bed_plan(s, events):
    """Resolve one observed timestamp as a group, independent of patient IDs.

    A release and a new location recorded at the same timestamp can coexist.
    Two final occupants of one physical bed are still a conflict.
    """
    changes = {}
    by_occupant = {b["occupant_id"]: b for b in s["beds"] if b["occupant_id"]}
    by_patient = {p["id"]: p for p in s["patients"]}
    for event in events:
        kind = event["kind"]
        if kind in ("hospital_admission", "operation_start", "location"):
            location = event["location"]
            old_bed = by_occupant.get(event["patient_id"])
            if old_bed and location in ("ICU", old_bed["unit"]):
                location = old_bed["id"]  # Less specific unit data is not an observed bed release.
            changes[event["patient_id"]] = location
        elif kind == "operation_end":
            from .model import phase
            p = {**by_patient[event["patient_id"]]}
            p["location"] = changes.get(p["id"], p["location"])
            if phase(p, s["minute"]) in ("OR", "PREOP"):
                changes[event["patient_id"]] = "PACU"
        elif kind == "hospital_discharge":
            changes[event["patient_id"]] = "DISCHARGED"
    occupants = {b["id"]: b["occupant_id"] for b in s["beds"]}
    for bid, occupant in list(occupants.items()):
        if occupant in changes and changes[occupant] != bid:
            occupants[bid] = None
    for pid, location in changes.items():
        if location in occupants:
            if occupants[location] not in (None, pid):
                from .engine import AppError
                raise AppError("기록 재생 병상 중복 점유: " + location, 409)
            occupants[location] = pid
    return occupants, changes


def replay_until(s):
    """Recorded future packets become observed data only at their timestamps."""
    if s["source"] != "import":
        return
    events = s.get("replay_events", [])
    while s["replay_cursor"] < len(events) and events[s["replay_cursor"]]["minute"] <= s["minute"]:
        cursor = s["replay_cursor"]
        now = events[cursor]["minute"]
        end = cursor + 1
        while end < len(events) and events[end]["minute"] == now:
            end += 1
        batch = events[cursor:end]
        occupants, changes = recorded_bed_plan(s, batch)
        before = {b["id"]: b["occupant_id"] for b in s["beds"]}
        by_patient = {p["id"]: p for p in s["patients"]}
        for event in batch:
            apply_recorded_event(s, event, by_patient[event["patient_id"]])
        for bed in s["beds"]:
            occupant = occupants[bed["id"]]
            if before[bed["id"]] != occupant:
                bed.update(occupant_id=occupant,
                    available_minute=now if occupant else now + s["policy"]["cleanup_minutes"],
                    availability_forecast_known=not bool(occupant),
                    available_basis="실제 재실 · 퇴실 시각 미확인" if occupant else "실제 퇴실 후 청소")
        for pid, location in changes.items():
            p = by_patient[pid]
            if p.get("status") not in TERMINAL:
                p["location"] = location
            if location in occupants:
                p["icu_bed_id"] = location
            else:
                p.pop("icu_bed_id", None)
        s["replay_cursor"] = end


def apply_recorded_event(s, event, p):
    """Apply observed chart events; bed ownership is committed per batch."""
    now, kind, pid = event["minute"], event["kind"], event["patient_id"]
    # Engine advance visits each event timestamp, so no later event can be
    # retroactively used in an earlier forecast or decision.
    if kind == "hospital_admission":
        p.update(status="active", location=event["location"])
        s["hospital"]["admissions"] += 1
        record(s, pid, kind, "기록된 신규 입원")
    elif kind == "operation_start":
        p.update(operation_start_minute=now, location=event["location"])
        record(s, pid, kind, "기록된 수술 시작")
    elif kind == "observation":
        if p.get("status") == "scheduled":
            return
        observation = copy.deepcopy(event["observation"])
        if p.get("status") in TERMINAL and observation["minute"] > p["discharge_minute"]:
            from .engine import AppError
            raise AppError("입원 종료 이후 측정된 재생 관측입니다")
        by_time = {o["minute"]: o for o in p["observations"]}
        by_time[observation["minute"]] = observation
        p["observations"] = [by_time[t] for t in sorted(by_time)][-1000:]
    elif kind == "operation_end":
        from .model import phase
        observed_phase = phase(p, now)
        p["actual_end_minute"] = event.get("actual_end_minute", now)
        if observed_phase in ("OR", "PREOP"):
            p["location"] = "PACU"
        s["hospital"]["completed_operations"] += 1
        record(s, pid, kind, "기록된 수술 종료")
    elif kind == "location":
        location = event["location"]
        p["location"] = location
        record(s, pid, kind, "기록된 위치 변경", location)
    elif kind == "hospital_discharge":
        hospital_discharge(s, p, event.get("outcome", "home"))


def public_hospital(s):
    h = ensure_hospital(s)
    patients = s["patients"]
    return {"initial_census": h["initial_census"], "current_census": sum(active(p) for p in patients),
        "admissions": h["admissions"], "discharges": h["discharges"],
        "exits": h["exits"], "deaths": h["deaths"], "transfers": h["transfers"],
        "completed_operations": h["completed_operations"], "days": max(1, math.ceil(s["horizon_minutes"] / 1440)),
        "day": min(max(1, math.ceil(s["horizon_minutes"] / 1440)), s["minute"] // 1440 + 1),
        "horizon_minutes": s["horizon_minutes"], "ended": s["minute"] >= s["horizon_minutes"],
        "ward_occupied": sum(bool(b["occupant_id"]) for b in s["ward_beds"]),
        "ward_capacity": sum(b["enabled"] for b in s["ward_beds"]),
        "ward_cleaning": sum(not b["occupant_id"] and b["available_minute"] > s["minute"] for b in s["ward_beds"]),
        "replay_mode": "recorded_events" if s.get("replay_events") else "synthetic_operations" if s["source"] == "synthetic" else "snapshot",
        "daily": copy.deepcopy(h["daily"]), "events": copy.deepcopy(h["events"][-20:])}
