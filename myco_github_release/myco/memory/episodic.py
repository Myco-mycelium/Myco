"""
myco/memory/episodic.py
SQLite-backed episodic memory: every conversation, experience, and mind state snapshot.
"""
from __future__ import annotations
import json, sqlite3, threading, time, uuid
from dataclasses import asdict
from pathlib import Path


class EpisodicMemory:
    """
    Stores the raw timeline of Myco's life.
    Thread-safe: uses per-thread connections (reads) and a write lock (writes).
    """

    def __init__(self, db_path: str = "data/myco.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path  = db_path
        self._write_lock = threading.Lock()
        self._local    = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_schema(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id         TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                metadata   TEXT DEFAULT '{}',
                ts         REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_ts      ON messages(ts);

            CREATE TABLE IF NOT EXISTS mind_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                ts    REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id      TEXT PRIMARY KEY,
                label   TEXT,
                state   TEXT NOT NULL,
                ts      REAL NOT NULL,
                reason  TEXT
            );
        """)
        conn.commit()

    # ── messages ──────────────────────────────────────────────────────────────

    def add(self, role: str, content: str, session_id: str,
            metadata: dict | None = None) -> str:
        mid = str(uuid.uuid4())
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, metadata, ts) VALUES (?,?,?,?,?,?)",
                (mid, session_id, role, content, json.dumps(metadata or {}), time.time())
            )
            conn.commit()
        return mid

    def get_recent(self, n: int = 10, session_id: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if session_id:
            rows = conn.execute(
                "SELECT role, content, metadata, ts FROM messages WHERE session_id=? ORDER BY ts DESC LIMIT ?",
                (session_id, n)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT role, content, metadata, ts FROM messages ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        return [{"role": r[0], "content": r[1], "metadata": json.loads(r[2]), "ts": r[3]}
                for r in reversed(rows)]

    def get_sessions(self, limit: int = 20) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT session_id, MIN(ts) as start, MAX(ts) as end, COUNT(*) as turns
            FROM messages GROUP BY session_id ORDER BY start DESC LIMIT ?
        """, (limit,)).fetchall()
        return [{"session_id": r[0], "start": r[1], "end": r[2], "turns": r[3]} for r in rows]

    def count(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    # ── mind state ────────────────────────────────────────────────────────────

    def save_mind_state(self, mind_state) -> None:
        data = asdict(mind_state) if hasattr(mind_state, "__dataclass_fields__") else mind_state.__dict__
        with self._write_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO mind_state (key, value, ts) VALUES ('current', ?, ?)",
                (json.dumps(data), time.time())
            )
            conn.commit()

    def load_mind_state(self) -> dict | None:
        row = self._get_conn().execute(
            "SELECT value FROM mind_state WHERE key='current'"
        ).fetchone()
        return json.loads(row[0]) if row else None

    # ── snapshots (versioning / rollback) ────────────────────────────────────

    def snapshot(self, label: str = "", reason: str = "") -> str:
        """Take a full mind-state snapshot before risky self-changes."""
        sid   = str(uuid.uuid4())
        conn  = self._get_conn()
        state = conn.execute(
            "SELECT value FROM mind_state WHERE key='current'"
        ).fetchone()
        with self._write_lock:
            conn.execute(
                "INSERT INTO snapshots (id, label, state, ts, reason) VALUES (?,?,?,?,?)",
                (sid, label, state[0] if state else "{}", time.time(), reason)
            )
            conn.commit()
        return sid

    def rollback(self, snapshot_id: str) -> bool:
        conn = self._get_conn()
        row  = conn.execute(
            "SELECT state FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        if not row:
            return False
        with self._write_lock:
            conn.execute(
                "INSERT OR REPLACE INTO mind_state (key, value, ts) VALUES ('current', ?, ?)",
                (row[0], time.time())
            )
            conn.commit()
        return True

    def list_snapshots(self) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT id, label, ts, reason FROM snapshots ORDER BY ts DESC LIMIT 20"
        ).fetchall()
        return [{"id": r[0], "label": r[1], "ts": r[2], "reason": r[3]} for r in rows]
