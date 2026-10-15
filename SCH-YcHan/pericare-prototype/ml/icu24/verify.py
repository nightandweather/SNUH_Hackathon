"""Verify a trusted local model through the actual PeriCare HTTP import path.

No services remain running. A temporary SQLite database is removed on exit.
The report contains no patient identifiers, rows, or individual probabilities.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import numpy as np
import pandas as pd

from app.engine import Engine
from app.model import validate_prediction
from app.server import make_handler
from .artifacts import FEATURE_COLUMNS, model_frame
from .features import make_features
from .serve import Predictor, create_server


def request(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def verify(model, snapshot, prepared=None):
    dataset = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    predictor = Predictor(model)
    model_server = create_server(predictor, "127.0.0.1", 0, api_key="")
    model_thread = threading.Thread(target=model_server.serve_forever, daemon=True)
    model_thread.start()
    app_server, app_thread = None, None
    try:
        model_url = f"http://127.0.0.1:{model_server.server_address[1]}"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "MODEL_BACKEND": "remote", "MODEL_TASK": "icu24_after_operation_end",
                "MODEL_URL": model_url + "/predict", "MODEL_API_KEY": "",
                "APP_USERNAME": "", "APP_PASSWORD": ""}):
            engine = Engine(str(Path(directory) / "verification.db"))
            app_server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine))
            app_thread = threading.Thread(target=app_server.serve_forever, daemon=True)
            app_thread.start()
            app_url = f"http://127.0.0.1:{app_server.server_address[1]}"
            before = request(app_url + "/api/state")
            request(app_url + "/api/actions/import", {"dataset": dataset, "expected_revision": before["revision"]})
            view = request(app_url + "/api/state")
            patient = view["patients"][0]
            prediction = patient["prediction"]
            assert prediction["mode"] == "remote_partial", prediction.get("model_error")
            assert prediction["model_version"] == predictor.bundle["model_version"]
            assert prediction["need_score"] is None and prediction["icu_los_hours"] is None and prediction["confidence"] is None
            assert patient["recommendation"]["status"] == "BLOCKED"
            assert not view["automation"]["enabled"]
            assert prediction["features"]["source_mode"] == "import"
            parity = None
            if prepared:
                frame = pd.read_csv(prepared, dtype={"op_id": str})
                expected = frame.loc[frame.op_id == str(patient["operation_id"])].iloc[[0]]
                actual = pd.DataFrame([make_features(prediction["features"])])
                expected, actual = model_frame(expected), model_frame(actual)
                for column in FEATURE_COLUMNS:
                    if expected[column].dtype.kind in "fiu":
                        np.testing.assert_allclose(expected[column], actual[column], equal_nan=True)
                    else:
                        assert expected[column].tolist() == actual[column].tolist(), column
                parity = True
            unsupported = request(model_url + "/predict", {"schema_version": "2.0", "features": {
                **prediction["features"], "phase": "ICU"}})
            validate_prediction(unsupported)
            assert unsupported["prediction_status"] == "unsupported"
            assert unsupported["icu_probability"] is None
            health = request(model_url + "/health")
            app_server.shutdown()
            app_server.server_close()
            app_thread.join(timeout=3)
            app_server = None
            return {"model_version": health["model_version"], "actual_http_import": True,
                    "training_serving_feature_parity": parity, "probability_only": True,
                    "unsupported_phase_abstains": True, "reservation_withheld": True,
                    "real_care_automation_disabled": True, "inference_latency_ms": prediction["latency_ms"]}
    finally:
        if app_server is not None:
            app_server.shutdown()
            app_server.server_close()
            app_thread.join(timeout=3)
        model_server.shutdown()
        model_server.server_close()
        model_thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--prepared")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = verify(args.model, args.snapshot, args.prepared)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
