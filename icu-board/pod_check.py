"""Standard-library readiness checks; only --model makes explicit API requests.

Offline checks import only the synthetic planner, never the public-data server.
API checks send synthetic strings and a dummy identifier, never patient data.
Raw responses, exception messages, authorization headers and full environments
are deliberately absent from the report. Passing does not authorize code import.
"""
import argparse
import ast
import importlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
REQUIRED = ("server.py", "pod_env.py", "engine.py", "consult.py", "handover.py", "nurse_portal.py", "synth.py",
            "units.json", "static/index.html", "static/nurse.html", "static/planning.html",
            "planner_core.py", "planner_agent.py", "planner_evaluate.py")


def check(name, status, detail, **extra):
    return dict(name=name, status=status, detail=detail, **extra)


def _no_network(*args, **kwargs):
    raise RuntimeError("offline_network_forbidden")


def _planner_smoke():
    """Exercise the planner contract without importing server or reading records."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
            patch.object(socket.socket, "connect", _no_network), \
            patch.object(socket, "create_connection", _no_network), \
            patch.object(urllib.request, "urlopen", _no_network):
        core = importlib.import_module("planner_core")
        factory = getattr(core, "PlannerHospital", None)
        if factory is None:
            return check("synthetic_planner", "pending", "PlannerHospital 계약이 생성 중입니다. 저장 후 다시 점검하세요.")
        planner = factory(seed=1)
        state = planner.state()
        if not isinstance(state, dict):
            raise TypeError("state_contract")
        patients = state.get("patients")
        if not isinstance(patients, list) or not patients:
            raise ValueError("synthetic_patients_missing")
        patient_id = patients[0].get("id") or patients[0].get("patient_id")
        if not isinstance(patient_id, str):
            raise ValueError("synthetic_identifier_missing")
        patient = planner.get_patient(patient_id)
        if not isinstance(patient, dict):
            raise TypeError("get_patient_contract")
        for row in patients + [patient]:
            if row.get("source") != "synthetic_scenario" or any(key.startswith("_") for key in row):
                raise ValueError("public_synthetic_contract")
            if any(event["t"] > state["t"] for event in row.get("observed_events", [])):
                raise ValueError("future_observation_leak")
        json.dumps(state, ensure_ascii=False)
        json.dumps(patient, ensure_ascii=False)
    return check("synthetic_planner", "pass", "외부 자료·네트워크 없이 합성 state/get_patient와 관찰 시점 확인.",
                 patient_count=len(patients))


def _ward_smoke():
    """The legacy board also starts in the same server; no cached pool is read."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
            patch.object(socket.socket, "connect", _no_network), \
            patch.object(socket, "create_connection", _no_network), \
            patch.object(urllib.request, "urlopen", _no_network):
        engine = importlib.import_module("engine")
        synth = importlib.import_module("synth")
        pool = synth.build(n_per_unit=1, seed=1)
        hospital = engine.Hospital(pool, seed=1, occupancy=0, arrivals_per_unit_shift=0)
        state = hospital.state()
        json.dumps(state, ensure_ascii=False)
    return check("synthetic_ward_dependencies", "pass", "외부 환자 풀·영상 없이 합성 생성기와 상황판 엔진 초기화 확인.",
                 on_duty=len(state["nurses"]))


def offline_checks():
    checks = [check("python_version", "pass" if sys.version_info >= (3, 10) else "fail",
                    "Python 3.10 이상 필요.", version=".".join(map(str, sys.version_info[:3])))]
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    checks.append(check("required_files", "pending" if missing else "pass",
                        "필수 planning 파일의 준비 상태.", missing=missing))
    bad_syntax = []
    for name in REQUIRED:
        if name.endswith(".py") and (ROOT / name).is_file():
            try:
                ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
            except (SyntaxError, UnicodeError, OSError):
                bad_syntax.append(name)
    checks.append(check("python_syntax", "fail" if bad_syntax else "pass",
                        "파일 import나 서버 실행 없이 Python 문법 확인.", invalid=bad_syntax))
    server_source = (ROOT / "server.py").read_text(encoding="utf-8") if (ROOT / "server.py").is_file() else ""
    checks.append(check("offline_startup_flag", "pass" if "OFFLINE_DEMO" in server_source else "pending",
                        "서버의 OFFLINE_DEMO 다운로드 차단 설정 존재 여부. 실제 포트 접속 검사는 별도입니다."))
    try:
        checks.append(_ward_smoke())
    except Exception as error:
        checks.append(check("synthetic_ward_dependencies", "fail", "합성 생성기·상황판 엔진 준비 실패.",
                            error_type=type(error).__name__))
    if not (ROOT / "planner_core.py").is_file():
        checks.append(check("synthetic_planner", "pending", "planner_core.py 생성 전입니다. 저장 후 다시 점검하세요."))
    elif "planner_core.py" in bad_syntax:
        checks.append(check("synthetic_planner", "fail", "planner_core.py 문법을 확인하세요."))
    else:
        try:
            checks.append(_planner_smoke())
        except Exception as error:
            checks.append(check("synthetic_planner", "fail", "합성 planner import/state/get_patient 실패.",
                                error_type=type(error).__name__))
    return checks


def model_configuration():
    base = (os.environ.get("LLM_BASE_URL") or os.environ.get("KHDP_BASE_URL") or "").strip()
    model = os.environ.get("LLM_MODEL") or os.environ.get("KHDP_MODEL") or ""
    if not model:
        model = os.environ.get("KHDP_MODELS", "").split(",")[0]
    key = os.environ.get("LLM_API_KEY") or os.environ.get("KHDP_API_KEY") or ""
    return base.rstrip("/"), model.strip(), key


def _request(base, model, key, messages, timeout, **extra):
    payload = dict(model=model, messages=messages, temperature=0, max_tokens=320, stream=False, **extra)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(base + "/chat/completions", json.dumps(payload).encode(), headers)
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("response_limit")
    return json.loads(raw), round(time.monotonic() - started, 3)


def _api_error(name, error):
    detail = "실제 모델 API 점검 실패. endpoint·권한·모델·지원 파라미터를 확인하세요."
    extra = {"error_type": type(error).__name__}
    if isinstance(error, urllib.error.HTTPError):
        extra["http_status"] = error.code
        # Closing without reading also prevents cleanup warnings from echoing
        # the exception's potentially sensitive reason/URL on stderr.
        try:
            error.close()
        except OSError:
            pass
    return check(name, "fail", detail, **extra)


def model_checks(timeout):
    base, model, key = model_configuration()
    parts = urllib.parse.urlsplit(base)
    valid_base = bool(parts.scheme in ("http", "https") and parts.hostname
                      and not parts.username and not parts.password and not parts.query and not parts.fragment)
    if not valid_base or not model:
        return [check("model_configuration", "fail", "명시적인 단일 base URL과 모델 ID가 필요합니다. 기본 endpoint는 선택하지 않습니다.",
                      base_configured=bool(base), model_configured=bool(model)),
                check("model_basic_response", "unverified", "설정 부족으로 실제 요청하지 않았습니다."),
                check("native_tool_call", "unverified", "설정 부족으로 실제 요청하지 않았습니다.")]
    checks = [check("model_configuration", "pass", "동일 endpoint·모델로 두 합성 API 요청을 수행합니다.")]
    try:
        result, latency = _request(base, model, key,
            [{"role": "user", "content": "합성 API 연결 점검입니다. POD_OK 한 줄로 답하세요. 환자 정보는 없습니다."}], timeout)
        content = result["choices"][0]["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty_response")
        checks.append(check("model_basic_response", "pass", "실제 API에서 비어 있지 않은 응답을 받았습니다. 원문은 출력하지 않습니다.",
                            latency_seconds=latency))
    except Exception as error:
        checks.append(_api_error("model_basic_response", error))
    tool = {"type": "function", "function": {"name": "get_patient", "description": "합성 연결 점검용 환자 조회 요청",
            "parameters": {"type": "object", "properties": {"patient_id": {"type": "string", "enum": ["POD-SYNTH-001"]}},
                           "required": ["patient_id"], "additionalProperties": False}}}
    try:
        result, latency = _request(base, model, key,
            [{"role": "user", "content": "실제 환자가 아닌 합성 ID POD-SYNTH-001로 get_patient 도구를 호출하세요."}],
            timeout, tools=[tool])
        calls = result["choices"][0]["message"].get("tool_calls") or []
        valid = False
        for call in calls:
            function = call.get("function", {})
            arguments = function.get("arguments")
            if (call.get("type") == "function" and isinstance(call.get("id"), str) and call["id"]
                    and function.get("name") == "get_patient" and isinstance(arguments, str)):
                value = json.loads(arguments)
                valid = (isinstance(value, dict) and set(value) == {"patient_id"}
                         and value.get("patient_id") == "POD-SYNTH-001")
                if valid:
                    break
        if not valid:
            raise ValueError("native_tool_response_missing")
        checks.append(check("native_tool_call", "pass", "native tool_calls의 이름·합성 인자를 확인했습니다. 실제 도구는 실행하지 않습니다.",
                            latency_seconds=latency))
    except Exception as error:
        checks.append(_api_error("native_tool_call", error))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pod 준비 검사. 기본은 네트워크 없는 합성 점검입니다.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true", help="합성 파일·import 확인만 수행(기본)")
    modes.add_argument("--model", action="store_true", help="설정한 모델 API에 합성 요청 2회를 실제 전송")
    parser.add_argument("--timeout", type=float, default=15, help="실제 API 요청당 제한 초(1~60, 기본 15)")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        parser.error("timeout은 1~60초여야 합니다.")
    checks = offline_checks()
    offline_ready = all(item["status"] == "pass" for item in checks)
    if args.model:
        try:
            checks.extend(model_checks(args.timeout))
        except Exception as error:
            checks.append(_api_error("model_configuration", error))
    status = "fail" if any(item["status"] == "fail" for item in checks) else (
        "pending" if any(item["status"] == "pending" for item in checks) else "pass")
    report = {"mode": "model" if args.model else "offline", "status": status, "checks": checks,
              "offline_ready": offline_ready,
              "real_model_call_verified": any(item["name"] == "model_basic_response" and item["status"] == "pass" for item in checks),
              "native_tool_call_verified": any(item["name"] == "native_tool_call" and item["status"] == "pass" for item in checks),
              "patient_data_sent": False, "code_import_permission": "unconfirmed", "probe_required": False,
              "limits": ["합성 smoke는 실제 K-MIMIC 연결·임상 효과·브라우저/포트 접근 성공의 증거가 아닙니다.",
                         "규칙 기반 합성 결과는 실제 모델 응답과 별도입니다."]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
