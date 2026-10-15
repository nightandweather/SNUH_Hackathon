"""Train an ICU24 model on prepared landmarks with untouched patient test data.

Example: python -m ml.icu24.train --data data/icu24/prepared.csv
    --output-dir data/icu24/run26 --dataset-kind inspire --seed 26
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from .artifacts import FEATURE_COLUMNS, calibrated_probability, logit, model_frame
from .evaluate import choose_threshold, evaluate, operation_weights, patient_bootstrap, probability_metrics, subgroup_metrics
from .features import NUMERIC_FEATURES, CATEGORICAL_FEATURES, FEATURE_VERSION

TASK = "icu24_after_operation_end"
SPLIT_FRACTIONS = {"train": .60, "validation": .15, "calibration": .10, "test": .15}


def patient_split(frame: pd.DataFrame, seed=26) -> pd.DataFrame:
    """Stratified patient split; every admission, operation and landmark stays together."""
    patients = (frame.groupby("subject_id", sort=True)["y_icu24"].max()
                .rename("patient_ever_positive").reset_index())
    if len(patients) < 40 or patients.patient_ever_positive.value_counts().min() < 10:
        raise ValueError("Need at least 40 eligible patients and 10 patients in each patient-level class for four stratified splits")
    remaining = patients
    pieces = []
    remaining_fraction = 1.0
    for index, name in enumerate(("test", "calibration", "validation")):
        try:
            remaining, selected = train_test_split(
                remaining, test_size=SPLIT_FRACTIONS[name] / remaining_fraction,
                stratify=remaining.patient_ever_positive, random_state=seed + index)
        except ValueError as error:
            raise ValueError("Insufficient patient/class counts for patient-disjoint four-way split") from error
        selected = selected.copy()
        selected["split"] = name
        pieces.append(selected)
        remaining_fraction -= SPLIT_FRACTIONS[name]
    remaining = remaining.copy()
    remaining["split"] = "train"
    manifest = pd.concat([*pieces, remaining], ignore_index=True).sort_values("subject_id").reset_index(drop=True)
    for name in SPLIT_FRACTIONS:
        identifiers = set(manifest.loc[manifest.split == name, "subject_id"])
        if frame[frame.subject_id.isin(identifiers)].y_icu24.nunique() != 2:
            raise ValueError(f"Split {name} lacks a label class; increase data or change split seed")
    return manifest


def build_pipeline(kind: str, seed=26, max_iter=150) -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    categorical = OneHotEncoder(handle_unknown="ignore", sparse_output=False, min_frequency=5)
    transformer = ColumnTransformer([
        ("numeric", numeric, list(NUMERIC_FEATURES)),
        ("categorical", categorical, list(CATEGORICAL_FEATURES)),
    ], sparse_threshold=0)
    if kind == "logistic":
        estimator = LogisticRegression(C=1.0, max_iter=max(300, max_iter), random_state=seed)
    elif kind == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(
            max_iter=max_iter, learning_rate=.07, max_leaf_nodes=15,
            l2_regularization=2.0, min_samples_leaf=30,
            early_stopping=False, random_state=seed)
    else:
        raise ValueError(f"Unknown candidate: {kind}")
    return Pipeline([("preprocess", transformer), ("classifier", estimator)])


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_prepared(path: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(path, dtype={"subject_id": str, "hadm_id": str, "op_id": str})
    required = {"subject_id", "hadm_id", "op_id", "landmark_minute", "phase", "y_icu24", "label_status", *FEATURE_COLUMNS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Prepared table lacks required columns: {', '.join(missing)}")
    input_rows = len(frame)
    statuses = frame.label_status.fillna("missing").value_counts().to_dict()
    frame = frame[frame.label_status == "valid"].copy()
    if not len(frame):
        raise ValueError("No valid label rows")
    if frame[["subject_id", "hadm_id", "op_id"]].isna().any().any():
        raise ValueError("Valid rows must have non-null patient/admission/operation identifiers")
    frame["y_icu24"] = pd.to_numeric(frame.y_icu24, errors="raise")
    if not frame.y_icu24.isin([0, 1]).all():
        raise ValueError("Valid labels must be exactly 0 or 1")
    frame["y_icu24"] = frame.y_icu24.astype(int)
    if not frame.phase.isin(["PREOP", "OR"]).all():
        raise ValueError("ICU24 development supports only PREOP/OR rows")
    if frame.duplicated(["subject_id", "hadm_id", "op_id", "landmark_minute"]).any():
        raise ValueError("Duplicate operation/landmark rows would distort evaluation")
    inconsistent = frame.groupby(["subject_id", "hadm_id", "op_id"]).y_icu24.nunique()
    if (inconsistent > 1).any():
        raise ValueError("An operation's ICU24 label must be constant across landmarks")
    frame = frame.sort_values(["subject_id", "hadm_id", "op_id", "landmark_minute"]).reset_index(drop=True)
    return frame, {"input_rows": input_rows, "eligible_rows": len(frame), "label_status_counts": statuses}


def prediction_table(frame, probability, threshold):
    columns = ["subject_id", "hadm_id", "op_id", "landmark_minute", "phase", "y_icu24"]
    result = frame[columns].copy()
    result["icu_probability"] = probability
    result["threshold"] = threshold
    result["predicted_positive"] = np.asarray(probability) >= threshold
    return result


def _train(args) -> dict:
    path = Path(args.data)
    output = Path(args.output_dir)
    if (output / "model.joblib").exists() and not args.overwrite:
        raise ValueError("Output already contains model.joblib; choose a new run directory or --overwrite")
    output.mkdir(parents=True, exist_ok=True)
    frame, audit = read_prepared(path)
    manifest = patient_split(frame, args.seed)
    assignments = manifest.set_index("subject_id")["split"]
    partitions = {name: frame.loc[frame.subject_id.map(assignments) == name].copy() for name in SPLIT_FRACTIONS}
    data_metadata = {}
    metadata_path = Path(args.metadata) if args.metadata else path.parent / "cohort_audit.json"
    if metadata_path.is_file():
        data_metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    if data_metadata.get("dataset_kind", args.dataset_kind) != args.dataset_kind:
        raise ValueError("dataset-kind disagrees with preparation provenance (synthetic data cannot be labelled INSPIRE)")
    if data_metadata.get("feature_version", FEATURE_VERSION) != FEATURE_VERSION:
        raise ValueError("Prepared-data feature version differs from training code")
    if data_metadata.get("prepared_sha256", file_sha256(path)) != file_sha256(path):
        raise ValueError("Prepared data checksum differs from its cohort audit")
    candidate_results = {}
    candidates = {}
    train_frame = partitions["train"]
    validation = partitions["validation"]
    for kind in args.candidates.split(","):
        kind = kind.strip()
        pipeline = build_pipeline(kind, args.seed, args.max_iter)
        pipeline.fit(model_frame(train_frame), train_frame.y_icu24,
                     classifier__sample_weight=operation_weights(train_frame))
        probability = pipeline.predict_proba(model_frame(validation))[:, 1]
        candidate_results[kind] = probability_metrics(validation.y_icu24, probability, operation_weights(validation))
        candidates[kind] = pipeline
    chosen = min(candidate_results, key=lambda kind: (candidate_results[kind]["log_loss"], kind))
    pipeline = candidates[chosen]
    calibration = partitions["calibration"]
    raw_calibration = pipeline.predict_proba(model_frame(calibration))[:, 1]
    calibrator = LogisticRegression(C=1e6, max_iter=1000, random_state=args.seed)
    calibrator.fit(logit(raw_calibration), calibration.y_icu24, sample_weight=operation_weights(calibration))
    version = f"{args.dataset_kind}-icu24-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{file_sha256(path)[:8]}"
    bundle = {
        "artifact_schema_version": 1, "task": TASK, "horizon_minutes": 1440,
        "pipeline": pipeline, "calibrator": calibrator,
        "numeric_features": list(NUMERIC_FEATURES), "categorical_features": list(CATEGORICAL_FEATURES),
        "feature_fingerprint": hashlib.sha256(json.dumps(FEATURE_COLUMNS).encode()).hexdigest(),
        "feature_version": FEATURE_VERSION,
        "model_version": version, "dataset_kind": args.dataset_kind,
        "source_sha256": file_sha256(path), "seed": args.seed,
        "supported_phases": sorted(frame.phase.unique().tolist()),
        "training_elapsed_operation_minutes": sorted(pd.to_numeric(frame.elapsed_operation_minutes).dropna().unique().tolist()),
        "input_population": {"minimum_age": 18, "maximum_age": 90},
        "metadata": data_metadata,
        "supported_outputs": ["icu_probability"],
        "target_definition": "New ICU admission from operation end through 1440 minutes after operation end",
        "versions": {"python": __import__("platform").python_version(), "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__, "joblib": joblib.__version__},
    }
    validation_probability = calibrated_probability(bundle, validation)
    threshold = choose_threshold(validation.y_icu24, validation_probability, operation_weights(validation), args.target_sensitivity)
    bundle["decision_threshold"] = threshold
    bundle["threshold_selection"] = {"split": "validation", "target_sensitivity": args.target_sensitivity,
                                     "rule": "highest cutoff reaching target sensitivity (minimum false-positive rate)"}
    test = partitions["test"]
    test_probability = calibrated_probability(bundle, test)
    report = {
        "model_version": version, "task": TASK, "horizon_minutes": 1440,
        "dataset_kind": args.dataset_kind, "source_sha256": bundle["source_sha256"],
        "data_metadata": data_metadata, "preparation_audit": audit,
        "seed": args.seed, "split_fractions": SPLIT_FRACTIONS,
        "split_method": "patient-group stratification by maximum ICU24 label; all operations/landmarks of a patient in one partition",
        "candidate_selection": {"split": "validation", "metric": "operation-weighted log_loss", "candidates": candidate_results, "chosen": chosen},
        "calibration_method": "sigmoid of raw log odds, fitted exclusively on calibration patients",
        "threshold_selection": bundle["threshold_selection"], "decision_threshold": threshold,
        "numeric_features": list(NUMERIC_FEATURES), "categorical_features": list(CATEGORICAL_FEATURES),
        "feature_version": FEATURE_VERSION, "supported_phases": bundle["supported_phases"],
        "training_elapsed_operation_minutes": bundle["training_elapsed_operation_minutes"],
        "partitions": {name: evaluate(part, calibrated_probability(bundle, part), threshold) for name, part in partitions.items()},
        "test_patient_bootstrap": patient_bootstrap(test, test_probability, args.bootstrap, args.seed + 100),
        "test_subgroups": subgroup_metrics(test, test_probability, threshold),
        "versions": bundle["versions"],
        "limitations": ["Retrospective research model; not prospectively or externally validated", "ICU use is an observed-care outcome, not clinical necessity", "Validation used both for candidate choice and threshold selection; test remains untouched", "No LOS, intensive-support or individual confidence model is provided"],
    }
    manifest.to_csv(output / "split_manifest.csv", index=False)
    prediction_table(test, test_probability, threshold).to_csv(output / "test_predictions.csv", index=False)
    prediction_table(validation, validation_probability, threshold).to_csv(output / "validation_predictions.csv", index=False)
    joblib.dump(bundle, output / "model.joblib", compress=3)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report


def train(args) -> dict:
    # Both BLAS logistic fitting and OpenMP histogram trees respect this limit.
    # This avoids a large host launching hundreds of threads for small tasks.
    with threadpool_limits(limits=2):
        return _train(args)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--data", required=True, help="Prepared CSV with exact feature whitelist and valid ICU24 labels")
    result.add_argument("--output-dir", required=True, help="LOCAL ignored directory; output includes patient identifiers")
    result.add_argument("--dataset-kind", required=True, choices=["inspire", "synthetic"])
    result.add_argument("--metadata", help="Optional prepared-data metadata JSON copied into artifact provenance")
    result.add_argument("--seed", type=int, default=26)
    result.add_argument("--max-iter", type=int, default=150)
    result.add_argument("--candidates", default="logistic,hist_gradient_boosting")
    result.add_argument("--target-sensitivity", type=float, default=.90)
    result.add_argument("--bootstrap", type=int, default=100)
    result.add_argument("--overwrite", action="store_true")
    return result


def main():
    args = parser().parse_args()
    if args.max_iter < 1 or args.bootstrap < 0:
        raise SystemExit("max-iter must be positive and bootstrap nonnegative")
    try:
        report = train(args)
    except (ValueError, FileNotFoundError) as error:
        raise SystemExit(str(error)) from error
    test = report["partitions"]["test"]
    print(json.dumps({"model_version": report["model_version"], "selected_model": report["candidate_selection"]["chosen"],
                      "test_patients": test["patients"], "test_auroc": test["auroc"], "test_auprc": test["auprc"],
                      "test_brier": test["brier"], "output_dir": str(Path(args.output_dir).resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
