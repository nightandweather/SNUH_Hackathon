"""가상 ICU 상황판 웹 서버 (표준 라이브러리만).

    python server.py            # http://127.0.0.1:8000
    PORT=8080 POOL=kmimic python server.py

기본 접속은 이 컴퓨터에서만. 공유 시 HOST를 명시한다.
"""
import copy
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from pod_env import load_pod_env
load_pod_env()

import consult
import engine
import handover
import nurse_portal
import planner_agent
from planner_core import PlannerError

ROOT = Path(__file__).parent
OFFLINE_DEMO = os.environ.get("OFFLINE_DEMO") == "1"


def first_pool():
    """POOL 환경변수 > 만들어둔 MIMIC 풀 > 공개 MIMIC-IV demo 자동 다운로드 > 가상 환자."""
    if os.environ.get("POOL"):
        return engine.load_pool(os.environ["POOL"])
    if OFFLINE_DEMO:
        return engine.load_pool("synth")
    if not (ROOT / "data" / "pool_mimic.json").exists():
        try:
            import mimic
            print("첫 실행: 공개 MIMIC-IV demo 내려받는 중 (약 8MB)…")
            d = ROOT / "data" / "mimic-iv-demo"
            mimic.fetch(d)
            mimic.save(d)
        except Exception as e:
            print(f"MIMIC-IV demo 준비 실패 ({e}) → 가상 환자로 실행")
            return engine.load_pool("synth")
    return engine.load_pool("mimic")


POOL = first_pool()
if not OFFLINE_DEMO:
    try:
        print("예시 흉부 X-ray: %d/%d장 준비됨" % consult.fetch_cxr())
    except Exception as e:  # 인터넷이 없으면 영상 없이 판독문만으로 상담
        print(f"예시 흉부 X-ray 준비 실패 ({e}) → 판독문만 사용")
lock = threading.Lock()
portal = nurse_portal.NursePortal()
planner = planner_agent.PlannerService()
sim = {"h": engine.Hospital(POOL, "auto", 1), "running": True, "speed": 2.0, "seed": 1,
       "baseline": None}


def reset(policy=None, seed=None):
    policy = policy or sim["h"].policy
    seed = sim["seed"] if seed is None else seed
    sim["h"] = engine.Hospital(POOL, policy, seed)
    sim["seed"] = seed
    sim["baseline"] = None


def ticker():
    while True:
        time.sleep(1.0 / sim["speed"])
        with lock:
            if sim["running"] and sim["h"].t < 24 * 60:
                sim["h"].step()
                if sim["h"].t >= 24 * 60:
                    sim["running"] = False


def compare(seed, minutes):
    """같은 시나리오(같은 seed)를 두 방식으로 끝까지 돌려 비교."""
    return {p: engine.run(POOL, p, seed, minutes) for p in ("fixed", "auto")}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (ROOT / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/nurse", "/nurse.html"):
            page = ROOT / "static" / "nurse.html"
            if page.is_file():
                return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            return self._send(404, {"error": "간호사 화면을 준비 중입니다."})
        if path in ("/planning", "/planning.html"):
            page = ROOT / "static" / "planning.html"
            if page.is_file():
                return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
            return self._send(404, {"error": "예약 시연 화면을 준비 중입니다."})
        if path == "/api/planning/state":
            return self._send(200, planner.state())
        if path == "/api/nurse/accounts":
            with lock:
                accounts = portal.accounts(sim["h"])
            return self._send(200, {"accounts": accounts})
        if path == "/api/nurse/state":
            try:
                with lock:
                    token = portal.bearer(self.headers)
                    state = portal.state(sim["h"], token, seed=sim["seed"], running=sim["running"],
                                         source=sorted({p["source"] for p in POOL}))
                    state["tasks"] = [task for patient in state["patients"]
                                      for task in self._diagnostic_images(sim["h"], patient["id"])]
            except nurse_portal.PortalError as error:
                return self._send(error.code, {"error": str(error)})
            return self._send(200, state)
        if path.startswith("/static/cxr/") and path.endswith((".jpg", ".png")):
            f = ROOT / "static" / "cxr" / Path(path).name
            if f.exists():
                return self._send(200, f.read_bytes(), "image/jpeg" if f.suffix == ".jpg" else "image/png")
        if path == "/api/llm":
            return self._send(200, {"model": consult.model_name(), "base": consult._cfg()["base"]})
        if path == "/api/state":
            with lock:
                st = sim["h"].state()
                st.update(running=sim["running"], speed=sim["speed"], seed=sim["seed"],
                          source=sorted({p["source"] for p in POOL}),
                          handover_receipts=copy.deepcopy(getattr(sim["h"], "handover_receipts", [])))
            return self._send(200, st)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # A handler may process several requests; authorization is per request.
        self._portal_token = None
        self._portal_operation = None
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if not isinstance(body, dict):
            return self._send(400, {"error": "JSON 객체가 필요합니다."})
        path = self.path.split("?")[0]
        if path == "/api/planning/action":
            if not isinstance(body.get("scenario_id"), str) or not body["scenario_id"]:
                return self._send(400, {"error": "현재 시나리오 ID가 필요합니다. 화면을 새로고침하세요.",
                                        "code": "SCENARIO_REQUIRED", "state": planner.state()})
            try:
                result = planner.handle(body)
            except PlannerError as error:
                return self._send(error.status, {"error": str(error), "code": error.code,
                                                 "state": planner.state(),
                                                 "agent": planner.state()["agent_status"]})
            return self._send(200, result)
        if path.startswith("/api/nurse/"):
            return self._nurse_post(path, body)
        if path == "/api/patient":
            return self._patient(body)
        if path == "/api/diagnostics":
            return self._diagnostics(body)
        if path == "/api/image-review":
            return self._image_review(body)
        if path == "/api/handover":
            return self._handover_receipt(body)
        if self.path.split("?")[0] == "/api/consult":
            return self._consult(body)
        if self.path.split("?")[0] == "/api/care-log":
            return self._care_log(body)
        if self.path.split("?")[0] == "/api/emergency":
            return self._emergency(body)
        a = body.get("action")
        with lock:
            if a == "pause":
                sim["running"] = False
            elif a == "play":
                sim["running"] = True
            elif a == "speed":
                sim["speed"] = max(0.5, min(30.0, float(body.get("value", 2))))
            elif a == "policy":
                reset(policy=body.get("value"))
            elif a == "reset":
                reset(seed=int(body.get("seed", sim["seed"] + 1)))
            elif a == "next_shift":
                # 시간만 바꾸지 않고 매 분 입퇴실·이벤트·간호·교대를 모두 진행한다.
                remaining = sim["h"].state()["shift"]["remaining_min"]
                target = min(24 * 60, sim["h"].t + remaining)
                sim["running"] = False
                while sim["h"].t < target:
                    sim["h"].step()
            elif a == "compare":
                try:
                    minutes = int(body.get("minutes", 480))
                except (ValueError, TypeError):
                    return self._send(400, {"error": "compare minutes must be 480 or 1440"})
                if minutes not in (480, 1440):
                    return self._send(400, {"error": "compare minutes must be 480 or 1440"})
                seed = sim["seed"]
            else:
                return self._send(400, {"error": "unknown action"})
        if a == "compare":  # 잠금 밖에서 계산
            return self._send(200, compare(seed, minutes))
        self._send(200, {"ok": True})

    def _nurse_post(self, path, body):
        """Reuse patient handlers after deriving the actor from a bearer session."""
        try:
            if path == "/api/nurse/login":
                with lock:
                    reply = portal.login(sim["h"], body.get("account_id"), body.get("pin"))
                return self._send(200, reply)
            token = portal.bearer(self.headers)
            if path == "/api/nurse/logout":
                with lock:
                    portal.logout(token)
                return self._send(200, {"ok": True})
            handlers = {"patient": self._patient, "care-log": self._care_log,
                        "diagnostics": self._diagnostics, "handover": self._handover_receipt,
                        "consult": self._consult}
            operation = path.removeprefix("/api/nurse/")
            if operation not in handlers:
                return self._send(404, {"error": "not found"})
            self._portal_token, self._portal_operation = token, operation
            return handlers[operation](body)
        except nurse_portal.PortalError as error:
            return self._send(error.code, {"error": str(error)})

    def _portal_response(self, body):
        if getattr(self, "_portal_token", None):
            return dict(body, account=copy.deepcopy(self._portal_account),
                        context_nurse=copy.deepcopy(self._portal_context_nurse))
        return body

    def _selection(self, body):
        """잠금 안에서 환자·근무조가 입력 시작 시점과 같은지 확인한다."""
        h = sim["h"]
        if getattr(self, "_portal_token", None):
            account, actor_id = portal.authorize(h, self._portal_token, body, self._portal_operation)
            self._portal_account = account
            self._portal_context_nurse = portal.actual_nurse(h, actor_id)
            # Client role, slot and staff fields cannot change the acting account.
            body["nurse_id"] = actor_id
            body["staff_id"] = h.nurses[actor_id]["staff_id"]
        bed_id = body.get("bed", "")
        bed = h.beds.get(bed_id)
        pt = bed and bed["patient"]
        if pt is None:
            return 404, "빈 병상입니다. 환자를 다시 선택하세요.", None
        key = body.get("patient_key")
        if key is not None and (not isinstance(key, dict) or
                                key.get("pid") != pt["src"]["pid"] or
                                key.get("admit_t") != pt["admit_t"]):
            return 409, "선택한 환자가 바뀌었습니다. 상담창을 다시 열어 주세요.", None
        nurse_id = body.get("nurse_id") or bed["nurse"]
        nurse = h.nurses.get(nurse_id)
        if nurse is None:
            return 400, "현재 근무 중인 간호사를 선택하세요.", None
        staff_id = body.get("staff_id")
        if staff_id is not None and staff_id != nurse["staff_id"]:
            return 409, "근무조가 바뀌었습니다. 새 담당자로 상담창을 다시 열어 주세요.", None
        return 200, None, nurse_id

    def _care_log(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            try:
                action = sim["h"].record_care_action(nurse_id, body["bed"], body.get("text"))
            except PermissionError as error:
                return self._send(403, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                return self._send(400, {"error": str(error)})
            actions = sim["h"].patient_actions(body["bed"])
        self._send(200, self._portal_response({"ok": True, "action": action, "actions": actions}))

    def _care_scope(self, nurse_id, bed_id):
        h = sim["h"]
        nurse, bed = h.nurses[nurse_id], h.beds[bed_id]
        responding = any(inc["bed"] == bed_id and inc["end"] is None
                         and nurse_id in inc["responders"] for inc in h.incidents)
        return nurse["unit"] == bed["unit"] and (bed["nurse"] == nurse_id
                or bed_id in nurse["cover"] or responding or nurse["role"] == "charge")

    @staticmethod
    def _diagnostic_images(h, bed_id):
        tasks = h.patient_diagnostics(bed_id)
        pt = h.beds[bed_id]["patient"]
        for task in tasks:
            if task["kind"] == "portable_xray" and task["status"] == "image_available" and pt:
                image = consult.cxr_for(pt["src"])
                if (consult.CXR_DIR / image["file"]).is_file():
                    task.update(image_url=f"/static/cxr/{image['file']}", image_id=image["image_id"],
                                image_source="public_nih_example", patient_linked=False)
        return tasks

    def _patient(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(403, {"error": "담당·대신 보기·출동 환자 또는 해당 병동 책임간호사 범위입니다."})
            h = sim["h"]
            history = h.patient_vital_history(body["bed"])
            tasks = self._diagnostic_images(h, body["bed"])
        self._send(200, self._portal_response({"history": history, "diagnostics": tasks,
                         "patient_key": history["patient_key"]}))

    def _diagnostics(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(403, {"error": "이 환자의 담당·대신 보기·출동 간호사 또는 병동 책임간호사만 요청할 수 있습니다."})
            h = sim["h"]
            if any(task["kind"] == body.get("kind") and task["status"] not in
                   ("specimen_sent", "image_available", "cancelled")
                   for task in h.patient_diagnostics(body["bed"])):
                return self._send(409, {"error": "같은 검사가 이미 진행 중입니다."})
            try:
                task = h.request_diagnostic(nurse_id, body["bed"], body.get("kind"))
            except PermissionError as error:
                return self._send(403, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                return self._send(400, {"error": str(error)})
            tasks = self._diagnostic_images(h, body["bed"])
        self._send(200, self._portal_response({"ok": True, "task": task, "diagnostics": tasks}))

    def _image_review(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(403, {"error": "현재 환자를 담당하는 병동 범위에서만 영상 검토를 요청할 수 있습니다."})
            h = sim["h"]
            try:
                task = h.diagnostic_task(body["bed"], body.get("task_id"))
            except (ValueError, TypeError, KeyError):
                return self._send(404, {"error": "이 환자의 검사 요청을 찾을 수 없습니다."})
            if task["kind"] != "portable_xray" or task["status"] != "image_available":
                return self._send(409, {"error": "포터블 촬영 시연이 완료된 뒤 영상 검토를 요청하세요."})
            ctx = consult.context(h, body["bed"], nurse_id=nurse_id)
            requested_staff_id = h.nurses[nurse_id]["staff_id"]
            requested_cycle = h._shift_at(h.t)["cycle"]
        answer = consult.image_review_turn(ctx, task)
        with lock:
            if sim["h"] is not h:
                return self._send(409, {"error": "시나리오가 바뀌어 영상 검토 결과를 저장하지 않았습니다."})
            if (h.nurses[nurse_id]["staff_id"] != requested_staff_id
                    or h._shift_at(h.t)["cycle"] != requested_cycle):
                return self._send(409, {"error": "영상 검토 중 근무조가 바뀌었습니다. 다음 담당자로 다시 요청하세요."})
            code, error, _ = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(409, {"error": "검토 중 환자 담당이 바뀌었습니다. 새 담당자로 다시 선택하세요."})
            answer.update(t=h.t, clock=h.clock(), as_of=ctx["now"], context_t=ctx["t"])
            try:
                h.save_image_review(body["bed"], task["id"], answer)
            except (ValueError, RuntimeError, KeyError) as error:
                return self._send(409, {"error": str(error)})
            tasks = self._diagnostic_images(h, body["bed"])
        self._send(200, dict(answer, diagnostics=tasks, patient_key=ctx["patient_key"]))

    def _handover_receipt(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            h = sim["h"]
            try:
                receipt = handover.record_receipt(h, nurse_id, body["bed"], body.get("handover_t"),
                                                  body.get("action"), body.get("text"))
            except PermissionError as error:
                return self._send(403, {"error": str(error)})
            except RuntimeError as error:
                return self._send(409, {"error": str(error)})
            except ValueError as error:
                return self._send(400, {"error": str(error)})
            snapshot = h.state()["last_handover"]
            if getattr(self, "_portal_token", None):
                snapshot = portal.scoped_handover(h, self._portal_account)
        self._send(200, self._portal_response({"ok": True, "receipt": receipt, "last_handover": snapshot}))

    def _emergency(self, body):
        """선택한 가상 환자에게 시연 사건을 주입한다. 수행 기록은 만들지 않는다."""
        with lock:
            code, error, _ = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            h = sim["h"]
            if any(i["bed"] == body["bed"] and i["end"] is None for i in h.incidents):
                return self._send(409, {"error": "이 환자는 이미 사건 대응 중입니다."})
            if body.get("scenario") not in ("code_blue", "hypoxia", "hypotension"):
                return self._send(400, {"error": "지원하지 않는 응급 시연입니다."})
            try:
                incident = h.trigger_emergency(body["bed"], body["scenario"])
            except ValueError as error:
                return self._send(400, {"error": str(error)})
        self._send(200, {"ok": True, "incident": incident})

    def _consult(self, body):
        """간호사 ↔ AI 에이전트 한 턴. 맥락은 잠금 안에서 뽑고, 모델 호출은 잠금 밖에서."""
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            h = sim["h"]
            ctx = consult.context(h, body.get("bed", ""), nurse_id=nurse_id)
            requested_staff_id = h.nurses[nurse_id]["staff_id"]
            requested_cycle = h._shift_at(h.t)["cycle"]
        if ctx is None:
            return self._send(404, {"error": "빈 병상"})
        history = body.get("history") or []
        if body.get("who") != "nurse" and consult.is_handover_request(history, body.get("task")):
            answer = consult.handover_turn(ctx)
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        elif body.get("who") == "nurse":
            answer = consult.nurse_turn_result(ctx, history)
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        else:
            answer = consult.agent_turn_result(ctx, history, task=body.get("task"))
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        if getattr(self, "_portal_token", None):
            with lock:
                if sim["h"] is not h:
                    return self._send(409, {"error": "상담 중 시나리오가 바뀌었습니다. 다시 선택하세요."})
                account = portal.account(h, self._portal_token)  # Logout invalidates an in-flight answer.
                if (not account["on_duty"] or h.nurses[nurse_id]["staff_id"] != requested_staff_id
                        or h._shift_at(h.t)["cycle"] != requested_cycle
                        or body["bed"] not in portal.visible_beds(h, account)):
                    return self._send(409, {"error": "상담 중 근무조나 환자 담당이 바뀌었습니다. 다시 선택하세요."})
                # Even clients omitting a key cannot receive a previous patient's answer.
                body["patient_key"] = ctx["patient_key"]
                code, error, _ = self._selection(body)
                if error:
                    return self._send(code, {"error": error})
        x = ctx["cxr"]
        self._send(200, self._portal_response({"text": text, "context": ctx["text"], "model": model, "mode": mode,
                         "actions": ctx.get("actions", []), "as_of": ctx["now"],
                         "activities": ctx.get("activities", []),
                         "patient_key": ctx.get("patient_key"),
                         "cxr": {"url": f"/static/cxr/{x['file']}", "finding": x["finding"],
                                 "ko": consult.FINDING_KO.get(x["finding"], ""), "image_id": x["image_id"]}}))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=ticker, daemon=True).start()
    print(f"3교대 ICU · 환자 풀 {len(POOL)}명 ({', '.join(sorted({p['source'] for p in POOL}))}) · http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
