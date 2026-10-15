"""Inference helpers. Only load joblib artifacts from a trusted local training run."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import NUMERIC_FEATURES, CATEGORICAL_FEATURES


FEATURE_COLUMNS = list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES)


def model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the same dtype contract at training and inference, without fitting."""
    result = frame.reindex(columns=FEATURE_COLUMNS).copy()
    for name in NUMERIC_FEATURES:
        result[name] = pd.to_numeric(result[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
    for name in CATEGORICAL_FEATURES:
        result[name] = result[name].map(lambda value: "MISSING" if pd.isna(value) else str(value))
    return result


def raw_probability(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    return bundle["pipeline"].predict_proba(model_frame(frame))[:, 1]


def logit(probability) -> np.ndarray:
    p = np.clip(np.asarray(probability, dtype=float), 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p)).reshape(-1, 1)


def calibrated_probability(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    p = raw_probability(bundle, frame)
    calibrator = bundle.get("calibrator")
    return calibrator.predict_proba(logit(p))[:, 1] if calibrator is not None else p
