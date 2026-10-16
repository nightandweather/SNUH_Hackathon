"""Explicit surgical ICU cohort for the public MIMIC demo.

Use original careunit labels: the legacy demo randomly assigns mixed MICU/SICU
stays, which is not evidence that those patients belong to a surgical cohort.
K-MIMIC requires its own verified hospital-specific unit mapping.
"""
import copy

MIMIC_SURGICAL_UNITS = {
    "Surgical Intensive Care Unit (SICU)": "SICU",
    "Cardiac Vascular Intensive Care Unit (CVICU)": "CSICU",
    "Neuro Surgical Intensive Care Unit (Neuro SICU)": "NSICU",
    "Trauma SICU (TSICU)": "TSICU",
}


def surgical_pool(pool):
    selected = []
    for patient in pool:
        unit = MIMIC_SURGICAL_UNITS.get(patient.get("careunit"))
        if patient.get("source") == "MIMIC-IV" and unit:
            row = copy.deepcopy(patient)
            row["unit_type"] = unit
            selected.append(row)
    if not selected:
        raise ValueError("No verified surgical MIMIC stays. K-MIMIC needs a validated unit mapping.")
    return selected


def surgical_config(config):
    cfg = copy.deepcopy(config)
    cfg["_note"] = "Public surgical ICU demo. Beds, floors and staffing are simulation assumptions."
    cfg["floors"] = [
        {"floor": 5, "units": [
            {"id": "CSICU", "name": "Cardiovascular Surgical ICU", "type": "CSICU", "beds": 8},
            {"id": "NSICU", "name": "Neurosurgical ICU", "type": "NSICU", "beds": 8},
        ]},
        {"floor": 4, "units": [
            {"id": "SICU", "name": "Surgical ICU", "type": "SICU", "beds": 8},
            {"id": "TSICU", "name": "Trauma Surgical ICU", "type": "TSICU", "beds": 8},
        ]},
    ]
    return cfg
