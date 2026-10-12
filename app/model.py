"""Replaceable prediction interface; the default is NOT a trained medical model."""
import json
import math
import os
import urllib.request

MODEL_VERSION = "demo-rules-3.0"


def phase(patient, minute):
    if minute < patient.get("admission_minute", -1e9):
        return "PENDING"
    if patient.get("status") in ("discharged", "deceased", "transferred"):
        return {"discharged": "DISCHARGED", "deceased": "DECEASED", "transferred": "TRANSFERRED"}[patient["status"]]
    if patient.get("location") == "ENTRY":
        return "ADMITTING"
    location = patient.get("location", "")
    # Observed ICU occupancy remains ICU even before a later planned operation.
    # Supplied bed IDs need not encode the unit in their name.
    if location.startswith(("SICU", "CCU", "ICU")) or (patient.get("icu_bed_id") and patient["icu_bed_id"] == location):
        return "ICU"
    start = patient["operation_start_minute"]
    actual = patient.get("actual_end_minute")
    if minute < start or patient.get("location", "").startswith("PREOP"):
        return "PREOP"
    if location.startswith("WARD"):
        return "WARD"
    if location.startswith("PACU"):
        return "PACU"
    if actual is None or minute < actual:
        return "OR"
    return "PACU"


def extract_features(patient, minute, policy):
    visible = sorted((o for o in patient.get("observations", []) if o["minute"] <= minute), key=lambda o: o["minute"])
    latest = visible[-1] if visible else {}
    window = [o for o in visible if minute - 30 <= o["minute"] <= minute]
    maps = [o["map"] for o in window if o.get("map") is not None]
    hrs = [o["hr"] for o in window if o.get("hr") is not None]
    spo2s = [o["spo2"] for o in window if o.get("spo2") is not None]
    age_minutes = minute - latest["minute"] if latest else None
    core_count = sum(latest.get(k) is not None for k in ("map", "hr", "spo2"))
    quality = core_count / 3
    current_phase = phase(patient, minute)
    freshness = policy.get("ward_stale_minutes", 480) if current_phase == "WARD" else policy.get("preop_stale_minutes", 120) if current_phase in ("PREOP", "ADMITTING") else policy["stale_minutes"]
    stale = age_minutes is None or age_minutes > freshness
    problems = []
    if stale:
        problems.append("관측 지연 또는 관측 없음")
    if core_count < 3:
        problems.append("핵심 신호 결측")
    if any(o.get("artifact") for o in window):
        problems.append("센서 오류 표식")
        quality *= 0.5
    if latest and latest.get("norepi") is None and phase(patient, minute) in ("OR", "PACU", "ICU"):
        problems.append("승압제 관측 정보 없음")
        quality *= 0.7
    support = latest.get("ventilation") if phase(patient, minute) != "OR" else False
    lab_time = patient.get("preop_labs_minute", minute)
    return {"minute": minute, "patient_id": patient["id"], "phase": phase(patient, minute),
            "age": patient["age"], "asa": patient["asa"], "emergency": patient.get("emergency", False),
            "planned_icu": patient.get("planned_icu", False) and current_phase not in ("WARD", "DISCHARGED", "DECEASED", "TRANSFERRED"), "conditions": patient.get("conditions", []),
            "preop_labs": patient.get("preop_labs", {}) if lab_time is not None and lab_time <= minute else {},
            "preop_labs_minute": patient.get("preop_labs_minute"), "latest": latest,
            "pre_admission": [e for e in patient.get("pre_admission", []) if e["minute"] < patient["admission_minute"] and e["minute"] <= minute],
            "signal_window": window,
            "treatment_history": [e for e in patient.get("treatments", []) if e["minute"] <= minute][-50:],
            "units": {"map": "mmHg", "hr": "bpm", "spo2": "%", "norepi": "ug/kg/min", "lactate": "mmol/L", "hemoglobin": "g/dL"},
            "map_min_30": min(maps) if maps else None,
            "low_map_fraction_30": sum(v < 65 for v in maps) / len(maps) if maps else None,
            "map_slope_30": (maps[-1] - maps[0]) / max(5, window[-1]["minute"] - window[0]["minute"]) if len(maps) > 1 else 0,
            "hr_max_30": max(hrs) if hrs else None, "spo2_min_30": min(spo2s) if spo2s else None,
            "persistent_postop_ventilation": bool(support), "observation_age_minutes": age_minutes,
            "quality": round(quality, 3), "stale": stale, "quality_issues": problems,
            "observed_count": len(visible), "elapsed_operation_minutes": max(0, min(minute, actual_end if (actual_end := patient.get("actual_end_minute")) is not None else minute) - patient["operation_start_minute"]),
            "elapsed_admission_hours": max(0, minute - patient["admission_minute"]) / 60,
            "elapsed_postop_hours": max(0, minute - patient["actual_end_minute"]) / 60 if patient.get("actual_end_minute") is not None else 0,
            "procedure_group": patient.get("procedure_group", "unknown")}


def demo_predict(f):
    points = []
    def add(label, value, detail):
        if value:
            points.append({"label": label, "points": round(value, 1), "detail": detail})
    add("ASA 상태", (f["asa"] - 1) * 7, f"ASA {f['asa']}")
    add("연령", max(0, f["age"] - 55) * 0.3, f"{f['age']}세")
    add("응급 수술", 12 if f["emergency"] else 0, "응급 수술 여부")
    add("기저질환 부담", min(10, len(f["conditions"]) * 3), ", ".join(f["conditions"]) or "없음")
    latest = f["latest"]
    low = f["low_map_fraction_30"]
    add("최근 30분 저혈압", (low or 0) * 24, "MAP <65 mmHg 관측 비율")
    add("현재 저혈압", max(0, 65 - (latest.get("map") if latest.get("map") is not None else 65)) * 0.65, "현재 MAP")
    add("승압제 부담", min(24, (latest.get("norepi") or 0) * 110), "Norepinephrine µg/kg/min")
    add("산소화 저하", min(25, max(0, 94 - (latest.get("spo2") if latest.get("spo2") is not None else 94)) * 3.8), "현재 SpO₂")
    add("젖산 상승", min(18, max(0, (latest.get("lactate") or f["preop_labs"].get("lactate", 1.2)) - 2) * 5), "가장 최근 젖산")
    add("빈맥", min(10, max(0, (latest.get("hr") or 80) - 100) * 0.35), "현재 HR")
    add("수술 후 호흡 지원", 10 if f["persistent_postop_ventilation"] else 0, "수술 중 통상적 환기는 제외")
    add("저혈압 회복 추세", -min(8, max(0, f["map_slope_30"]) * 12), "30분 MAP 회복 기울기")
    raw = 8 + sum(p["points"] for p in points)
    score = round(max(2, min(98, raw)))
    prob_need = round(1 / (1 + math.exp(-(score - 47) / 12)), 3)
    prob_icu = max(prob_need, 0.94 if f["planned_icu"] else 0.0)
    if f["phase"] == "ICU":
        prob_icu = 1.0
    elapsed = f.get("elapsed_postop_hours", 0)
    hours = round(max(2, 6 + score * 0.62 + (12 if f["planned_icu"] else 0) - elapsed * .3), 1)
    intensive = round(max(1, 2 + score * 0.35), 1)
    baseline = {"minor": .8, "standard": 3, "major": 5, "complex": 8}.get(f.get("procedure_group"), 2 + f["asa"] * .7)
    # Demonstration only: known surgery group + elapsed postoperative time and
    # observed current instability. No future discharge time or final LOS input.
    hospital = round(max(.1, baseline - elapsed / 24 + max(0, score - 40) / 40), 1)
    confidence = max(0.1, 0.9 * f["quality"] - (0.45 if f["stale"] else 0) - (0.05 if f["phase"] == "PREOP" else 0))
    return {"need_score": score, "need_probability": prob_need, "icu_probability": round(prob_icu, 3),
            "intensive_hours": intensive, "intensive_hours_upper": round(intensive * 1.65, 1),
            "icu_los_hours": hours, "icu_los_upper": round(hours * 1.5, 1),
            "hospital_los_days": hospital, "hospital_los_upper": round(hospital * 1.5, 1),
            "confidence": round(confidence, 2), "contributions": sorted(points, key=lambda p: abs(p["points"]), reverse=True),
            "model_version": MODEL_VERSION, "mode": "demo", "interval_kind": "illustrative_range", "model_error": None}


def validate_prediction(p):
    required = {"need_score": (0, 100), "need_probability": (0, 1), "icu_probability": (0, 1),
                "intensive_hours": (0, 720), "intensive_hours_upper": (0, 1440),
                "icu_los_hours": (0, 1440), "icu_los_upper": (0, 2160),
                "hospital_los_days": (0, 365), "hospital_los_upper": (0, 730), "confidence": (0, 1)}
    if not isinstance(p, dict):
        raise ValueError("모델 응답은 JSON 객체여야 합니다")
    for key, (lo, hi) in required.items():
        v = p.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"유효하지 않은 모델 응답: {key}")
    for a, b in (("intensive_hours", "intensive_hours_upper"), ("icu_los_hours", "icu_los_upper"), ("hospital_los_days", "hospital_los_upper")):
        if p[a] > p[b]:
            raise ValueError(f"예측 범위 역전: {a}")
    contributions = p.get("contributions", [])
    if not isinstance(contributions, list) or len(contributions) > 30:
        raise ValueError("contributions는 최대 30개 항목입니다")
    for c in contributions:
        if not isinstance(c, dict) or not isinstance(c.get("label"), str) or not isinstance(c.get("detail", ""), str):
            raise ValueError("모델 설명 형식 오류")
        v = c.get("points")
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or abs(v) > 1000:
            raise ValueError("모델 설명 기여도 오류")
    return p


def predict(f, backend="demo"):
    if f["phase"] in ("PENDING", "DISCHARGED", "DECEASED", "TRANSFERRED"):
        result = demo_predict(f)
        result.update(need_score=None, need_probability=None, icu_probability=None,
                      intensive_hours=0, intensive_hours_upper=0, icu_los_hours=0, icu_los_upper=0,
                      hospital_los_days=0, hospital_los_upper=0, confidence=0, contributions=[],
                      mode="pending" if f["phase"] == "PENDING" else "completed", model_version="no-current-forecast")
        return result
    if backend == "demo":
        return demo_predict(f)
    try:
        url = os.environ.get("MODEL_URL", "")
        if not url.startswith(("http://", "https://")):
            raise ValueError("MODEL_URL 설정이 필요합니다")
        request = urllib.request.Request(url, data=json.dumps({"schema_version": "1.0", "as_of_minute": f["minute"], "features": f}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        key = os.environ.get("MODEL_API_KEY", "")
        if key:
            request.add_header("Authorization", "Bearer " + key)
        with urllib.request.urlopen(request, timeout=3) as response:
            p = validate_prediction(json.loads(response.read(1024 * 1024)))
        p["mode"] = "remote"
        p["model_version"] = str(p.get("model_version", "external"))[:80]
        p["interval_kind"] = str(p.get("interval_kind", "model_range"))[:50]
        p["model_error"] = None
        return p
    except Exception as exc:
        return {"need_score": None, "need_probability": None, "icu_probability": None,
                "intensive_hours": None, "intensive_hours_upper": None, "icu_los_hours": None,
                "icu_los_upper": None, "hospital_los_days": None, "hospital_los_upper": None,
                "mode": "unavailable", "confidence": 0, "contributions": [], "interval_kind": "unavailable",
                "model_error": "외부 예측 실패: " + type(exc).__name__, "model_version": "unavailable"}
