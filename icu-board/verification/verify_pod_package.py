"""Unpack the synthetic ZIP and verify it without cached data or outbound network."""
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent / "icu-pod-ready.zip"


def main():
    with tempfile.TemporaryDirectory(prefix="icu-pod-verify-") as folder:
        stage = Path(folder)
        with zipfile.ZipFile(ARCHIVE) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read("package-manifest.json"))
            for record in manifest["files"]:
                assert hashlib.sha256(archive.read(record["path"])).hexdigest() == record["sha256"]
            archive.extractall(stage)
        source = stage / "icu-board"
        env = dict(os.environ)
        for key in list(env):
            if key.startswith(("LLM_", "KHDP_")) or key in ("POOL", "POD_ENV_FILE"):
                env.pop(key)
        env.update(OFFLINE_DEMO="1", PLANNER_MODE="offline", POOL="synth", PYTHONDONTWRITEBYTECODE="1")
        check = subprocess.run([sys.executable, "pod_check.py", "--offline"], cwd=source, env=env,
                               capture_output=True, text=True, check=True)
        readiness = json.loads(check.stdout)
        assert readiness["offline_ready"] and not readiness["real_model_call_verified"]
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q"], cwd=source, env=env,
                               capture_output=True, text=True, check=True)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        env.update(PORT=str(port), HOST="127.0.0.1")
        boot = "import socket, urllib.request, runpy\ndef denied(*a, **k):\n raise RuntimeError('OUTBOUND_NETWORK_FORBIDDEN')\nsocket.socket.connect=denied\nsocket.socket.connect_ex=denied\nsocket.create_connection=denied\nurllib.request.urlopen=denied\nimport consult\nconsult.chat=lambda *a, **k: None\nrunpy.run_path('server.py',run_name='__main__')\n"
        server = subprocess.Popen([sys.executable, "-u", "-c", boot], cwd=source, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            base = f"http://127.0.0.1:{port}"
            for attempt in range(40):
                try:
                    with urllib.request.urlopen(base + "/api/planning/state", timeout=1) as reply:
                        state = json.load(reply)
                    break
                except OSError:
                    if server.poll() is not None:
                        raise AssertionError("clean package server did not start")
                    time.sleep(.1)
            else:
                raise AssertionError("clean package listener unavailable")
            assert len(state["patients"]) == 8 and len(state["beds"]) == 3
            assert state["real_patient_data"] is False
            for route in ("/planning", "/", "/nurse"):
                with urllib.request.urlopen(base + route, timeout=2) as reply:
                    assert reply.status == 200 and reply.read()
            def request(path, body=None, token=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                req = urllib.request.Request(base + path, headers=headers,
                    data=json.dumps(body).encode() if body is not None else None)
                with urllib.request.urlopen(req, timeout=5) as reply:
                    return json.load(reply)

            # Exercise the original portal in a fresh package too. A handover
            # needs the public image catalog even when no images are downloaded.
            request("/api/control", {"action": "pause"})
            token = request("/api/nurse/login", {"account_id": "D-MICU-C", "pin": "2026"})["token"]
            nurse = request("/api/nurse/state", token=token)
            patient = nurse["patients"][0]
            selection = {"bed": patient["id"], "task": "handover",
                         "patient_key": {"pid": patient["patient"]["pid"],
                                         "admit_t": patient["patient"]["admit_t"]}}
            context = request("/api/nurse/consult", selection, token)
            assert context["text"] and context["context"]
            assert context["model"] is None and context["mode"] == "rules"
            request("/api/nurse/logout", {}, token)
            http = subprocess.run([sys.executable, "verification/verify_planning_http.py", "--base", base,
                                   "--output", "verification/package-http.json"], cwd=source, env=env,
                                  capture_output=True, text=True, check=True)
            http_report = json.loads(http.stdout)
        finally:
            server.terminate()
            stdout, stderr = server.communicate(timeout=5)
            if "Traceback" in stderr:
                raise AssertionError("clean package HTTP handler failed:\n" + stderr)
        assert "OUTBOUND_NETWORK_FORBIDDEN" not in stdout + stderr
        report = {"status": "passed", "fresh_unpack": True, "source_hashes_verified": True,
                  "no_patient_data_cache": True, "outbound_network_blocked": True,
                  "offline_ready": readiness["offline_ready"],
                  "package_unit_tests": int(re.search(r"Ran (\d+) tests", tests.stderr).group(1)),
                  "http_check_count": http_report["check_count"], "real_model_call_verified": False,
                  "nurse_handover_without_cached_images": True,
                  "ward_model_transport": "stubbed_unavailable",
                  "scope": "synthetic_operational_demo"}
        (ROOT / "verification/package-readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
