"""Small local ICU24 inference service, loaded once at startup.

Run: python -m ml.icu24.serve --artifact data/icu24/run26/model.joblib
Only trusted local joblib artifacts may be loaded; joblib can execute code.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Keep one prediction from consuming every CPU in a multi-request UI session.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import joblib
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from .artifacts import FEATURE_COLUMNS, calibrated_probability
from .features import NUMERIC_FEATURES, CATEGORICAL_FEATURES, FEATURE_VERSION, make_features

TASK = "icu24_after_operation_end"
NULL_OUTPUTS = (
    "need_score", "need_probability", "intensive_hours", "intensive_hours_upper",
    "icu_los_hours", "icu_los_upper", "hospital_los_days", "hospital_los_upper", "confidence",
)


class Predictor:
    def __init__(self, artifact, allow_synthetic=False):
        self.bundle = joblib.load(artifact)
        if self.bundle.get("task") != TASK or self.bundle.get("artifact_schema_version") != 1:
            raise ValueError("Unsupported ICU24 artifact task or schema")
        expected = hashlib.sha256(json.dumps(FEATURE_COLUMNS).encode()).hexdigest()
        if (self.bundle.get("feature_fingerprint") != expected
                or self.bundle.get("feature_version") != FEATURE_VERSION):
            raise ValueError("Artifact feature whitelist differs from this service; use matching code/model versions")
        if self.bundle.get("dataset_kind") not in ("inspire", "synthetic"):
            raise ValueError("Artifact does not declare its training data kind")
        if self.bundle.get("dataset_kind") == "synthetic" and not allow_synthetic:
            raise ValueError("Synthetic artifacts require --allow-synthetic-artifact and are only for software smoke tests")
        trained_version = self.bundle.get("versions", {}).get("sklearn")
        if trained_version != sklearn.__version__:
            raise ValueError(f"scikit-learn version mismatch: artifact needs {trained_version}, runtime has {sklearn.__version__}; use the training environment")
        self.thread_limit = threadpool_limits(limits=2)
        self.lock = threading.Lock()

    def base_result(self, status="available", reason=None):
        result = {
            "schema_version": "2.0", "task": TASK, "prediction_status": status,
            "supported_outputs": ["icu_probability"],
            "icu_probability": None, "model_version": self.bundle["model_version"],
            "horizon_minutes": 1440, "interval_kind": "not_applicable",
            "contributions": [], "feature_version": FEATURE_VERSION,
            "training_dataset_kind": self.bundle["dataset_kind"],
            "supported_phases": self.bundle["supported_phases"],
            **dict.fromkeys(NULL_OUTPUTS, None),
        }
        if reason:
            result["unsupported_reason"] = reason
        return result

    def predict(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Request must be a JSON object")
        if "schema_version" in payload and payload["schema_version"] != "2.0":
            raise ValueError("ICU24 requests require schema_version 2.0")
        features = payload.get("features", payload)
        if not isinstance(features, dict):
            raise ValueError("features must be a JSON object")
        phase = str(features.get("phase", "")).upper()
        if phase not in ("PREOP", "OR", "PACU", "ICU", "WARD", "PENDING", "ADMITTING", "DISCHARGED", "DECEASED", "TRANSFERRED"):
            raise ValueError("A valid current phase is required")
        if phase not in self.bundle["supported_phases"]:
            return self.base_result("unsupported", "현재 단계는 이 학습 모델의 적용 범위에 포함되지 않습니다.")
        source = features.get("source") or {}
        context = features.get("data_context") or {}
        source_context = context.get("source") or {} if isinstance(context, dict) else {}
        mode = features.get("source_mode")
        if mode is None and isinstance(source, dict):
            mode = source.get("mode", source.get("kind", source.get("type")))
        if mode is None and isinstance(source_context, dict):
            mode = source_context.get("mode", source_context.get("kind", source_context.get("type")))
        if mode not in ("import", "imported"):
            return self.base_result("unsupported", "실제 자료의 가져오기 모드가 확인된 입력만 예측할 수 있습니다.")
        # Keep laboratory visibility identical to preparation. The client must
        # not widen the model's training lookback or introduce unseen lab fields
        # into a static-only artifact's all-missing training columns.
        feature_payload = dict(features)
        training_metadata = self.bundle.get("metadata", {})
        feature_payload["max_lab_age_minutes"] = float(training_metadata.get("lab_lookback_days", 30)) * 1440
        if training_metadata.get("include_labs") is False:
            feature_payload["preop_labs"] = {}
        try:
            values = make_features(feature_payload)
        except (TypeError, AttributeError, ValueError) as error:
            raise ValueError("Invalid current-time feature structure") from error
        population = self.bundle["input_population"]
        if (values["age"] is None or not population["minimum_age"] <= values["age"] <= population["maximum_age"]):
            return self.base_result("unsupported", "성인 연령 정보가 없거나 학습 범위를 벗어나 예측을 보류합니다.")
        frame = pd.DataFrame([values])
        started = time.perf_counter()
        with self.lock:
            probability = float(calibrated_probability(self.bundle, frame)[0])
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise RuntimeError("Model generated an invalid probability")
        result = self.base_result()
        result["icu_probability"] = probability
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result["input_missing_numeric_features"] = [name for name in NUMERIC_FEATURES if values[name] is None]
        result["decision_threshold"] = self.bundle["decision_threshold"]
        result["target_definition"] = self.bundle["target_definition"]
        return result


def create_server(predictor, host="127.0.0.1", port=9000, api_key=None):
    expected_key = os.environ.get("MODEL_API_KEY", "") if api_key is None else api_key

    class Handler(BaseHTTPRequestHandler):
        server_version = "PeriCareICU24/1.0"

        def send_json(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/health":
                return self.send_json(404, {"error": "not_found"})
            self.send_json(200, {"status": "ok", "task": TASK,
                                 "model_version": predictor.bundle["model_version"],
                                 "training_dataset_kind": predictor.bundle["dataset_kind"],
                                 "supported_phases": predictor.bundle["supported_phases"]})

        def do_POST(self):
            if self.path != "/predict":
                return self.send_json(404, {"error": "not_found"})
            if expected_key and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + expected_key):
                return self.send_json(401, {"error": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 1024 * 1024:
                    return self.send_json(413, {"error": "JSON body must be between 1 byte and 1 MiB"})
                payload = json.loads(self.rfile.read(length))
                result = predictor.predict(payload)
                self.send_json(200, result)
            except (ValueError, UnicodeDecodeError) as error:
                self.send_json(400, {"error": str(error)})
            except Exception:
                # Payloads and exception representations may contain patient data.
                self.send_json(500, {"error": "model_prediction_failed"})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", "--model", dest="artifact", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--allow-synthetic-artifact", action="store_true")
    args = parser.parse_args()
    predictor = Predictor(Path(args.artifact), args.allow_synthetic_artifact)
    server = create_server(predictor, args.host, args.port)
    print(json.dumps({"status": "listening", "host": args.host, "port": server.server_address[1],
                      "model_version": predictor.bundle["model_version"]}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
