"""Deterministic, entirely synthetic perioperative trajectories.

Future observations are kept in a private scenario store, NEVER model input.
All minutes share an explicitly synthetic hospital calendar.
"""
import math
import random
from .capacity import WARD_BEDS, ICU_UNITS, BED_REFERENCE
from .version import RUNTIME_VERSION

BASE_TIME = "2026-10-16T08:30:00+09:00"


def make_small_demo(seed=26):
    specs = [
        ("001", "위절제술", "GS", "OR-01", 67, "M", 3, -55, 70, "hypotension", ["고혈압", "만성 신장질환"], False, "SICU"),
        ("002", "간절제술", "GS", "OR-02", 58, "F", 3, -90, 90, "bleeding", ["간경변", "빈혈"], False, "SICU"),
        ("003", "척추 유합술", "OS", "OR-03", 72, "M", 3, -95, 55, "moderate", ["관상동맥질환", "고혈압"], False, "SICU"),
        ("004", "응급 췌십이지장절제술", "GS", "OR-04", 73, "F", 4, -80, 40, "shock", ["당뇨", "만성 신장질환"], False, "SICU"),
        ("005", "복강경 대장절제술", "GS", "OR-05", 45, "F", 2, -20, 100, "stable", [], False, "SICU"),
        ("006", "관상동맥 우회술", "CS", "PREOP-01", 69, "M", 4, 20, 200, "cardiac", ["심부전", "당뇨"], True, "CCU"),
        ("007", "대동맥 치환술", "CS", "OR-06", 66, "M", 4, -130, 20, "cardiac", ["고혈압"], True, "CCU"),
        ("008", "폐엽절제술", "TS", "PACU-01", 59, "F", 3, -190, -25, "hypoxia", ["만성 폐질환"], False, "SICU"),
        ("009", "복강경 담낭절제술", "GS", "PACU-02", 38, "M", 1, -115, -10, "stable", [], False, "SICU"),
        ("010", "심장판막 치환술", "CS", "CCU-01", 74, "F", 4, -330, -160, "recovering", ["심부전", "심방세동"], True, "CCU"),
        ("011", "응급 장천공 수술", "GS", "SICU-01", 76, "M", 4, -400, -220, "shock", ["만성 신장질환", "당뇨"], False, "SICU"),
        ("012", "유방 부분절제술", "BS", "PREOP-02", 52, "F", 2, 80, 160, "stable", [], False, "SICU"),
        ("013", "신장 이식술", "URO", "OR-07", 54, "M", 3, -60, 65, "moderate", ["말기 신장질환"], False, "SICU"),
        ("014", "외상 골반 고정술", "OS", "SICU-02", 49, "M", 4, -360, -150, "recovering", ["다발성 외상"], False, "SICU"),
        ("015", "뇌종양 절제술", "NS", "PREOP-03", 61, "F", 3, 45, 175, "moderate", ["고혈압"], False, "SICU"),
        ("016", "로봇 전립선절제술", "URO", "WARD-01", 68, "M", 2, -480, -350, "stable", ["고혈압"], False, "SICU"),
    ]
    rng = random.Random(seed)
    patients, trajectories = [], {}
    for idx, spec in enumerate(specs):
        num, surgery, dept, location, age, sex, asa, start, end, course, conditions, planned, unit = spec
        pid = "DEMO-" + num
        emergency = course == "shock"
        base_hb = 9.3 if course in ("bleeding", "shock") else 12.6
        pre = {"hemoglobin": base_hb, "creatinine": 1.8 if "신장" in str(conditions) else 0.9,
               "platelets": 112 if course == "bleeding" else 215, "albumin": 2.8 if emergency else 3.8,
               "lactate": 2.7 if emergency else 1.2}
        patients.append({
            "id": pid, "subject_id": "SUB-" + num, "admission_id": "ADM-" + num, "operation_id": "OP-" + num,
            "name": "데모 " + num, "age": age, "sex": sex, "asa": asa,
            "surgery": surgery, "department": dept, "location": location,
            "admission_minute": -1440 if not emergency else min(-240, start - 60),
            "operation_start_minute": start, "estimated_end_minute": end,
            "actual_end_minute": end if end <= 0 else None,
            "planned_icu": planned, "preferred_unit": unit, "emergency": emergency,
            "conditions": conditions, "preop_labs": pre, "preop_labs_minute": min(-120, start - 10),
            "pre_admission": [{"minute": -43200, "type": "병력", "label": ", ".join(conditions) or "특이 병력 없음"},
                              {"minute": -2880, "type": "외래 검사", "label": "Hb %.1f g/dL · Cr %.1f mg/dL" % (base_hb, pre["creatinine"])}],
            "observations": [], "treatments": [], "source": "synthetic", "course": course,
            "capabilities_required": ["ventilator"] + (["crrt"] if pid == "DEMO-011" else []),
        })
        obs, treatments = [], []
        for minute in range(max(-300, start - 30), 601, 5):
            x = max(0, minute - start)
            noise = math.sin((minute + idx * 13) / 12) * 2 + rng.uniform(-1, 1)
            mapv, hr, spo2, lactate, norepi = 79 + noise, 77 + noise, 98, 1.2, 0.0
            hb, urine = base_hb, 0.7
            if course == "hypotension" and minute >= -30:
                severity = max(0, 1 - max(0, minute - 20) / 130)
                mapv, hr = 76 - 21 * severity + noise, 80 + 28 * severity + noise
                norepi, lactate, urine = 0.11 * severity, 1.3 + 1.8 * severity, 0.35
            elif course == "bleeding" and minute >= 15:
                severity = min(1, (minute - 15) / 40) * max(0.1, 1 - max(0, minute - 90) / 190)
                mapv, hr = 78 - 25 * severity + noise, 80 + 42 * severity
                hb, lactate, norepi, urine = base_hb - 2.1 * severity, 1.3 + 3.8 * severity, 0.18 * severity, 0.2
            elif course == "shock":
                severity = max(0.2, 1 - max(0, minute - 90) / 360)
                mapv, hr, spo2 = 75 - 16 * severity + noise, 81 + 32 * severity, 95
                norepi, lactate, urine = 0.21 * severity, 1.4 + 3.8 * severity, 0.2 + (1 - severity) * 0.5
            elif course == "moderate":
                mapv, hr, norepi, lactate = 69 + noise, 86 + noise, 0.025 if start <= minute < end else 0, 1.8
            elif course == "cardiac":
                mapv, hr, norepi, lactate = 68 + noise, 92 + noise, 0.08 if minute >= start else 0, 2.1
            elif course == "hypoxia" and minute >= end:
                spo2, hr, lactate = min(97, 89 + max(0, minute - 20) / 18), 102 + noise, 1.9
            elif course == "recovering":
                mapv, hr, norepi = 78 + noise, 84 + noise, max(0, 0.05 - (minute + 60) * 0.0002)
                lactate = max(1.1, 2.2 - (minute + 30) / 150)
            in_or = start <= minute < end
            ventilation = in_or or (course in ("shock", "cardiac") and end <= minute < end + 150)
            o = {"minute": minute, "map": round(mapv, 1), "hr": round(hr, 1), "spo2": round(spo2, 1),
                 "lactate": round(lactate, 2), "hemoglobin": round(hb, 1), "norepi": round(norepi, 3),
                 "urine_ml_kg_h": round(urine, 2), "ventilation": ventilation,
                 "crrt": pid == "DEMO-011", "source": "synthetic-monitor"}
            obs.append(o)
            if minute % 30 == 0 and minute >= start and norepi > 0:
                treatments.append({"minute": minute, "kind": "승압제", "label": "Norepinephrine", "dose": round(norepi, 3), "unit": "µg/kg/min"})
            if course == "bleeding" and minute == 65:
                treatments.append({"minute": minute, "kind": "수혈", "label": "농축적혈구", "dose": 2, "unit": "unit"})
        patient = patients[-1]
        patient["observations"] = [o for o in obs if o["minute"] <= 0]
        patient["treatments"] = [o for o in treatments if o["minute"] <= 0]
        trajectories[pid] = {"observations": obs, "treatments": treatments,
                             "actual_end_minute": end,
                             "truth_icu": course in ("shock", "cardiac", "bleeding", "hypoxia", "hypotension"),
                             "truth_icu_hours": {"shock": 72, "cardiac": 38, "bleeding": 46, "hypoxia": 20, "hypotension": 26}.get(course, 0)}
    beds = []
    for unit, count in ICU_UNITS:
        for n in range(1, count + 1):
            bid = f"{unit}-{n:02d}"
            occupant = {"SICU-01": "DEMO-011", "SICU-02": "DEMO-014", "CCU-01": "DEMO-010", "SICU-05": "비수술 환자 A"}.get(bid)
            beds.append({"id": bid, "unit": unit, "capabilities": ["ventilator"] + (["crrt"] if n <= 4 else []),
                         "enabled": bid not in ("SICU-08", "CCU-04"), "occupant_id": occupant,
                         "available_minute": {"SICU-01": 480, "SICU-02": 150, "CCU-01": 90, "SICU-05": 110, "SICU-04": 20}.get(bid, 0),
                         "available_basis": "모의 퇴실 예상" if occupant else ("청소 완료 예정" if bid == "SICU-04" else "현재 가용"),
                         "closed_reason": "인력 부족" if bid == "SICU-08" else ("정비 중" if bid == "CCU-04" else "")})
    return {"schema_version": "1.0", "base_time": BASE_TIME, "minute": 0, "seed": seed,
            "running": False, "speed": 5, "source": "synthetic", "clock_kind": "synthetic_shared",
            "patients": patients, "trajectories": trajectories, "beds": beds,
            "reservations": [{"id": "RES-DEMO-006", "patient_id": "DEMO-006", "bed_id": "CCU-02", "start": 205,
                              "end": 3085, "status": "confirmed", "created_minute": -60, "reason": "예정 심장수술 ICU", "actor": "초기 시나리오"}],
            "policy": {"icu_threshold": 0.65, "prepare_minutes": 30, "transfer_minutes": 5,
                       "release_threshold": 0.3, "release_stability_minutes": 20,
                       "stale_minutes": 15, "confidence_min": 0.65, "cleanup_minutes": 20,
                       "delay_weight": 5, "idle_weight": 1, "change_weight": 20},
            "events": [], "acknowledged": {}, "notes": [], "prediction_history": {}, "active_scenarios": {},
            "model_backend": "demo", "revision": 1}


# These are illustrative recovery profiles, not estimates of a real dataset's
# stay distribution. The real-data importer never synthesizes missing recovery.
PROFILES = [
    ("복강경 담낭절제술", "GS", 1, "minor", "stable", False, "SICU", 75),
    ("유방 부분절제술", "BS", 2, "minor", "stable", False, "SICU", 95),
    ("서혜부 탈장 교정술", "GS", 1, "minor", "stable", False, "SICU", 70),
    ("로봇 전립선절제술", "URO", 2, "standard", "stable", False, "SICU", 170),
    ("복강경 대장절제술", "GS", 2, "standard", "stable", False, "SICU", 150),
    ("척추 유합술", "OS", 3, "major", "moderate", False, "SICU", 200),
    ("위절제술", "GS", 3, "major", "hypotension", False, "SICU", 210),
    ("폐엽절제술", "TS", 3, "major", "hypoxia", False, "SICU", 160),
    ("관상동맥 우회술", "CS", 4, "complex", "cardiac", True, "CCU", 240),
    ("응급 장천공 수술", "GS", 4, "complex", "shock", False, "SICU", 180),
]


def make_patient(number, profile, admission, start, seed):
    surgery, dept, asa, group, course, planned, unit, duration = profile
    pid = f"DEMO-{number:03d}"
    age = 28 + (number * 7 + seed) % 53
    conditions = [] if asa == 1 else ["고혈압"] if asa == 2 else ["고혈압", "당뇨"]
    p = {"id": pid, "subject_id": f"SUB-{number:03d}", "admission_id": f"ADM-{number:03d}",
         "operation_id": f"OP-{number:03d}", "name": f"모의 환자 {number:03d}", "age": age,
         "sex": "F" if number % 2 else "M", "asa": asa, "surgery": surgery, "department": dept,
         "location": "ENTRY" if admission >= 0 else "WARD", "admission_minute": admission,
         "operation_start_minute": start, "scheduled_operation_start_minute": start,
         "estimated_end_minute": start + duration + 15, "actual_end_minute": start + duration if start + duration <= 0 else None,
         "planned_icu": planned, "preferred_unit": unit, "emergency": course == "shock", "conditions": conditions,
         "procedure_group": group, "preop_labs": {"hemoglobin": 12.4, "creatinine": 1.1, "lactate": 1.2},
         "preop_labs_minute": admission - 60, "pre_admission": [{"minute": admission - 2880,
             "type": "외래 평가", "label": ", ".join(conditions) or "특이 병력 없음"}],
         "observations": [], "treatments": [], "source": "synthetic", "course": course,
         "capabilities_required": ["ventilator"], "discharge_minute": None, "status": "active"}
    trajectory = {"observations": [], "treatments": [], "actual_end_minute": start + duration,
                  "duration_minutes": duration, "course": course, "generator": "recovery-v5",
                  "truth_icu": course in ("shock", "cardiac", "hypoxia", "hypotension"),
                  "truth_icu_hours": {"shock": 72, "cardiac": 38, "hypoxia": 20, "hypotension": 26}.get(course, 0)}
    return p, trajectory


def make_demo(seed=26, initial_patients=60, days=7, daily_arrivals=24):
    """A mixed census at time zero, followed by daily scheduled admissions.

    Future arrivals/physiology stay private. No final stay is copied into a
    prediction feature; simulated clinicians decide from observed milestones.
    """
    from .hospital import synthetic_observation, ensure_hospital, claim_ward_bed
    s = make_small_demo(seed)
    s.update(runtime_version=RUNTIME_VERSION, horizon_minutes=days * 1440, speed=15,
             simulation_config={"initial_patients": initial_patients, "days": days,
                                "daily_arrivals": daily_arrivals, "ward_beds": WARD_BEDS,
                                "icu_beds": sum(n for _, n in ICU_UNITS),
                                "bed_reference": dict(BED_REFERENCE)}, arrival_queue=[], replay_events=[])
    for p in s["patients"]:
        p.update(status="active", discharge_minute=None,
                 procedure_group="minor" if p["id"] in ("DEMO-009", "DEMO-012") else "complex" if p["asa"] >= 4 else "major")
        s["trajectories"][p["id"]]["course"] = p["course"]
        s["trajectories"][p["id"]]["generator"] = "legacy-extended"
    for n in range(17, initial_patients + 1):
        profile = PROFILES[(n - 17) % 8]
        group = profile[3]
        recovery_days = {"minor": .8, "standard": 3, "major": 5, "complex": 8}[group]
        # Six near-discharge carryover patients make the first operating day
        # demonstrate discharge without shortening every new admission's stay.
        if n <= 22:
            profile = PROFILES[(n - 17) % 3]
            age_of_operation = 24 * 60 + (n - 17) * 30
        else:
            age_of_operation = int((recovery_days * .25 + (n % 6) * .2) * 1440)
        start = -age_of_operation - profile[-1]
        p, tr = make_patient(n, profile, start - 1440, start, seed)
        s["patients"].append(p)
        s["trajectories"][p["id"]] = tr
        p["observations"] = [synthetic_observation(p, t, tr) for t in range(-360, 1, 60)]
    # The hospital's physical bed mix is an explicit scenario assumption.
    # Imported datasets retain their supplied inventory without this scaling.
    ensure_hospital(s)
    for p in s["patients"]:
        if not p["location"].startswith(("SICU", "CCU", "ICU")):
            claim_ward_bed(s, p)
    number = initial_patients
    # 18 elective arrivals during daytime and six urgent/night arrivals daily.
    for day in range(days):
        for i in range(daily_arrivals):
            number += 1
            minute = day * 1440 + (20 + i * 30 if i < 18 else 690 + (i - 18) * 110)
            profile = PROFILES[(number + seed) % len(PROFILES)]
            start = minute + (35 if profile[4] == "shock" else 90 + (i % 3) * 25)
            p, tr = make_patient(number, profile, minute, start, seed)
            s["arrival_queue"].append({"minute": minute, "patient": p, "trajectory": tr})
    s["hospital"]["initial_census"] = initial_patients
    return s
