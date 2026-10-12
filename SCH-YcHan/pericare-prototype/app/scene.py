"""Observed hospital scene for the synthetic demo; no future trajectories are read.

Coordinates are an illustrative floor layout, not measured patient/staff locations.
Patient routes follow active handoff jobs. Staff are persistent virtual role slots.
The scene never changes reservations, clinical decisions, or actual bed occupancy.
"""
import copy
import math

WIDTH = 2000
ROLE_NAMES = {"charge": "병상 준비", "transport": "이송", "ward": "병동 인수",
              "anesthesia": "마취과", "intensivist": "ICU 전담", "surgeon": "담당 외과"}
ZONE_LABELS = {"PREOP": "수술 전 대기", "OR": "수술실", "PACU": "회복실",
               "SICU": "외과계 ICU", "CCU": "심장계 ICU", "WARD": "일반병동", "ENTRY": "입원 접수·인계", "EXIT": "퇴원·출구"}


def _zone(p, beds):
    if p["location"] in beds:
        return beds[p["location"]]["unit"]
    phase = p["prediction"]["features"]["phase"]
    if phase == "ADMITTING":
        return "ENTRY"
    if phase in ("DISCHARGED", "DECEASED", "TRANSFERRED"):
        return "EXIT"
    if phase == "ICU":
        return p.get("preferred_unit", "SICU")
    return phase if phase in ("PREOP", "OR", "PACU", "WARD") else "WARD"


def _route(start, target, zones, hallway):
    a, b = zones[start["zone"]], zones[target["zone"]]
    # Shared hallway and side aisles make transfers recognizable at every zoom.
    start_aisle = start["y"] + (74 if start["zone"] in ("SICU", "CCU") else 58)
    target_aisle = target["y"] + (74 if target["zone"] in ("SICU", "CCU") else 58)
    points = [[start["x"], start["y"]], [start["x"], start_aisle], [a["x"] + 15, start_aisle],
              [a["x"] + 15, hallway], [b["x"] + 15, hallway],
              [b["x"] + 15, target_aisle], [target["x"], target_aisle], [target["x"], target["y"]]]
    return [p for i, p in enumerate(points) if not i or p != points[i - 1]]


def _walk(origin, target, now, old, job, hallway):
    if old and old.get("job") == job:
        return old.get("walk")
    if abs(origin[0] - target[0]) + abs(origin[1] - target[1]) < 1:
        return None
    return {"start": now, "end": now + 2,
            "points": [origin, [origin[0], hallway], [target[0], hallway], target]}


def motion_point(motion, minute):
    points = motion["points"]
    duration = max(.01, motion["end"] - motion["start"])
    progress = max(0, min(1, (minute - motion["start"]) / duration))
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    distance = sum(lengths) * progress
    for a, b, length in zip(points, points[1:], lengths):
        if distance <= length and length:
            f = distance / length
            return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]
        distance -= length
    return list(points[-1])


def update_scene(s):
    """Called inside the existing atomic state transaction, after predictions/team."""
    now, team = s["minute"], s.get("automation", {})
    active = bool(team.get("enabled") and team.get("eligible"))
    beds = {b["id"]: b for b in s["beds"]}
    recent_exits = sorted((p for p in s["patients"] if p.get("status") == "discharged"
                           and p.get("discharge_minute", -999) >= now - 30), key=lambda p: p["discharge_minute"], reverse=True)[:8]
    exits = {p["id"] for p in recent_exits}
    patients = [{**p, "prediction": s["predictions"][p["id"]]} for p in s["patients"]
                if s["predictions"][p["id"]]["features"]["phase"] not in ("PENDING", "DISCHARGED", "DECEASED", "TRANSFERRED") or p["id"] in exits]
    fingerprint = [sorted(beds), s["source"], "layout-v6"]
    memory = s.setdefault("scene_memory", {})
    if memory.get("fingerprint") != fingerprint:
        memory.clear()
        memory.update(fingerprint=fingerprint, slots={}, staff={})

    jobs, needed = [], {z: set() for z in ZONE_LABELS}
    origins, destinations = {}, {}
    reservations = {r["patient_id"]: r for r in s["reservations"] if r["status"] == "confirmed"}
    workflows = team.get("workflows", {}) if active else {}
    for p in patients:
        pid, zone = p["id"], _zone(p, beds)
        origins[pid] = zone
        if zone not in ("SICU", "CCU") or p["location"] not in beds:
            needed[zone].add(pid)
        w = workflows.get(pid, {})
        if zone == "ENTRY" and not p.get("admission_wait") and p.get("admission_handoff_due"):
            due = p["admission_handoff_due"]
            destinations[pid] = {"zone": "PREOP", "start": due - 10, "end": due,
                                 "label": "입원 인계·수술 전 이동", "role": "ward"}
            needed["PREOP"].add(pid)
        elif w.get("stage") == "hospital_discharge_handoff" and w.get("hospital_exit_due"):
            due = w["hospital_exit_due"]
            destinations[pid] = {"zone": "EXIT", "start": due - 15, "end": due,
                                 "label": "퇴원 간호 인계·출구 이동", "role": "ward"}
            needed["EXIT"].add(pid)
        if w.get("stage") == "preparing" and pid in reservations:
            jobs.append({"key": "prep:" + pid + ":" + reservations[pid]["bed_id"],
                         "role": "charge", "patient_id": pid, "target_bed": reservations[pid]["bed_id"],
                         "start": w["prep_due"] - s["policy"]["prepare_minutes"], "label": "병상·장비 준비"})
        if w.get("stage") == "transporting" and w.get("transfer_due") and pid in reservations:
            r = reservations[pid]
            destinations[pid] = {"zone": beds[r["bed_id"]]["unit"], "bed_id": r["bed_id"],
                                 "start": w["transfer_due"] - s["policy"]["transfer_minutes"] - 2,
                                 "end": w["transfer_due"], "label": "ICU 이송·인계", "role": "transport"}
        elif w.get("stage") == "ward_handoff":
            due = w.get("discharge_due") if zone in ("SICU", "CCU") else w.get("ward_due")
            if due is not None:
                destinations[pid] = {"zone": "WARD", "start": due - 5, "end": due,
                                     "label": "병동 이동·인계", "role": "ward"}
                needed["WARD"].add(pid)

    # Stable slots prevent unrelated patients jumping when another patient leaves.
    for zone, ids in needed.items():
        slots = memory["slots"].setdefault(zone, {})
        for pid in list(slots):
            if pid not in ids:
                del slots[pid]
        used = set(slots.values())
        for pid in sorted(ids):
            if pid not in slots:
                slot = next(n for n in range(len(ids) + 1) if n not in used)
                slots[pid] = slot
                used.add(slot)
    cols = {"PREOP": 3, "OR": 4, "PACU": 5, "SICU": 4, "CCU": 2, "WARD": 12, "ENTRY": 4, "EXIT": 12}
    counts = {z: max(memory["slots"][z].values(), default=-1) + 1 for z in ZONE_LABELS}
    counts["SICU"] = sum(b["unit"] == "SICU" for b in beds.values())
    counts["CCU"] = sum(b["unit"] == "CCU" for b in beds.values())
    for zone in ("SICU", "CCU"):
        counts[zone] += len(needed[zone])
    top_h = max(286, math.ceil(counts["OR"] / cols["OR"]) * 106 + 76,
                math.ceil(counts["PREOP"] / cols["PREOP"]) * 94 + 76,
                math.ceil(counts["PACU"] / cols["PACU"]) * 94 + 76)
    hall_y, bottom_y = top_h + 78, top_h + 152
    lower_h = max(384, math.ceil(counts["SICU"] / cols["SICU"]) * 148 + 76,
                  math.ceil(counts["CCU"] / cols["CCU"]) * 148 + 76,
                  math.ceil(counts["WARD"] / cols["WARD"]) * 94 + 96)
    exit_y = bottom_y + lower_h + 24
    exit_h = max(176, math.ceil(counts["EXIT"] / cols["EXIT"]) * 94 + 76,
                 math.ceil(counts["ENTRY"] / cols["ENTRY"]) * 94 + 76)
    specs = {"PREOP": (24, 30, 332, top_h), "OR": (380, 30, 1052, top_h),
             "PACU": (1456, 30, 520, top_h), "SICU": (24, bottom_y, 456, lower_h),
             "CCU": (504, bottom_y, 248, lower_h), "WARD": (776, bottom_y, 1200, lower_h),
             "ENTRY": (24, exit_y, 456, exit_h), "EXIT": (504, exit_y, 1472, exit_h)}
    zones = {z: {"id": z, "label": ZONE_LABELS[z], "x": x, "y": y, "width": w, "height": h,
                  "count": sum(bool(b["occupant_id"]) for b in beds.values() if b["unit"] == z) + len(needed[z]) if z in ("SICU", "CCU") else sum(origins[p["id"]] == z for p in patients), "columns": cols[z]}
             for z, (x, y, w, h) in specs.items()}

    def slot_position(zone, slot):
        z = zones[zone]
        row, col = divmod(slot, cols[zone])
        pitch = 148 if zone in ("SICU", "CCU") else 106 if zone == "OR" else 94
        return {"zone": zone, "x": round(z["x"] + 28 + (col + .5) * (z["width"] - 46) / cols[zone], 2),
                "y": z["y"] + (130 if zone in ("SICU", "CCU") else 104) + row * pitch}

    bed_positions = {}
    for zone in ("SICU", "CCU"):
        for i, bed in enumerate(sorted((b for b in beds.values() if b["unit"] == zone), key=lambda b: b["id"])):
            bed_positions[bed["id"]] = slot_position(zone, i)
    patient_entities = []
    for p in patients:
        pid, zone = p["id"], origins[p["id"]]
        home = bed_positions.get(p["location"]) if zone in ("SICU", "CCU") else slot_position(zone, memory["slots"][zone][pid])
        if zone in ("SICU", "CCU") and home is None:
            offset = sum(b["unit"] == zone for b in beds.values())
            home = slot_position(zone, offset + memory["slots"][zone][pid])
        # A malformed external ICU location is still represented without losing a patient.
        home = home or slot_position("WARD", 0)
        w, motion = workflows.get(pid, {}), None
        dest = destinations.get(pid)
        if dest:
            target = bed_positions[dest["bed_id"]] if "bed_id" in dest else slot_position(dest["zone"], memory["slots"][dest["zone"]][pid])
            motion = {"start": dest["start"] + 1, "end": dest["end"], "points": _route(home, target, zones, hall_y),
                      "origin": p["location"], "destination": dest.get("bed_id", dest["zone"]), "label": dest["label"],
                      "pickup_start": dest["start"], "awaiting_confirmation": now >= dest["end"]}
            jobs.append({"key": "transfer:" + pid + ":" + str(dest["start"]), "role": dest["role"],
                         "patient_id": pid, "start": dest["start"], "label": dest["label"], "motion": motion, "home": home})
        patient_entities.append({"id": pid, "zone": zone, "location": p["location"], "home": home, "motion": motion,
                                 "phase": p["prediction"]["features"]["phase"], "risk": p["prediction"]["need_score"],
                                 "quality_hold": w.get("stage") == "quality_hold", "label": w.get("label", "경과 관찰")})

    roster = []
    for role, prefix, n in (("charge", "P", team.get("resources", {}).get("prep_slots", 2)),
                            ("transport", "T", team.get("resources", {}).get("transport_slots", 2)),
                            ("ward", "W", 6), ("anesthesia", "A", 1), ("intensivist", "I", 1), ("surgeon", "G", 1)):
        roster.extend({"id": prefix + str(i + 1), "role": role, "kind": "doctor" if role in ("anesthesia", "intensivist", "surgeon") else "nurse",
                       "name": ROLE_NAMES[role] + (f" 간호사 {i + 1}" if role in ("charge", "transport", "ward") else " 의사")} for i in range(n))
    # Keep the same nurse assigned for the full preparation/escort job.
    current_keys = {j["key"] for j in jobs}
    assignment = memory.setdefault("assignments", {})
    for key in list(assignment):
        if key not in current_keys:
            del assignment[key]
    for job in sorted(jobs, key=lambda j: (j["start"], j["key"])):
        if job["key"] not in assignment:
            available = [r["id"] for r in roster if r["role"] == job["role"] and r["id"] not in assignment.values()]
            if available:
                assignment[job["key"]] = available[0]
    by_staff = {assignment[j["key"]]: j for j in jobs if j["key"] in assignment}
    public_staff = []
    for index, person in enumerate(roster):
        sid, role = person["id"], person["role"]
        desk_index = index if index < 4 else index - 4
        base = [640 + desk_index * 70, hall_y + 13]
        if role == "ward":
            base = [1460 + (index % 6) * 72, hall_y + 28]
        previous = memory["staff"].get(sid, {})
        job = by_staff.get(sid) if active else None
        pid, motion, status = None, None, "대기" if active else "자동 진행 대기"
        target, job_key = base, "idle"
        if job:
            pid, status, job_key = job["patient_id"], job["label"], job["key"]
            if job.get("motion"):
                # Nurse walks to the patient during the first minute of SBAR handoff.
                origin = previous.get("pickup_origin", previous.get("position", base)) if previous.get("job") == job_key else previous.get("position", base)
                pickup = {"start": job["start"], "end": job["motion"]["start"],
                          "points": [origin, [origin[0], hall_y], [job["home"]["x"] + 35, hall_y],
                                         [job["home"]["x"] + 55, job["home"]["y"] + 10]]}
                motion = {**job["motion"], "offset": [55, 10], "pickup": pickup}
                target = [job["home"]["x"] + 55, job["home"]["y"] + 10]
            else:
                b = bed_positions[job["target_bed"]]
                target = [b["x"] + 46, b["y"] - 20]
        elif active and person["kind"] == "doctor":
            wanted = ("WARD",) if role == "surgeon" else ("SICU", "CCU") if role == "intensivist" else ("PREOP", "OR", "PACU")
            candidates = [p for p in patients if origins[p["id"]] in wanted]
            recent = next((e for e in reversed(team.get("log", [])) if e["role"] == role and any(p["id"] == e["patient_id"] for p in candidates)), None)
            focus = next((p for p in candidates if recent and p["id"] == recent["patient_id"]), None)
            focus = focus or max(candidates, key=lambda p: p["prediction"]["need_score"] or 0, default=None)
            if focus:
                pid = focus["id"]
                home = next(p["home"] for p in patient_entities if p["id"] == pid)
                target, job_key, status = [home["x"] - 36, home["y"] - 7], "round:" + pid, "평가·회진"
        old_position = previous.get("position", base)
        walk = _walk(old_position, target, now, previous, job_key, hall_y) if not motion else None
        motion = motion or walk
        picking_up = motion and motion.get("pickup") and now < motion["start"]
        position = motion_point(motion["pickup"] if picking_up else motion, now) if motion else target
        if motion and motion.get("offset") and not picking_up:
            position = [position[0] + motion["offset"][0], position[1] + motion["offset"][1]]
        memory["staff"][sid] = {"job": job_key, "position": position, "walk": walk,
                                "pickup_origin": motion["pickup"]["points"][0] if motion and motion.get("pickup") else None}
        public_staff.append({**person, "patient_id": pid, "status": status, "position": position,
                             "home": target, "motion": motion, "on_shift": active,
                             "bed_id": job.get("target_bed") if job else None,
                             "destination": job.get("target_bed") or job.get("motion", {}).get("destination") if job else None})

    bed_entities = []
    for bed in beds.values():
        rs = [r for r in s["reservations"] if r["bed_id"] == bed["id"] and r["status"] == "confirmed"]
        status = "occupied" if bed["occupant_id"] else "closed" if not bed["enabled"] else "cleaning" if bed["available_minute"] > now else "reserved" if rs else "available"
        bed_entities.append({"id": bed["id"], "unit": bed["unit"], "position": bed_positions[bed["id"]],
                             "status": status, "occupant_id": bed["occupant_id"],
                             "external_patient": bool(bed["occupant_id"] and bed["occupant_id"] not in origins),
                             "reserved_patient_ids": [r["patient_id"] for r in rs],
                             "available_minute": bed["available_minute"], "closed_reason": bed["closed_reason"]})
    s["scene"] = {"schema_version": "1.1", "as_of_minute": now, "width": WIDTH, "height": exit_y + exit_h + 30,
                  "hallway_y": hall_y, "zones": list(zones.values()), "patients": patient_entities,
                  "staff": public_staff if s["source"] == "synthetic" else [], "beds": bed_entities, "active": active,
                  "mode": "synthetic_workflow" if active else "observed_locations",
                  "unassigned_handoffs": sum(j["key"] not in assignment for j in jobs),
                  "description": "가상 병원 배치 · 관측된 환자 위치와 자동 의료진 단계의 이동 시뮬레이션"}


def public_scene(s):
    return copy.deepcopy(s["scene"])
