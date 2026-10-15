"""SQLite snapshots and append-only audit events, committed atomically."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, real_time TEXT NOT NULL,
                    minute REAL NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS archived_snapshot (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    real_time TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM snapshot WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else None

    def archive(self, state):
        with self.connect() as db:
            db.execute("INSERT INTO archived_snapshot(real_time,payload) VALUES(?,?)",
                (datetime.now(timezone.utc).isoformat(), json.dumps(state, ensure_ascii=False, allow_nan=False)))

    def save(self, state, action=None, actor="운영자", payload=None, audit_events=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO snapshot(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (json.dumps(state, ensure_ascii=False, allow_nan=False),))
            if action:
                db.execute("INSERT INTO audit(real_time,minute,action,actor,payload) VALUES(?,?,?,?,?)",
                           (datetime.now(timezone.utc).isoformat(), state["minute"], action, actor,
                            json.dumps(payload or {}, ensure_ascii=False, allow_nan=False)))
            for event in audit_events or []:
                db.execute("INSERT INTO audit(real_time,minute,action,actor,payload) VALUES(?,?,?,?,?)",
                           (datetime.now(timezone.utc).isoformat(), event["minute"], event["action"], event["actor"],
                            json.dumps(event["payload"], ensure_ascii=False, allow_nan=False)))

    def audit(self, limit=200):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
