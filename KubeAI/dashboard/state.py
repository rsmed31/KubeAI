"""RuntimeState is the etcd analogue: central in-memory store for all dashboard-visible cluster state."""
import random
import time
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRecord:
    """Represents a running agent instance — the Pod analogue in KubeAI."""

    id: str
    blueprint: str
    state: str          # PENDING | RUNNING | IDLE | SNAPSHOT | TERMINATED
    model_id: str
    tier: str           # fast | capable | best
    spawned_at: float
    last_active: float
    task_count: int
    mcp_servers: list[str]

    def __repr__(self) -> str:
        return f"AgentRecord(id={self.id!r}, state={self.state!r}, blueprint={self.blueprint!r})"


@dataclass
class TaskRecord:
    """Represents a submitted task — the Job analogue in KubeAI."""

    id: str
    description: str
    status: str         # QUEUED | ROUTING | ASSIGNED | RUNNING | COMPLETE | FAILED
    blueprint: str | None
    agent_id: str | None
    submitted_at: float
    completed_at: float | None
    result: str | None
    latency_ms: float | None

    def __repr__(self) -> str:
        return f"TaskRecord(id={self.id!r}, status={self.status!r})"


@dataclass
class MetricPoint:
    """A single time-series data point — the Prometheus sample analogue."""

    ts: float
    value: float

    def __repr__(self) -> str:
        return f"MetricPoint(ts={self.ts:.1f}, value={self.value:.4f})"


class RuntimeState:
    """Singleton in-memory state store with background fluctuation.

    Analogous to etcd in Kubernetes — the authoritative source of truth for
    all cluster state visible to the dashboard.
    """

    _instance: "RuntimeState | None" = None

    def __new__(cls) -> "RuntimeState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def __repr__(self) -> str:
        return f"RuntimeState(agents={len(self.agents)}, tasks={len(self.tasks)})"

    def _init(self) -> None:
        self._lock = threading.RLock()
        self.agents: dict[str, AgentRecord] = {}
        self.tasks: list[TaskRecord] = []
        self.metrics: dict[str, list[MetricPoint]] = {
            "throughput": [],
            "latency_ms": [],
            "cost_usd": [],
            "eval_score": [],
            "pool_utilization": [],
            "error_rate": [],
        }
        self._seed_demo_data()
        self._start_fluctuation_thread()

    def _seed_demo_data(self) -> None:
        import uuid

        blueprints = ["research_agent", "coding_agent", "data_agent", "writing_agent"]
        models = [
            ("claude-haiku-4", "fast"),
            ("claude-sonnet-4", "capable"),
            ("claude-opus-4", "best"),
        ]
        states = ["RUNNING", "RUNNING", "IDLE", "RUNNING", "IDLE", "PENDING"]
        now = time.time()

        for i, state in enumerate(states):
            aid = f"agent-{uuid.uuid4().hex[:8]}"
            model_id, tier = models[i % len(models)]
            self.agents[aid] = AgentRecord(
                id=aid,
                blueprint=blueprints[i % len(blueprints)],
                state=state,
                model_id=model_id,
                tier=tier,
                spawned_at=now - random.uniform(60, 3600),
                last_active=now - random.uniform(0, 120),
                task_count=random.randint(0, 50),
                mcp_servers=random.sample(["web", "code", "db", "files"], k=random.randint(0, 2)),
            )

        descs = [
            "Summarize Q3 earnings report",
            "Debug authentication middleware",
            "Analyze customer churn data",
            "Write product changelog",
            "Research competitor pricing",
            "Refactor payment service",
            "Generate test suite for API",
            "Draft support documentation",
        ]
        statuses = [
            "COMPLETE", "COMPLETE", "RUNNING", "COMPLETE",
            "QUEUED", "RUNNING", "COMPLETE", "ROUTING",
        ]
        agent_ids = list(self.agents.keys())

        for i, (desc, status) in enumerate(zip(descs, statuses)):
            tid = f"task-{uuid.uuid4().hex[:8]}"
            is_done = status in ("COMPLETE", "FAILED")
            latency = random.uniform(800, 8000) if is_done else None
            self.tasks.append(TaskRecord(
                id=tid,
                description=desc,
                status=status,
                blueprint=blueprints[i % len(blueprints)],
                agent_id=agent_ids[i % len(agent_ids)] if status not in ("QUEUED", "ROUTING") else None,
                submitted_at=now - random.uniform(10, 7200),
                completed_at=now - random.uniform(0, 300) if is_done else None,
                result="Task completed successfully." if is_done else None,
                latency_ms=latency,
            ))

        for i in range(30):
            ts = now - (30 - i)
            self.metrics["throughput"].append(MetricPoint(ts, random.uniform(2, 8)))
            self.metrics["latency_ms"].append(MetricPoint(ts, random.uniform(1200, 4000)))
            self.metrics["cost_usd"].append(MetricPoint(ts, random.uniform(0.001, 0.05)))
            self.metrics["eval_score"].append(MetricPoint(ts, random.uniform(0.75, 0.98)))
            self.metrics["pool_utilization"].append(MetricPoint(ts, random.uniform(0.3, 0.85)))
            self.metrics["error_rate"].append(MetricPoint(ts, random.uniform(0, 0.08)))

    def _start_fluctuation_thread(self) -> None:
        def _fluctuate() -> None:
            import uuid

            while True:
                time.sleep(2)
                with self._lock:
                    now = time.time()
                    for agent in self.agents.values():
                        if random.random() < 0.1:
                            if agent.state == "RUNNING":
                                agent.state = random.choice(["RUNNING", "IDLE"])
                            elif agent.state == "IDLE":
                                agent.state = random.choice(["IDLE", "RUNNING"])
                        if agent.state == "RUNNING":
                            agent.last_active = now - random.uniform(0, 30)

                    for key, default_range in [
                        ("throughput", (2, 8)),
                        ("latency_ms", (1200, 4000)),
                        ("cost_usd", (0.001, 0.05)),
                        ("eval_score", (0.75, 0.98)),
                        ("pool_utilization", (0.3, 0.85)),
                        ("error_rate", (0, 0.08)),
                    ]:
                        self.metrics[key].append(MetricPoint(now, random.uniform(*default_range)))
                        if len(self.metrics[key]) > 60:
                            self.metrics[key] = self.metrics[key][-60:]

        t = threading.Thread(target=_fluctuate, daemon=True)
        t.start()

    def snapshot(self) -> dict:
        """Return a complete snapshot of runtime state — analogous to a kubectl get all."""
        with self._lock:
            return {
                "agents": [vars(a) for a in self.agents.values()],
                "tasks": [vars(t) for t in self.tasks],
                "metrics": {
                    k: [{"ts": p.ts, "value": p.value} for p in v[-30:]]
                    for k, v in self.metrics.items()
                },
            }

    def add_task(self, description: str, blueprint: str | None = None) -> TaskRecord:
        """Submit a new task — analogous to kubectl apply for a Job."""
        import uuid

        with self._lock:
            tid = f"task-{uuid.uuid4().hex[:8]}"
            rec = TaskRecord(
                id=tid,
                description=description,
                status="QUEUED",
                blueprint=blueprint,
                agent_id=None,
                submitted_at=time.time(),
                completed_at=None,
                result=None,
                latency_ms=None,
            )
            self.tasks.append(rec)

            def _route() -> None:
                time.sleep(1)
                with self._lock:
                    rec.status = "ROUTING"
                time.sleep(1.5)
                with self._lock:
                    available = [a for a in self.agents.values() if a.state in ("RUNNING", "IDLE")]
                    if available:
                        chosen = random.choice(available)
                        rec.agent_id = chosen.id
                        rec.blueprint = rec.blueprint or chosen.blueprint
                        rec.status = "RUNNING"
                        chosen.state = "RUNNING"
                    else:
                        rec.status = "FAILED"
                time.sleep(random.uniform(2, 5))
                with self._lock:
                    if rec.status == "RUNNING":
                        rec.status = "COMPLETE"
                        rec.completed_at = time.time()
                        rec.result = (
                            f"Task '{description[:40]}...' completed successfully by agent {rec.agent_id}."
                        )
                        rec.latency_ms = (rec.completed_at - rec.submitted_at) * 1000

            threading.Thread(target=_route, daemon=True).start()
            return rec

    def terminate_agent(self, agent_id: str) -> bool:
        """Terminate an agent — analogous to kubectl delete pod."""
        with self._lock:
            if agent_id in self.agents:
                self.agents[agent_id].state = "TERMINATED"
                return True
            return False

    def get_memory_snapshot(self) -> dict:
        """Return a snapshot of the 3-tier memory system — analogous to PersistentVolume stats."""
        with self._lock:
            return {
                "working": {
                    "agent_contexts": len(self.agents),
                    "size_bytes": random.randint(4096, 65536),
                },
                "short_term": {
                    "keys": random.randint(20, 80),
                    "ttl_avg_s": random.randint(60, 600),
                    "size_bytes": random.randint(65536, 524288),
                },
                "long_term": {
                    "blueprints": 4,
                    "fact_entries": random.randint(100, 500),
                    "size_bytes": random.randint(524288, 4194304),
                },
            }

    def get_blueprints(self) -> list[dict]:
        """Return registered blueprints — analogous to kubectl get deployments."""
        return [
            {
                "name": "research_agent",
                "description": "Deep web research with source synthesis",
                "tier": "capable",
                "version": "1.0",
                "capabilities": ["web_search", "fetch_url"],
            },
            {
                "name": "coding_agent",
                "description": "Code generation, review, and debugging",
                "tier": "best",
                "version": "1.2",
                "capabilities": ["code_exec", "file_read"],
            },
            {
                "name": "data_agent",
                "description": "Statistical analysis and data pipeline work",
                "tier": "capable",
                "version": "1.0",
                "capabilities": ["code_exec", "db_query"],
            },
            {
                "name": "writing_agent",
                "description": "Long-form content and documentation writing",
                "tier": "fast",
                "version": "1.1",
                "capabilities": [],
            },
        ]
