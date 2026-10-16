"""Package the verified synthetic demo, excluding data caches and credentials."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
TARGET = ROOT.parent / "icu-pod-ready.zip"
CODE = ("engine.py", "server.py", "consult.py", "handover.py", "nurse_portal.py", "synth.py", "mimic.py", "kmimic.py",
        "planner_core.py", "planner_agent.py", "planner_evaluate.py", "pod_check.py", "pod_env.py", "timeline_check.py",
        "units.json", "concepts.json", "README.md", "POD_사용방법.md", ".env.pod.example", "Dockerfile",
        "test_planner_core.py", "test_planner_agent.py", "test_pod_check.py", "test_timeline_check.py",
        "build_pod_package.py", "static/index.html", "static/nurse.html", "static/planning.html",
        "static/cxr/index.json")
REPORTS = ("verification/planning-offline.json", "verification/planning-http.json", "verification/planning-browser.json",
           "verification/pod-readiness.json", "verification/planning-checks.json", "verification/package-readiness.json",
           "verification/verify_planning_http.py", "verification/verify_pod_package.py")


def main():
    files = [(ROOT / name, "icu-board/" + name) for name in CODE + REPORTS]
    files.append((ROOT.parent / "start-pod-demo.command", "start-pod-demo.command"))
    missing = [target for source, target in files if not source.is_file()]
    if missing:
        raise SystemExit("Required files missing: " + ", ".join(missing))
    manifest = {"release": "2026-10-16-github-demo-1", "scope": "synthetic_operational_demo",
                "real_patient_data_included": False, "api_keys_included": False,
                "code_import_permission": "unconfirmed", "live_model_verified": False,
                "files": [{"path": target, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
                          for source, target in files]}
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, target in files:
            archive.write(source, target)
        archive.writestr("icu-board/data/.keep", "Synthetic pools are generated locally. No patient data cache included.\n")
        archive.writestr("package-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(TARGET) as archive:
        assert archive.testzip() is None
        for entry in manifest["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
        assert all(not name.endswith((".env", ".env.pod", ".jpg", ".png")) for name in archive.namelist())
        assert not any("pool_mimic" in name or "pool_kmimic" in name for name in archive.namelist())
    print(json.dumps({"archive": str(TARGET), "bytes": TARGET.stat().st_size,
                      "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(), "source_files": len(files),
                      "verified": True, "real_patient_data_included": False}))


if __name__ == "__main__":
    main()
