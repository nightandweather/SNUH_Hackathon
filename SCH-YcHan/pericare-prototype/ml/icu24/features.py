"""One leakage-safe feature implementation shared by preparation and serving.

No patient IDs, final surgery durations, future outcomes, planned ICU inferred
from outcomes, or final procedure codes enter this whitelist. Missing is None.
"""
import math

FEATURE_VERSION = "inspire-icu24-features-1.0"
TASK = "icu24_after_operation_end"
HORIZON_MINUTES = 1440
LABS = ("hemoglobin", "creatinine", "platelets", "albumin", "lactate")
NUMERIC_FEATURES = (
    "age", "asa", "weight", "height", "emergency", "elapsed_operation_minutes",
    "map_last", "map_min_30", "map_mean_30", "low_map_fraction_30",
    "hr_last", "hr_max_30", "spo2_last", "spo2_min_30",
    "signal_count_30", "signal_age_minutes",
    *(f"lab_{name}" for name in LABS),
    *(f"lab_{name}_age_minutes" for name in LABS),
)
CATEGORICAL_FEATURES = ("sex", "department", "anesthesia_type", "phase")
FEATURE_COLUMNS = (*NUMERIC_FEATURES, *CATEGORICAL_FEATURES)
BOUNDS = {"map": (20, 200), "hr": (20, 220), "spo2": (50, 100),
          "hemoglobin": (2, 22), "creatinine": (0.1, 30), "platelets": (1, 2000),
          "albumin": (0.5, 8), "lactate": (0, 30)}
LAB_ALIASES = {"hb": "hemoglobin", "hemoglobin": "hemoglobin",
               "creatinine": "creatinine", "cr": "creatinine",
               "plt": "platelets", "platelet": "platelets", "platelets": "platelets",
               "albumin": "albumin", "lacate": "lactate", "lactate": "lactate"}


def number(value, bounds=None):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or (bounds and not bounds[0] <= value <= bounds[1]):
        return None
    return value


def category(value):
    if value is None or str(value).strip().lower() in ("", "nan", "none", "null"):
        return "unknown"
    return str(value).strip()[:100]


def make_features(payload):
    """Build features from a current PeriCare model-request feature dictionary.

    Lab times are assumed availability times supplied by the adapter. Preparation
    explicitly delays INSPIRE chart_time because result-availability is absent.
    A value with no usable timestamp is withheld, never silently backfilled.
    """
    now = number(payload.get("minute"))
    if now is None:
        raise ValueError("minute must be finite")
    out = {key: None for key in NUMERIC_FEATURES}
    for key, bounds in (("age", (18, 100)), ("asa", (1, 5)),
                        ("weight", (10, 250)), ("height", (100, 230)),
                        ("elapsed_operation_minutes", (0, 10080))):
        out[key] = number(payload.get(key), bounds)
    emergency = payload.get("emergency")
    if isinstance(emergency, bool):
        out["emergency"] = float(emergency)
    elif number(emergency) in (0, 1):
        out["emergency"] = number(emergency)
    out.update({key: category(payload.get(key)) for key in CATEGORICAL_FEATURES})
    out["phase"] = out["phase"].upper()
    if out["phase"] == "PREOP":
        out["elapsed_operation_minutes"] = 0.0
    # An INSPIRE 5-year age category is used as supplied; no false precision.
    observations = []
    for observation in payload.get("signal_window", []) or []:
        minute = number(observation.get("minute"))
        available = number(observation.get("available_minute", minute))
        if (minute is not None and available is not None and available <= now
                and now - 30 <= minute <= now and not observation.get("artifact")):
            observations.append((minute, observation))
    observations.sort(key=lambda item: item[0])
    out["signal_count_30"] = len(observations)
    out["signal_age_minutes"] = now - observations[-1][0] if observations else None
    for signal, summaries in (("map", ("last", "min", "mean")),
                              ("hr", ("last", "max")), ("spo2", ("last", "min"))):
        values = [(t, number(obs.get(signal), BOUNDS[signal])) for t, obs in observations]
        values = [(t, value) for t, value in values if value is not None]
        if not values:
            continue
        vals = [v for _, v in values]
        out[f"{signal}_last"] = vals[-1]
        if "min" in summaries:
            out[f"{signal}_min_30"] = min(vals)
        if "max" in summaries:
            out[f"{signal}_max_30"] = max(vals)
        if "mean" in summaries:
            out[f"{signal}_mean_30"] = sum(vals) / len(vals)
        if signal == "map":
            # Explicitly a fraction of observed samples, not time under MAP65.
            out["low_map_fraction_30"] = sum(v < 65 for v in vals) / len(vals)
    labs = payload.get("preop_labs", {}) or {}
    times = payload.get("preop_lab_times", {}) or {}
    fallback_time = number(payload.get("preop_labs_minute"))
    measured_times = payload.get("preop_lab_measurement_times", {}) or {}
    max_lab_age = number(payload.get("max_lab_age_minutes", 30 * 1440), (1, 365 * 1440))
    if max_lab_age is None:
        raise ValueError("max_lab_age_minutes must be positive and finite")
    for source_name, value in labs.items():
        name = LAB_ALIASES.get(source_name)
        if name is None:
            continue
        available = number(times.get(source_name, times.get(name, fallback_time)))
        measured = number(measured_times.get(source_name, measured_times.get(name, available)))
        if (available is None or measured is None or available > now or measured > now
                or now - measured > max_lab_age):
            continue
        value = number(value, BOUNDS[name])
        if value is not None:
            out[f"lab_{name}"] = value
            out[f"lab_{name}_age_minutes"] = now - measured
    return out
