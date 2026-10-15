"""Export one prepared PREOP case as a local, future-free PeriCare snapshot.

The schedule is explicitly supplied by the operator. Actual future operation,
ICU, death and discharge times and outcome labels are never exported.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from .features import LABS, TASK, number

DISPLAY_ORIGIN = "2000-01-01T00:00:00+00:00"


def _table_path(directory: Path) -> Path:
    for path in (directory / "operations.csv", directory / "operations.csv" / "operations.csv",
                 directory / "operations.csv.gz"):
        if path.is_file():
            return path
    raise ValueError("operations.csv or operations.csv.gz is missing")


def _rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def _positive(value, name):
    value = number(value)
    if value is None or value <= 0:
        raise ValueError(f"{name} must be a finite positive number supplied by the operator")
    return value


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_snapshot(data_dir, prepared, planned_start_in_minutes, estimated_duration_minutes,
                  op_id=None):
    """Build a single PREOP snapshot; never infer a plan from observed outcomes."""
    data_dir, prepared = Path(data_dir).resolve(), Path(prepared).resolve()
    start = _positive(planned_start_in_minutes, "planned_start_in_minutes")
    duration = _positive(estimated_duration_minutes, "estimated_duration_minutes")
    if start + duration > 10080:
        raise ValueError("Planned start plus estimated duration must be within 10080 minutes")
    metadata_path = prepared.parent / "cohort_audit.json"
    if not metadata_path.is_file():
        raise ValueError("cohort_audit.json next to prepared.csv is required for feature provenance")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("task") != TASK:
        raise ValueError("Prepared metadata is not an ICU24 cohort")
    if metadata.get("prepared_sha256") != _sha256(prepared):
        raise ValueError("Prepared CSV checksum does not match its cohort metadata")
    delay = number(metadata.get("lab_delay_minutes"))
    if delay is None or delay < 0:
        raise ValueError("Valid preparation lab_delay_minutes metadata is required")

    selected = None
    for row in _rows(prepared):
        if op_id is not None and str(row.get("op_id", "")) != str(op_id):
            continue
        if row.get("phase") == "PREOP" and row.get("label_status") == "valid":
            selected = row
            break
    if selected is None:
        raise ValueError("No valid PREOP row matches the selected operation")
    landmark = number(selected.get("landmark_minute"))
    if landmark is None:
        raise ValueError("Selected PREOP landmark is invalid")
    admission = None
    for operation in _rows(_table_path(data_dir)):
        if str(operation.get("op_id", "")) == selected["op_id"]:
            # This is the only time taken from the source operations table.
            admission = number(operation.get("admission_time"))
            break
    if admission is None or admission > landmark:
        raise ValueError("The source admission time is absent or after the snapshot")

    patient = {
        "id": "INSPIRE-" + selected["op_id"], "subject_id": selected["subject_id"],
        "admission_id": selected["hadm_id"], "operation_id": selected["op_id"],
        "name": "INSPIRE " + selected["op_id"], "age": number(selected.get("age")),
        "sex": selected.get("sex") if selected.get("sex") in ("M", "F") else "U",
        "asa": number(selected.get("asa")), "surgery": "수술 종류 미상 (INSPIRE)",
        "department": selected.get("department") or "unknown", "location": "PREOP",
        "anesthesia_type": selected.get("anesthesia_type") or None,
        "admission_minute": admission - landmark,
        "operation_start_minute": start, "estimated_end_minute": start + duration,
        "actual_end_minute": None,
        "conditions": [], "capabilities_required": [], "procedure_group": "unknown",
        "pre_admission": [], "observations": [], "treatments": [],
        "preop_labs": {}, "preop_lab_times": {}, "preop_lab_measurement_times": {},
    }
    for key, bounds in (("weight", (20, 250)), ("height", (100, 230))):
        value = number(selected.get(key), bounds)
        if value is not None:
            patient[key] = value
    emergency = number(selected.get("emergency"))
    if emergency in (0, 1):
        patient["emergency"] = bool(emergency)
    for lab in LABS:
        value = number(selected.get("lab_" + lab))
        age = number(selected.get("lab_" + lab + "_age_minutes"))
        if value is None:
            continue
        if age is None or age < 0 or age < delay:
            raise ValueError("Prepared lab age conflicts with its availability-delay metadata")
        patient["preop_labs"][lab] = value
        patient["preop_lab_measurement_times"][lab] = -age
        patient["preop_lab_times"][lab] = -age + delay

    # Keep the actual ICU label, actual operation start/end and final outcomes
    # out of this payload, including explanatory strings and provenance.
    from app.importer import UNITS, validate_dataset
    snapshot = {
        "schema_version": "1.1", "units": dict(UNITS), "base_time": DISPLAY_ORIGIN,
        "minute": 0, "clock_kind": "case_relative", "horizon_minutes": 10080,
        "source": "import", "patients": [patient], "beds": [], "replay_events": [],
        "import_provenance": {
            "dataset_kind": metadata.get("dataset_kind", "inspire"),
            "snapshot_kind": "single_observed_PREOP_landmark",
            "display_origin_is_arbitrary": True,
            "schedule_origin": "operator_supplied_plan_not_actual_future_surgery_times",
            "planned_icu_status": "unknown_not_supplied",
            "bed_inventory_status": "not_supplied",
            "laboratory_delay_minutes_assumed": delay,
        },
    }
    validate_dataset(snapshot)
    return snapshot


def export_snapshot(data_dir, prepared, output, planned_start_in_minutes,
                    estimated_duration_minutes, op_id=None):
    target, source = Path(output).resolve(), Path(data_dir).resolve()
    if target == source or source in target.parents:
        raise ValueError("Export must be outside the read-only original dataset directory")
    if target.exists():
        raise FileExistsError("Export target already exists; choose a new local filename")
    snapshot = make_snapshot(source, prepared, planned_start_in_minutes,
                             estimated_duration_minutes, op_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--op-id", help="Optional operation identifier; defaults to first valid PREOP case")
    parser.add_argument("--output", required=True, help="Local-only JSON; contains patient linkage IDs")
    parser.add_argument("--planned-start-in-minutes", type=float, required=True)
    parser.add_argument("--estimated-duration-minutes", type=float, required=True)
    args = parser.parse_args()
    try:
        export_snapshot(args.data_dir, args.prepared, args.output,
                        args.planned_start_in_minutes, args.estimated_duration_minutes, args.op_id)
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"status": "exported", "snapshot": "single_PREOP_case_relative", "output": str(Path(args.output).resolve())}))


if __name__ == "__main__":
    main()
