import copy
import math
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from .demo import make_demo
from .model import extract_features, predict, demo_predict, phase
from .store import Store
from .version import RUNTIME_VERSION, COMPATIBLE_RUNTIMES

PHASE_LABELS = {"PREOP": "수술 전", "OR": "수술 중", "PACU": "회복실", "ICU": "ICU", "WARD": "일반병동",
                "PENDING": "입원 예정", "ADMITTING": "입원 인계", "DISCHARGED": "병원 퇴원", "DECEASED": "사망", "TRANSFERRED": "기관 전원"}


class AppError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
        super().__init__(message)


def finite_number(value, label, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lo <= value <= hi:
        raise AppError(f"{label}: {lo}~{hi} 범위의 숫자가 필요합니다")
    return value


def overlap(a, b, c, d):
    return a < d and c < b


def iso_time(state, minute):
    return (datetime.fromisoformat(state["base_time"]) + timedelta(minutes=minute)).isoformat()


def patient_by_id(state, pid):
    p = next((p for p in state["patients"] if p["id"] == pid), None)
    if not p:
        raise AppError("환자를 찾을 수 없습니다", 404)
    return p


def active_reservation(state, pid):
    return next((r for r in state["reservations"] if r["patient_id"] == pid and r["status"] in ("confirmed", "occupied")), None)


def bed_fits(state, bed, patient, start, end, ignore=None):
    if not bed["enabled"] or bed["unit"] != patient["preferred_unit"]:
        return False
    if not set(patient.get("capabilities_required", [])).issubset(bed["capabilities"]):
        return False
    if bed["occupant_id"] and not bed.get("availability_forecast_known", True):
        return False
    if bed["occupant_id"] and bed["available_minute"] <= state["minute"]:
        return False  # Expired discharge forecast is NOT an observed discharge.
    if start < max(state["minute"], bed["available_minute"]):
        return False
    for r in state["reservations"]:
        if r["id"] != ignore and r["bed_id"] == bed["id"] and r["status"] in ("confirmed", "occupied"):
            if overlap(start, end, r["start"], r["end"] + state["policy"]["cleanup_minutes"]):
                return False
    return True


def recommend(state, patient):
    now, policy = state["minute"], state["policy"]
    pr = state["predictions"][patient["id"]]
    current_phase = pr["features"]["phase"]
    existing = active_reservation(state, patient["id"])
    arrival = max(now, patient["estimated_end_minute"]) + policy["transfer_minutes"]
    end = arrival + math.ceil((pr["icu_los_upper"] or 0) * 60)
    from .evaluation import optimized_booking
    optimization = optimized_booking(now, arrival, pr["icu_probability"] or 0, policy)
    due = optimization["booking_minute"]
    r = {"patient_id": patient["id"], "start": arrival, "end": end, "due": due,
         "bed_id": None, "existing_id": existing["id"] if existing else None,
         "status": "MONITOR", "reason": "현재 관측을 지속합니다", "priority": pr["need_score"] or 0,
         "actionable": False, "prediction_revision": state["revision"], "optimization": optimization}
    if current_phase in ("PENDING", "DISCHARGED", "DECEASED", "TRANSFERRED", "ADMITTING"):
        r.update(status="COMPLETED" if current_phase in ("DISCHARGED", "DECEASED", "TRANSFERRED") else "MONITOR",
                 reason="종료된 입원 사례 · 현재 예측과 예약 대상에서 제외" if current_phase != "ADMITTING" else "입원 접수·인계를 확인합니다")
        return r
    if current_phase == "ICU":
        r.update(status="ADMITTED", reason="현재 ICU 재실 중 · 지원 종료와 퇴실을 별도로 확인")
        return r
    if pr["mode"] in ("remote_partial", "unsupported") or any(pr.get(key) is None for key in ("icu_probability", "icu_los_upper", "confidence")):
        # A classifier supplies no occupancy window or individual certainty.
        # Keep existing confirmed reservations; never generate replacement times.
        r.update(status="BLOCKED", reason=pr.get("model_error") or "ICU24 입실 확률만 제공 · 체류기간·예약 시점 예측은 지원하지 않습니다",
                 start=None, end=None, due=None, optimization=None)
        return r
    if state["clock_kind"] not in ("synthetic_shared", "hospital_shared"):
        r.update(status="BLOCKED", reason="환자 간 공통 시간축이 없어 병상 경쟁을 계산할 수 없습니다")
        return r
    if not state["beds"]:
        r.update(status="BLOCKED", reason="실제 병상 재고가 제공되지 않아 예약·자원 경쟁을 계산하지 않습니다")
        return r
    if pr["mode"] == "unavailable" or pr["features"]["stale"] or pr["confidence"] < policy["confidence_min"]:
        r.update(status="BLOCKED", reason="예측 신뢰·관측 품질 확인 후 예약을 검토하세요")
        return r
    if pr["icu_probability"] < policy["icu_threshold"]:
        if existing:
            history = state["prediction_history"].get(patient["id"], [])
            relevant = [h for h in history if h["minute"] >= now - policy["release_stability_minutes"]]
            stable = relevant and relevant[0]["minute"] <= now - policy["release_stability_minutes"] and all(h["icu_probability"] is not None and h["icu_probability"] < policy["release_threshold"] and h["confidence"] >= policy["confidence_min"] for h in relevant)
            if stable and not patient.get("planned_icu"):
                r.update(status="REVIEW_RELEASE", reason="낮은 ICU 이용 예측이 안정적으로 유지됨 · 해제 여부 검토", actionable=True)
            else:
                r.update(status="KEEP", reason="기존 예약 유지 · 해제 기준 또는 안정 관측기간 미충족")
        else:
            r.update(status="NO_ICU", reason="현재 ICU 이용 예측이 예약 기준 미만")
        return r
    options = [b for b in state["beds"] if bed_fits(state, b, patient, arrival, end, r["existing_id"])]
    options.sort(key=lambda b: (0 if existing and b["id"] == existing["bed_id"] else 1, b["available_minute"], b["id"]))
    if not options:
        r.update(status="WAIT", reason="필요 장비·병동·시간 조건을 충족하는 병상 없음")
        return r
    r["bed_id"] = options[0]["id"]
    if existing:
        change = abs(existing["start"] - arrival) > 15 or end > existing["end"] + 30 or r["bed_id"] != existing["bed_id"]
        r.update(status="UPDATE" if change else "KEEP", actionable=change,
                 reason="도착·점유 예상이 변경되어 예약 갱신 필요" if change else "현재 예측과 기존 예약이 일치")
    elif now >= due:
        r.update(status="BOOK_NOW", actionable=True, reason="ICU 이용 예측이 기준 이상이며 병상 준비 시점에 도달")
    else:
        r.update(status="PLAN", reason="예약 후보 확보 · 준비시간을 고려한 예약 시점 대기")
    return r


class Engine:
    def __init__(self, db_path):
        self.lock = threading.RLock()
        self.store = Store(db_path)
        loaded = self.store.load()
        if loaded and loaded.get("runtime_version") not in COMPATIBLE_RUNTIMES and loaded.get("source") == "synthetic":
            self.store.archive(loaded)
            loaded = make_demo(loaded.get("seed", 26))
            loaded["migration_notice"] = "이전 모의 운영 상태를 보관하고 v6의 일반 128·ICU 12병상 시나리오를 준비했습니다."
        self.state = loaded or make_demo()
        if loaded:
            self.state["revision"] += 1  # Invalidates decisions reviewed before restart.
        self.state["running"] = False
        backend = os.environ.get("MODEL_BACKEND", "demo")
        if backend not in ("demo", "remote"):
            raise ValueError("MODEL_BACKEND must be demo or remote")
        self.state["model_backend"] = backend
        self.state["runtime_version"] = RUNTIME_VERSION
        from .hospital import ensure_hospital
        ensure_hospital(self.state)
        from .team import ensure_team
        ensure_team(self.state)
        self.refresh(self.state)
        self.store.save(self.state)

    def refresh(self, s, reuse=False):
        from .hospital import ensure_hospital
        ensure_hospital(s)
        def run(p):
            old = s.get("predictions", {}).get(p["id"])
            if old and ((reuse and old["features"]["minute"] == s["minute"] and old["features"]["phase"] == phase(p, s["minute"]))
                        or (old["mode"] == "completed" and phase(p, s["minute"]) in ("DISCHARGED", "DECEASED", "TRANSFERRED"))):
                return p["id"], old
            features = extract_features(p, s["minute"], s["policy"])
            features.update(source_mode="synthetic" if s["source"] == "synthetic" else "import",
                            source=s["source"], clock_kind=s["clock_kind"],
                            data_context={"source": {"kind": "synthetic" if s["source"] == "synthetic" else "import"},
                                          "clock_kind": s["clock_kind"]})
            result = predict(features, s["model_backend"])
            result["features"] = features
            return p["id"], result
        if s["model_backend"] == "remote":
            with ThreadPoolExecutor(max_workers=4) as pool:
                s["predictions"] = dict(pool.map(run, s["patients"]))
        else:
            s["predictions"] = dict(run(p) for p in s["patients"])
        for patient in s["patients"]:
            pid = patient["id"]
            hist = s["prediction_history"].setdefault(pid, [])
            pr = s["predictions"][pid]
            if pr["mode"] in ("pending", "completed"):
                continue
            h = {"minute": s["minute"], "need_score": pr["need_score"], "icu_probability": pr["icu_probability"], "confidence": pr["confidence"]}
            if hist and hist[-1]["minute"] == s["minute"]:
                hist[-1] = h
            else:
                hist.append(h)
            s["prediction_history"][pid] = hist[-500:]
        recs = {p["id"]: recommend(s, p) for p in s["patients"]}
        s["recommendations"] = recs
        old_alerts = {a["key"]: a for a in s.get("alerts", [])}
        alerts = []
        def alert(pid, kind, title, message, severity):
            key = pid + ":" + kind
            a = copy.deepcopy(old_alerts.get(key)) or {"id": "ALT-" + uuid.uuid4().hex[:10], "key": key, "first_minute": s["minute"], "acknowledged": False}
            a.update(patient_id=pid, kind=kind, title=title, message=message, severity=severity)
            alerts.append(a)
        for p in s["patients"]:
            pr = s["predictions"][p["id"]]
            if pr["mode"] in ("pending", "completed"):
                continue
            if pr["features"]["quality_issues"] or pr["mode"] in ("unavailable", "unsupported"):
                alert(p["id"], "quality", "관측·예측 확인", pr["model_error"] or " · ".join(pr["features"]["quality_issues"]), "warning")
            if pr["need_score"] is not None and pr["need_score"] >= 75:
                alert(p["id"], "risk", "집중관리 고위험", f"동적 지표 {pr['need_score']} · 현재 장기 지지와 관측을 확인하세요", "critical")
            if recs[p["id"]]["status"] == "WAIT":
                alert(p["id"], "capacity", "병상 확보 지연", recs[p["id"]]["reason"], "critical")
            reservation = active_reservation(s, p["id"])
            if reservation and reservation["status"] == "confirmed":
                bed = next(b for b in s["beds"] if b["id"] == reservation["bed_id"])
                if bed["occupant_id"] and (not bed.get("availability_forecast_known", True) or bed["available_minute"] > reservation["start"] or bed["available_minute"] <= s["minute"]):
                    alert(p["id"], "reservation_conflict", "확정 예약 가용성 재검토", "기존 재실·퇴실 전망과 예약이 충돌합니다. 실제 퇴실과 예약 변경을 확인하세요", "critical")
        s["alerts"] = alerts
        from .scene import update_scene
        update_scene(s)

    def mutate(self, action, body):
        with self.lock:
            expected = body.get("expected_revision")
            if expected is not None and expected != self.state["revision"]:
                raise AppError("다른 사용자가 상태를 변경했습니다. 최신 추천을 확인한 뒤 다시 실행하세요", 409)
            if action in ("reserve", "apply_recommendation", "cancel", "admit", "discharge", "hospital_discharge", "bed", "bed_forecast", "import", "automation") and expected is None:
                raise AppError("expected_revision이 필요합니다")
            candidate = copy.deepcopy(self.state)
            candidate["revision"] += 1
            actor = str(body.get("actor", "운영자"))[:80]
            result = self.dispatch(candidate, action, body, actor)
            self.refresh(candidate, reuse=action == "advance")
            if action in ("scenario", "automation") or (action == "play" and candidate["running"]):
                from .team import run_team
                run_team(self, candidate)
                self.refresh(candidate, reuse=True)
            audit_events = candidate.pop("_audit_buffer", [])
            self.store.save(candidate, action, actor, {k: v for k, v in body.items() if k not in ("dataset", "expected_revision")}, audit_events)
            self.state = candidate
            return {"ok": True, "revision": candidate["revision"], "result": result}

    def dispatch(self, s, action, b, actor):
        now = s["minute"]
        if action == "advance":
            self.advance(s, int(finite_number(b.get("minutes", 5), "진행시간", 1, 1440)))
        elif action == "play":
            s["running"] = bool(b.get("running", True))
            s["speed"] = int(finite_number(b.get("speed", s["speed"]), "속도", 1, 240))
            if s["running"] and now >= s["horizon_minutes"]:
                raise AppError("운영 기간을 마쳤습니다. 다시 시작해 새 운영을 진행하세요")
        elif action == "automation":
            from .team import ensure_team, emit
            team = ensure_team(s)
            enabled = b.get("enabled")
            if not isinstance(enabled, bool):
                raise AppError("enabled는 boolean이어야 합니다")
            if enabled and not team["eligible"]:
                raise AppError("의료진 자동 진행은 공통 시간축의 합성 시나리오에서만 가능합니다")
            team["enabled"] = enabled
            emit(s, "charge", "", "의료진 자동 진행 시작" if enabled else "의료진 자동 진행 중지",
                 "역할별 판단·병상 준비·이송·인계를 자동 진행합니다." if enabled else "사용자가 직접 검토하는 수동 모드로 전환했습니다.", "mode")
        elif action == "reset":
            new = make_demo(int(finite_number(b.get("seed", s["seed"]), "seed", 1, 999999)))
            new["revision"] = s["revision"]
            new["model_backend"] = s["model_backend"]
            s.clear()
            s.update(new)
            from .team import ensure_team
            ensure_team(s)
        elif action == "policy":
            ranges = {"icu_threshold": (0.1, 0.95), "prepare_minutes": (5, 120), "transfer_minutes": (0, 30),
                      "release_threshold": (0.05, 0.6), "release_stability_minutes": (10, 120),
                      "stale_minutes": (5, 60), "confidence_min": (0.4, 0.95), "cleanup_minutes": (0, 120),
                      "delay_weight": (0.1, 20), "idle_weight": (0.1, 20), "change_weight": (0, 200)}
            values = b.get("policy")
            if not isinstance(values, dict) or not values or any(k not in ranges for k in values):
                raise AppError("정책 필드를 확인하세요")
            for k, v in values.items():
                s["policy"][k] = finite_number(v, k, *ranges[k])
            if s["policy"]["release_threshold"] >= s["policy"]["icu_threshold"]:
                raise AppError("해제 기준은 예약 기준보다 낮아야 합니다")
        elif action == "scenario":
            self.scenario(s, b)
        elif action == "apply_recommendation":
            p = patient_by_id(s, b.get("patient_id"))
            r = recommend(s, p)
            if not r["actionable"]:
                raise AppError("현재 추천은 실행 가능하지 않습니다. 최신 상태를 확인하세요", 409)
            if r["status"] == "REVIEW_RELEASE":
                self.cancel(s, {"reservation_id": r["existing_id"], "reason": b.get("reason", "안정 관측 후 예약 해제 검토")}, actor)
            else:
                self.reserve(s, {"patient_id": p["id"], "bed_id": r["bed_id"], "start": r["start"], "end": r["end"],
                                 "reason": b.get("reason", "현재 예측과 병상 준비시간에 따른 예약 승인")}, actor)
        elif action == "reserve":
            self.reserve(s, b, actor)
        elif action == "cancel":
            self.cancel(s, b, actor)
        elif action == "admit":
            r = next((r for r in s["reservations"] if r["id"] == b.get("reservation_id")), None)
            if not r or r["status"] != "confirmed":
                raise AppError("입실 가능한 확정 예약이 없습니다")
            bed = next(bed for bed in s["beds"] if bed["id"] == r["bed_id"])
            patient = patient_by_id(s, r["patient_id"])
            if bed["occupant_id"] or bed["available_minute"] > now or not bed["enabled"]:
                raise AppError("현재 병상이 준비되지 않았습니다", 409)
            if phase(patient, now) not in ("PACU", "WARD"):
                raise AppError("수술 종료를 확인한 뒤 실제 ICU 입실을 기록하세요")
            if now < r["start"] - 10:
                raise AppError("예약 입실 시각이 아직 도래하지 않았습니다")
            actual_end = now + max(60, r["end"] - r["start"])
            if not bed_fits(s, bed, patient, now, actual_end, r["id"]):
                raise AppError("실제 입실 구간이 다른 예약과 충돌합니다", 409)
            r.update(status="occupied", start=now, end=actual_end)
            patient["location"] = bed["id"]
            patient["icu_bed_id"] = bed["id"]
            patient["icu_admission_minute"] = now
            from .hospital import release_ward_bed, record
            release_ward_bed(s, patient)
            record(s, patient["id"], "icu_admission", "ICU 실제 입실", bed["id"])
            bed.update(occupant_id=patient["id"], available_minute=r["end"] + s["policy"]["cleanup_minutes"], available_basis="모델 기반 퇴실 예상", availability_forecast_known=True)
        elif action == "discharge":
            bed = next((bed for bed in s["beds"] if bed["id"] == b.get("bed_id")), None)
            if not bed or not bed["occupant_id"]:
                raise AppError("재실 환자가 없습니다")
            self.reason(b)
            occupant = bed["occupant_id"]
            patient = next((p for p in s["patients"] if p["id"] == occupant), None)
            if patient:
                from .hospital import claim_ward_bed
                if s["ward_beds"] and not claim_ward_bed(s, patient):
                    raise AppError("병동 가용 병상이 없어 ICU 전실을 보류합니다", 409)
                patient["location"] = "WARD"
            for r in s["reservations"]:
                if r["patient_id"] == occupant and r["status"] == "occupied":
                    r.update(status="completed", end=now)
            bed.update(occupant_id=None, available_minute=now + s["policy"]["cleanup_minutes"], available_basis="실제 퇴실 후 청소", availability_forecast_known=True)
        elif action == "hospital_discharge":
            from .hospital import hospital_discharge
            p = patient_by_id(s, b.get("patient_id"))
            self.reason(b)
            if phase(p, now) != "WARD":
                raise AppError("병동 환자의 실제 퇴원만 기록할 수 있습니다")
            hospital_discharge(s, p)
        elif action == "bed":
            bed = next((bed for bed in s["beds"] if bed["id"] == b.get("bed_id")), None)
            if not bed:
                raise AppError("병상 없음", 404)
            self.reason(b)
            enable = b.get("enabled")
            if not isinstance(enable, bool):
                raise AppError("enabled는 boolean이어야 합니다")
            if not enable and (bed["occupant_id"] or any(r["bed_id"] == bed["id"] and r["status"] in ("confirmed", "occupied") for r in s["reservations"])):
                raise AppError("재실·예약 환자를 먼저 조정해야 합니다", 409)
            bed.update(enabled=enable, closed_reason="" if enable else b["reason"])
        elif action == "bed_forecast":
            bed = next((bed for bed in s["beds"] if bed["id"] == b.get("bed_id")), None)
            if not bed:
                raise AppError("병상 없음", 404)
            self.reason(b)
            available = finite_number(b.get("available_minute"), "가용 예상 시각", now + 1, now + 43200)
            bed.update(available_minute=available, available_basis="운영 검토 가용 예상", availability_forecast_known=True)
        elif action == "ack":
            alert = next((a for a in s["alerts"] if a["id"] == b.get("alert_id")), None)
            if not alert:
                raise AppError("이미 종료된 알림입니다", 404)
            alert.update(acknowledged=True, acknowledged_by=actor, acknowledged_minute=now)
        elif action == "note":
            patient_by_id(s, b.get("patient_id"))
            text = str(b.get("text", "")).strip()
            if not 2 <= len(text) <= 2000:
                raise AppError("메모는 2~2000자입니다")
            s["notes"].append({"id": uuid.uuid4().hex[:10], "patient_id": b["patient_id"], "text": text, "minute": now, "actor": actor})
        elif action == "import":
            from .importer import validate_dataset
            dataset = validate_dataset(b.get("dataset"))
            dataset.update(revision=s["revision"], model_backend=s["model_backend"])
            s.clear()
            s.update(dataset)
            from .team import ensure_team
            ensure_team(s)
        elif action == "end_operation":
            p = patient_by_id(s, b.get("patient_id"))
            if phase(p, now) != "OR":
                raise AppError("수술 중 환자만 종료를 기록할 수 있습니다")
            self.reason(b)
            p.update(actual_end_minute=now, estimated_end_minute=now, location="PACU")
            from .hospital import record
            s["hospital"]["completed_operations"] += 1
            record(s, p["id"], "operation_end", "관측된 수술 종료 기록")
        elif action == "observe":
            from .importer import validate_observation
            p = patient_by_id(s, b.get("patient_id"))
            as_of = finite_number(b.get("as_of_minute", now), "판단 시각", now, now + 1440)
            if int(as_of) != as_of:
                raise AppError("판단 시각은 정수입니다")
            incoming = b.get("observations")
            if not isinstance(incoming, list) or not 1 <= len(incoming) <= 200:
                raise AppError("관측은 1~200개입니다")
            normalized = [validate_observation(o, as_of) for o in incoming]
            if as_of > now:
                self.advance(s, int(as_of - now))
            if p.get("status") == "scheduled" or p["admission_minute"] > as_of:
                raise AppError("입원 전 사례의 입원 중 관측은 입원 사건 이후에 입력하세요")
            cutoff = p.get("discharge_minute") if p.get("status") in ("discharged", "deceased", "transferred") else as_of
            if any(o["minute"] > cutoff for o in normalized):
                raise AppError("입원 종료 이후에 측정된 관측은 이 입원 사례에 입력할 수 없습니다")
            by_time = {o["minute"]: o for o in p["observations"]}
            by_time.update({o["minute"]: o for o in normalized})
            p["observations"] = sorted(by_time.values(), key=lambda o: o["minute"])[-1000:]
            if b.get("actual_end_minute") is not None:
                actual = finite_number(b["actual_end_minute"], "실제 종료 관측", p["operation_start_minute"], cutoff)
                observed_phase = phase(p, as_of)
                first_end = p.get("actual_end_minute") is None
                p["actual_end_minute"] = actual
                if observed_phase in ("OR", "PREOP"):
                    p["location"] = "PACU"
                if first_end:
                    from .hospital import record
                    s["hospital"]["completed_operations"] += 1
                    record(s, p["id"], "operation_end", "수신한 실제 수술 종료", str(actual))
            if b.get("estimated_end_minute") is not None:
                p["estimated_end_minute"] = finite_number(b["estimated_end_minute"], "예상 종료", p["operation_start_minute"] + 1, as_of + 10080)
            s["events"].append({"minute": as_of, "patient_id": p["id"], "label": f"관측 {len(normalized)}건 수신", "kind": "데이터"})
        else:
            raise AppError("지원하지 않는 작업입니다", 404)
        return {"action": action}

    @staticmethod
    def reason(b):
        reason = str(b.get("reason", "")).strip()
        if not 3 <= len(reason) <= 500:
            raise AppError("변경 사유를 3~500자로 입력하세요")
        return reason

    def reserve(self, s, b, actor):
        if s["clock_kind"] not in ("hospital_shared", "synthetic_shared"):
            raise AppError("공통 시간축이 없어 예약할 수 없습니다")
        reason = self.reason(b)
        patient = patient_by_id(s, b.get("patient_id"))
        if phase(patient, s["minute"]) not in ("PREOP", "OR", "PACU", "WARD"):
            raise AppError("현재 환자는 신규 ICU 예약 대상이 아닙니다")
        bed = next((b1 for b1 in s["beds"] if b1["id"] == b.get("bed_id")), None)
        if not bed:
            raise AppError("병상을 선택하세요")
        start = finite_number(b.get("start"), "입실 시각", s["minute"], s["minute"] + 10080)
        end = finite_number(b.get("end"), "종료 시각", start + 1, start + 43200)
        existing = active_reservation(s, patient["id"])
        for other in s["patients"]:
            if other["id"] != patient["id"] and other.get("subject_id", other["id"]) == patient.get("subject_id", patient["id"]):
                other_r = active_reservation(s, other["id"])
                if other_r and overlap(start, end, other_r["start"], other_r["end"]):
                    raise AppError("같은 환자의 다른 수술 예약과 점유기간이 겹칩니다", 409)
        if not bed_fits(s, bed, patient, start, end, existing["id"] if existing else None):
            raise AppError("병동·장비·준비시간 또는 기존 예약과 충돌합니다", 409)
        record = {"patient_id": patient["id"], "bed_id": bed["id"], "start": start, "end": end,
                  "reason": reason, "status": "confirmed", "actor": actor, "updated_minute": s["minute"]}
        if existing:
            record["previous"] = {k: existing[k] for k in ("bed_id", "start", "end")}
            existing.update(record)
        else:
            # Preserve the prediction available when this reservation was first made.
            # Later refreshes and reservation updates must not rewrite this evidence.
            rec = s.get("recommendations", {}).get(patient["id"], {})
            prediction = s.get("predictions", {}).get(patient["id"], {})
            record.update(id="RES-" + uuid.uuid4().hex[:10], created_minute=s["minute"],
                          initial_booking_forecast={
                              "as_of_minute": s["minute"],
                              "recommended_due_minute": rec.get("due"),
                              "expected_arrival_minute": rec.get("start"),
                              "need_score": prediction.get("need_score"),
                              "icu_probability": prediction.get("icu_probability")})
            s["reservations"].append(record)

    def cancel(self, s, b, actor):
        reason = self.reason(b)
        r = next((r for r in s["reservations"] if r["id"] == b.get("reservation_id")), None)
        if not r or r["status"] != "confirmed":
            raise AppError("취소 가능한 예약이 없습니다")
        r.update(status="cancelled", cancelled_minute=s["minute"], cancel_reason=reason, actor=actor)

    def scenario(self, s, b):
        if s["source"] != "synthetic":
            raise AppError("시나리오 주입은 합성 시연 데이터에서만 가능합니다")
        patient = patient_by_id(s, b.get("patient_id"))
        kind = b.get("kind")
        if kind not in ("hypotension", "bleeding", "hypoxia", "improving", "stale", "artifact", "clear"):
            raise AppError("시나리오 종류를 확인하세요")
        now = s["minute"]
        if kind == "clear":
            s["active_scenarios"].pop(patient["id"], None)
            trajectory = s["trajectories"].get(patient["id"], {})
            before = [o for o in trajectory.get("observations", []) if o["minute"] <= now]
            if before:
                latest = copy.deepcopy(before[-1])
                latest["minute"] = now
                patient["observations"] = [o for o in patient["observations"] if o["minute"] < now] + [latest]
        else:
            s["active_scenarios"][patient["id"]] = {"kind": kind, "start": now, "end": now + 60}
            if kind == "stale":
                patient["observations"] = [o for o in patient["observations"] if o["minute"] <= now - 20]
            else:
                base = copy.deepcopy(patient["observations"][-1]) if patient["observations"] else {"minute": now, "map": 78, "hr": 80, "spo2": 98}
                base["minute"] = now
                self.apply_effect(base, kind)
                patient["observations"] = [o for o in patient["observations"] if o["minute"] < now] + [base]
        labels = {"hypotension": "저혈압 악화", "bleeding": "출혈·순환 불안정", "hypoxia": "산소화 악화", "improving": "처치 후 회복", "stale": "관측 지연", "artifact": "센서 오류", "clear": "시나리오 해제"}
        s["events"].append({"minute": now, "patient_id": patient["id"], "label": labels[kind], "kind": "모의 사건"})

    @staticmethod
    def apply_effect(obs, kind):
        if kind == "hypotension":
            obs.update(map=54, hr=115, norepi=0.14, lactate=3.2)
        elif kind == "bleeding":
            obs.update(map=52, hr=128, hemoglobin=7.1, lactate=5.8, norepi=0.2, urine_ml_kg_h=0.15)
        elif kind == "hypoxia":
            obs.update(spo2=88, hr=112)
        elif kind == "improving":
            obs.update(map=84, hr=78, spo2=98, norepi=0, lactate=1.3, ventilation=False, crrt=False, urine_ml_kg_h=0.8)
        elif kind == "artifact":
            obs.update(map=None, spo2=None, artifact=True)

    def advance(self, s, minutes):
        target = s["minute"] + minutes
        if target > s["horizon_minutes"]:
            raise AppError("운영 기간을 초과합니다. 남은 기간만 진행하거나 다시 시작하세요")
        # Five-minute clinical steps plus exact recorded event timestamps. A
        # long advance visits intermediate events; it cannot jump over a death,
        # discharge or ICU transfer, or feed future observations to a forecast.
        boundaries = set(range((int(s["minute"]) // 5 + 1) * 5, int(target) + 1, 5))
        boundaries.add(int(target))
        boundaries.update(int(e["minute"]) for e in s.get("replay_events", [])[s.get("replay_cursor", 0):]
                          if s["minute"] < e["minute"] <= target)
        for minute in sorted(boundaries):
            s["minute"] = minute
            from .hospital import update_synthetic, replay_until
            update_synthetic(s)
            replay_until(s)
            self.refresh(s)
            if minute % 5 == 0:
                from .team import run_team
                run_team(self, s)
                self.refresh(s, reuse=True)
        if target == s["horizon_minutes"]:
            s["running"] = False
        s["events"] = s["events"][-500:]

    def tick(self):
        with self.lock:
            if self.state["running"]:
                if self.state["minute"] >= self.state["horizon_minutes"]:
                    self.mutate("play", {"running": False})
                else:
                    self.mutate("advance", {"minutes": min(self.state["speed"], self.state["horizon_minutes"] - self.state["minute"]), "actor": "운영 시간 진행"})

    def view(self):
        with self.lock:
            s = copy.deepcopy(self.state)
        patients = []
        for patient in s["patients"]:
            if phase(patient, s["minute"]) == "PENDING":
                continue
            p = {k: v for k, v in patient.items() if k not in ("course", "observations", "treatments")}
            pr = s["predictions"][p["id"]]
            # The dashboard is a display projection, not a raw-data export.
            # Retain short-term detail and extrema for the full stored history.
            history = s["prediction_history"].get(p["id"], [])
            if len(history) > 72:
                bucket_size = math.ceil((len(history) - 8) / 32)
                reduced = []
                for index in range(0, len(history) - 8, bucket_size):
                    bucket = history[index:index + bucket_size]
                    measured = [h for h in bucket if h["need_score"] is not None]
                    if measured:
                        reduced.extend([min(measured, key=lambda h: h["need_score"]), max(measured, key=lambda h: h["need_score"])])
                by_minute = {h["minute"]: h for h in [history[0], *reduced, *history[-8:]]}
                history = [by_minute[k] for k in sorted(by_minute)]
            terminal = pr["mode"] == "completed"
            p.update(prediction=pr, phase=pr["features"]["phase"], phase_label=PHASE_LABELS[pr["features"]["phase"]],
                     history=history, recommendation=s["recommendations"][p["id"]],
                     observations=[o for o in patient["observations"] if o["minute"] <= s["minute"]][-12 if terminal else -72:],
                     treatments=[o for o in patient["treatments"] if o["minute"] <= s["minute"]][-50:])
            patients.append(p)
        for bed in s["beds"]:
            bed["reservations"] = [r for r in s["reservations"] if r["bed_id"] == bed["id"] and r["status"] in ("confirmed", "occupied")]
        from .team import public_team
        from .scene import public_scene
        from .hospital import public_hospital, active
        automation = public_team(s)
        for p in patients:
            p["workflow"] = automation["workflows"].get(p["id"], {"stage": "observing", "label": "경과 관찰", "owner": "anesthesia", "detail": "시뮬레이션을 시작하면 의료진이 평가합니다."})
        return {"revision": s["revision"], "minute": s["minute"], "base_time": s["base_time"], "clock": iso_time(s, s["minute"]),
                "running": s["running"], "speed": s["speed"], "seed": s["seed"], "source": s["source"], "clock_kind": s["clock_kind"],
                "hospital": public_hospital(s), "migration_notice": s.get("migration_notice", ""),
                "model_backend": s["model_backend"], "policy": s["policy"], "patients": patients, "beds": s["beds"], "automation": automation, "scene": public_scene(s),
                "reservations": s["reservations"], "alerts": s["alerts"], "events": s["events"][-80:], "notes": s["notes"][-100:],
                "summary": {"patients": sum(active(p) for p in patients), "cases_seen": len(patients), "high_risk": sum(p["prediction"]["need_score"] is not None and p["prediction"]["need_score"] >= 70 for p in patients),
                            "book_now": sum(p["recommendation"]["status"] in ("BOOK_NOW", "UPDATE", "WAIT") for p in patients),
                            "available_beds": sum(b["enabled"] and not b["occupant_id"] and b["available_minute"] <= s["minute"] for b in s["beds"]),
                            "enabled_beds": sum(b["enabled"] for b in s["beds"]), "occupied_beds": sum(bool(b["occupant_id"]) for b in s["beds"]),
                            "blocked": sum(p["recommendation"]["status"] == "BLOCKED" for p in patients),
                            "unacknowledged": sum(not a["acknowledged"] for a in s["alerts"])},
                "audit": self.store.audit(80)}
