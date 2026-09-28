"""SQLite persistence for memory records (survives restarts)."""
import json
import sqlite3
import threading


class SQLiteBackend:
    def __init__(self, path: str):
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._c.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            self._c.commit()

    def add(self, rec: dict) -> None:
        with self._lock:
            self._c.execute("INSERT OR REPLACE INTO records (id, body) VALUES (?, ?)", (rec["id"], json.dumps(rec)))
            self._c.commit()

    def all(self) -> list[dict]:
        with self._lock:
            return [json.loads(b) for (b,) in self._c.execute("SELECT body FROM records")]
