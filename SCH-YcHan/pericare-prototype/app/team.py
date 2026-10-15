"""Synthetic clinical-team workflow. Decisions only use observations already seen.

This is a transparent rule simulation, not autonomous care for imported patients.
Future trajectories belong to the scenario generator and are never read here.
"""
import copy

ROLES = {
    "anesthesia": {"name": "마취과 당직의", "short": "의사", "job": "수술·회복 평가", "color": "blue"},
    "intensivist": {"name": "ICU 전담의", "short": "의사", "job": "집중관리·전실 판단", "color": "purple"},
    "charge": {"name": "ICU 책임간호사", "short": "간호사", "job": "병상·장비 준비", "color": "green"},
    "transport": {"name": "이송 간호사", "short": "간호사", "job": "이송·SBAR 인계", "color": "amber"},
    "ward": {"name": "병동 간호사", "short": "간호사", "job": "병동 인수·회복 관찰", "color": "blue"},
    "surgeon": {"name": "담당 외과의", "short": "의사", "job": "회복·퇴원 판단", "color": "blue"},
}


def ensure_team(s):
    eligible = s.get("source") == "synthetic" and s.get("clock_kind") == "synthetic_shared"
    team = s.setdefault("automation", {})
    team.setdefault("enabled", eligible)
    team["eligible"] = eligible
    if not eligible:
        team["enabled"] = False
    team.setdefault("log", [])
    team.setdefault("workflows", {})
    team.setdefault("sequence", 0)
    team.setdefault("counters", {"orders": 0, "reservations": 0, "admissions": 0,
                                 "ward_transfers": 0, "handoffs": 0, "quality_checks": 0})
    team.setdefault("resources", {"prep_slots": 2, "transport_slots": 2})
    team["resources"].setdefault("ward_slots", 6)
    team["counters"].setdefault("hospital_discharges", 0)
    team.setdefault("started", False)
    return team


def emit(s, role, pid, title, detail, kind="assessment", severity="info", evidence=None):
    team = ensure_team(s)
    team["sequence"] += 1
    event = {"id": team["sequence"], "minute": s["minute"], "role": role,
             "actor": ROLES[role]["name"], "patient_id": pid, "title": title,
             "detail": detail, "kind": kind, "severity": severity,
             "evidence": copy.deepcopy(evidence or {})}
    team["log"].append(event)
    team["log"] = team["log"][-600:]
    s.setdefault("_audit_buffer", []).append({"minute": s["minute"], "action": "team_" + kind,
        "actor": event["actor"], "payload": {k: v for k, v in event.items() if k not in ("id", "actor", "minute")}})
    return event


def set_stage(w, stage, label, owner, detail, now):
    w.update(stage=stage, label=label, owner=owner, detail=detail, updated_minute=now)


def brief(pr):
    f, o = pr["features"], pr["features"]["latest"]
    return {"as_of_minute": f["minute"], "risk": pr["need_score"],
            "icu_probability": pr["icu_probability"], "map": o.get("map"),
            "spo2": o.get("spo2"), "norepi": o.get("norepi"), "lactate": o.get("lactate"),
            "observation_minute": o.get("minute"), "elapsed_postop_hours": f.get("elapsed_postop_hours"),
            "recovery": {k: o.get(k) for k in ("oral_intake", "ambulating", "pain_score", "wound_ok", "discharge_plan_confirmed")}}


def stable_observation(o, strict=False):
    limits = {"map": (65, 200), "hr": (40, 105 if strict else 110),
              "spo2": (95 if strict else 94, 100), "lactate": (0, 2 if strict else 2.5),
              "norepi": (0, .015 if strict else .03)}
    return (all(isinstance(o.get(k), (int, float)) and lo <= o[k] <= hi for k, (lo, hi) in limits.items())
            and o.get("ventilation") is False and o.get("crrt") is not True and not o.get("artifact"))


def stable_window(patient, now, minutes=20, strict=False):
    obs = sorted((o for o in patient["observations"] if now - minutes <= o["minute"] <= now), key=lambda o:o["minute"])
    return (len(obs) >= 4 and obs[0]["minute"] <= now - minutes + 5
            and all(stable_observation(o, strict) for o in obs))


def run_team(engine, s):
    from .engine import active_reservation, recommend, bed_fits, AppError
    from .model import phase
    team = ensure_team(s)
    if not team["enabled"] or not team["eligible"]:
        return
    now = s["minute"]
    if not team["started"]:
        emit(s, "charge", "", "가상 의료진 근무 시작", "수술실·회복실·ICU 환자를 인계받았습니다. 의사 평가와 간호 준비에 따라 시나리오를 진행합니다.", "shift")
        team["started"] = True

    workflows = team["workflows"]
    def workload(stage):
        return sum(w.get("stage") == stage for w in workflows.values())
    patients = sorted(s["patients"], key=lambda p: -(s["predictions"][p["id"]]["need_score"] or 0))
    for p in patients:
        pid, pr = p["id"], s["predictions"][p["id"]]
        f, o, current = pr["features"], pr["features"]["latest"], phase(p, now)
        w = workflows.setdefault(pid, {"stage": "observing", "label": "경과 인계", "owner": "anesthesia",
                                      "detail": "현재 관측을 확인하고 있습니다.", "updated_minute": now})
        evidence = brief(pr)
        if current in ("PENDING", "DISCHARGED", "DECEASED", "TRANSFERRED"):
            set_stage(w, "completed", "병원 퇴원 완료" if current == "DISCHARGED" else "입원 경과 종료", "ward", "현재 진료·예약 대상에서 제외하고 기록을 보관합니다.", now)
            continue
        if current == "ADMITTING":
            set_stage(w, "hospital_admission", "입원 접수·인계", "ward",
                      "병동 가용 병상 확인 중" if p.get("admission_wait") else "간호사가 입원 정보와 수술 전 준비를 인계합니다.", now)
            continue
        quality_bad = (pr["mode"] in ("unavailable", "unsupported", "remote_partial") or f["stale"] or f["quality_issues"]
                       or pr.get("confidence") is None or pr["confidence"] < s["policy"]["confidence_min"])
        if quality_bad:
            issue = pr.get("model_error") or ("ICU24 입실 확률만 제공 · 가상 의료진 자동 판단 보류" if pr["mode"] == "remote_partial" else None) or " · ".join(f["quality_issues"]) or "예측 신뢰 신호 부족"
            if w.get("quality_reason") != issue:
                emit(s, "charge", pid, "관측 재확인 요청", issue + ". 새 관측을 확인할 때까지 이동 결정을 보류합니다.", "quality", "warning", evidence)
                team["counters"]["quality_checks"] += 1
            w["quality_reason"] = issue
            set_stage(w, "quality_hold", "관측 재확인", "charge", issue, now)
            # Transport is restarted only after a new assessment and valid observations.
            w.pop("transfer_due", None)
            w.pop("hospital_exit_due", None)
            for a in s["alerts"]:
                if a["patient_id"] == pid and not a["acknowledged"]:
                    a.update(acknowledged=True, acknowledged_by=ROLES["charge"]["name"], acknowledged_minute=now)
            continue
        if w.pop("quality_reason", None):
            emit(s, "charge", pid, "관측 재확인 완료", "새 생체신호와 예측 연결을 확인했습니다. 의료진 평가를 재개합니다.", "quality_resolved", evidence=evidence)
            set_stage(w, "observing", "재평가 중", "anesthesia", "관측 회복 후 이동 계획을 재확인합니다.", now)
            w["review_due"] = now + 3
            w.pop("doctor_order", None)

        acute = []
        if isinstance(o.get("map"), (int, float)) and o["map"] < 65:
            acute.append(f"MAP {o['map']:g} mmHg · 순환·승압제 기록 확인")
        if isinstance(o.get("spo2"), (int, float)) and o["spo2"] < 94:
            acute.append(f"SpO₂ {o['spo2']:g}% · 산소화·호흡 지원 확인")
        if acute and w.get("last_escalation", -30) <= now - 30:
            emit(s, "intensivist" if current == "ICU" else "anesthesia", pid,
                 "현재 불안정 관측 · 의료진 재평가", " / ".join(acute) + ". 지원 필요성을 재평가하고 간호팀에 인계했습니다.",
                 "escalation", "warning", evidence)
            w["last_escalation"] = now
        for treatment in sorted(p.get("treatments", []), key=lambda t:t["minute"]):
            if w.get("last_treatment_minute", now - 6) < treatment["minute"] <= now:
                emit(s, "charge" if current == "ICU" else "anesthesia", pid, "처치 기록 확인 · 경과 인계",
                     str(treatment.get("label") or treatment.get("kind") or "처치") + " · 새 관측과 지원 필요성 변화를 함께 확인합니다.", "treatment", evidence=evidence)
                w["last_treatment_minute"] = treatment["minute"]

        if current == "ICU":
            w.setdefault("icu_since", now)  # Admission time or first observed ICU round.
            if w.get("stage") not in ("icu_monitoring", "discharge_review", "ward_handoff"):
                set_stage(w, "icu_monitoring", "ICU 집중관찰", "intensivist", "장기 지지와 회복 추세를 확인합니다.", now)
            ready = (now - w["icu_since"] >= 45 and stable_window(p, now, strict=True)
                     and pr["need_score"] < 65)
            if not ready:
                w.pop("discharge_due", None)
                w.pop("doctor_order", None)
                if w["stage"] != "icu_monitoring":
                    emit(s, "intensivist", pid, "전실 계획 보류", "회복 조건이 유지되지 않아 ICU 관찰을 계속합니다.", "discharge_hold", "warning", evidence)
                    set_stage(w, "icu_monitoring", "ICU 집중관찰", "intensivist", "지원 필요성과 새 관측을 확인합니다.", now)
                if w.get("last_icu_round", -60) <= now - 30:
                    w["last_icu_round"] = now
                    emit(s, "intensivist", pid, "ICU 회진 · 집중관찰 유지", "현재 혈압·산소화·장기 지지와 회복 경과를 검토했습니다.", "round", evidence=evidence)
                continue
            if "discharge_due" not in w:
                w["discharge_due"] = now + 5
                emit(s, "intensivist", pid, "일반병동 전실 결정", "안정 관측과 호흡·순환 지원 감소를 확인했습니다. 병동 인수와 퇴실 후 청소를 요청합니다.", "discharge_order", evidence=evidence)
                set_stage(w, "ward_handoff", "병동 인계 중", "ward", "병동 간호사가 환자 상태와 인계 내용을 확인합니다.", now)
            elif now >= w["discharge_due"]:
                bed = next(b for b in s["beds"] if b["occupant_id"] == pid)
                try:
                    engine.dispatch(s, "discharge", {"bed_id": bed["id"], "reason": "가상 ICU 전담의 안정 경과 확인 및 병동 간호사 인수 완료"}, ROLES["intensivist"]["name"])
                except AppError as exc:
                    set_stage(w, "ward_bed_wait", "병동 병상 대기", "ward", exc.message, now)
                    w.pop("discharge_due", None)
                    continue
                emit(s, "ward", pid, "병동 인수 · ICU 퇴실 완료", bed["id"] + "에서 병동으로 이동했습니다. 반복 관찰을 이어갑니다.", "discharge", evidence=evidence)
                emit(s, "charge", pid, "퇴실 병상 청소 시작", bed["id"] + f" · {s['policy']['cleanup_minutes']:g}분 후 준비 상태를 다시 확인합니다.", "cleaning")
                team["counters"]["ward_transfers"] += 1
                team["counters"]["handoffs"] += 1
                w["ward_since"] = now
                for key in ("reservation_id", "icu_since", "discharge_due", "doctor_order",
                            "prep_due", "prepared_logged", "reserved_bed", "ward_due"):
                    w.pop(key, None)
                set_stage(w, "ward_monitoring", "병동 회복 관찰", "ward", "전실 인계를 완료하고 회복을 관찰합니다.", now)
            continue

        severe_support = (current not in ("PREOP", "OR") and (o.get("ventilation") is True or o.get("crrt") is True))
        needs_icu = (p["planned_icu"] and current != "WARD") or pr["icu_probability"] >= s["policy"]["icu_threshold"] or severe_support
        if current == "WARD" and not needs_icu:
            from .hospital import can_review_discharge, hospital_discharge
            ready = can_review_discharge(p, now)
            if ready:
                if "hospital_exit_due" not in w:
                    if workload("hospital_discharge_handoff") >= team["resources"]["ward_slots"]:
                        set_stage(w, "discharge_queue", "퇴원 간호 인계 대기", "ward", "진행 중인 퇴원 인계를 마친 뒤 순서대로 진행합니다.", now)
                        continue
                    emit(s, "surgeon", pid, "회복 평가 · 병원 퇴원 결정",
                         "관측된 안정 경과, 식이·보행·통증·상처와 퇴원 계획을 확인했습니다. 병동 간호사에게 퇴원 인계를 요청합니다.", "hospital_discharge_order", evidence=evidence)
                    w["hospital_exit_due"] = now + 15
                    set_stage(w, "hospital_discharge_handoff", "퇴원 교육·간호 인계", "ward", "복약·외래 일정 안내와 퇴원 인계를 마친 뒤 병원을 떠납니다.", now)
                elif now >= w["hospital_exit_due"]:
                    hospital_discharge(s, p)
                    emit(s, "ward", pid, "병원 퇴원 완료 · 병상 정리",
                         "퇴원 인계를 마쳤습니다. 병동 병상을 비우고 청소 후 다음 환자를 인수합니다.", "hospital_discharge", evidence=evidence)
                    team["counters"]["hospital_discharges"] += 1
                    set_stage(w, "completed", "병원 퇴원 완료", "ward", "퇴원 기록을 보관하고 현재 진료 대상에서 제외합니다.", now)
                continue
            if w.pop("hospital_exit_due", None) is not None:
                emit(s, "surgeon", pid, "퇴원 계획 보류 · 경과 재평가", "새 관측에서 회복 조건을 재확인해야 하므로 퇴원 인계를 중지합니다.", "hospital_discharge_hold", "warning", evidence)
            set_stage(w, "ward_monitoring", "병동 회복 관찰", "ward", "병동 간호사가 회복 경과를 관찰합니다.", now)
            continue
        if current == "PREOP" and now < p["operation_start_minute"]:
            if not w.get("preop_checked"):
                emit(s, "anesthesia", pid, "수술 전 평가 완료", "병력·ASA 상태·수술 전 검사와 예정 ICU 입실 계획을 확인했습니다.", "preop", evidence=evidence)
                w["preop_checked"] = True
            if not needs_icu:
                set_stage(w, "preop", "수술 전 준비", "anesthesia", "예정 수술 시각에 맞춰 수술실로 이동합니다.", now)
                continue
        if current == "OR" and not w.get("or_seen"):
            emit(s, "anesthesia", pid, "수술 중 경과 인계", "최근 관측과 현재 처치를 확인했습니다. 수술 종료 후 회복 경로를 준비합니다.", "assessment", evidence=evidence)
            w["or_seen"] = True
        if current == "PACU" and not w.get("postop_seen"):
            emit(s, "anesthesia", pid, "수술 후 회복 평가 시작", "수술 종료와 회복실 도착을 확인했습니다. 현재 호흡·순환 상태를 재평가합니다.", "assessment", evidence=evidence)
            w["postop_seen"] = True

        if needs_icu:
            w["route"] = "icu"
            w.pop("ward_due", None)
            if "doctor_order" not in w or w["doctor_order"] != "icu":
                due = w.setdefault("review_due", now + 3)
                set_stage(w, "doctor_review", "의사 평가 중", "anesthesia", "현재 관측·집중관리 지원·예정 입실을 함께 검토합니다.", now)
                if now < due:
                    continue
                emit(s, "anesthesia", pid, "ICU 관찰·입실 계획 결정", "수술 후 지원 필요성과 예정 입실 계획을 확인하고 ICU 전담의에게 인계했습니다.", "order", evidence=evidence)
                team["counters"]["orders"] += 1
                w["doctor_order"] = "icu"
                w.pop("review_due", None)
            existing = active_reservation(s, pid)
            r = recommend(s, p)  # Recompute against reservations made earlier in this same step.
            # A simulated physician may retain planned care or actual organ support
            # even when the forecast alone is below the configurable booking threshold.
            # Preserve the prediction; use the same capability and conflict checks.
            if (severe_support or p["planned_icu"]) and not existing and r["status"] == "NO_ICU":
                start = max(r["start"], now + s["policy"]["prepare_minutes"])
                end = start + max(60, r["end"] - r["start"])
                beds = sorted((b for b in s["beds"] if bed_fits(s, b, p, start, end)), key=lambda b:b["id"])
                r = {**r, "start": start, "end": end,
                     "status": "BOOK_NOW" if beds else "WAIT", "bed_id": beds[0]["id"] if beds else None,
                     "reason": "의사 장기 지지·예정 입실 확인" if beds else "필요 장비·병동·시간 조건을 충족하는 병상 없음"}
            can_book = r["status"] == "BOOK_NOW" or (severe_support and r["bed_id"] and not existing)
            needs_update = (existing and r["status"] == "UPDATE" and
                            (r["bed_id"] != existing["bed_id"] or
                             (current in ("PREOP", "OR") and
                              (abs(existing["start"] - r["start"]) > 15 or r["end"] > existing["end"] + 30))))
            if can_book or needs_update:
                start = max(r["start"], now + s["policy"]["prepare_minutes"])
                duration = max(60, r["end"] - r["start"])
                try:
                    engine.reserve(s, {"patient_id": pid, "bed_id": r["bed_id"], "start": start,
                        "end": start + duration, "reason": "가상 의사 ICU 계획 확인 · 책임간호사 병동·장비·예약 충돌 검토"}, ROLES["charge"]["name"])
                    existing = active_reservation(s, pid)
                    emit(s, "charge", pid, "병상 예약 갱신" if needs_update else "ICU 병상 확보", existing["bed_id"] + " · 병동·필요 장비·기존 예약을 확인했습니다.", "reservation", evidence=evidence)
                    team["counters"]["reservations"] += 1
                    if w.get("reserved_bed") != existing["bed_id"]:
                        w.pop("prep_due", None)
                        w.pop("prepared_logged", None)
                        w.pop("transfer_due", None)
                    w["reserved_bed"] = existing["bed_id"]
                except AppError as exc:
                    set_stage(w, "capacity_wait", "병상 조정 중", "charge", exc.message, now)
                    continue
            if not existing:
                label = "병상 조정 중" if r["status"] == "WAIT" else "입실 계획 확인"
                stage = "capacity_wait" if r["status"] == "WAIT" else "planned"
                if stage == "capacity_wait" and w.get("last_capacity_report", -30) <= now - 15:
                    emit(s, "charge", pid, "가용 병상 재확인", r["reason"] + ". 환자 관찰을 유지하며 다음 가용 병상을 확인합니다.", "capacity", "warning", evidence)
                    w["last_capacity_report"] = now
                set_stage(w, stage, label, "charge", r["reason"], now)
                continue
            w["reservation_id"] = existing["id"]
            bed = next(b for b in s["beds"] if b["id"] == existing["bed_id"])
            if bed["occupant_id"] or bed["available_minute"] > now:
                set_stage(w, "capacity_wait", "병상 가용 확인", "charge", bed["id"] + "의 실제 퇴실·청소 완료를 기다립니다.", now)
                continue
            if now < existing["start"] - s["policy"]["prepare_minutes"]:
                set_stage(w, "planned", "입실 계획 확인", "charge", bed["id"] + " 예약 완료 · 도착 시각에 맞춰 준비합니다.", now)
                continue
            if "prep_due" not in w:
                if workload("preparing") >= team["resources"]["prep_slots"]:
                    set_stage(w, "prep_queue", "간호 준비 대기", "charge", "진행 중인 병상 준비를 마친 뒤 다음 환자를 준비합니다.", now)
                    continue
                w["prep_due"] = now + s["policy"]["prepare_minutes"]
                emit(s, "charge", pid, "병상·장비 준비 시작", bed["id"] + " · 모니터·호흡 지원 장비·환자 인수 준비를 시작했습니다.", "preparation")
            if now < w["prep_due"]:
                set_stage(w, "preparing", "병상·장비 준비", "charge", bed["id"] + " 준비 중", now)
                continue
            if not w.get("prepared_logged"):
                emit(s, "charge", pid, "병상 준비 완료", bed["id"] + "의 모니터·장비·인수 준비를 확인했습니다.", "ready")
                w["prepared_logged"] = True
            if current in ("PREOP", "OR"):
                set_stage(w, "bed_ready", "병상 준비 완료", "anesthesia", "수술 종료와 이송 가능 상태를 기다립니다.", now)
                continue
            if now < existing["start"]:
                set_stage(w, "bed_ready", "이송 시각 대기", "transport", "예약 시각에 맞춰 환자와 병상을 인계합니다.", now)
                continue
            if "transfer_due" not in w:
                if workload("transporting") >= team["resources"]["transport_slots"]:
                    set_stage(w, "transport_queue", "이송 간호 인계 대기", "transport", "이송 중인 환자 인계를 완료한 뒤 출발합니다.", now)
                    continue
                w["transfer_due"] = now + s["policy"]["transfer_minutes"] + 2
                emit(s, "transport", pid, "ICU 이송 · SBAR 인계", f"{p['location']} → {bed['id']} · 현재 생체신호·지원·최근 처치를 인계합니다.", "transport", evidence=evidence)
            if now < w["transfer_due"]:
                set_stage(w, "transporting", "이송·인계 중", "transport", bed["id"] + "로 이동하고 환자 상태를 인계합니다.", now)
                continue
            try:
                engine.dispatch(s, "admit", {"reservation_id": existing["id"]}, ROLES["charge"]["name"])
            except AppError as exc:
                set_stage(w, "capacity_wait", "입실 조건 재확인", "charge", exc.message, now)
                w.pop("transfer_due", None)
                if w.get("last_admit_error") != exc.message:
                    emit(s, "charge", pid, "입실 조건 재확인", exc.message, "capacity", "warning", evidence)
                    w["last_admit_error"] = exc.message
                continue
            emit(s, "charge", pid, "ICU 입실 · 인수 완료", bed["id"] + "에서 환자 인수를 완료했습니다. ICU 전담의와 집중관찰을 이어갑니다.", "admission", evidence=evidence)
            team["counters"]["admissions"] += 1
            team["counters"]["handoffs"] += 1
            w["icu_since"] = now
            w.pop("transfer_due", None)
            set_stage(w, "icu_monitoring", "ICU 집중관찰", "intensivist", "입실 인계 완료 · 현재 지원과 회복 경과를 확인합니다.", now)
        else:
            w.pop("review_due", None)
            existing = active_reservation(s, pid)
            r = recommend(s, p)
            if existing:
                if r["status"] == "REVIEW_RELEASE":
                    engine.cancel(s, {"reservation_id": existing["id"], "reason": "가상 의사·간호사 안정 경과 재검토 후 예약 해제"}, ROLES["intensivist"]["name"])
                    emit(s, "intensivist", pid, "회복 평가 · 예약 해제", "낮은 ICU 이용 예측과 안정 관측을 함께 확인했습니다.", "release", evidence=evidence)
                    for key in ("reservation_id", "prep_due", "prepared_logged", "transfer_due", "reserved_bed"):
                        w.pop(key, None)
                else:
                    set_stage(w, "recovery_review", "회복 경과 재평가", "anesthesia", "현재 예약을 유지하며 안정 경과와 이동 계획을 재평가합니다.", now)
                    w.pop("transfer_due", None)
                    continue
            if current == "OR":
                set_stage(w, "or_monitoring", "수술 중 관찰", "anesthesia", "수술 중 관측과 회복 경로를 확인합니다.", now)
            elif current == "PACU":
                if stable_window(p, now) and now - p["actual_end_minute"] >= 20:
                    w["route"] = "ward"
                    if "ward_due" not in w:
                        w["ward_due"] = now + 5
                        emit(s, "anesthesia", pid, "회복실 평가 · 병동 이동 결정", "안정된 관측과 호흡·순환 상태를 확인했습니다. 병동 간호사 인수를 요청합니다.", "ward_order", evidence=evidence)
                    if now >= w["ward_due"]:
                        from .hospital import claim_ward_bed
                        if s["ward_beds"] and not claim_ward_bed(s, p):
                            set_stage(w, "ward_bed_wait", "병동 병상 대기", "ward", "가용 병상이 준비될 때까지 회복실에서 관찰을 유지합니다.", now)
                            continue
                        p["location"] = "WARD"
                        emit(s, "ward", pid, "일반병동 도착 · 인수 완료", "회복실 인계를 받고 병동 회복 관찰을 시작합니다.", "ward_arrival", evidence=evidence)
                        team["counters"]["ward_transfers"] += 1
                        team["counters"]["handoffs"] += 1
                        w["ward_since"] = now
                        set_stage(w, "ward_monitoring", "병동 회복 관찰", "ward", "회복실 인계를 완료했습니다.", now)
                    else:
                        set_stage(w, "ward_handoff", "병동 인계 중", "ward", "환자 상태와 회복실 인계 내용을 확인합니다.", now)
                else:
                    w.pop("ward_due", None)
                    set_stage(w, "recovery_review", "회복실 관찰", "anesthesia", "혈압·산소화·지원 필요성이 안정되는지 확인합니다.", now)

    # Bed turnover is an observed workflow event, not a forecast expiry.
    for bed in s["beds"]:
        if (not bed["occupant_id"] and bed["enabled"] and bed["available_basis"] == "실제 퇴실 후 청소"
                and bed["available_minute"] <= now):
            bed["available_basis"] = "간호사 청소·장비 확인 완료"
            emit(s, "charge", "", "청소·병상 확인 완료", bed["id"] + " · 다음 환자 인수 준비가 가능합니다.", "cleaned")


def public_team(s):
    team = ensure_team(s)
    return {**team, "log": team["log"][-200:], "roles": ROLES,
            "description": "관측에 근거한 가상 의료진 역할 시뮬레이션 · 합성 데이터 전용"}
