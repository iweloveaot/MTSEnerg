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

    def save(self, session_id, state):
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (session_id, json.dumps(state, ensure_ascii=False)),
            )
