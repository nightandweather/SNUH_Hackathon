"""Inference-only CalMRL v19 runtime. No training, dataset, or pickle loading.

Inputs are anonymous, already time-verified 24-hour EMR tensors and three
distinct frozen CXR feature views. External image encoder weights are separate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

SCHEMA = "calmrl-v19-fixed24-inference-v1"
FEATURES = ["heart_rate", "sbp", "dbp", "map", "resp_rate", "spo2", "temperature_c", "glucose_mg_dl",
            "albumin_g_dl", "bicarbonate_meq_l", "bun_mg_dl", "creatinine_mg_dl", "chloride_meq_l",
            "sodium_meq_l", "potassium_meq_l", "hematocrit_pct", "hemoglobin_g_dl", "platelets_k_ul", "wbc_k_ul"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -50, 50)))


class OriginalGaussian(nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("W", torch.zeros(1, 64, 16))
        self.register_buffer("mu", torch.zeros(1, 64))
        self.register_buffer("noise", torch.ones(1))
        self.register_buffer("updates", torch.zeros((), dtype=torch.long))

    def mean(self, representation):
        W = self.W.double()[0]
        noise = self.noise.double().clamp_min(.0025)[0]
        precision = torch.eye(16, dtype=torch.float64, device=W.device) + W.T @ W / noise
        chol = torch.linalg.cholesky(precision)
        score = (representation.double() - self.mu.double()[0]) @ W / noise
        return torch.cholesky_solve(score.T, chol).T.to(representation.dtype)


class OriginalEMR(nn.Module):
    def __init__(self):
        super().__init__()
        self.feature = nn.Embedding(19, 64)
        self.measured_value = nn.Linear(2, 64)
        self.empty_hour = nn.Parameter(torch.zeros(64))
        self.hour = nn.Embedding(24, 64)
        self.gru = nn.GRU(64, 64, batch_first=True)
        self.emr_projection = nn.Sequential(nn.LayerNorm(64), nn.Linear(64, 64))
        self.gaussian = OriginalGaussian()
        self.head = nn.Sequential(nn.Linear(83, 64), nn.GELU(), nn.Dropout(.1), nn.Linear(64, 2))

    def forward(self, events, metadata):
        n, device = len(metadata), metadata.device
        require(len(events) > 0 and bool(metadata[:, 0].bool().all()), "observed_EMR_required_for_each_eligible_stay")
        owner, hour, feature = [events[:, number].long() for number in range(3)]
        encoded = self.feature(feature) + self.measured_value(events[:, 3:])
        flat = metadata.new_zeros((n * 24, 64)).index_add(0, owner * 24 + hour, encoded)
        counts = metadata.new_zeros(n * 24).index_add(0, owner * 24 + hour, torch.ones(len(events), device=device))
        bins = torch.where(counts[:, None] > 0, flat / counts[:, None].clamp_min(1), self.empty_hour[None])
        bins = bins.reshape(n, 24, 64) + self.hour(torch.arange(24, device=device))[None]
        _, state = self.gru(bins)
        representation = F.normalize(self.emr_projection(state[-1]), dim=-1)
        mean = self.gaussian.mean(representation)
        logits = self.head(torch.cat((representation, metadata, mean), 1))
        return logits, representation


def project(x, pca):
    x = np.asarray(x, np.float64)
    if pca["normalize"]:
        x = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)
    return ((x - pca["center"]) @ pca["components"]) / pca["scale"]


def conditional_cxr(gaussian, emr):
    W, noise = gaussian["W"][0], gaussian["noise"][0]
    precision = np.eye(W.shape[1]) + W.T @ W / noise
    score = (emr - gaussian["mu"][0]) @ W / noise
    mean = score @ np.linalg.inv(precision)
    return gaussian["mu"][1] + mean @ gaussian["W"][1].T


def clinical_features(cache, model):
    prep, observed = model["preprocessor"], cache["cxr_observed"]
    emr = project(cache["emr"], prep["emr_pca"])
    conditional = conditional_cxr(prep["gaussian"], emr)
    estimated = prep["cxr_mean"] + prep["shrink"] * (conditional - prep["cxr_mean"])
    completed = estimated.copy()
    if observed.any():
        completed[observed] = project(cache[prep["view"]][observed], prep["cxr_pca"])
    first = completed if model["mode"] == "completed_estimated" else completed - estimated
    age = np.where(observed, np.log1p(np.maximum(cache["cxr_age_hours"], 0)) / np.log(73), 0.)
    value = np.column_stack((first, estimated, observed.astype(float), age))
    require(np.isfinite(value).all(), "nonfinite_completed_feature")
    return value


def days(logits, scaler):
    return np.expm1(np.maximum(np.asarray(logits, float) * scaler["LOS_log1p_std"] + scaler["LOS_log1p_mean"], 0))


def encode_days(value, scaler):
    return (np.log1p(value) - scaler["LOS_log1p_mean"]) / scaler["LOS_log1p_std"]


def predict_module(cache, model, scaler):
    task = model["task"]
    if model["baseline"]:
        return cache["logits"][:, task].copy()
    head = model["head"]
    features = clinical_features(cache, model)
    score = ((features - head["feature_mean"]) / head["feature_scale"]) @ head["coefficients"]
    if model["kind"] == "linear_risk":
        return cache["logits"][:, 0] + score + head["intercept"]
    if model["kind"] == "day_regression":
        delta = head["bound_multiplier"] * head["bound_scale"] * np.tanh(score + head["intercept"])
        return encode_days(np.maximum(days(cache["logits"][:, 1], scaler) + delta, 0), scaler)
    require(model["kind"] == "ordinal_LOS", "unsupported_inference_module")
    ordinal_score = head["base_positive_slope"] * cache["logits"][:, 1].astype(float) + np.tanh(score)
    survival = sigmoid(ordinal_score[:, None] - head["ordered_cutpoints"][None])
    probability = np.column_stack((1 - survival[:, 0], -np.diff(survival, axis=1), survival[:, -1]))
    probability = np.maximum(probability, 0)
    probability /= probability.sum(1, keepdims=True)
    mean = probability @ head["bin_means_days"]
    median_bin = (np.cumsum(probability, axis=1) < .5).sum(1).clip(0, len(head["bin_medians_days"]) - 1)
    median = head["bin_medians_days"][median_bin]
    policy = model["point_policy"]
    require(policy in ("mean", "median", "half_mean_median"), "unsupported_ordinal_point_policy")
    point = mean if policy == "mean" else median if policy == "median" else .5 * (mean + median)
    blend = model["distribution_blend"]
    return encode_days((1 - blend) * days(cache["logits"][:, 1], scaler) + blend * point, scaler)


class InferenceBundle:
    def __init__(self, folder, device="cpu"):
        folder = Path(folder)
        metadata = json.loads((folder / "model.json").read_text(encoding="utf-8"))
        require(metadata["schema"] == SCHEMA and metadata["scaler"]["features"] == FEATURES, "unsupported_model_contract")
        require(sha(folder / "parameters.npz") == metadata["parameters_sha256"], "model_parameter_hash_mismatch")
        with np.load(folder / "parameters.npz", allow_pickle=False) as stored:
            arrays = {key: stored[key].copy() for key in stored.files}
        require(all(value.dtype.kind in "biuf" and np.isfinite(value).all() for value in arrays.values()), "numeric_finite_parameters_required")
        def resolve(value):
            if isinstance(value, dict) and set(value) == {"array"}:
                return arrays[value["array"]]
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            return value
        self.metadata, self.scaler, self.models = metadata, resolve(metadata["scaler"]), resolve(metadata["models"])
        self.calibrator = metadata["risk_calibration"]
        self.device = torch.device(device)
        self.original = OriginalEMR()
        original_state = {key: torch.from_numpy(value.copy()) for key, value in resolve(metadata["original_state"]).items()}
        self.original.load_state_dict(original_state, strict=True)
        self.original.requires_grad_(False)
        self.original.to(self.device).eval()

    @torch.no_grad()
    def encode_emr_events(self, events, metadata):
        """events: [owner,hour,feature,standardized_value,log1p_delta]."""
        events = torch.as_tensor(events, dtype=torch.float32, device=self.device)
        metadata = torch.as_tensor(metadata, dtype=torch.float32, device=self.device)
        require(events.ndim == 2 and events.shape[1] == 5 and metadata.ndim == 2 and metadata.shape[1] == 3,
                "invalid_original_EMR_event_or_metadata_shape")
        logits, representation = self.original(events, metadata)
        return logits.cpu().numpy(), representation.cpu().numpy()

    def encode_emr(self, values, observed_mask, delta_hours, emr_age_hours):
        values, observed, delta = np.asarray(values, float), np.asarray(observed_mask, bool), np.asarray(delta_hours, float)
        require(values.shape == observed.shape == delta.shape and values.ndim == 3 and values.shape[1:] == (24, 19),
                "expected_N_by_24_by_19_hourly_EMR")
        require(np.isfinite(values[observed]).all() and np.isfinite(delta).all() and (delta >= 0).all(), "invalid_observed_EMR_or_delta")
        active = observed & np.asarray(self.scaler["active_features"], bool)[None, None]
        owner, hour, feature = np.where(active)
        normalized = (values[owner, hour, feature] - self.scaler["mean"][feature]) / self.scaler["std"][feature]
        event = np.column_stack((owner, hour, feature, normalized, np.log1p(delta[owner, hour, feature]))).astype(np.float32)
        age = np.asarray(emr_age_hours, float)
        require(age.shape == (len(values),) and np.isfinite(age).all() and (age >= 0).all(), "invalid_EMR_recency")
        metadata = np.column_stack((active.any((1, 2)).astype(float), np.log1p(age), np.zeros(len(values)))).astype(np.float32)
        return self.encode_emr_events(event, metadata)

    def predict_from_features(self, emr, base_logits, cxr_imagenet, cxr_medical, cxr_semantic11, cxr_observed, cxr_age_hours):
        """No IDs, labels, or patient tables are accepted or returned."""
        observed, age = np.asarray(cxr_observed, bool), np.asarray(cxr_age_hours, float)
        emr, base_logits = np.asarray(emr), np.asarray(base_logits)
        n = len(base_logits)
        require(emr.shape == (n, 64) and base_logits.shape == (n, 2) and observed.shape == age.shape == (n,), "invalid_feature_batch_shape")
        require(np.isfinite(emr).all() and np.isfinite(base_logits).all(), "nonfinite_EMR_feature_or_base_output")
        require(np.isfinite(age[observed]).all() and ((age[observed] >= 0) & (age[observed] <= 72)).all(), "CXR_age_must_be_verified_0_to_72_hours")
        cache = {"emr": emr, "logits": base_logits, "cxr_observed": observed, "cxr_age_hours": age}
        for key, value, dimension in (("cxr", cxr_imagenet, 1024), ("cxr_medical", cxr_medical, 1024), ("cxr_semantic11", cxr_semantic11, 11)):
            if value is None and not observed.any():
                value = np.full((n, dimension), np.nan, dtype=np.float32)
            value = np.asarray(value)
            require(value.shape == (n, dimension) and np.isfinite(value[observed]).all(), "invalid_observed_feature_view:" + key)
            cache[key] = value
        risk = predict_module(cache, self.models["risk"], self.scaler)
        regression = predict_module(cache, self.models["LOS_regression"], self.scaler)
        ordinal = predict_module(cache, self.models["LOS_ordinal"], self.scaler)
        los = encode_days(.5 * days(regression, self.scaler) + .5 * days(ordinal, self.scaler), self.scaler)
        logits = np.column_stack((risk, los))
        require(np.isfinite(logits).all(), "nonfinite_final_prediction")
        return {"logits": logits, "mortality_probabilities_raw": sigmoid(risk),
                "mortality_probabilities_calibrated": sigmoid(risk * self.calibrator["slope"] + self.calibrator["intercept"]),
                "ward_los_days_predicted": days(los, self.scaler)}
