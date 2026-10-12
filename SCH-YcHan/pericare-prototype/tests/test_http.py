import base64
import copy
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.engine import Engine
from app.model import demo_predict
from app.server import make_handler, csv_bytes


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Engine(self.tmp.name + "/api.db")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.engine))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        h = headers or {}
        if data is not None or raw is not None:
            h = {"Content-Type": "application/json", **h}
            conn.request("POST", path, raw if raw is not None else json.dumps(data), h)
        else:
            conn.request("GET", path, headers=h)
        r = conn.getresponse()
        payload, status, response_headers = r.read(), r.status, dict(r.getheaders())
        conn.close()
        return status, payload, response_headers

    def test_health_and_static_assets(self):
        for path in ("/health", "/", "/app.js", "/hospital.js", "/styles.css", "/accessibility.css", "/hospital.css", "/core.css", "/favicon.svg", "/api/example"):
            status, body, headers = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

    def test_state_and_exports(self):
        status, body, _ = self.request("/api/state")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual(len(state["patients"]), 60)
        for path in ("/api/export/data", "/api/export/audit", "/api/export/predictions", "/api/export/reservations"):
            status, body, headers = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn("attachment", headers["Content-Disposition"])

    def test_json_errors_and_nan_rejected(self):
        self.assertEqual(self.request("/api/actions/advance", raw="{bad}")[0], 400)
        self.assertEqual(self.request("/api/actions/advance", raw='{"minutes":NaN}')[0], 400)
        self.assertEqual(self.request("/api/actions/advance", data=[])[0], 400)

    def test_cross_origin_browser_requests_rejected(self):
        self.assertEqual(self.request("/api/actions/advance", data={"minutes": 5}, headers={"Origin": "http://untrusted.example"})[0], 403)

    def test_concurrent_stale_review_is_409_over_http(self):
        rev = self.engine.state["revision"]
        body = {"expected_revision": rev, "patient_id": "DEMO-007"}
        self.assertEqual(self.request("/api/actions/apply_recommendation", data=body)[0], 200)
        self.assertEqual(self.request("/api/actions/apply_recommendation", data=body)[0], 409)

    def test_failed_import_does_not_replace_current_state(self):
        state = copy.deepcopy(self.engine.state)
        status, _, _ = self.request("/api/actions/import", data={"expected_revision": state["revision"], "dataset": {}})
        self.assertEqual(status, 400)
        self.assertEqual(self.engine.state, state)

    def test_csv_formula_escaping(self):
        payload = csv_bytes([{"name": "=HYPERLINK(\"bad\")", "number": -2}], ["name", "number"]).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", payload)
        self.assertIn(",-2", payload)

    def test_path_traversal_is_not_served(self):
        self.assertEqual(self.request("/../server.py")[0], 404)


class RemoteAdapterTests(unittest.TestCase):
    def test_remote_contract_roundtrip_and_no_future_payload(self):
        requests = []
        class FakeModel(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                prediction = demo_predict(body["features"])
                prediction["model_version"] = "test-external-v1"
                data = json.dumps(prediction).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeModel)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"MODEL_BACKEND": "remote", "MODEL_URL": f"http://127.0.0.1:{server.server_port}/predict"}):
                engine = Engine(d + "/remote.db")
                self.assertEqual(len(requests), 60)
                self.assertTrue(all(p["mode"] == "remote" for p in engine.state["predictions"].values()))
                for req in requests:
                    self.assertTrue(all(o["minute"] <= req["as_of_minute"] for o in req["features"]["signal_window"]))
                    self.assertNotIn("actual_end_minute", req["features"])
                    self.assertNotIn("truth_icu", json.dumps(req))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_remote_failure_blocks_and_masks_predictions(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"MODEL_BACKEND": "remote", "MODEL_URL": ""}):
            engine = Engine(d + "/failed.db")
            view = engine.view()
            for p in view["patients"]:
                self.assertIsNone(p["prediction"]["need_score"])
                if p["phase"] not in ("ICU", "WARD"):
                    self.assertEqual(p["recommendation"]["status"], "BLOCKED")


class AuthTests(unittest.TestCase):
    def test_optional_auth_and_health_exception(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"APP_USERNAME": "tester", "APP_PASSWORD": "unit-test-only"}):
            engine = Engine(d + "/auth.db")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
                conn.request("GET", "/api/state")
                response = conn.getresponse()
                self.assertEqual(response.status, 401)
                response.read()
                auth = "Basic " + base64.b64encode(b"tester:unit-test-only").decode()
                conn.request("GET", "/api/state", headers={"Authorization": auth})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                conn.request("GET", "/health")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
