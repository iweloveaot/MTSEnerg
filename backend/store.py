import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock


class SessionStore:
    """Persistent histories; session locks work within a single server process."""

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.locks = [Lock() for _ in range(64)]
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS applications (session_id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def lock(self, session_id):
        return self.locks[hash(session_id) % len(self.locks)]

    def load(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT state FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else {"messages": [], "application_requested": False}

    def save(self, session_id, state, application=None):
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (session_id, json.dumps(state, ensure_ascii=False)),
            )
            if application is not None:
                db.execute(
                    "INSERT INTO applications VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data",
                    (session_id, json.dumps(application, ensure_ascii=False)),
                )

    def get(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT state FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            application = db.execute("SELECT data FROM applications WHERE session_id = ?", (session_id,)).fetchone()
        state = json.loads(row[0])
        return {"session_id": session_id, "status": state.get("status", "active"),
                "messages": state.get("messages", []),
                "application": json.loads(application[0]) if application else None}

    def list_sessions(self):
        with self.connect() as db:
            rows = db.execute("SELECT id, state FROM sessions ORDER BY rowid DESC").fetchall()
        return [{"session_id": session_id, "status": json.loads(state).get("status", "active")}
                for session_id, state in rows]
