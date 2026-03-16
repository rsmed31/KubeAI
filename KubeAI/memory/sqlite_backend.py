"""SQLiteBackend is the PersistentVolume analogue: file-backed storage for long-term agent memory that survives restarts."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .base import SharedMemoryBackend

_DDL = """
CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    expires_at REAL
);
"""


class SQLiteBackend(SharedMemoryBackend):
    """SQLite-backed KV store for long-term tier persistence.

    Analogous to a Kubernetes PersistentVolume — data survives process
    restarts as long as the db file is retained. Pass ``db_path=':memory:'``
    (the default) for an ephemeral in-process SQLite instance (useful in tests).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_DDL)
        self._conn.commit()

    # ── Core ops ─────────────────────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        """Return the stored value, or None if absent or expired."""
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires_at FROM kv WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            raw, expires_at = row
            if expires_at is not None and now >= expires_at:
                self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
                self._conn.commit()
                return None
            return json.loads(raw)

    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        """Upsert *value* for *key* with an optional TTL in seconds."""
        expires_at = (time.time() + ttl_s) if ttl_s is not None else None
        serialised = json.dumps(value)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv (key, value, expires_at) VALUES (?, ?, ?)",
                (key, serialised, expires_at),
            )
            self._conn.commit()

    def delete(self, key: str) -> bool:
        """Remove *key*. Returns True if it existed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._conn.commit()
            return cursor.rowcount > 0

    def keys(self, prefix: str = "") -> list[str]:
        """Return all live keys matching *prefix*, pruning expired entries."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
            )
            self._conn.commit()
            rows = self._conn.execute(
                "SELECT key FROM kv WHERE key LIKE ?", (f"{prefix}%",)
            ).fetchall()
            return [r[0] for r in rows]

    def clear(self) -> None:
        """Delete all rows."""
        with self._lock:
            self._conn.execute("DELETE FROM kv")
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __repr__(self) -> str:
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
        return f"SQLiteBackend(db_path={self._db_path!r}, entries={count})"
