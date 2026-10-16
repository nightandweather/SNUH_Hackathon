"""Reproducible, fully fictional surgical ICU staffing scenarios."""
import engine
import copy
from cohort import surgical_config

PROFILES = {
    "calm": {"name": "Calm shift", "description": "Six stable patients, one planned postoperative admission and one available bed per ICU. Initial nurse fatigue: 10/100 (assumed).", "fatigue": 10},
    "bleeding": {"name": "Suspected bleeding", "description": "One fictional postoperative bleeding case in SICU, a watch-level patient, and reserved / available beds. Initial nurse fatigue: 20/100 (assumed).", "fatigue": 20},
    "surge": {"name": "Overloaded shift", "description": "Seven occupied beds per ICU, simultaneous emergencies and a reserved admission. Initial nurse fatigue: 70/100 (assumed); workload and response delays then evolve in the simulator.", "fatigue": 70},
}


def create(profile, policy="auto", seed=1, multi_hospital=False, hospital_profiles=None):
    if profile not in PROFILES:
        raise ValueError("Select a supported shift scenario.")
    cfg = surgical_config(engine.load_config())
    if multi_hospital:
        floors = copy.deepcopy(cfg["floors"])
        cfg["floors"] = []
        for index, hospital_id in enumerate(("A", "B", "C")):
            for floor in copy.deepcopy(floors):
                floor["floor"] += index * 100
                for unit in floor["units"]:
                    unit["hospital_id"] = hospital_id
                    unit["hospital_name"] = f"Demo Hospital {hospital_id}"
                    unit["display_floor"] = floor["floor"] % 100
                    if index:
                        unit["id"] = f"{hospital_id}-{unit['id']}"
                        unit["type"] = unit["id"]
                cfg["floors"].append(floor)
    pool = []
    for unit in (u["type"] for f in cfg["floors"] for u in f["units"]):
        for i in range(1, 9):
            pool.append({"pid": f"SIM-{unit}-{i:02}", "source": "synthetic", "unit_type": unit,
                         "dx": "Fictional postoperative monitoring case", "age": 50+i, "sex": "F" if i%2 else "M",
                         "vent": 0, "pressor": 0, "prior_risk": 15, "los_min": 3000, "step": 1, "cpr": [],
                         "series": {key: [value]*3001 for key, value in
                                    {"hr": 82, "sbp": 118, "map": 82, "spo2": 98, "rr": 18}.items()}})
    h = engine.Hospital(pool, policy=policy, seed=seed, occupancy=0, arrivals_per_unit_shift=0, cfg=cfg)
    h.demo_profile = profile
    h.hospital_profiles = {"A": profile, "B": "calm", "C": "surge"} if multi_hospital else {"A": profile}
    if hospital_profiles:
        for hospital_id, selected in hospital_profiles.items():
            if hospital_id not in h.hospital_profiles or selected not in PROFILES:
                raise ValueError("Unsupported hospital or shift scenario.")
            h.hospital_profiles[hospital_id] = selected
    for unit in h.units.values():
        unit_profile = h.hospital_profiles[unit.get("hospital_id", "A")]
        occupied = 7 if unit_profile == "surge" else 6
        for i, bid in enumerate(unit["bed_ids"]):
            bed = h.beds[bid]
            if i < occupied:
                bed["patient"] = h._pick_patient(unit["type"], False)
                src = bed["patient"]["src"]
                src["devices"] = {"ventilator": i == 2 or (unit_profile == "surge" and i == 4), "oxygen": i in (1, 4), "iv": True,
                                  "central_line": i == 2, "arterial_line": i in (0, 2),
                                  "urinary_catheter": i < 3, "drain": i in (0, 1),
                                  "crrt": i in (3, 4) and unit_profile == "surge", "ecmo": None}
                src["extra_observations"] = {"temperature": 38.3 if i == 4 and unit_profile != "calm" else 36.8,
                                             "pain": 6 if i == 1 and unit_profile != "calm" else 2, "gcs": 12 if i == 2 and unit_profile != "calm" else 15}
                # Explicit fictional observations: arrest or a pressor flag alone is not proof
                # of performed CPR, dose escalation, or surgery on the current calendar day.
                src["care_indicators"] = {
                    "calendar_day": 0, "source": "simulation_fixture",
                    "cpr_today": unit_profile == "surge" and i == 4,
                    "surgery_today": i < 3 or (unit_profile == "surge" and i == 4),
                    "pressor_unstable": unit_profile == "surge" and i in (3, 4),
                }
                src["vent"] = int(src["devices"]["ventilator"])
                src["pressor"] = int(src["care_indicators"]["pressor_unstable"])
                if (unit_profile == "bleeding" and unit["id"].split("-")[-1] == "SICU" and i == 1) or (unit_profile == "surge" and i >= 4):
                    # A synthetic watch-level baseline, not an injected emergency.
                    bed["patient"]["src"]["series"]["map"] = [64]*3001
                    bed["patient"]["src"]["series"]["hr"] = [110]*3001
                    bed["patient"]["src"]["prior_risk"] = 75
                h._update_patient(bed)
            elif i == occupied:
                bed["reservation"] = {"label": "Surgery scheduled · postoperative ICU admission", "expected_t": 120,
                                      "source": "simulation_schedule", "note": "Fictional schedule; patient not yet admitted."}
    for nurse in h.nurses.values():
        hospital_id = h.units[nurse["unit"]].get("hospital_id", "A")
        nurse["fatigue"] = nurse["peak"] = PROFILES[h.hospital_profiles[hospital_id]]["fatigue"]
    for unit in h.units:
        unit_profile = h.hospital_profiles[h.units[unit].get("hospital_id", "A")]
        if unit_profile == "bleeding" and h.units[unit]["type"].endswith("SICU") and unit.split("-")[-1] == "SICU":
            h.trigger_emergency(f"{unit}-01", "bleeding")
        elif unit_profile == "surge":
            for suffix, scenario in (("01", "bleeding"), ("02", "code_blue"), ("03", "hypoxia"), ("04", "hypotension")):
                h.trigger_emergency(f"{unit}-{suffix}", scenario)
    return h
