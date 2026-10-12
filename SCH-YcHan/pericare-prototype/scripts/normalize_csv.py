"""Normalize already linked CSVs, not arbitrary hospital schemas.

patients.csv: canonical scalar fields plus JSON columns conditions,
preop_labs, pre_admission, capabilities_required.
observations.csv: patient_id (app case id), minute, canonical signal columns.
beds.csv: canonical bed fields; capabilities is a JSON array.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.importer import UNITS, BOUNDS, validate_dataset


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def number(value):
    return None if value in (None, "") else float(value)


def boolean(value, unknown=False):
    if value in (None, ""):
        return None if unknown else False
    if str(value).lower() in ("true", "1", "yes"):
        return True
    if str(value).lower() in ("false", "0", "no"):
        return False
    raise ValueError("boolean 형식 오류: " + str(value))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("patients", "observations", "beds", "base-time", "clock-kind", "output"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--minute", type=int, default=0)
    ap.add_argument("--replay", action="store_true", help="미래 관측·실제 종료를 비공개 재생 사건으로 분리")
    ap.add_argument("--events", help="minute,patient_id,kind,location,outcome 열의 관측 사건 CSV")
    ap.add_argument("--horizon-minutes", type=int, default=10080)
    args = ap.parse_args()
    try:
        patients, events = [], []
        for row in rows(args.patients):
            p = {k: v for k, v in row.items() if v != ""}
            for k in ("age", "asa", "admission_minute", "operation_start_minute", "estimated_end_minute", "actual_end_minute", "preop_labs_minute"):
                p[k] = number(row.get(k))
            for k in ("planned_icu", "emergency"):
                p[k] = boolean(row.get(k))
            for k, default in (("conditions", []), ("preop_labs", {}), ("pre_admission", []), ("capabilities_required", ["ventilator"])):
                p[k] = json.loads(row[k]) if row.get(k) else default
            p.update(observations=[], treatments=[])
            if args.replay:
                if p["admission_minute"] > args.minute:
                    if not row.get("admission_location"):
                        raise ValueError("미래 입원에는 관측된 admission_location이 필요합니다")
                    events.append({"minute": p["admission_minute"], "patient_id": p["id"],
                                   "kind": "hospital_admission", "location": row["admission_location"]})
                    p["location"] = "NOT_ARRIVED"
                if p["actual_end_minute"] is not None and p["actual_end_minute"] > args.minute:
                    events.append({"minute": p["actual_end_minute"], "patient_id": p["id"], "kind": "operation_end"})
                    p["actual_end_minute"] = None
                discharge = number(row.get("discharge_minute"))
                if discharge is not None and discharge > args.minute:
                    if row.get("outcome") not in ("home", "death", "transfer"):
                        raise ValueError("병원 종료에는 home/death/transfer outcome이 필요합니다")
                    events.append({"minute": discharge, "patient_id": p["id"], "kind": "hospital_discharge", "outcome": row["outcome"]})
                    p["discharge_minute"] = None
            patients.append(p)
        by_id = {p["id"]: p for p in patients}
        for row in rows(args.observations):
            pid = row.get("patient_id")
            if pid not in by_id:
                raise ValueError("미확인 수술 사례: " + str(pid))
            o = {"minute": number(row.get("minute")), "source": row.get("source") or "csv"}
            for k in BOUNDS:
                o[k] = number(row.get(k))
            for k in ("ventilation", "crrt", "artifact", "oral_intake", "ambulating", "wound_ok", "discharge_plan_confirmed"):
                o[k] = boolean(row.get(k), unknown=True)
            o["pain_score"] = number(row.get("pain_score"))
            available = number(row.get("available_minute"))
            available = o["minute"] if available is None else available
            if args.replay and available > args.minute:
                events.append({"minute": available, "patient_id": pid, "kind": "observation", "observation": o})
            else:
                by_id[pid]["observations"].append(o)
        if args.events:
            if not args.replay:
                raise ValueError("사건 CSV는 --replay와 함께 사용하세요")
            for row in rows(args.events):
                event = {k: v for k, v in row.items() if v != ""}
                event["minute"] = number(event.get("minute"))
                events.append(event)
        beds = []
        for row in rows(args.beds):
            beds.append({"id": row["id"], "unit": row["unit"], "enabled": boolean(row.get("enabled", "true")),
                         "occupant_id": row.get("occupant_id") or None, "available_minute": number(row.get("available_minute")) or 0,
                         "capabilities": json.loads(row.get("capabilities") or "[]"),
                         "available_basis": row.get("available_basis") or "CSV 가용 예측", "closed_reason": row.get("closed_reason", "")})
        data = {"schema_version": "1.1" if args.replay else "1.0", "units": UNITS.copy(), "base_time": args.base_time, "minute": args.minute,
                "clock_kind": args.clock_kind, "patients": patients, "beds": beds}
        if args.replay:
            data.update(horizon_minutes=args.horizon_minutes, replay_events=events)
        validate_dataset(data)
        Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"{args.output}: {len(patients)}개 수술 사례, {len(beds)}개 병상")
    except Exception as exc:
        ap.exit(1, "변환 실패: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
