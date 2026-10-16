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

import consult
import engine
import handover
import team_chat
import demo_profiles
import bed_flow

ROOT = Path(__file__).parent


def first_pool():
    """POOL 환경변수 > 만들어둔 MIMIC 풀 > 공개 MIMIC-IV demo 자동 다운로드 > 가상 환자."""
    if os.environ.get("ICU_DEMO_SCENARIO") == "bleeding":
        # Sharing the fictional demo must never load a real patient pool.
        fictional = demo_profiles.create("calm")
        return [patient for rows in fictional.by_type.values() for patient in rows]
    if os.environ.get("POOL"):
        return engine.load_pool(os.environ["POOL"])
    if not (ROOT / "data" / "pool_mimic.json").exists():
        try:
            import mimic
            print("First launch: downloading public MIMIC-IV demo (approximately 8 MB)…")
            d = ROOT / "data" / "mimic-iv-demo"
            mimic.fetch(d)
            mimic.save(d)
        except Exception as e:
            print(f"MIMIC-IV demo 준비 실패 ({e}) → Synthetic Patient로 실행")
            return engine.load_pool("synth")
    return engine.load_pool("mimic")


POOL = first_pool()
try:
    print("Example chest X-rays ready: %d/%d" % consult.fetch_cxr())
except Exception as e:  # 인터넷이 없으면 영상 없이 판독문만으로 상담
    print(f"예시 Chest X-ray 준비 실패 ({e}) → 판독문만 사용")
lock = threading.Lock()
sim = {"h": engine.Hospital(POOL, "auto", 1), "running": True, "speed": 2.0, "seed": 1,
       "baseline": None}


def seed_demo():
    if os.environ.get("ICU_DEMO_SCENARIO") != "bleeding":
        return
    sim["profile"] = sim.get("profile", "bleeding")
    sim["h"] = demo_profiles.create(sim["profile"], sim["h"].policy, sim["seed"], multi_hospital=True, hospital_profiles=sim.get("hospital_profiles"))
    sim["hospital_profiles"] = dict(sim["h"].hospital_profiles)
    sim["bed_flow"] = bed_flow.build(sim["profile"])
    sim["running"] = False  # Keep the initial case available for discussion.


seed_demo()


def reset(policy=None, seed=None):
    policy = policy or sim["h"].policy
    seed = sim["seed"] if seed is None else seed
    sim["h"] = engine.Hospital(POOL, policy, seed)
    sim["seed"] = seed
    sim["baseline"] = None
    seed_demo()


def ticker():
    while True:
        time.sleep(1.0 / sim["speed"])
        with lock:
            if sim["running"] and sim["h"].t < 24 * 60:
                sim["h"].step()
                if sim["h"].t >= 24 * 60:
                    sim["running"] = False


def compare(seed, minutes, profile=None, hospital_profiles=None):
    """같은 시나리오(같은 seed)를 두 방식으로 끝까지 돌려 비교."""
    if profile:
        results = {}
        for policy in ("fixed", "auto"):
            h = demo_profiles.create(profile, policy, seed, multi_hospital=True, hospital_profiles=hospital_profiles)
            for _ in range(minutes):
                h.step()
            results[policy] = h.metrics()
        return results
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
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # The user closed/cancelled the conversation while generation was running.

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (ROOT / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/static/app-shell.css":
            return self._send(200, (ROOT / "static" / "app-shell.css").read_bytes(), "text/css; charset=utf-8")
        if path in ("/static/i18n.js", "/static/network.js", "/static/anatomy.js", "/static/transfers.js", "/static/readiness.js"):
            return self._send(200, (ROOT / "static" / Path(path).name).read_bytes(), "application/javascript; charset=utf-8")
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
                          cohort=os.environ.get("ICU_COHORT", "all"),
                          source=sorted({p["source"] for rows in sim["h"].by_type.values() for p in rows}),
                          demo_profile=sim.get("profile"), profiles=demo_profiles.PROFILES,
                          hospital_profiles=sim.get("hospital_profiles", {}),
                          bed_flow=sim.get("bed_flow"),
                          handover_receipts=copy.deepcopy(getattr(sim["h"], "handover_receipts", [])))
            return self._send(200, st)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if not isinstance(body, dict):
            return self._send(400, {"A JSON object is required.": "A JSON object is required."})
        path = self.path.split("?")[0]
        if path == "/api/patient":
            return self._patient(body)
        if path == "/api/diagnostics":
            return self._diagnostics(body)
        if path == "/api/image-review":
            with consult.response_language(body.get("language", "en")):
                return self._image_review(body)
        if path == "/api/handover":
            return self._handover_receipt(body)
        if path == "/api/call-standby":
            with lock:
                code, error, _ = self._selection(body)
                if error:
                    return self._send(code, {"error": error})
                h = sim["h"]
                event = next((i for i in h.incidents if i["bed"] == body["bed"] and i["end"] is None), None)
                if not event:
                    return self._send(409, {"error": "Select a patient with an active simulated event."})
                candidates = [nid for nid in h._eligible(event) if h._free(nid)]
                candidates.sort(key=lambda nid: (any(h.beds[bid]["patient"] for bid in h.nurses[nid]["beds"] + h.nurses[nid]["cover"]),
                                                  h.nurses[nid]["role"] == "charge",
                                                  h.nurses[nid]["fatigue"]))
                preferred = candidates[0] if candidates else None
                if len(event["responders"]) < event["need"]:
                    h._dispatch(event, preferred=preferred)
                else:
                    event["need"] += 1
                    h._dispatch(event, preferred=preferred)
                return self._send(200, {"ok": True, "incident": h._incident_json(event),
                                      "message": "Standby assistance requested within this ICU. Press Play to advance movement and arrival."})
        if self.path.split("?")[0] == "/api/consult":
            if body.get("language", "en") not in ("ko", "en"):
                return self._send(400, {"error": "Unsupported language. Use ko or en."})
            with consult.response_language(body.get("language", "en")):
                return self._consult(body)
        if self.path.split("?")[0] == "/api/care-log":
            return self._care_log(body)
        if self.path.split("?")[0] == "/api/emergency":
            return self._emergency(body)
        a = body.get("action")
        with lock:
            if a == "profile":
                if os.environ.get("ICU_DEMO_SCENARIO") != "bleeding" or body.get("value") not in demo_profiles.PROFILES:
                    return self._send(400, {"error": "Select a supported shift scenario."})
                hospital_id = body.get("hospital_id", "A")
                if hospital_id not in sim.get("hospital_profiles", {"A": sim.get("profile")}):
                    return self._send(400, {"error": "Select a supported hospital."})
                sim.setdefault("hospital_profiles", {"A": sim.get("profile", "bleeding")})[hospital_id] = body["value"]
                sim["profile"] = sim["hospital_profiles"]["A"]
                reset(seed=sim["seed"] + 1)
            elif a == "pause":
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
                profile = sim.get("profile")
                hospital_profiles = copy.deepcopy(sim.get("hospital_profiles"))
            else:
                return self._send(400, {"error": "unknown action"})
        if a == "compare":  # 잠금 밖에서 계산
            return self._send(200, compare(seed, minutes, profile, hospital_profiles) if profile else compare(seed, minutes))
        self._send(200, {"ok": True})

    def _selection(self, body):
        """잠금 안에서 환자·근무조가 입력 시작 시점과 같은지 확인한다."""
        h = sim["h"]
        bed_id = body.get("bed", "")
        bed = h.beds.get(bed_id)
        pt = bed and bed["patient"]
        if pt is None:
            return 404, "This bed is empty. Select another patient.", None
        key = body.get("patient_key")
        if key is not None and (not isinstance(key, dict) or
                                key.get("pid") != pt["src"]["pid"] or
                                key.get("admit_t") != pt["admit_t"]):
            return 409, "The selected patient changed. Reopen the consultation.", None
        nurse_id = body.get("nurse_id") or bed["nurse"]
        nurse = h.nurses.get(nurse_id)
        if nurse is None:
            return 400, "Select a currently on-duty nurse.", None
        staff_id = body.get("staff_id")
        if staff_id is not None and staff_id != nurse["staff_id"]:
            return 409, "The shift changed. Reopen the consultation as the current nurse.", None
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
        self._send(200, {"ok": True, "action": action, "actions": actions})

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
                return self._send(403, {"Access is limited to assigned, covered or responding patients, or your ICU as charge nurse.": "Access is limited to assigned, covered or responding patients, or your ICU as charge nurse."})
            h = sim["h"]
            history = h.patient_vital_history(body["bed"])
            tasks = self._diagnostic_images(h, body["bed"])
        self._send(200, {"history": history, "diagnostics": tasks,
                         "patient_key": history["patient_key"]})

    def _diagnostics(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(403, {"Only an assigned, covering or responding nurse, or the ICU charge nurse, may request this workflow.": "Only an assigned, covering or responding nurse, or the ICU charge nurse, may request this workflow."})
            h = sim["h"]
            if any(task["kind"] == body.get("kind") and task["status"] not in
                   ("specimen_sent", "image_available", "cancelled")
                   for task in h.patient_diagnostics(body["bed"])):
                return self._send(409, {"The same diagnostic workflow is already active.": "The same diagnostic workflow is already active."})
            try:
                task = h.request_diagnostic(nurse_id, body["bed"], body.get("kind"))
            except PermissionError as error:
                return self._send(403, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                return self._send(400, {"error": str(error)})
            tasks = self._diagnostic_images(h, body["bed"])
        self._send(200, {"ok": True, "task": task, "diagnostics": tasks})

    def _image_review(self, body):
        with lock:
            code, error, nurse_id = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(403, {"Request image review only within the ICU responsible for this patient.": "Request image review only within the ICU responsible for this patient."})
            h = sim["h"]
            try:
                task = h.diagnostic_task(body["bed"], body.get("task_id"))
            except (ValueError, TypeError, KeyError):
                return self._send(404, {"No diagnostic request found for this patient.": "No diagnostic request found for this patient."})
            if task["kind"] != "portable_xray" or task["status"] != "image_available":
                return self._send(409, {"Complete the portable imaging simulation before requesting image review.": "Complete the portable imaging simulation before requesting image review."})
            ctx = consult.context(h, body["bed"], nurse_id=nurse_id)
            requested_staff_id = h.nurses[nurse_id]["staff_id"]
            requested_cycle = h._shift_at(h.t)["cycle"]
        answer = consult.image_review_turn(ctx, task)
        with lock:
            if sim["h"] is not h:
                return self._send(409, {"The scenario changed. The image review was not saved.": "The scenario changed. The image review was not saved."})
            if (h.nurses[nurse_id]["staff_id"] != requested_staff_id
                    or h._shift_at(h.t)["cycle"] != requested_cycle):
                return self._send(409, {"The shift changed during image review. Request again as the incoming nurse.": "The shift changed during image review. Request again as the incoming nurse."})
            code, error, _ = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            if not self._care_scope(nurse_id, body["bed"]):
                return self._send(409, {"Patient assignment changed during review. Reselect the current nurse.": "Patient assignment changed during review. Reselect the current nurse."})
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
        self._send(200, {"ok": True, "receipt": receipt, "last_handover": snapshot})

    def _emergency(self, body):
        """선택한 가상 환자에게 시연 사건을 주입한다. 수행 기록은 만들지 않는다."""
        with lock:
            code, error, _ = self._selection(body)
            if error:
                return self._send(code, {"error": error})
            h = sim["h"]
            if any(i["bed"] == body["bed"] and i["end"] is None for i in h.incidents):
                return self._send(409, {"This patient already has an active event.": "This patient already has an active event."})
            if body.get("scenario") not in engine.EMERGENCY_SCENARIOS:
                return self._send(400, {"Unsupported emergency simulation.": "Unsupported emergency simulation."})
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
            requested_hospital = sim["h"]
            ctx = consult.context(requested_hospital, body.get("bed", ""), nurse_id=nurse_id)
        if ctx is None:
            return self._send(404, {"error": "Empty bed"})
        history = body.get("history") or []
        if not isinstance(history, list) or any(not isinstance(m, dict) or not isinstance(m.get("text"), str) for m in history):
            return self._send(400, {"error": "Discussion history must contain text messages."})
        if body.get("task") == "team":
            if body.get("who") not in ("nurse", "doctor", "agent", "patient"):
                return self._send(400, {"error": "Select a supported discussion role."})
            answer = team_chat.turn(ctx, history, body["who"])
            if answer["mode"] == "unavailable":
                return self._send(503, {"error": answer["text"]})
            with lock:
                code, error, _ = self._selection(body)
                if sim["h"] is not requested_hospital or error:
                    return self._send(409, {"error": "Patient or scenario changed during generation. Start a new conversation."})
                current_override = requested_hospital.beds[body["bed"]]["patient"].get("simulation_override") or {}
                previous_override = ctx["handover"]["patient"].get("simulation_override") or {}
                if current_override.get("incident_id") != previous_override.get("incident_id"):
                    return self._send(409, {"error": "The simulated event changed during generation. Start a new conversation."})
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        elif body.get("task") == "cxr_chat":
            answer = consult.cxr_chat_turn(ctx, history)
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        elif body.get("who") != "nurse" and consult.is_handover_request(history, body.get("task")):
            answer = consult.handover_turn(ctx)
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        elif body.get("who") == "nurse":
            answer = consult.nurse_turn_result(ctx, history)
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        else:
            answer = consult.agent_turn_result(ctx, history, task=body.get("task"))
            text, mode, model = answer["text"], answer["mode"], answer["model"]
        x = ctx["cxr"]
        self._send(200, {"text": text, "context": answer.get("input_context", ctx["text"]), "model": model, "mode": mode,
                         "image_source": answer.get("source"),
                         "actions": ctx.get("actions", []), "as_of": ctx["now"],
                         "activities": ctx.get("activities", []),
                         "patient_key": ctx.get("patient_key"),
                         "cxr": {"url": f"/static/cxr/{x['file']}", "finding": x["finding"],
                                 "ko": consult.FINDING_KO.get(x["finding"], ""), "image_id": x["image_id"]}})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), H)
    threading.Thread(target=ticker, daemon=True).start()
    print(f"3Shift change ICU · Patient 풀 {len(POOL)} staff ({', '.join(sorted({p['source'] for p in POOL}))}) · http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
