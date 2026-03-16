# KubeAI — Full Project Context for AI Coding Assistants

You are helping build **KubeAI** — a Kubernetes-inspired runtime for AI agents.
Read this entire file before writing any code.

---

## What KubeAI is

KubeAI is NOT a framework for building agents (LangChain, AutoGen, CrewAI do that).
KubeAI IS the runtime infrastructure that manages agents at scale — the layer that
sits above your agent code and handles everything Kubernetes handles for containers.

The thesis: deploying AI agents today is like deploying servers before Kubernetes.
KubeAI is the Kubernetes moment for AI agents.

---

## Full Kubernetes → KubeAI mapping

| Kubernetes              | KubeAI                                      |
|-------------------------|---------------------------------------------|
| Pod                     | Agent instance                              |
| Deployment              | KubeAIeployment (desired state spec)        |
| ReplicaSet              | Agent pool (N running instances)            |
| StatefulSet             | StatefulAgent (persistent identity)         |
| DaemonSet               | GlobalAgent (one per domain, always on)     |
| Job / CronJob           | AgentJob / AgentCronJob                     |
| Scheduler               | AgentScheduler                              |
| kubelet                 | Agentlet (node-level agent manager)         |
| etcd                    | Shared Data Plane (3-tier memory)           |
| Ingress + Istio         | Orchestrator (semantic router)              |
| Service                 | AgentService (stable endpoint to a pool)    |
| ConfigMap               | AgentConfig (runtime config injection)      |
| Secret                  | AgentSecret (API keys, credentials)         |
| Namespace               | KubeAIomain (isolation boundary)            |
| RBAC                    | AgentRBAC (who can run what agents)         |
| NetworkPolicy           | AgentPolicy (what agents can talk to what)  |
| PersistentVolume        | MemoryVolume (pluggable memory backends)    |
| HorizontalPodAutoscaler | AgentAutoscaler (scale on queue depth/cost) |
| PodDisruptionBudget     | KubeAIisruptionBudget                       |
| Resource Limits/Requests| Token budgets, cost limits per agent        |
| Health Probes           | Eval Loop (quality-based, not TCP)          |
| Container Image         | Agent Blueprint                             |
| Helm Chart              | KubeAI Template (RAG, memory, tools)        |
| kubectl                 | agentctl CLI                                |
| Kubernetes Dashboard    | KubeAI UI (web dashboard)                   |
| Prometheus + Grafana    | KubeAI Monitoring (cost, quality, latency)  |
| CRD                     | Custom agent types via YAML                 |
| Operator pattern        | AgentOperator (self-managing agent systems) |
| Service Mesh (Istio)    | A2A Protocol layer (agent-to-agent comms)   |
| Sidecar                 | AgentSidecar (logging, tracing, guardrails) |

---

## Technology stack — use these, do not reinvent them

### LLM layer
- **LiteLLM** — unified interface for Anthropic, OpenAI, Gemini, Ollama, Azure
  Use everywhere LLM calls are made. Never call provider SDKs directly.
  `from litellm import completion`
- **LLMPool** — orchestrator-owned model registry and allocator
   Supports tier mapping (`fast`, `capable`, `best`), health checks, and failover.

### Agent execution
- **LangChain Core** — tool calling, structured output, chains
  Use langchain_core.tools, langchain_core.messages
- **LangGraph** — for stateful multi-step agent workflows (StatefulAgent type)

### Agent-to-Agent communication
- **Google A2A Protocol** — standardized agent-to-agent messaging
  Use for all inter-agent communication in multi-agent workflows
  Implement AgentCard (capability advertisement) and Task objects
- **Anthropic MCP** — tool/context protocol for agent↔tool connections
  All tools exposed as MCP servers, agents connect via MCP clients
- **MCPPool** — orchestrator-owned MCP server registry
   Capability-tag matching decides which MCP servers are attached at spawn.

### RAG / Retrieval
- **LlamaIndex** — retrieval pipelines, document indexing
  BasicRAG: VectorStoreIndex
  HybridRAG: BM25 + vector via QueryFusionRetriever
  RerankingRAG: + CohereRerank or SentenceTransformerRerank
- **ChromaDB** — local persistent vector store (default)
- **Qdrant** — production vector store (optional backend)
- **fastembed** — local embeddings, no API key needed
- **rank_bm25** — BM25 keyword search

### Memory
- **Mem0** — agent memory management (handles sliding window, summarizing, episodic)
  Use as the memory backend behind KubeAI's SharedMemory abstraction
- **Redis** — short-term memory backend (production)
- **SQLite via SQLModel** — long-term memory backend (default/local)

### Monitoring & Observability
- **LangSmith** (optional) — LLM tracing
- **OpenTelemetry** — spans and traces for all agent operations
- **Prometheus client** — metrics export (token usage, latency, cost, quality scores)
- **structlog** — structured logging throughout

### UI / Dashboard
- **FastAPI** — REST API server (KubeAI control plane API)
- **WebSockets** — real-time agent status streaming to UI
- **React + Vite** — frontend dashboard (separate ui/ directory)
- Dashboard shows: live agent pool status, routing decisions, memory usage,
  cost per agent, eval scores, task history, topology graph

### CLI
- **Typer** — CLI framework (by FastAPI author, beautiful output)
- **Rich** — terminal formatting (tables, live status, progress bars)

### Config & Secrets
- **Pydantic v2** — all config objects, blueprint validation, template schemas
- **python-dotenv** — .env loading
- **PyYAML** — blueprint and template YAML files

### Testing
- **pytest** — all tests
- **pytest-asyncio** — async test support
- **respx** — mock HTTP for LiteLLM calls in tests

---

## Full project structure

```
KubeAI/
├── KubeAI/
│   ├── __init__.py
│   ├── runtime.py              # AgentRuntime — main entrypoint
│   │
│   ├── core/
│   │   ├── agent.py            # Agent, AgentBlueprint, AgentState
│   │   ├── deployment.py       # KubeAIeployment (desired state)
│   │   ├── job.py              # AgentJob, AgentCronJob
│   │   ├── service.py          # AgentService (stable pool endpoint)
│   │   ├── config.py           # AgentConfig, AgentSecret
│   │   └── policy.py           # AgentRBAC, AgentPolicy
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── router.py           # semantic routing (LiteLLM scored)
│   │   ├── decomposer.py       # task decomposition
│   │   ├── llm_pool.py         # model registry + assignment policy
│   │   ├── mcp_pool.py         # MCP registry + capability matching
│   │   ├── assignment.py       # combines routing, model, and MCP decisions
│   │   ├── a2a.py              # A2A protocol implementation
│   │   └── mcp.py              # MCP client/server bridge
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── scheduler.py        # AgentScheduler — lifecycle management
│   │   ├── autoscaler.py       # AgentAutoscaler (HPA equivalent)
│   │   ├── pool.py             # AgentPool per blueprint
│   │   └── gc.py               # garbage collection + snapshot logic
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── data_plane.py       # SharedMemory — 3-tier abstraction
│   │   ├── backends/
│   │   │   ├── in_memory.py    # default (dev)
│   │   │   ├── redis.py        # production short-term
│   │   │   └── sqlite.py       # production long-term
│   │   └── mem0_adapter.py     # Mem0 integration
│   │
│   ├── registry/
│   │   ├── __init__.py
│   │   ├── registry.py         # BlueprintRegistry
│   │   └── versioning.py       # blueprint version management
│   │
│   ├── templates/
│   │   ├── base.py             # Template base class
│   │   ├── rag/
│   │   │   ├── basic.py        # LlamaIndex VectorStoreIndex
│   │   │   ├── hybrid.py       # BM25 + vector via LlamaIndex
│   │   │   └── reranking.py    # + CohereRerank / SentenceTransformer
│   │   └── memory/
│   │       ├── sliding_window.py   # keep last N turns
│   │       ├── summarizing.py      # auto-summarize via Mem0
│   │       └── episodic.py         # key-fact extraction via Mem0
│   │
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── eval_loop.py        # background eval thread
│   │   ├── probes.py           # probe task definitions per blueprint
│   │   └── scorer.py           # output quality scoring
│   │
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── metrics.py          # Prometheus metrics definitions
│   │   ├── tracing.py          # OpenTelemetry spans
│   │   └── logger.py           # structlog setup
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py           # FastAPI app
│   │   ├── routes/
│   │   │   ├── agents.py       # GET/POST /agents
│   │   │   ├── blueprints.py   # GET/POST /blueprints
│   │   │   ├── tasks.py        # POST /tasks, GET /tasks/{id}
│   │   │   ├── memory.py       # GET /memory/{domain}
│   │   │   └── metrics.py      # GET /metrics (Prometheus)
│   │   └── ws/
│   │       └── stream.py       # WebSocket: live agent events
│   │
│   └── cli/
│       ├── __init__.py
│       ├── main.py             # Typer app root
│       └── commands/
│           ├── run.py          # agentctl run
│           ├── blueprints.py   # agentctl blueprints
│           ├── templates.py    # agentctl templates
│           ├── status.py       # agentctl status
│           ├── logs.py         # agentctl logs
│           └── demo.py         # agentctl demo
│
├── ui/                         # React dashboard
│   ├── src/
│   │   ├── components/
│   │   │   ├── AgentTopology.tsx   # live agent graph (d3 or reactflow)
│   │   │   ├── AgentPool.tsx       # pool status cards
│   │   │   ├── TaskFeed.tsx        # live task stream
│   │   │   ├── MemoryViewer.tsx    # browse shared memory
│   │   │   ├── CostTracker.tsx     # token cost per agent/domain
│   │   │   └── EvalScores.tsx      # quality scores over time
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── blueprints/
│   ├── research_agent.yaml
│   ├── coding_agent.yaml
│   ├── data_agent.yaml
│   └── writing_agent.yaml
│
├── templates/
│   ├── rag/
│   │   ├── basic.yaml
│   │   ├── hybrid.yaml
│   │   └── reranking.yaml
│   └── memory/
│       ├── sliding_window.yaml
│       ├── summarizing.yaml
│       └── episodic.yaml
│
├── examples/
│   ├── demo.py                 # end-to-end demo
│   ├── multi_agent.py          # A2A multi-agent example
│   └── custom_blueprint.py     # register a custom agent
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── docs/
│   ├── architecture.md
│   ├── blueprints.md
│   ├── templates.md
│   └── api.md
│
├── CLAUDE.md                   # this file
├── DESIGN.md                   # architecture rationale
├── README.md
├── pyproject.toml
└── docker-compose.yml          # redis + qdrant for local dev
```

---

## Core design rules — never break these

1. **Agents are stateless.** Never store task state on the Agent object.
   All state goes to SharedMemory (data_plane.py).

2. **No hardcoded routing.** All routing goes through router.py using LiteLLM scoring.
   Never write `if "code" in task` anywhere.

3. **Blueprints are immutable.** Never modify a registered blueprint.
   Always create a new version. Semantic versioning (1.0.0, 1.1.0, etc.).

4. **Use LiteLLM for all LLM calls.** Never call anthropic.Anthropic() or OpenAI()
   directly. Always go through LiteLLM so provider is swappable.

5. **Use A2A for agent-to-agent communication.** Never call agent.run() from
   inside another agent directly. Route through the Orchestrator's a2a.py.

6. **Templates are composable.** An agent can have both a RAG template and a
   memory template. Templates attach at spawn time, not at blueprint definition time.

7. **Everything emits metrics.** Every scheduler decision, every routing decision,
   every eval score, every task completion must emit a Prometheus metric and an
   OpenTelemetry span.

8. **Pydantic v2 for all data models.** BlueprintSpec, TemplateConfig,
   AgentStatus, TaskResult — all Pydantic BaseModel. Never raw dicts for public APIs.

9. **The API is the source of truth.** The CLI calls the API. The UI calls the API.
   Nothing talks to the runtime directly except through KubeAI/api/server.py.

10. **Blueprint model requirements are tier-based.** Blueprints declare minimum
   tiers (`fast`, `capable`, `best`), not provider-specific model names.

11. **Routing always uses the largest registered model.** The Orchestrator's
   routing-quality decision is the highest-value inference in the system.

12. **Agents never self-assign models or MCP tools.** Model and MCP attachment
   happens only in orchestrator assignment at spawn time.

---

## Key data models

### AgentBlueprint
```python
class AgentBlueprint(BaseModel):
    name: str
    version: str                          # semver
    description: str
    capability_tags: list[str]
    system_prompt: str
    tools: list[dict]                     # MCP tool definitions
      llm_tier_min: Literal["fast", "capable", "best"] = "capable"
      required_mcp_capabilities: list[str] = []
    max_tokens: int = 2048
    resource_limits: ResourceLimits
    rag_template: str | None = None       # e.g. "reranking"
    memory_template: str | None = None    # e.g. "summarizing"
```

### KubeAIeployment (new — Kubernetes Deployment equivalent)
```python
class KubeAIeployment(BaseModel):
    name: str
    blueprint: str                        # blueprint name
    blueprint_version: str = "latest"
    replicas: int = 1                     # desired instance count
    domain: str = "default"
    autoscale: AutoscalePolicy | None
    rag_template: str | None
    memory_template: str | None
```

### TaskResult
```python
class TaskResult(BaseModel):
    task_id: str
    task: str
    result: str
    agent_id: str
    blueprint_name: str
    latency_ms: float
    token_cost: float
    eval_score: float | None
    timestamp: float
```

## LLMPool (new core component)

LLMPool is an orchestrator-owned registry of available models, their tiers,
cost envelopes, and live health signals.

Assignment policy uses three signals:
1. **Cost signal**: simple tasks route to low-cost models by default.
2. **Load signal**: rate-limit or latency events trigger failover.
3. **Blueprint tier signal**: blueprint `llm_tier_min` sets a floor.

Hard rule:
- The **Orchestrator routing step** always executes on the largest registered model.

## MCPPool (new core component)

MCPPool is an orchestrator-owned registry of MCP servers and capability tags.

Assignment policy:
1. Extract capability requirements from task intent and blueprint metadata.
2. Match MCP servers by capability tags.
3. Attach one or more MCP servers during agent spawn.

Extensibility:
- Custom MCP servers are first-class and can be registered via CLI.

## Assignment policy interface

```python
class LLMPool(Protocol):
   def register(self, model_id: str, tier: str, metadata: dict) -> None: ...
   def select(self, task: str, tier_min: str, route_call: bool = False) -> str: ...


class MCPPool(Protocol):
   def register(self, name: str, endpoint: str, capabilities: list[str]) -> None: ...
   def select(self, task: str, required: list[str] | None = None) -> list[str]: ...


class AssignmentPolicy(Protocol):
   def assign(self, task: str, blueprint: AgentBlueprint) -> tuple[str, list[str]]:
      """Return assigned model_id and attached MCP names."""
```

---

## A2A implementation details

Use Google's A2A spec: https://google.github.io/A2A

Each agent exposes an AgentCard:
```python
class AgentCard(BaseModel):
    name: str
    description: str
    capabilities: list[str]
    endpoint: str                         # http://localhost:8000/agents/{id}
    input_schema: dict
    output_schema: dict
```

The Orchestrator's a2a.py:
- Maintains a registry of AgentCards for all running agents
- When agent A needs to call agent B, it sends an A2A Task object
- Tasks flow through the Orchestrator, not direct HTTP calls
- This enables tracing, policy enforcement, and circuit breaking

---

## Monitoring stack

Prometheus metrics to expose at GET /metrics:

```
KubeAI_tasks_total{blueprint, status}          counter
KubeAI_task_latency_ms{blueprint}              histogram
KubeAI_agent_spawns_total{blueprint}           counter
KubeAI_agent_pool_size{blueprint, state}       gauge
KubeAI_routing_confidence{blueprint}           histogram
KubeAI_eval_score{blueprint}                   histogram
KubeAI_token_cost_total{blueprint, provider}   counter
KubeAI_memory_entries{tier, domain}            gauge
```

OpenTelemetry spans:
- orchestrator.route (task routing decision)
- scheduler.spawn / scheduler.reuse
- agent.run (full task execution)
- template.rag.retrieve
- template.memory.load / template.memory.save
- eval.probe

---

## UI dashboard pages

### 1. Overview (/)
Live topology graph — nodes are agent instances, edges are A2A calls.
Color-coded by state (green=running, yellow=idle, red=eval-failed).
Top metrics strip: active agents, tasks/min, avg latency, total cost today.

### 2. Agents (/agents)
Table: all running agents with state, blueprint, idle time, eval score, cost.
Click row → agent detail: full task history, memory contents, eval history.

### 3. Tasks (/tasks)
Live feed of tasks as they arrive and complete.
Each row: task preview, routed blueprint, latency, cost, eval score.
Click → full task detail with routing scores for all blueprints.

### 4. Memory (/memory)
Domain selector → browse short-term and long-term memory entries.
Search by key or content.

### 5. Blueprints (/blueprints)
All registered blueprints with versions.
Click → blueprint detail: system prompt, tools, resource limits, routing history.

### 6. Monitoring (/monitoring)
Embedded Grafana or custom charts:
- Tasks/min over time
- Avg eval score per blueprint over time
- Token cost per domain per day
- Agent pool utilization
- Routing confidence distribution

---

## CLI commands (full spec)

```bash
# Task execution
agentctl run "<task>"
agentctl run "<task>" --rag reranking --memory summarizing
agentctl run "<task>" --blueprint coding_agent --domain myapp
agentctl run "<task>" --decompose          # auto-decompose + parallel
agentctl run "<task>" --watch              # stream output live

# Agent management
agentctl agents list
agentctl agents list --domain myapp
agentctl agents inspect <agent-id>
agentctl agents terminate <agent-id>
agentctl agents logs <agent-id>

# Deployments (desired state)
agentctl deploy research_agent --replicas 3 --rag hybrid
agentctl deployments list
agentctl deployments scale research_agent --replicas 5
agentctl deployments delete research_agent

# Blueprints
agentctl blueprints list
agentctl blueprints register ./my_agent.yaml
agentctl blueprints inspect research_agent
agentctl blueprints versions research_agent

# Templates
agentctl templates list
agentctl templates inspect rag/reranking
agentctl templates inspect memory/summarizing

# MCP registry
agentctl mcps list
agentctl mcps register ./mcp/postgres.yaml

# Memory
agentctl memory show --domain myapp
agentctl memory show --tier long_term --blueprint research_agent
agentctl memory clear --domain myapp --tier short_term

# System
agentctl status                            # full runtime status
agentctl metrics                           # print Prometheus metrics
agentctl api-server --port 8000            # start the API + UI
agentctl demo                              # run end-to-end demo
```

---

## What already exists (do not rewrite)

- KubeAI/agent.py — Agent, AgentBlueprint, AgentState
- KubeAI/memory.py — SharedMemory (in-memory, to be replaced with backends/)
- KubeAI/registry.py — BlueprintRegistry
- KubeAI/orchestrator.py — Orchestrator with LLM-based routing
- KubeAI/scheduler.py — Scheduler with GC loop
- KubeAI/eval_loop.py — EvalLoop with probe tasks
- KubeAI/runtime.py — AgentRuntime wiring everything together
- examples/demo.py — end-to-end demo

---

## Build order (do this in sequence)

1. **Refactor core** — move existing files into core/, orchestrator/, scheduler/, memory/
   Add Pydantic models. Wire LiteLLM in place of direct Anthropic calls.

2. **Memory backends** — memory/backends/in_memory.py, redis.py, sqlite.py

3. **Templates** — templates/base.py → rag/* → memory/*
   Wire LlamaIndex for RAG, Mem0 for memory.

4. **A2A + MCP** — orchestrator/a2a.py, orchestrator/mcp.py
   Implement AgentCard, Task routing through Orchestrator.

5. **LLMPool + MCPPool allocator** — orchestrator/llm_pool.py,
   orchestrator/mcp_pool.py, orchestrator/assignment.py
   Implement cost/load/tier model selection and capability-based MCP attachment.

6. **Deployments** — core/deployment.py, scheduler/autoscaler.py
   Desired state reconciliation loop (like kube-controller-manager).

7. **Monitoring** — monitoring/metrics.py, monitoring/tracing.py
   Prometheus metrics + OTel spans on every operation.

8. **API server** — api/server.py + all routes
   FastAPI with WebSocket streaming.

9. **CLI** — cli/ with Typer + Rich
   All commands call the API server.

10. **UI dashboard** — ui/ React app
   Calls the API. WebSocket for live updates.

11. **Tests** — tests/unit/, tests/integration/

---

## When in doubt

Ask: "what would Kubernetes do here?"
The answer maps directly to what KubeAI should do.
The K8s documentation is the architecture spec for this project.