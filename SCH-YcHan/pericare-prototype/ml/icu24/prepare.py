"""Prepare auditable INSPIRE ICU24 landmarks without modifying source data.

The endpoint is RECORDED new ICU admission after surgery through 24 hours,
before recorded hospital exit. Missing ICU records are negatives only under
the documented INSPIRE recording convention, not proof of no clinical need.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import pandas as pd

from .features import (FEATURE_COLUMNS, FEATURE_VERSION, TASK, HORIZON_MINUTES,
                       LAB_ALIASES, LABS, BOUNDS, make_features, number)

REQUIRED_OPERATIONS = ("op_id", "subject_id", "hadm_id", "age", "asa", "orin_time",
                       "opstart_time", "opend_time", "admission_time", "discharge_time",
                       "icuin_time", "icuout_time", "inhosp_death_time")
VITAL_ALIASES = {"art_mbp": "art_map", "nibp_mbp": "nibp_map", "hr": "hr", "spo2": "spo2"}


def find_table(directory, name, required=True):
    directory = Path(directory)
    for path in (directory / f"{name}.csv", directory / f"{name}.csv" / f"{name}.csv",
                 directory / f"{name}.csv.gz"):
        if path.is_file():
            return path
    if required:
        raise ValueError(f"Missing table {name}.csv or {name}.csv.gz in {directory}")
    return None


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify_label(row, competing_operation=None):
    """Return (nullable label, reason); no future outcomes are feature inputs."""
    get = lambda key: number(row.get(key))
    admission, start, end, exit_time = (get(k) for k in
                                       ("admission_time", "opstart_time", "opend_time", "discharge_time"))
    icuin, icuout, death = (get(k) for k in ("icuin_time", "icuout_time", "inhosp_death_time"))
    if any(value is None for value in (admission, start, end, exit_time)):
        return None, "missing_followup_or_surgery_time"
    if not admission <= start < end <= exit_time:
        return None, "invalid_surgery_or_hospital_time_order"
    if icuin is None and icuout is not None:
        return None, "icu_exit_without_entry"
    if icuin is not None and admission <= icuin < end:
        return None, "icu_entry_before_operation_end"
    # Some source rows point to an ICU event in another admission. It must not
    # determine this admission's cohort membership or be labelled positive.
    qualifying_entry = icuin is not None and end <= icuin <= exit_time
    horizon = end + HORIZON_MINUTES
    if competing_operation is not None and competing_operation < min(horizon, exit_time):
        return None, "repeat_surgery_during_label_window"
    if death is not None and death < end:
        return None, "death_before_operation_end"
    if qualifying_entry and icuin <= horizon:
        if death is not None and death < icuin:
            return None, "death_before_recorded_icu_entry"
        return 1, "valid"
    if death is not None and death <= min(horizon, exit_time):
        return None, "death_before_endpoint_without_icu"
    # A later ICU admission is not positive for the specified 24h endpoint.
    # Live hospital exit before 24h terminates the within-institution endpoint.
    return 0, "valid"


def parse_landmarks(specification):
    values = []
    for item in specification.split(","):
        item = item.strip().lower()
        value = "preop" if item == "preop" else int(item)
        if value != "preop" and value < 0:
            raise ValueError("Intraoperative landmarks must be non-negative")
        if value not in values:
            values.append(value)
    if not values:
        raise ValueError("At least one landmark is required")
    return values


def operation_landmarks(operations, landmarks):
    rows, audit = [], Counter()
    sorted_ops = operations.sort_values(["subject_id", "hadm_id", "opstart_time", "op_id"])
    # Preserve all surgeries for prior ICU and intervening-surgery checks, while
    # restricting the primary cohort to the first operation of each admission.
    sorted_ops = sorted_ops.copy()
    sorted_ops["next_operation_start"] = sorted_ops.groupby(["subject_id", "hadm_id"], dropna=False).opstart_time.shift(-1)
    first_operations = sorted_ops.drop_duplicates(["subject_id", "hadm_id"], keep="first")
    audit["operations_after_first_in_admission"] = len(operations) - len(first_operations)
    intervals = {}
    known_icu = sorted_ops.loc[sorted_ops.icuin_time.notna() & sorted_ops.icuout_time.notna(),
                               ["subject_id", "hadm_id", "icuin_time", "icuout_time"]].drop_duplicates()
    for subject, admission_id, entry, exit_ in known_icu.itertuples(index=False, name=None):
        intervals.setdefault((str(subject), str(admission_id)), []).append((float(entry), float(exit_)))
    for first in first_operations.to_dict("records"):
        if any(pd.isna(first.get(key)) or not str(first.get(key)).strip() for key in ("subject_id", "hadm_id", "op_id")):
            audit["missing_identifier"] += 1
            continue
        age, asa = number(first.get("age")), number(first.get("asa"))
        if age is None or not 18 <= age <= 90 or asa is None or not 1 <= asa <= 5:
            audit["age_or_asa_outside_cohort"] += 1
            continue
        next_start = number(first.get("next_operation_start"))
        if (number(first.get("icuin_time")) is not None and number(first.get("discharge_time")) is not None
                and first["icuin_time"] > first["discharge_time"]):
            audit["nonqualifying_icu_entry_after_index_discharge"] += 1
        if (number(first.get("inhosp_death_time")) is not None and number(first.get("discharge_time")) is not None
                and first["inhosp_death_time"] > first["discharge_time"]):
            audit["nonqualifying_death_after_index_discharge"] += 1
        target, label_status = classify_label(first, next_start)
        if target is None:
            audit[label_status] += 1
            continue
        start, end = number(first["opstart_time"]), number(first["opend_time"])
        orin, admission = number(first.get("orin_time")), number(first.get("admission_time"))
        emitted = False
        for landmark in landmarks:
            minute = orin if landmark == "preop" else start + landmark
            phase = "PREOP" if landmark == "preop" else "OR"
            if landmark == "preop" and (minute is None or not admission <= minute <= start):
                audit["invalid_preop_anchor"] += 1
                continue
            if minute is None or minute >= end:
                audit["landmark_after_surgery_end"] += 1
                continue
            if minute < admission:
                audit["landmark_before_admission"] += 1
                continue
            if any(entry <= minute < exit_ for entry, exit_ in intervals.get((str(first["subject_id"]), str(first["hadm_id"])), [])):
                audit["already_in_recorded_icu_at_landmark"] += 1
                continue
            row = {"subject_id": str(first["subject_id"]), "hadm_id": str(first["hadm_id"]),
                   "op_id": str(first["op_id"]), "landmark_minute": float(minute),
                   "anchor_kind": str(landmark), "phase": phase,
                   "y_icu24": int(target), "label_status": label_status,
                   "_operation": first}
            rows.append(row)
            emitted = True
        if emitted:
            audit["eligible_operations"] += 1
    if not rows:
        raise ValueError(f"No eligible landmarks: {dict(audit)}")
    return rows, dict(audit)


def load_labs(path, rows, delay_minutes, lookback_minutes, chunksize=250000):
    """Chunk scan, then backward as-of joins by subject and availability time."""
    subjects = {r["subject_id"] for r in rows}
    pieces = []
    for chunk in pd.read_csv(path, usecols=["subject_id", "chart_time", "item_name", "value"],
                             dtype={"subject_id": str, "item_name": str}, chunksize=chunksize):
        chunk = chunk.loc[chunk.subject_id.isin(subjects) & chunk.item_name.isin(LAB_ALIASES)].copy()
        if chunk.empty:
            continue
        chunk["name"] = chunk.item_name.map(LAB_ALIASES)
        chunk["chart_time"] = pd.to_numeric(chunk.chart_time, errors="coerce").astype(float)
        chunk["value"] = pd.to_numeric(chunk.value, errors="coerce")
        chunk = chunk.dropna(subset=["chart_time", "value"])
        chunk["available_time"] = (chunk.chart_time + delay_minutes).astype(float)
        pieces.append(chunk[["subject_id", "name", "chart_time", "available_time", "value"]])
    output = {i: {} for i in range(len(rows))}
    if not pieces:
        return output
    labs = pd.concat(pieces, ignore_index=True)
    queries = pd.DataFrame({"_index": list(range(len(rows))),
                            "subject_id": [r["subject_id"] for r in rows],
                            "landmark_minute": [r["landmark_minute"] for r in rows]})
    queries = queries.sort_values("landmark_minute")
    for name in LABS:
        selected = labs.loc[labs.name == name].copy()
        if selected.empty:
            continue
        # Equal-time duplicate results are median-aggregated, never selected by
        # input file order (the source itself is already discretized).
        selected = selected.groupby(["subject_id", "chart_time", "available_time"], as_index=False).value.median()
        selected = selected.sort_values("available_time")
        matched = pd.merge_asof(queries, selected, left_on="landmark_minute", right_on="available_time",
                                by="subject_id", direction="backward", tolerance=float(lookback_minutes))
        matched = matched.loc[matched.value.notna() & (matched.landmark_minute - matched.chart_time <= lookback_minutes)]
        for item in matched.itertuples(index=False, name=None):
            index, _, _, measured, available, value = item
            output[int(index)][name] = (float(value), float(measured), float(available))
    return output


def load_vitals(path, rows, chunksize=250000):
    wanted = {r["op_id"] for r in rows if r["phase"] == "OR"}
    if not wanted:
        return {}
    windows = {}
    for row in rows:
        if row["op_id"] not in wanted:
            continue
        lower, upper = windows.get(row["op_id"], (row["landmark_minute"] - 30, row["landmark_minute"]))
        windows[row["op_id"]] = (min(lower, row["landmark_minute"] - 30), max(upper, row["landmark_minute"]))
    pieces = []
    for chunk in pd.read_csv(path, usecols=["op_id", "chart_time", "item_name", "value"],
                             dtype={"op_id": str, "item_name": str}, chunksize=chunksize):
        chunk = chunk.loc[chunk.op_id.isin(wanted) & chunk.item_name.isin(VITAL_ALIASES)].copy()
        if chunk.empty:
            continue
        chunk.chart_time = pd.to_numeric(chunk.chart_time, errors="coerce")
        chunk.value = pd.to_numeric(chunk.value, errors="coerce")
        low = chunk.op_id.map(lambda op: windows[op][0])
        high = chunk.op_id.map(lambda op: windows[op][1])
        chunk = chunk.loc[chunk.chart_time.ge(low) & chunk.chart_time.le(high)]
        chunk["signal"] = chunk.item_name.map(VITAL_ALIASES)
        pieces.append(chunk[["op_id", "chart_time", "signal", "value"]])
    if not pieces:
        return {}
    table = pd.concat(pieces, ignore_index=True).pivot_table(index=["op_id", "chart_time"], columns="signal", values="value", aggfunc="median")
    output = {}
    for (op_id, minute), item in table.iterrows():
        arterial = number(item.get("art_map"), BOUNDS["map"])
        observation = {"minute": float(minute), "map": arterial if arterial is not None else number(item.get("nibp_map"), BOUNDS["map"]),
                       "hr": number(item.get("hr")), "spo2": number(item.get("spo2"))}
        output.setdefault(str(op_id), []).append(observation)
    return output


def prepare(data_dir, output_dir, landmarks="preop", include_labs=False,
            lab_delay_minutes=60, lab_lookback_days=30, chunksize=250000):
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    if output_dir == data_dir or data_dir in output_dir.parents:
        raise ValueError("Output must be outside the read-only raw dataset")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Output directory must be empty; do not overwrite an existing experiment")
    if lab_delay_minutes < 0 or lab_lookback_days <= 0:
        raise ValueError("Invalid laboratory time settings")
    operations_path = find_table(data_dir, "operations")
    operations = pd.read_csv(operations_path, dtype={"op_id": str, "subject_id": str, "hadm_id": str})
    missing = set(REQUIRED_OPERATIONS) - set(operations.columns)
    if missing:
        raise ValueError(f"Missing operation columns: {sorted(missing)}")
    if operations.op_id.isna().any() or operations.op_id.duplicated().any():
        raise ValueError("Operation IDs must be present and unique")
    for column in ("age", "asa", "orin_time", "opstart_time", "opend_time", "admission_time", "discharge_time", "icuin_time", "icuout_time", "inhosp_death_time"):
        operations[column] = pd.to_numeric(operations[column], errors="coerce")
    print(f"Building label cohort from {len(operations)} source operations...", flush=True)
    rows, exclusions = operation_landmarks(operations, parse_landmarks(landmarks))
    sources = {"operations": operations_path}
    lab_values = {}
    if include_labs:
        print("Scanning laboratory table using only backward, delayed measurements...", flush=True)
        sources["labs"] = find_table(data_dir, "labs")
        lab_values = load_labs(sources["labs"], rows, lab_delay_minutes, lab_lookback_days * 1440, chunksize)
    signal_values = {}
    if any(row["phase"] == "OR" for row in rows):
        print("Scanning intraoperative vitals for requested past windows...", flush=True)
        sources["vitals"] = find_table(data_dir, "vitals")
        signal_values = load_vitals(sources["vitals"], rows, chunksize)
    output_rows = []
    for index, row in enumerate(rows):
        operation = row.pop("_operation")
        minute = row["landmark_minute"]
        patient_labs = lab_values.get(index, {})
        payload = {"minute": minute, "phase": row["phase"], "age": operation.get("age"),
                   "asa": operation.get("asa"), "weight": operation.get("weight"), "height": operation.get("height"),
                   "sex": operation.get("sex"), "department": operation.get("department"),
                   "anesthesia_type": operation.get("antype"), "emergency": operation.get("emop"),
                   "elapsed_operation_minutes": max(0, minute - float(operation["opstart_time"])),
                   "signal_window": [] if row["phase"] == "PREOP" else signal_values.get(row["op_id"], []),
                   "preop_labs": {key: value[0] for key, value in patient_labs.items()},
                   "max_lab_age_minutes": lab_lookback_days * 1440,
                   "preop_lab_measurement_times": {key: value[1] for key, value in patient_labs.items()},
                   "preop_lab_times": {key: value[2] for key, value in patient_labs.items()}}
        output_rows.append({**row, **make_features(payload)})
    frame = pd.DataFrame(output_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "prepared.csv"
    frame.to_csv(output_path, index=False, encoding="utf-8")
    synthetic = (data_dir / "SYNTHETIC_ONLY.json").is_file()
    audit = {"task": TASK, "horizon_minutes": HORIZON_MINUTES, "feature_version": FEATURE_VERSION,
             "dataset_kind": "synthetic" if synthetic else "inspire", "landmarks": landmarks,
             "input_operations": len(operations), "input_patients": int(operations.subject_id.nunique()),
             "prepared_rows": len(frame), "prepared_patients": int(frame.subject_id.nunique()),
             "prepared_operations": int(frame.op_id.nunique()), "positive_rows": int(frame.y_icu24.sum()),
             "exclusions": exclusions, "missing_features": frame[list(FEATURE_COLUMNS)].isna().sum().to_dict(),
             "lab_delay_minutes": lab_delay_minutes, "lab_lookback_days": lab_lookback_days,
             "include_labs": include_labs, "prepared_sha256": sha256(output_path),
             "source_files": {name: {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)} for name, path in sources.items()},
             "endpoint_definition": "Recorded new ICU entry in [operation end, operation end+1440min], before recorded hospital exit; absence interpreted under INSPIRE recording convention.",
             "limitations": ["Negative means no qualifying recorded admission, not no clinical need; transfers/unrecorded outside-hospital admissions cannot be adjudicated.",
                             "Laboratory delay is an explicit assumption: source chart_time does not establish result availability.",
                             "Preoperative operation characteristics are retrospectively recorded; prospective availability needs institutional verification.",
                             "No true population calendar, bed inventory, planned ICU status or unplanned-admission label is reconstructed."]}
    (output_dir / "cohort_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: audit[key] for key in ("dataset_kind", "prepared_rows", "prepared_patients", "prepared_operations", "positive_rows")}), flush=True)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--landmarks", default="preop", help="preop, or comma-separated elapsed operation minutes such as preop,30,60,90")
    parser.add_argument("--labs", action="store_true")
    parser.add_argument("--lab-delay-minutes", type=float, default=60)
    parser.add_argument("--lab-lookback-days", type=float, default=30)
    parser.add_argument("--chunksize", type=int, default=250000)
    args = parser.parse_args()
    prepare(args.data_dir, args.output_dir, args.landmarks, args.labs,
            args.lab_delay_minutes, args.lab_lookback_days, args.chunksize)


if __name__ == "__main__":
    main()
