"""Offline-compatible HTTP API using only the Python standard library."""
import base64
import csv
import hmac
import io
import json
import logging
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .engine import Engine, AppError
from .importer import export_canonical
from .evaluation import compare
from .version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("pericare")


def csv_safe(v):
    if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + v
    return v


def csv_bytes(rows, fields):
    f = io.StringIO(newline="")
    writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: csv_safe(row.get(k, "")) for k in fields})
    return b"\xef\xbb\xbf" + f.getvalue().encode("utf-8")


def make_handler(engine):
    username, password = os.environ.get("APP_USERNAME", ""), os.environ.get("APP_PASSWORD", "")
    if bool(username) != bool(password):
        raise ValueError("APP_USERNAME과 APP_PASSWORD를 함께 설정하세요")

    class Handler(BaseHTTPRequestHandler):
        server_version = "PeriCare/" + APP_VERSION
        def log_message(self, fmt, *args):
            LOGGER.info("%s %s", self.address_string(), fmt % args)

        def send(self, status, payload, content_type="application/json; charset=utf-8", filename=None):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="PeriCare"')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if not username:
                return True
            expected = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
            if hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                return True
            self.send(401, {"error": "로그인이 필요합니다"})
            return False

        def do_GET(self):
            try:
                path = urlparse(self.path).path
                if path == "/health":
                    return self.send(200, {"status": "ok", "app": "PeriCare", "version": APP_VERSION})
                if not self.authorized():
                    return
                if path == "/api/state":
                    return self.send(200, engine.view())
                if path == "/api/export/data":
                    with engine.lock:
                        data = export_canonical(engine.state)
                    return self.send(200, json.dumps(data, ensure_ascii=False, indent=2).encode(), filename="pericare-data.json")
                if path == "/api/export/audit":
                    return self.send(200, engine.store.audit(10000), filename="pericare-audit.json")
                if path == "/api/export/reservations":
                    v = engine.view()
                    return self.send(200, csv_bytes(v["reservations"], ["id", "patient_id", "bed_id", "start", "end", "status", "reason", "actor"]), "text/csv; charset=utf-8", "pericare-reservations.csv")
                if path == "/api/export/predictions":
                    v = engine.view()
                    rows = [{"patient_id": p["id"], "surgery": p["surgery"], "phase": p["phase"], "as_of": v["clock"], **p["prediction"]} for p in v["patients"]]
                    fields = ["patient_id", "surgery", "phase", "as_of", "need_score", "need_probability", "icu_probability", "intensive_hours", "icu_los_hours", "hospital_los_days", "confidence", "mode", "model_version"]
                    return self.send(200, csv_bytes(rows, fields), "text/csv; charset=utf-8", "pericare-predictions.csv")
                if path == "/api/example/replay":
                    return self.send(200, (ROOT / "examples" / "recorded-replay.json").read_bytes(), filename="pericare-recorded-replay.json")
                if path == "/api/example":
                    return self.send(200, (ROOT / "examples" / "canonical-data.json").read_bytes(), filename="pericare-example.json")
                if path.startswith("/docs/"):
                    file = ROOT / "docs" / Path(path).name
                    if file.suffix == ".md" and file.is_file():
                        return self.send(200, file.read_bytes(), "text/plain; charset=utf-8")
                if path == "/":
                    path = "/index.html"
                static = (ROOT / "static" / path.lstrip("/")).resolve()
                if static.is_relative_to(ROOT / "static") and static.is_file():
                    mime = mimetypes.guess_type(static.name)[0] or "application/octet-stream"
                    return self.send(200, static.read_bytes(), mime + ("; charset=utf-8" if mime.startswith("text/") or mime.endswith("javascript") else ""))
                self.send(404, {"error": "경로를 찾을 수 없습니다"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOGGER.exception("GET failure")
                self.send(500, {"error": "서버 오류. 서버 로그를 확인하세요"})

        def do_POST(self):
            if not self.authorized():
                return
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self.send(403, {"error": "동일 출처 요청만 허용합니다"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n <= 0 or n > 20 * 1024 * 1024:
                    raise AppError("요청 크기는 1바이트~20MB입니다", 413)
                if self.headers.get_content_type() != "application/json":
                    raise AppError("Content-Type: application/json이 필요합니다", 415)
                body = json.loads(self.rfile.read(n), parse_constant=lambda x: (_ for _ in ()).throw(ValueError("비유한 숫자")))
                if not isinstance(body, dict):
                    raise AppError("JSON 객체가 필요합니다")
                path = urlparse(self.path).path
                if path == "/api/compare":
                    with engine.lock:
                        policy, seed = engine.state["policy"].copy(), engine.state["seed"]
                        if engine.state["source"] != "synthetic":
                            raise AppError("정책 비교는 합성 시연 데이터에서만 지원합니다")
                    return self.send(200, compare(seed, policy, body.get("horizon_minutes", 360)))
                if not path.startswith("/api/actions/"):
                    raise AppError("지원하지 않는 API입니다", 404)
                return self.send(200, engine.mutate(path.rsplit("/", 1)[-1], body))
            except AppError as exc:
                self.send(exc.status, {"error": exc.message})
            except (ValueError, UnicodeDecodeError, TypeError, KeyError) as exc:
                self.send(400, {"error": "입력 형식을 확인하세요: " + str(exc)[:120]})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOGGER.exception("POST failure")
                self.send(500, {"error": "서버 오류. 서버 로그를 확인하세요"})
    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "data"))
    engine = Engine(data_dir / "pericare.db")
    server = ThreadingHTTPServer((os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", "8000"))), make_handler(engine))
    server.daemon_threads = True
    stop = threading.Event()
    def ticker():
        while not stop.wait(2):
            try:
                engine.tick()
            except Exception:
                LOGGER.exception("Ticker paused after failure")
                with engine.lock:
                    engine.state["running"] = False
                    engine.store.save(engine.state)
    threading.Thread(target=ticker, daemon=True).start()
    LOGGER.info("PeriCare · http://localhost:%s · model=%s", server.server_port, engine.state["model_backend"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
