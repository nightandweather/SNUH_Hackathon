"""Patient-aware, per-operation weighted evaluation for ICU24 predictions."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix, log_loss,
    roc_auc_score, roc_curve,
)


def operation_weights(frame: pd.DataFrame) -> np.ndarray:
    """Each operation contributes one total unit, however many landmarks it has."""
    keys = ["subject_id", "hadm_id", "op_id"]
    counts = frame.groupby(keys, dropna=False)["y_icu24"].transform("size")
    return 1.0 / counts.to_numpy(dtype=float)


def choose_threshold(y, probability, weights, target_sensitivity=0.9) -> float:
    """Maximum specificity among calibration thresholds reaching sensitivity."""
    if not 0 < target_sensitivity <= 1:
        raise ValueError("target_sensitivity must be in (0, 1]")
    if len(np.unique(y)) != 2:
        raise ValueError("Threshold selection requires both calibration classes")
    fpr, tpr, thresholds = roc_curve(y, probability, sample_weight=weights)
    eligible = np.flatnonzero((tpr >= target_sensitivity) & np.isfinite(thresholds))
    if not len(eligible):
        return 0.0
    # roc_curve orders thresholds from high to low; the first eligible threshold
    # has minimum false-positive rate and is the highest eligible cutoff.
    return float(np.clip(thresholds[eligible[0]], 0, 1))


def probability_metrics(y, probability, weights=None) -> dict:
    y = np.asarray(y, dtype=int)
    probability = np.asarray(probability, dtype=float)
    weights = np.ones(len(y)) if weights is None else np.asarray(weights, dtype=float)
    if len(y) == 0:
        return {"auroc": None, "auprc": None, "brier": None, "log_loss": None}
    two_classes = len(np.unique(y[weights > 0])) == 2
    return {
        "auroc": float(roc_auc_score(y, probability, sample_weight=weights)) if two_classes else None,
        "auprc": float(average_precision_score(y, probability, sample_weight=weights)) if two_classes else None,
        "brier": float(brier_score_loss(y, probability, sample_weight=weights)),
        "log_loss": float(log_loss(y, probability, labels=[0, 1], sample_weight=weights)),
    }


def threshold_metrics(y, probability, threshold, weights=None) -> dict:
    y = np.asarray(y, dtype=int)
    decision = np.asarray(probability) >= threshold
    tn, fp, fn, tp = confusion_matrix(y, decision, labels=[0, 1], sample_weight=weights).ravel()
    divide = lambda numerator, denominator: float(numerator / denominator) if denominator else None
    raw = confusion_matrix(y, decision, labels=[0, 1]).tolist()
    return {
        "threshold": float(threshold), "sensitivity": divide(tp, tp + fn),
        "specificity": divide(tn, tn + fp), "ppv": divide(tp, tp + fp),
        "npv": divide(tn, tn + fn), "positive_prediction_fraction": divide(tp + fp, tp + fp + tn + fn),
        "landmark_confusion_matrix_tn_fp_fn_tp": raw,
        "operation_weighted_confusion": {"tn": float(tn), "fp": float(fp), "fn": float(fn), "tp": float(tp)},
    }


def reliability(y, probability, weights=None, bins=10) -> dict:
    y = np.asarray(y, dtype=float)
    probability = np.asarray(probability, dtype=float)
    weights = np.ones(len(y)) if weights is None else np.asarray(weights, dtype=float)
    indices = np.minimum((probability * bins).astype(int), bins - 1)
    result = []
    ece = 0.0
    for index in range(bins):
        selected = indices == index
        mass = float(weights[selected].sum())
        mean_p = float(np.average(probability[selected], weights=weights[selected])) if mass else None
        incidence = float(np.average(y[selected], weights=weights[selected])) if mass else None
        if mass:
            ece += mass / weights.sum() * abs(mean_p - incidence)
        result.append({"lower": index / bins, "upper": (index + 1) / bins,
                       "landmarks": int(selected.sum()), "operation_weight": mass,
                       "mean_predicted": mean_p, "observed_fraction": incidence})
    return {"expected_calibration_error": float(ece), "bins": result}


def evaluate(frame, probability, threshold) -> dict:
    y = frame.y_icu24.to_numpy(dtype=int)
    weights = operation_weights(frame)
    return {
        "patients": int(frame.subject_id.nunique()),
        "operations": int(frame[["subject_id", "hadm_id", "op_id"]].drop_duplicates().shape[0]),
        "landmarks": len(frame), "positive_landmarks": int(y.sum()),
        "weighted_prevalence": float(np.average(y, weights=weights)),
        "metric_weighting": "Each operation contributes total weight 1 across its landmarks",
        **probability_metrics(y, probability, weights),
        "selected_threshold": threshold_metrics(y, probability, threshold, weights),
        "threshold_0_5": threshold_metrics(y, probability, 0.5, weights),
        "calibration": reliability(y, probability, weights),
    }


def patient_bootstrap(frame, probability, draws=100, seed=26) -> dict:
    """Resample whole patients, retaining all operations and landmarks together."""
    if draws < 1:
        return {"draws": 0, "method": "disabled", "intervals": {}}
    patients, codes = np.unique(frame.subject_id.astype(str), return_inverse=True)
    y = frame.y_icu24.to_numpy(dtype=int)
    weights = operation_weights(frame)
    rng = np.random.default_rng(seed)
    samples = {name: [] for name in ("auroc", "auprc", "brier", "log_loss")}
    skipped = 0
    for _ in range(draws):
        multiplicity = np.bincount(rng.integers(0, len(patients), size=len(patients)), minlength=len(patients))
        resample_weights = weights * multiplicity[codes]
        selected = resample_weights > 0
        if len(np.unique(y[selected])) != 2:
            skipped += 1
            continue
        metrics = probability_metrics(y[selected], np.asarray(probability)[selected], resample_weights[selected])
        for name in samples:
            samples[name].append(metrics[name])
    intervals = {name: {"lower": float(np.quantile(values, .025)), "upper": float(np.quantile(values, .975))}
                 for name, values in samples.items() if values}
    return {"draws": draws, "valid_draws": draws - skipped,
            "method": "95% percentile bootstrap, whole-patient resampling", "seed": seed, "intervals": intervals}


def subgroup_metrics(frame, probability, threshold) -> dict:
    """Descriptive test subgroups; never used for model or threshold selection."""
    output = {}
    for column in ("phase", "sex", "asa", "department", "anesthesia_type"):
        if column not in frame:
            continue
        values = frame[column].fillna("MISSING").astype(str)
        groups = {}
        for value in sorted(values.unique()):
            selected = values == value
            subset = frame.loc[selected]
            if subset.subject_id.nunique() < 10:
                groups[value] = {"patients": int(subset.subject_id.nunique()), "status": "too_small_for_metrics"}
                continue
            groups[value] = evaluate(subset, np.asarray(probability)[selected], threshold)
        output[column] = groups
    return output
