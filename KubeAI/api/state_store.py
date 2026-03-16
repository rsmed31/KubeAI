"""StateStore provides SQLite-backed persistence for ControlPlaneAPI agent and task records across restarts."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from KubeAI.api.control_plane import AgentRecord, ControlPlaneAPI, TaskRecord

_DEFAULT_DB_PATH = Path.home() / ".kubeai" / "state.db"

_TERMINAL_TASK_STATUSES = frozenset({"complete", "success", "failed", "error", "cancelled"})
_RECOVERABLE_AGENT_STATES = frozenset({"terminated", "idle"})


class StateStore:
    """
    SQLite-backed persistence for ControlPlaneAPI.

    Analogous to etcd snapshots in Kubernetes: periodically checkpoints
    agent and task state to disk and restores it on startup.

    Only terminal/idle records are persisted — running agents restart as idle
    on recovery since their execution thread no longer exists.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self._lock = threading.RLock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._checkpoint_thread: threading.Thread | None = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS agents (
                        agent_id    TEXT PRIMARY KEY,
                        name        TEXT NOT NULL,
                        description TEXT NOT NULL,
                        state       TEXT NOT NULL,
                        healthy     INTEGER NOT NULL,
                        load        REAL NOT NULL,
                        capabilities TEXT NOT NULL,
                        metadata     TEXT NOT NULL,
                        saved_at     REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id    TEXT PRIMARY KEY,
                        blueprint  TEXT NOT NULL,
                        status     TEXT NOT NULL,
                        latency_ms REAL NOT NULL,
                        token_cost REAL NOT NULL,
                        eval_score REAL,
                        agent_id   TEXT,
                        timestamp  REAL NOT NULL,
                        saved_at   REAL NOT NULL
                    );
                """)
                conn.commit()
            finally:
                conn.close()

    # ── Persistence ──────────────────────────────────────────────────────────

    def checkpoint(self, control_plane: "ControlPlaneAPI") -> None:
        """Persist all current agent and task records to SQLite."""
        with control_plane._lock:  # noqa: SLF001
            agents = list(control_plane._agents.values())  # noqa: SLF001
            tasks = list(control_plane._tasks.values())  # noqa: SLF001

        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM agents")
                conn.execute("DELETE FROM tasks")

                for agent in agents:
                    # Only persist terminal/idle agents; running agents become idle on recovery
                    persisted_state = agent.state if agent.state in _RECOVERABLE_AGENT_STATES else "idle"
                    conn.execute(
                        "INSERT OR REPLACE INTO agents VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            agent.agent_id,
                            agent.name,
                            agent.description,
                            persisted_state,
                            int(agent.healthy),
                            float(agent.load),
                            json.dumps(list(agent.capabilities)),
                            json.dumps(agent.metadata),
                            now,
                        ),
                    )

                for task in tasks:
                    conn.execute(
                        "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            task.task_id,
                            task.blueprint,
                            task.status,
                            float(task.latency_ms),
                            float(task.token_cost),
                            task.eval_score,
                            task.agent_id,
                            float(task.timestamp),
                            now,
                        ),
                    )

                conn.commit()
            finally:
                conn.close()

    def load(self, control_plane: "ControlPlaneAPI") -> None:
        """Restore persisted agent and task records into ControlPlaneAPI on startup."""
        from KubeAI.api.control_plane import AgentRecord, TaskRecord

        with self._lock:
            conn = self._connect()
            try:
                agent_rows = conn.execute("SELECT * FROM agents").fetchall()
                task_rows = conn.execute("SELECT * FROM tasks").fetchall()
            finally:
                conn.close()

        with control_plane._lock:  # noqa: SLF001
            for row in agent_rows:
                record = AgentRecord(
                    agent_id=row["agent_id"],
                    name=row["name"],
                    description=row["description"],
                    state=row["state"],
                    healthy=bool(row["healthy"]),
                    load=float(row["load"]),
                    capabilities=tuple(json.loads(row["capabilities"])),
                    metadata=json.loads(row["metadata"]),
                )
                control_plane._agents[record.agent_id] = record  # noqa: SLF001

            for row in task_rows:
                record_t = TaskRecord(
                    task_id=row["task_id"],
                    blueprint=row["blueprint"],
                    status=row["status"],
                    latency_ms=float(row["latency_ms"]),
                    token_cost=float(row["token_cost"]),
                    eval_score=row["eval_score"],
                    agent_id=row["agent_id"],
                    timestamp=float(row["timestamp"]),
                )
                control_plane._tasks[record_t.task_id] = record_t  # noqa: SLF001

    # ── Background checkpointing ─────────────────────────────────────────────

    def start_periodic_checkpoint(
        self, control_plane: "ControlPlaneAPI", interval_s: float = 30.0
    ) -> None:
        """Start a daemon thread that checkpoints state every *interval_s* seconds."""

        def _loop() -> None:
            while True:
                time.sleep(interval_s)
                try:
                    self.checkpoint(control_plane)
                except Exception:
                    pass  # never crash the checkpoint thread

        t = threading.Thread(target=_loop, daemon=True, name="kubeai-state-checkpoint")
        t.start()
        self._checkpoint_thread = t

    def __repr__(self) -> str:
        return f"StateStore(db_path={str(self._db_path)!r})"
