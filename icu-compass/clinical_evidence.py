"""Auditable calculator results and replay alerts; no LLM-generated diagnosis.

AgentMD (doi:10.1038/s41467-025-64430-x) motivates eligibility -> executable
calculator -> interpretation. This is not a reproduction of AgentMD, its LLM
ranking scores, or its validation. qSOFA: Singer et al., JAMA 2016, Box 4.
"""
import math

AGENTMD_URL = "https://www.nature.com/articles/s41467-025-64430-x"
QSOFA_URL = "https://doi.org/10.1001/jama.2016.0287"


def number(value, low, high):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and low <= value <= high else None


def qsofa(vitals, *, age=None, suspected_infection=None, in_icu=True):
    """Missing/invalid components remain missing, never normal or imputed.

    In an ICU this is displayed only as a reference calculation, not a validated
    standalone deterioration, sepsis or mortality classification.
    """
    rr = number(vitals.get("rr"), 0, 100)
    sbp = number(vitals.get("sbp"), 1, 300)
    gcs = number(vitals.get("gcs"), 3, 15)
    if gcs is not None and not gcs.is_integer():
        gcs = None
    components = [
        {"name": "Respiratory rate", "value": rr, "unit": "/min", "rule": "RR >= 22/min", "points": None if rr is None else int(rr >= 22)},
        {"name": "Systolic BP", "value": sbp, "unit": "mmHg", "rule": "SBP <= 100 mmHg", "points": None if sbp is None else int(sbp <= 100)},
        {"name": "Mental status (GCS proxy)", "value": gcs, "unit": "/15", "rule": "GCS < 15", "points": None if gcs is None else int(gcs < 15)},
    ]
    missing = [c["name"] for c in components if c["points"] is None]
    lower = sum(c["points"] or 0 for c in components)
    eligible = not in_icu and number(age, 18, 120) is not None and suspected_infection is True
    return {"name": "qSOFA", "score": None if missing else lower,
            "range": [lower, lower + len(missing)], "missing": missing,
            "components": components, "eligible": eligible,
            "interpretation": ("Higher risk in an eligible adult with suspected infection; not a sepsis diagnosis."
                               if eligible and not missing and lower >= 2 else
                               "Reference calculation only in this ICU. No emergency classification from qSOFA."),
            "source_url": QSOFA_URL, "method_url": AGENTMD_URL,
            "formula": "1[RR >= 22] + 1[SBP <= 100] + 1[altered mentation]"}


def source_assessment(case, row_index):
    """Compute qSOFA reference components solely from fresh selected-row inputs.

    Neither historical display observations nor interpolated values are inputs.
    Unmapped GCS remains unknown; this ICU use never establishes eligibility.
    """
    if type(row_index) is not int or not 0 <= row_index < len(case.get('rows', [])):
        raise ValueError('Invalid observation index')
    row = case['rows'][row_index]
    minute = row.get('minute')
    if type(minute) not in (int, float) or not math.isfinite(minute):
        raise ValueError('Invalid observation time')
    specs = {'rr': ('/min', 0, 100), 'sbp': ('mmHg', 1, 300), 'gcs': ('/15', 3, 15)}
    inputs = {}
    for key, (unit, low, high) in specs.items():
        value, age = row.get('vitals', {}).get(key), row.get('age', {}).get(key)
        conflicts = row.get('same_time_conflict', {})
        statuses = row.get('status', {})
        reason = 'observed'
        if conflicts is True or isinstance(conflicts, dict) and conflicts.get(key) is True:
            reason = 'same_time_conflict'
        elif statuses == 'unknown' or isinstance(statuses, dict) and statuses.get(key) == 'unknown':
            reason = 'explicit_unknown'
        elif type(value) not in (int, float) or not math.isfinite(value):
            reason = 'missing_or_invalid_value'
        elif not low <= value <= high or key == 'gcs' and not float(value).is_integer():
            reason = 'invalid_component_value'
        elif type(age) not in (int, float) or not math.isfinite(age) or age < 0:
            reason = 'unknown_or_future_observation_time'
        elif age > 30:
            reason = 'stale_observation'
        known = reason == 'observed'
        inputs[key] = {'value': value if known else None, 'unit': unit,
                       'status': 'observed' if known else 'unknown', 'reason': reason,
                       'age_minute': age if known else None,
                       'observed_minute': minute - age if known else None}
    calculator = qsofa({key: item['value'] for key, item in inputs.items()}, in_icu=True)
    return {'kind': 'deterministic_reference', 'as_of_minute': minute,
            'calculator': calculator, 'inputs': inputs,
            'supporting_vital_keys': [key for key, item in inputs.items() if item['status'] == 'observed'],
            'clinical_decision': False,
            'limitation': 'Reference calculation only; not a source-observed diagnosis, ICU outcome prediction, triage or transfer decision. Missing components remain unknown. AgentMD itself is not running.'}


def alert_evidence(v, th):
    """Existing configurable simulation rules, explicitly distinct from qSOFA."""
    checks = [("hr", "Heart rate", "bpm", "<", th["hr_low"], "Bradycardia"),
              ("hr", "Heart rate", "bpm", ">", th["hr_high"], "Tachycardia"),
              ("map", "Mean arterial pressure", "mmHg", "<", th["map_low"], "Low MAP"),
              ("spo2", "Oxygen saturation", "%", "<", th["spo2_low"], "Low oxygen saturation"),
              ("rr", "Respiratory rate", "/min", ">", th["rr_high"], "Tachypnea")]
    rows = []
    for key, name, unit, operator, threshold, label in checks:
        value = number(v.get(key), 0, 400)
        if value is not None and ((value < threshold) if operator == "<" else (value > threshold)):
            rows.append({"key": key, "name": name, "value": value, "unit": unit,
                         "operator": operator, "threshold": threshold, "label": label,
                         "basis": "Configurable replay alert; not an AgentMD formula"})
    return rows


def assessment(vitals, thresholds, source, simulated=False, age=None):
    evidence = alert_evidence(vitals, thresholds)
    missing = [key for key in ("hr", "map", "spo2", "rr") if vitals.get(key) is None]
    title = " / ".join(dict.fromkeys(e["label"] for e in evidence))
    return {"title": title or ("Incomplete observations" if missing else "No configured threshold crossed"),
            "evidence": evidence, "calculator": qsofa(vitals, age=age),
            "source": "Injected simulation" if simulated else source + " retrospective replay",
            "method": "AgentMD-inspired calculator workflow; deterministic qSOFA reference implementation. AgentMD itself is not running.",
            "note": "Replay alerts are not confirmed clinical events. Missing measurements are not treated as normal."}
