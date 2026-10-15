"""Strict canonical JSON import; hospital-specific crosswalks stay upstream."""
import copy
from datetime import datetime
from .engine import AppError, finite_number
from .demo import make_small_demo
from .version import RUNTIME_VERSION

UNITS = {"map": "mmHg", "hr": "bpm", "spo2": "%", "lactate": "mmol/L", "hemoglobin": "g/dL",
         "norepi": "ug/kg/min", "urine_ml_kg_h": "mL/kg/h"}
BOUNDS = {"map": (20, 200), "hr": (20, 220), "spo2": (50, 100), "lactate": (0, 30),
          "hemoglobin": (2, 22), "norepi": (0, 5), "urine_ml_kg_h": (0, 20)}


def text(value, label, maximum=150):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AppError(f"{label}: 1~{maximum}자 문자열이 필요합니다")
    return value.strip()


def validate_observation(obs, current):
    if not isinstance(obs, dict):
        raise AppError("관측은 JSON 객체여야 합니다")
    o = {"minute": finite_number(obs.get("minute"), "관측 시각", -5256000, current)}
    if "available_minute" in obs:
        o["available_minute"] = finite_number(obs["available_minute"], "관측 가용 시각", o["minute"], current)
    for key, bounds in BOUNDS.items():
        value = obs.get(key)
        o[key] = None if value is None else finite_number(value, key, *bounds)
    for key in ("ventilation", "crrt", "artifact", "oral_intake", "ambulating", "wound_ok", "discharge_plan_confirmed"):
        if key in obs and obs[key] is not None and not isinstance(obs[key], bool):
            raise AppError(f"{key}는 boolean 또는 null이어야 합니다")
        o[key] = obs.get(key)
    o["pain_score"] = None if obs.get("pain_score") is None else finite_number(obs["pain_score"], "통증 점수", 0, 10)
    o["source"] = text(obs.get("source", "import"), "관측 출처", 80)
    return o


def reconcile_snapshot_beds(patients, beds):
    """Require two supplied descriptions of physical occupancy to agree."""
    by_patient = {p["id"]: p for p in patients}
    by_bed = {b["id"]: b for b in beds}
    for bed in beds:
        p = by_patient.get(bed["occupant_id"])
        if not p:
            continue  # External occupants remain explicit, unmodelled occupancy.
        location = p["location"]
        if location in ("ICU", "SICU", "CCU"):
            if location != "ICU" and location != bed["unit"]:
                raise AppError("환자 ICU 구역과 병상 병동이 다릅니다: " + p["id"])
            # The supplied occupant-to-bed link is an observed location.
            p["location"] = bed["id"]
        elif location != bed["id"]:
            raise AppError("환자 위치와 실제 점유 병상 ID가 다릅니다: " + p["id"])
        p["icu_bed_id"] = bed["id"]
    for p in patients:
        bed = by_bed.get(p["location"])
        if bed:
            if bed["occupant_id"] != p["id"]:
                raise AppError("환자 위치와 병상 재실 정보가 일치하지 않습니다: " + p["id"])
            p["icu_bed_id"] = bed["id"]


def validate_dataset(data):
    if not isinstance(data, dict) or data.get("schema_version") not in ("1.0", "1.1"):
        raise AppError("schema_version='1.0' 또는 '1.1'인 JSON 데이터가 필요합니다")
    if data.get("units") != UNITS:
        raise AppError("units가 표준 단위와 다릅니다. 변환 후 가져오세요")
    base = data.get("base_time")
    try:
        dt = datetime.fromisoformat(base)
        if dt.utcoffset() is None:
            raise ValueError()
    except (TypeError, ValueError):
        raise AppError("base_time은 시간대가 있는 ISO 8601 시각이어야 합니다")
    current = finite_number(data.get("minute", 0), "현재 시각", 0, 525600)
    if int(current) != current:
        raise AppError("현재 시각 minute은 정수여야 합니다")
    horizon = finite_number(data.get("horizon_minutes", current + 10080), "운영 종료 시각", current, current + 43200)
    if int(horizon) != horizon:
        raise AppError("운영 종료 시각은 정수입니다")
    clock_kind = data.get("clock_kind")
    if clock_kind not in ("synthetic_shared", "hospital_shared", "patient_relative", "case_relative"):
        raise AppError("clock_kind를 명시하세요")
    raw = data.get("patients")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 1000:
        raise AppError("환자는 1~1000명입니다")
    patients, seen, operation_ids = [], set(), set()
    for p in raw:
        if not isinstance(p, dict):
            raise AppError("환자 형식 오류")
        pid = text(p.get("id"), "환자 ID", 80)
        if pid in seen:
            raise AppError("중복 환자 ID: " + pid)
        seen.add(pid)
        subject_id = text(p.get("subject_id", pid), "공통 환자키", 80)
        admission_id = text(p.get("admission_id", "ADM-" + pid), "입원키", 80)
        operation_id = text(p.get("operation_id", pid), "수술키", 80)
        if operation_id in operation_ids:
            raise AppError("중복 수술키: " + operation_id)
        operation_ids.add(operation_id)
        start = finite_number(p.get("operation_start_minute"), "수술 시작", -5256000, current + 10080)
        end = finite_number(p.get("estimated_end_minute"), "예상 종료", start + 1, current + 10080)
        actual = p.get("actual_end_minute")
        if actual is not None:
            actual = finite_number(actual, "관측된 실제 종료", start, current)
        admission = finite_number(p.get("admission_minute"), "입원 시각", -5256000,
                                  min(start, horizon) if data["schema_version"] == "1.1" else min(start, current))
        pending = admission > current
        if pending and p.get("location") != "NOT_ARRIVED":
            raise AppError("미래 입원 사례의 location은 NOT_ARRIVED여야 합니다")
        unit = p.get("preferred_unit", "SICU")
        if unit not in ("SICU", "CCU"):
            raise AppError("preferred_unit은 SICU 또는 CCU입니다")
        observations = p.get("observations", [])
        if not isinstance(observations, list) or len(observations) > 1000:
            raise AppError("환자별 관측은 최대 1000개입니다")
        times = set()
        obs = []
        for o in observations:
            normalized = validate_observation(o, current)
            if normalized["minute"] in times:
                raise AppError("중복 관측 시각: " + pid)
            times.add(normalized["minute"])
            obs.append(normalized)
        conditions = p.get("conditions", [])
        if not isinstance(conditions, list) or len(conditions) > 30:
            raise AppError("conditions 형식 오류")
        conditions = [text(v, "병력", 150) for v in conditions]
        labs = p.get("preop_labs", {})
        if not isinstance(labs, dict):
            raise AppError("preop_labs 형식 오류")
        lab_ranges = {"hemoglobin": (2, 22), "creatinine": (0, 30), "platelets": (0, 2000), "albumin": (0, 10), "lactate": (0, 30)}
        labs = {k: finite_number(v, k, *lab_ranges[k]) for k, v in labs.items() if k in lab_ranges and v is not None}
        lab_time = p.get("preop_labs_minute")
        lab_times = p.get("preop_lab_times", {})
        if not isinstance(lab_times, dict):
            raise AppError("preop_lab_times 형식 오류")
        lab_times = {k: finite_number(v, k + " 검사 가용 시각", -5256000, admission if pending else current)
                     for k, v in lab_times.items() if k in labs}
        lab_measurement_times = p.get("preop_lab_measurement_times", {})
        if not isinstance(lab_measurement_times, dict):
            raise AppError("preop_lab_measurement_times 형식 오류")
        lab_measurement_times = {k: finite_number(v, k + " 검사 측정 시각", -5256000, min(start, admission if pending else current))
                                 for k, v in lab_measurement_times.items() if k in labs}
        if any(lab_measurement_times[k] > lab_times[k] for k in lab_measurement_times if k in lab_times):
            raise AppError("검사 가용 시각은 측정 시각보다 빠를 수 없습니다")
        if labs:
            if any(k not in lab_times for k in labs):
                finite_number(lab_time, "수술 전 검사 관측 시각", -5256000, min(start, admission if pending else current))
        pre = p.get("pre_admission", [])
        if not isinstance(pre, list) or len(pre) > 100:
            raise AppError("입원 전 기록 형식 오류")
        if any(not isinstance(v, dict) for v in pre):
            raise AppError("입원 전 기록 항목은 JSON 객체여야 합니다")
        pre = [{"minute": finite_number(v.get("minute"), "입원 전 기록 시각", -5256000, admission - 0.001),
                "type": text(v.get("type"), "기록 종류", 50), "label": text(v.get("label"), "기록 내용", 500)} for v in pre if isinstance(v, dict)]
        requirements = p.get("capabilities_required", ["ventilator"])
        if not isinstance(requirements, list) or any(x not in ("ventilator", "crrt") for x in requirements):
            raise AppError("필요 장비 형식 오류")
        for boolean in ("emergency", "planned_icu"):
            if boolean in p and not isinstance(p[boolean], bool):
                raise AppError(boolean + "는 boolean이어야 합니다")
        treatments = p.get("treatments", [])
        if not isinstance(treatments, list) or len(treatments) > 500:
            raise AppError("처치는 최대 500개입니다")
        normalized_treatments = []
        for t in treatments:
            if not isinstance(t, dict):
                raise AppError("처치 형식 오류")
            normalized_treatments.append({"minute": finite_number(t.get("minute"), "처치 시각", -5256000, current),
                "kind": text(t.get("kind"), "처치 종류", 80), "label": text(t.get("label"), "처치 이름", 150),
                "dose": finite_number(t.get("dose", 0), "처치 용량", 0, 100000), "unit": text(t.get("unit", "미상"), "처치 단위", 50)})
        asa = finite_number(p.get("asa"), "ASA", 1, 5)
        if int(asa) != asa:
            raise AppError("ASA는 1~5 정수입니다")
        status = p.get("status", "active")
        if status not in ("active", "discharged", "deceased", "transferred"):
            raise AppError("환자 status 형식 오류")
        discharge = p.get("discharge_minute")
        if status != "active":
            discharge = finite_number(discharge, "관측된 병원 종료 시각", admission, current)
        elif discharge is not None:
            raise AppError("활성 환자에 미래·완료 퇴원 시각을 넣을 수 없습니다")
        if discharge is not None and (any(o["minute"] > discharge for o in obs)
                                      or any(t["minute"] > discharge for t in normalized_treatments)
                                      or (actual is not None and actual > discharge)):
            raise AppError("입원 종료 이후의 관측·처치·수술 종료가 포함되어 있습니다: " + pid)
        if pending and (observations or treatments or actual is not None):
            raise AppError("미래 입원 사례의 관측·처치·실제 수술 종료는 replay_events에 분리하세요")
        group = p.get("procedure_group", "unknown")
        if group not in ("minor", "standard", "major", "complex", "unknown"):
            raise AppError("procedure_group 형식 오류")
        patients.append({"id": pid, "subject_id": subject_id, "admission_id": admission_id, "operation_id": operation_id,
                         "name": text(p.get("name", pid), "표시 이름", 80),
                         "age": finite_number(p.get("age"), "나이", 18, 100), "sex": p.get("sex", "U") if p.get("sex", "U") in ("M", "F", "U") else "U",
                         "weight": None if p.get("weight") is None else finite_number(p["weight"], "체중 kg", 20, 350),
                         "height": None if p.get("height") is None else finite_number(p["height"], "키 cm", 80, 250),
                         "anesthesia_type": None if p.get("anesthesia_type") is None else text(p["anesthesia_type"], "마취 종류", 80),
                         "asa": asa, "surgery": text(p.get("surgery"), "수술명"),
                         "department": text(p.get("department", "SURG"), "진료과", 30), "location": text(p.get("location", "OR"), "위치", 60),
                         "operation_start_minute": start, "estimated_end_minute": end, "actual_end_minute": actual,
                         "admission_minute": admission, "preferred_unit": unit, "emergency": p.get("emergency", False),
                         "planned_icu": p.get("planned_icu", False), "conditions": conditions, "preop_labs": labs,
                         "preop_labs_minute": lab_time, "preop_lab_times": lab_times,
                         "preop_lab_measurement_times": lab_measurement_times, "pre_admission": pre, "observations": sorted(obs, key=lambda v: v["minute"]),
                         "treatments": normalized_treatments, "source": "import", "capabilities_required": requirements,
                         "procedure_group": group, "status": "scheduled" if pending else status, "discharge_minute": discharge})
    raw_beds = data.get("beds", [])
    if not isinstance(raw_beds, list) or not 0 <= len(raw_beds) <= 100:
        raise AppError("병상은 0~100개입니다. 재고 미제공이면 빈 목록을 사용하세요")
    beds, ids, occupants = [], set(), set()
    for b in raw_beds:
        if not isinstance(b, dict):
            raise AppError("병상 형식 오류")
        bid = text(b.get("id"), "병상 ID", 80)
        if bid in ids:
            raise AppError("병상 ID 중복")
        ids.add(bid)
        if b.get("unit") not in ("SICU", "CCU"):
            raise AppError("병상 병동 오류")
        if not isinstance(b.get("enabled", True), bool):
            raise AppError("병상 enabled는 boolean입니다")
        occupant = b.get("occupant_id")
        if occupant is not None:
            occupant = text(occupant, "재실 환자", 80)
            if occupant in occupants:
                raise AppError("동일 환자의 병상 중복 점유")
            occupants.add(occupant)
            matching = next((p for p in patients if p["id"] == occupant), None)
            if matching and matching["status"] != "active":
                raise AppError("입원 예정·종료 환자가 병상을 점유할 수 없습니다")
        capabilities = b.get("capabilities", [])
        if not isinstance(capabilities, list) or any(x not in ("ventilator", "crrt") for x in capabilities):
            raise AppError("병상 장비 형식 오류")
        forecast_known = b.get("availability_forecast_known", "available_minute" in b)
        if not isinstance(forecast_known, bool) or (forecast_known and "available_minute" not in b):
            raise AppError("availability_forecast_known이 true이면 가용 예상 시각을 제공하세요")
        beds.append({"id": bid, "unit": b["unit"], "capabilities": capabilities, "enabled": b.get("enabled", True),
                     "occupant_id": occupant, "available_minute": finite_number(b.get("available_minute", current), "병상 가용 시각", 0, current + 43200),
                     "availability_forecast_known": forecast_known,
                     "available_basis": text(b.get("available_basis", "제공된 가용 예측" if forecast_known else "가용 예상 시각 미제공"), "가용 근거", 100),
                     "closed_reason": str(b.get("closed_reason", ""))[:150]})
    reconcile_snapshot_beds(patients, beds)
    raw_events = data.get("replay_events", [])
    if not isinstance(raw_events, list) or len(raw_events) > 100000:
        raise AppError("replay_events는 최대 100000개입니다")
    if raw_events and data["schema_version"] != "1.1":
        raise AppError("기록 재생은 schema_version='1.1'을 사용하세요")
    events, admissions, unique_events = [], set(), set()
    for event in raw_events:
        if not isinstance(event, dict):
            raise AppError("재생 사건은 객체여야 합니다")
        pid = text(event.get("patient_id"), "재생 환자 ID", 80)
        if pid not in seen:
            raise AppError("재생 사건의 환자가 기준표에 없습니다: " + pid)
        minute = finite_number(event.get("minute"), "재생 가용 시각", current + 1, horizon)
        if int(minute) != minute:
            raise AppError("재생 사건 시각은 정수 분입니다")
        kind = event.get("kind")
        if kind not in ("hospital_admission", "observation", "operation_start", "operation_end", "location", "hospital_discharge"):
            raise AppError("지원하지 않는 재생 사건입니다")
        key = (pid, minute, kind)
        if key in unique_events:
            raise AppError("중복 재생 사건")
        unique_events.add(key)
        normalized = {"patient_id": pid, "minute": int(minute), "kind": kind}
        patient = next(p for p in patients if p["id"] == pid)
        if kind == "observation":
            normalized["observation"] = validate_observation(event.get("observation"), minute)
        elif kind in ("location", "operation_start"):
            location = text(event.get("location"), "관측 위치", 60)
            if location in ("NOT_ARRIVED", "DISCHARGED", "DECEASED", "TRANSFERRED"):
                raise AppError("입퇴원은 전용 재생 사건으로 기록하세요")
            normalized["location"] = location
        elif kind == "hospital_discharge":
            if event.get("outcome") not in ("home", "death", "transfer"):
                raise AppError("퇴원·사망·전원 outcome을 명시하세요")
            normalized["outcome"] = event["outcome"]
        elif kind == "operation_end" and "actual_end_minute" in event:
            normalized["actual_end_minute"] = finite_number(event["actual_end_minute"], "실제 수술 종료 시각", -5256000, minute)
        elif kind == "hospital_admission":
            if patient["admission_minute"] != minute or pid in admissions:
                raise AppError("입원 사건과 입원 시각이 일치하지 않거나 중복입니다")
            admissions.add(pid)
            normalized["location"] = text(event.get("location", "PREOP"), "입원 위치", 60)
            if normalized["location"] in ("NOT_ARRIVED", "DISCHARGED", "DECEASED", "TRANSFERRED"):
                raise AppError("입원 사건에는 실제 입원 구역을 지정하세요")
        if minute < patient["admission_minute"]:
            raise AppError("입원 이전에 발생하는 입원 중 사건입니다")
        events.append(normalized)
    if any(p["status"] == "scheduled" and p["id"] not in admissions for p in patients):
        raise AppError("미래 입원 사례에는 hospital_admission 재생 사건이 필요합니다")
    order = {"hospital_admission": 0, "operation_start": 1, "observation": 2,
             "operation_end": 3, "location": 4, "hospital_discharge": 5}
    events.sort(key=lambda e: (e["minute"], order[e["kind"]], e["patient_id"]))
    finished = {p["id"]: p["discharge_minute"] for p in patients if p["status"] in ("discharged", "deceased", "transferred")}
    ended_operations = {p["id"] for p in patients if p["actual_end_minute"] is not None}
    starts = {p["id"]: p["operation_start_minute"] for p in patients}
    for event in events:
        if event["patient_id"] in finished:
            if event["kind"] == "observation" and event["observation"]["minute"] <= finished[event["patient_id"]]:
                continue  # Late chart receipt belongs to history, never reopens the encounter.
            raise AppError("종료된 입원 이후의 재생 사건입니다")
        if event["kind"] == "hospital_discharge":
            finished[event["patient_id"]] = event["minute"]
        elif event["kind"] == "operation_start":
            if event["patient_id"] in ended_operations:
                raise AppError("이미 종료된 수술을 다시 시작할 수 없습니다")
            starts[event["patient_id"]] = event["minute"]
        elif event["kind"] == "operation_end":
            if event["patient_id"] in ended_operations or event.get("actual_end_minute", event["minute"]) < starts[event["patient_id"]]:
                raise AppError("수술 종료 시각·중복 기록을 확인하세요")
            ended_operations.add(event["patient_id"])
    empty = make_small_demo()
    empty.update(base_time=base, minute=int(current), source="import", clock_kind=clock_kind, patients=patients, beds=beds,
                 trajectories={}, reservations=[], events=[], notes=[], prediction_history={}, active_scenarios={},
                 runtime_version=RUNTIME_VERSION, horizon_minutes=int(horizon), arrival_queue=[], replay_events=events, replay_cursor=0, ward_beds=[])
    for k in ("predictions", "recommendations", "alerts"):
        empty.pop(k, None)
    return empty


def export_canonical(state):
    # Import/export intentionally excludes private simulation truth and future trajectories.
    patients = []
    for p in state["patients"]:
        if p["admission_minute"] > state["minute"]:
            continue
        item = {k: copy.deepcopy(v) for k, v in p.items() if k not in ("course", "admission_handoff_due", "admission_wait")}
        item["observations"] = item["observations"][-12 if p.get("status") in ("discharged", "deceased", "transferred") else -72:]
        item["treatments"] = item["treatments"][-50:]
        patients.append(item)
    return {"schema_version": "1.1", "units": copy.deepcopy(UNITS), "base_time": state["base_time"], "minute": state["minute"],
            "clock_kind": state["clock_kind"], "horizon_minutes": state["horizon_minutes"],
            "patients": patients,
            "beds": copy.deepcopy(state["beds"])}
