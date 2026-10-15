"""Create entirely fictional INSPIRE-shaped data for pipeline smoke tests.

These values contain an intentionally learnable association and are not a
clinical simulation, a performance benchmark, or a substitute for INSPIRE.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path


OPERATION_COLUMNS = [
    "op_id", "subject_id", "hadm_id", "case_id", "opdate", "age", "sex",
    "weight", "height", "race", "asa", "emop", "department", "antype",
    "icd10_pcs", "orin_time", "orout_time", "opstart_time", "opend_time",
    "admission_time", "discharge_time", "anstart_time", "anend_time",
    "cpbon_time", "cpboff_time", "icuin_time", "icuout_time",
    "inhosp_death_time", "allcause_death_time",
]


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def generate(output_dir: str | Path, patients: int = 300, seed: int = 26) -> dict:
    """Write fake source tables and return a small non-patient summary.

    A subset of people has more than one admission and a subset of admissions
    has more than one operation, allowing patient-split checks. Existing source
    table files are never silently overwritten.
    """
    if patients < 12:
        raise ValueError("Use at least 12 synthetic patients; 300 is recommended.")
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    names = ("operations.csv", "vitals.csv", "labs.csv", "parameters.csv", "SYNTHETIC_ONLY.json")
    if any((target / name).exists() for name in names):
        raise FileExistsError("Output already contains a fixture table; choose an empty output directory.")

    rng = random.Random(seed)
    operations: list[dict] = []
    vitals: list[dict] = []
    labs: list[dict] = []
    positive_cases = 0
    admission_count = 0

    for patient_index in range(patients):
        subject_id = 1_900_000 + patient_index
        age = rng.randint(20, 89)
        sex = rng.choice(("M", "F"))
        admissions = 2 if patient_index % 10 == 0 else 1
        for admission_index in range(admissions):
            admission_count += 1
            hadm_id = 2_900_000 + admission_count
            admission_time = admission_index * 40_000
            # A repeat operation occurs after the first target's 24-hour window.
            case_count = 2 if patient_index % 17 == 0 and admission_index == 0 else 1
            for case_index in range(case_count):
                op_id = 4_900_000 + len(operations)
                opstart = admission_time + 1_000 + case_index * 4_000
                duration = rng.randint(110, 280)
                opend = opstart + duration
                asa = rng.choices((1, 2, 3, 4), weights=(15, 45, 33, 7))[0]
                emergency = int(rng.random() < 0.15)
                latent = -3.5 + 0.8 * asa + 0.02 * (age - 50) + 0.8 * emergency
                label = int(rng.random() < 1 / (1 + math.exp(-latent)))
                positive_cases += label
                icuin = opend + rng.randint(0, 180) if label else ""
                icuout = int(icuin) + rng.randint(12, 96) * 60 if label else ""
                # All operations in an admission share its final discharge.
                discharge = admission_time + 18_000
                row = dict.fromkeys(OPERATION_COLUMNS, "")
                row.update(
                    op_id=op_id, subject_id=subject_id, hadm_id=hadm_id,
                    opdate=opstart - opstart % 1440, age=age, sex=sex,
                    weight=round(rng.uniform(45, 105), 1), height=round(rng.uniform(148, 188), 1),
                    race="SYNTHETIC", asa=asa, emop=emergency,
                    department=rng.choice(("GS", "OS", "NS", "TS")), antype="General",
                    icd10_pcs="SYNTHETIC", orin_time=opstart - 30,
                    orout_time=opend + 20, opstart_time=opstart, opend_time=opend,
                    admission_time=admission_time, discharge_time=discharge,
                    anstart_time=opstart - 20, anend_time=opend + 10,
                    icuin_time=icuin, icuout_time=icuout,
                )
                operations.append(row)

                for elapsed in range(-20, duration + 21, 5):
                    chart_time = opstart + elapsed
                    map_value = 80 - 9 * label - 2 * emergency + rng.gauss(0, 7)
                    for item_name, value in (
                        ("art_mbp", map_value),
                        ("nibp_mbp", map_value + rng.gauss(0, 3)),
                        ("hr", 73 + 10 * label + rng.gauss(0, 7)),
                        ("spo2", min(100, 98.5 - label + rng.gauss(0, 0.7))),
                        ("nepi", max(0, 0.07 * label + rng.gauss(0, 0.015))),
                    ):
                        # Missing measurements are missing, never fabricated zeroes.
                        if rng.random() < 0.04:
                            continue
                        vitals.append(dict(op_id=op_id, subject_id=subject_id,
                                           chart_time=chart_time, item_name=item_name,
                                           value=round(value, 4)))

                for chart_time in (opstart - 240, opstart + 45, opend + 240):
                    for item_name, value in (
                        ("hb", 13.0 - 0.8 * label + rng.gauss(0, 1)),
                        ("creatinine", 0.9 + 0.3 * label + rng.gauss(0, 0.15)),
                        ("albumin", 4.0 - 0.3 * label + rng.gauss(0, 0.2)),
                        ("platelet", 240 - 25 * label + rng.gauss(0, 30)),
                        ("sodium", 140 + rng.gauss(0, 2)),
                        ("potassium", 4.0 + rng.gauss(0, 0.25)),
                        # INSPIRE 1.4.2 parameters.csv spells this as "lacate".
                        ("lacate", 1.0 + label + rng.gauss(0, 0.2)),
                    ):
                        labs.append(dict(subject_id=subject_id, chart_time=chart_time,
                                         item_name=item_name, value=round(value, 4)))

    _write_csv(target / "operations.csv", OPERATION_COLUMNS, operations)
    _write_csv(target / "vitals.csv", ["op_id", "subject_id", "chart_time", "item_name", "value"], vitals)
    _write_csv(target / "labs.csv", ["subject_id", "chart_time", "item_name", "value"], labs)
    parameter_rows = [
        dict(Table=table, Label=label, Unit=unit, Description="Fictional smoke-test measurement")
        for table, label, unit in (
            ("vitals", "art_mbp", "mmHg"), ("vitals", "nibp_mbp", "mmHg"),
            ("vitals", "hr", "/min"), ("vitals", "spo2", "%"),
            ("vitals", "nepi", "ug/kg/min"), ("labs", "hb", "g/dL"),
            ("labs", "creatinine", "mg/dL"), ("labs", "albumin", "g/dL"),
            ("labs", "platelet", "/nL"),
            ("labs", "sodium", "mmol/L"), ("labs", "potassium", "mmol/L"),
            ("labs", "lacate", "mmol/L"),
        )
    ]
    _write_csv(target / "parameters.csv", ["Table", "Label", "Unit", "Description"], parameter_rows)
    summary = dict(synthetic_only=True, seed=seed, patients=patients,
                   admissions=admission_count, operations=len(operations),
                   positive_cases=positive_cases,
                   note="All rows are fictional; scores do not establish clinical performance.")
    (target / "SYNTHETIC_ONLY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--patients", type=int, default=300)
    parser.add_argument("--seed", type=int, default=26)
    args = parser.parse_args()
    print(json.dumps(generate(args.output_dir, args.patients, args.seed), indent=2))


if __name__ == "__main__":
    main()
