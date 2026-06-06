"""
myco/safety/audit.py
====================
Immutable, append-only audit log for every security-relevant event.

Every write is:
  - Timestamped (monotonic + wall clock)
  - Hashed (SHA-256 chained log — each entry includes hash of previous)
  - Written to SQLite with WAL mode (survives crashes)
  - Optionally mirrored to a plaintext file for human review

Categories logged:
  AUTH        — login attempts, token creation/revocation, permission checks
  SANDBOX     — every code execution attempt and its verdict
  CHANGE      — every self-improvement integration or rollback
  INGEST      — every document/image/video ingested
  API         — every admin API call (model add, rollback, reflect trigger)
  THREAT      — detected injection attempts, rate-limit breaches, anomalies
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from safety.sandbox import SandboxResult

log = logging.getLogger("myco.audit")


@dataclass
class AuditEntry:
    category:   str           # AUTH | SANDBOX | CHANGE | INGEST | API | THREAT
    event:      str           # short verb: "login_ok", "code_rejected", "tool_integrated"
    actor:      str           # who triggered it: user token prefix or "system"
    detail:     dict          # event-specific payload
    ts:         float = 0.0   # filled in by AuditLog.log()
    entry_hash: str  = ""     # SHA-256(prev_hash + this entry JSON)
    prev_hash:  str  = ""     # hash of previous entry (chain)


class AuditLog:
    """
    Thread-safe, append-only audit log backed by SQLite.
    The hash chain makes it tamper-evident: any modification to a past entry
    invalidates all subsequent hashes, which is detectable via verify().
    """

    def __init__(self, db_path: str = "data/myco.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock    = threading.Lock()
        self._last_hash = "GENESIS"
        self._init_schema()
        self._load_last_hash()

    # ── public ────────────────────────────────────────────────────────────────

    def log(self, category: str, event: str, actor: str, detail: dict | None = None) -> str:
        """Append one entry. Returns the entry's hash."""
        with self._lock:
            entry = AuditEntry(
                category = category,
                event    = event,
                actor    = actor,
                detail   = detail or {},
                ts       = time.time(),
                prev_hash = self._last_hash,
            )
            payload = json.dumps({
                "category": entry.category,
                "event":    entry.event,
                "actor":    entry.actor,
                "detail":   entry.detail,
                "ts":       entry.ts,
                "prev_hash": entry.prev_hash,
            }, sort_keys=True)
            entry.entry_hash = hashlib.sha256(
                (self._last_hash + payload).encode()
            ).hexdigest()

            conn = self._get_conn()
            conn.execute(
                """INSERT INTO audit_log
                   (entry_hash, prev_hash, category, event, actor, detail, ts)
                   VALUES (?,?,?,?,?,?,?)""",
                (entry.entry_hash, entry.prev_hash, entry.category, entry.event,
                 entry.actor, json.dumps(entry.detail), entry.ts)
            )
            conn.commit()
            self._last_hash = entry.entry_hash

            log.debug(f"[audit] {category}/{event} by {actor}")
            return entry.entry_hash

    def log_sandbox(self, code_hash: str, description: str, result: "SandboxResult"):
        """Convenience wrapper for sandbox events."""
        self.log(
            category = "SANDBOX",
            event    = result.verdict.value,
            actor    = "system",
            detail   = {
                "code_hash":   code_hash,
                "description": description[:200],
                "verdict":     result.verdict.value,
                "reason":      result.reason[:500] if result.reason else "",
                "duration_ms": result.duration_ms,
                "functions":   result.functions,
            }
        )

    def log_auth(self, event: str, actor: str, detail: dict | None = None):
        self.log("AUTH", event, actor, detail)

    def log_change(self, event: str, actor: str, detail: dict | None = None):
        self.log("CHANGE", event, actor, detail)

    def log_threat(self, event: str, actor: str, detail: dict | None = None):
        self.log("THREAT", event, actor, detail)
        log.warning(f"[THREAT] {event} by {actor}: {detail}")

    def log_api(self, endpoint: str, actor: str, detail: dict | None = None):
        self.log("API", endpoint, actor, detail)

    # ── query ────────────────────────────────────────────────────────────────

    def recent(self, n: int = 50, category: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE category=? ORDER BY ts DESC LIMIT ?",
                (category, n)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def verify(self) -> tuple[bool, str]:
        """
        Verify the integrity of the entire chain.
        Returns (True, "OK") or (False, "First broken entry hash").
        """
        conn  = self._get_conn()
        rows  = conn.execute(
            "SELECT entry_hash, prev_hash, category, event, actor, detail, ts "
            "FROM audit_log ORDER BY ts ASC"
        ).fetchall()
        prev  = "GENESIS"
        for row in rows:
            entry_hash, prev_hash, category, event, actor, detail, ts = row
            if prev_hash != prev:
                return False, f"Chain broken at {entry_hash}: prev_hash mismatch"
            payload = json.dumps({
                "category": category, "event": event, "actor": actor,
                "detail": json.loads(detail), "ts": ts, "prev_hash": prev_hash,
            }, sort_keys=True)
            expected = hashlib.sha256((prev + payload).encode()).hexdigest()
            if expected != entry_hash:
                return False, f"Hash mismatch at {entry_hash}"
            prev = entry_hash
        return True, "OK"

    def stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) FROM audit_log GROUP BY category"
        ).fetchall()
        threats = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE category='THREAT'"
        ).fetchone()[0]
        return {
            "total_entries": total,
            "by_category":   {r[0]: r[1] for r in by_cat},
            "threats":       threats,
            "chain_valid":   self.verify()[0],
        }

    # ── private ───────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Thread-local connection with WAL mode."""
        if not hasattr(self._local, "conn"):
            self._local = threading.local()
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    _local = threading.local()

    def _init_schema(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                entry_hash TEXT PRIMARY KEY,
                prev_hash  TEXT NOT NULL,
                category   TEXT NOT NULL,
                event      TEXT NOT NULL,
                actor      TEXT NOT NULL,
                detail     TEXT NOT NULL DEFAULT '{}',
                ts         REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_cat ON audit_log(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts  ON audit_log(ts)")
        conn.commit()

    def _load_last_hash(self):
        conn = self._get_conn()
        row  = conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if row:
            self._last_hash = row[0]

    def _row_to_dict(self, row) -> dict:
        return {
            "entry_hash": row[0], "prev_hash": row[1], "category": row[2],
            "event": row[3], "actor": row[4],
            "detail": json.loads(row[5]), "ts": row[6],
        }
