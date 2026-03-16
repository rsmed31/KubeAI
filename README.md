# KubeAI
kubernetes-like architecture for auto-spinning ai agents

> *Kubernetes taught us how to manage containers at scale. **KubeAI** does the same for AI agents.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status: Experimental](https://img.shields.io/badge/Status-Experimental-orange.svg)]()
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)]()

---

## The Problem

AI agent frameworks are everywhere. LangChain, AutoGen, CrewAI, kagent — they all help you *build* agents. But once your agents are running in production:

- **Who decides which agent handles which task?**
- **Who spins up a new agent when demand spikes?**
- **Where does context live when an agent is destroyed?**
- **How do you know when an agent is performing poorly?**

Nobody is solving this. Today's agents are stateful monoliths you deploy manually, route to with hardcoded logic, and pray don't crash. It's 2014 again — except instead of servers, we're managing AI agents by hand.

**KubeAI** is the missing runtime layer.

---

## The Analogy

| Kubernetes          | KubeAI                                        |
|---------------------|-----------------------------------------------|
| Pod                 | Agent instance                                |
| Scheduler           | Agent Scheduler                               |
| etcd                | Shared Memory / Data Plane                    |
| Ingress + Istio     | Orchestrator (semantic task router)           |
| Container Image     | Agent Blueprint (prompt + tools + LLM config) |
| Health Check        | Agent Eval Loop (quality-based)               |
| kubectl             | agentctl CLI                                  |
| Namespace           | Agent Domain                                  |
| Helm Chart          | KubeAI Template (RAG, memory, tools)          |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             KubeAI runtime                               │
│                                                                          │
│  incoming task                                                           │
│      │                                                                   │
│      ▼                                                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                         ORCHESTRATOR                              │  │
│  │  • semantic routing    task → best agent type (LLM scored)        │  │
│  │  • task decomposition  1 complex task → N parallel sub-tasks      │  │
│  │  • blueprint lookup    queries the registry                       │  │
│  └─────────────────────────────┬─────────────────────────────────────┘  │
│                                │ route(blueprint)                        │
│                                ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                          SCHEDULER                                │  │
│  │  • warm path    idle agent exists → reuse it   (~0ms)             │  │
│  │  • cold path    no idle agent    → spawn new   (pull blueprint)   │  │
│  │  • GC loop      idle too long   → snapshot → terminate            │  │
│  │  • capacity     enforce max concurrent per blueprint              │  │
│  └──────────────┬───────────────┬───────────────┬─────────────────┘   │
│                 │               │               │                        │
│          spawn  ▼        reuse  ▼        reuse  ▼                       │
│          ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│          │ agent:A  │  │ agent:B  │  │ agent:C  │  · · · n agents      │
│          │          │  │          │  │          │                       │
│          │blueprint │  │blueprint │  │blueprint │                       │
│          │+ tools   │  │+ tools   │  │+ tools   │                       │
│          │+ RAG tpl │  │+ mem tpl │  │          │                       │
│          └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
│               │             │             │                              │
│               └─────────────┼─────────────┘                             │
│                             │ read / write                               │
│                             ▼                                            │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      SHARED DATA PLANE                            │  │
│  │                                                                   │  │
│  │  working memory        short-term memory      long-term memory   │  │
│  │  per agent, ephemeral  session-scoped, TTL    blueprint-scoped   │  │
│  │                        shared across agents   survives restarts  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────┐   ┌──────────────────────────────────┐   │
│  │    BLUEPRINT REGISTRY    │   │           EVAL LOOP              │   │
│  │  versioned agent defs    │   │  probe tasks → quality score     │   │
│  │  prompt · tools · model  │   │  replace underperformers         │   │
│  │  resource limits         │   │  runs in background thread       │   │
│  └──────────────────────────┘   └──────────────────────────────────┘   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                         TEMPLATES                                 │  │
│  │                                                                   │  │
│  │  RAG templates                    Memory templates               │  │
│  │  ├── basic       vector search    ├── sliding_window             │  │
│  │  ├── hybrid      BM25 + vector    ├── summarizing                │  │
│  │  └── reranking   + cross-encoder  └── episodic                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Request Lifecycle

```
  1. task arrives
  2. Orchestrator scores all blueprints → picks best match
  3. Scheduler: idle agent? reuse it — else spawn new from blueprint
  4. Agent loads context from Shared Data Plane
  5. Agent attaches RAG template → retrieves relevant docs  (if configured)
  6. Agent applies memory template → trims/summarizes history  (if configured)
  7. Agent runs task with LLM + tools
  8. Agent writes result + updated context → Shared Data Plane
  9. Agent → IDLE
     ├── new task arrives?  → back to step 4
     └── idle too long?     → snapshot context → TERMINATED
```

---

## Core Components

**Orchestrator** — Receives any task, semantically scores it against all registered blueprints using an LLM, picks the best match. No hardcoded routing rules. Can also decompose a complex task into independent sub-tasks and fan them out to multiple specialized agents in parallel.

**Scheduler** — Maintains a pool of agent instances per blueprint. Reuses idle agents (warm path) to avoid spawn latency. Spawns fresh instances on demand (cold path). Runs a background GC loop: idle agents past their timeout get snapshotted and terminated.

**Shared Data Plane** — Three-tier memory store all agents share. Working memory is ephemeral and per-instance. Short-term memory is session-scoped with TTL, shared across agents in the same domain. Long-term memory is blueprint-scoped and survives agent restarts. Agent handoffs work by one agent reading another's working memory snapshot.

**Blueprint Registry** — Versioned, immutable agent definitions. Each blueprint specifies system prompt, tools, LLM provider + model, input/output schema, and resource limits. Blueprints are the unit of versioning, rollback, and instantiation — exactly like container images.

**Templates** — Composable capability modules that mount onto agents at spawn time. RAG templates add a retrieval pipeline (basic vector / hybrid BM25+vector / reranking with cross-encoder). Memory templates control history management (sliding window / auto-summarizing / episodic key-fact extraction). Declared in YAML, attached via CLI flags.

**Eval Loop** — Background thread that periodically runs small probe tasks against idle agents and scores the output quality. Agents below the threshold are replaced. Quality-based lifecycle management, not just uptime pings.

---

## Novel Contributions

**Semantic Routing** — Route by meaning, not rules. Tasks are LLM-scored against agent capability descriptions. No `if "code" in task → coding_agent`.

**Agent GC with Memory Snapshots** — Agents serialize working context before termination. Future instances rehydrate from the snapshot. Context survives agent death.

**Agent Eval Loop** — Quality-based health checks. Probe tasks benchmark idle agents continuously. Underperformers are replaced, not just restarted.

**Agent-as-a-Primitive** — Formal lifecycle: `PENDING → RUNNING → IDLE → SNAPSHOT → TERMINATED`. Agents are first-class runtime objects.

**Composable Templates** — RAG and memory strategies are external YAML configs, not hardcoded in agent logic. Swap retrieval strategy with one CLI flag.

---

## Quickstart

```bash
git clone https://github.com/yourname/KubeAI
cd KubeAI
pip install -e .

# optional: run tests
python -m pytest -q

# check local CLI state and built-in templates
agentctl status
agentctl templates list

# sample CLI usage
agentctl run "Explain how transformers work"
agentctl run "Write a Python binary search" --rag basic
agentctl run "Summarize this doc" --rag reranking --memory summarizing
agentctl blueprints register ./my_blueprint.yaml
agentctl blueprints list
agentctl templates list
agentctl mcps register ./mcp/postgres.yaml
agentctl mcps list
agentctl demo

# run dashboard API + UI
python -c "from KubeAI.dashboard.server import serve; serve(port=8080)"
```

Open `http://localhost:8080` to view the dashboard UI.

## Use etcd for Shared Memory (Kubernetes-style)

If you want KubeAI memory persistence to match Kubernetes control-plane storage,
use the etcd-backed backend for long-term tier keys.

```python
from KubeAI.memory import SharedMemory

memory = SharedMemory(
  long_term_backend="etcd",
  etcd_host="127.0.0.1",
  etcd_port=2379,
  etcd_namespace="kubeai",
)

memory.set_long_term("coding_agent", "style", {"guide": "pep8"})
print(memory.get_long_term("coding_agent", "style"))
```

Notes:
- `working` and `short_term` still default to in-process memory.
- `long_term_backend="sqlite"` remains available for local-only development.
- Install backend dependency: `pip install etcd3`
- If etcd is unavailable, keep `long_term_backend="sqlite"` for local runs.

## File-Based Pool Config (JSON)

Define all orchestrator pools in one JSON file and load them at startup.

Sample file: `examples/pools.sample.json`

```python
from KubeAI.orchestrator import load_assignment_policy_from_json, load_pools_from_json

bundle = load_pools_from_json("examples/pools.sample.json")
policy = load_assignment_policy_from_json("examples/pools.sample.json")

# Use in runtime bootstrap
llm_pool = bundle.llm_pool
mcp_pool = bundle.mcp_pool
a2a_pool = bundle.a2a_pool
```

Expected top-level JSON keys:
- `llm_models`
- `mcp_servers`
- `a2a_agents`

Pool selection hints:
- `description` can be added to LLM, MCP, and A2A entries.
- Assignment uses task text + description overlap to prefer better-fitting models/tools.
- For local inference, set provider to `ollama` or `local` (or set `is_local: true`).

---

## Project Structure

```
KubeAI/
├── KubeAI/
│   ├── api/
│   │   ├── __init__.py
│   │   └── control_plane.py    # in-memory control-plane facade
│   ├── dashboard/
│   │   ├── server.py           # FastAPI app + WebSocket stream
│   │   ├── deps.py             # control-plane dependency injection
│   │   ├── ws_manager.py
│   │   ├── api/
│   │   │   ├── overview.py
│   │   │   ├── agents.py
│   │   │   ├── tasks.py
│   │   │   ├── memory.py
│   │   │   ├── blueprints.py
│   │   │   └── monitoring.py
│   │   └── static/             # dashboard frontend assets
│   ├── memory/
│   │   ├── base.py             # SharedMemoryBackend contract
│   │   ├── in_memory.py        # working/short-term volatile backend
│   │   ├── sqlite_backend.py   # local persistent backend
│   │   ├── etcd_backend.py     # kubernetes-style distributed backend
│   │   └── shared_memory.py    # 3-tier memory facade
│   ├── monitoring/
│   │   ├── metrics.py          # metrics registry + Prometheus text output
│   │   └── events.py           # runtime event stream
│   ├── orchestrator/
│   │   ├── llm_pool.py
│   │   ├── mcp_pool.py
│   │   ├── a2a_pool.py
│   │   ├── a2a_router.py
│   │   ├── assignment.py
│   │   ├── document_probe.py
│   │   ├── document_dispatch.py
│   │   ├── orchestrator.py
│   │   └── pool_loader.py
│   ├── scheduler/
│   │   └── scheduler_module_policy.py
│   ├── scraper/
│   │   ├── loader.py
│   │   ├── normalize.py
│   │   └── chunk.py
│   ├── blueprint.py
│   ├── cli.py
│   └── templates/
│       ├── base.py             # template interface
│       ├── rag/
│       │   ├── basic.py        # vector search
│       │   ├── hybrid.py       # BM25 + vector
│       │   ├── reranking.py    # hybrid + cross-encoder rerank
│       │   ├── scraper.py      # ingestion-oriented RAG template
│       │   └── knowledge_graph.py
│       └── memory/
│           ├── sliding_window.py
│           ├── summarizing.py
│           └── episodic.py
├── examples/
│   └── pools.sample.json       # declarative pool config
├── blueprints/
│   └── research_agent.yaml
├── templates/
│   ├── rag/
│   │   ├── basic.yaml
│   │   ├── hybrid.yaml
│   │   └── reranking.yaml
│   └── memory/
│       ├── sliding_window.yaml
│       ├── summarizing.yaml
│       └── episodic.yaml
├── tests/
├── agents.md
├── plan.md
├── CLAUDE.md
├── README.md
└── pyproject.toml
```

---

## Implementation Status

Implemented now:
- Semantic orchestrator with LLM/MCP/A2A pools and assignment policy.
- File-based pool loading via JSON (`examples/pools.sample.json`).
- RAG templates: basic, hybrid, reranking, scraper, knowledge_graph.
- Memory templates: sliding_window, summarizing, episodic.
- Shared memory backends: in-memory, SQLite, and etcd.
- Control-plane facade with metrics/event streams.
- FastAPI dashboard routes with WebSocket updates and static UI.
- CLI surface for run, blueprints, templates, MCP registry, status, and demo.

In progress:
- Wiring orchestrator/scheduler runtime lifecycle directly into control-plane updates.
- Hardening API contracts and expanding deployment lifecycle management.

Planned:
- Kubernetes operator and cluster-native deployment workflows.
- Full productionization of observability/tracing and autoscaling paths.

---

## Difference from Existing Projects

| Project      | What it does                          | What KubeAI adds                    |
|--------------|---------------------------------------|-------------------------------------|
| kagent       | Deploy agents ON Kubernetes           | Runtime layer above the infra       |
| LangGraph    | Define agent graphs in code           | Infrastructure, not a framework     |
| AutoGen      | Multi-agent conversations             | Lifecycle + scheduling + memory     |
| Gas Town     | Orchestrate coding agents (git-based) | Domain-agnostic, general-purpose    |
| OpenAI Swarm | Lightweight handoff pattern           | Full runtime: schedule, route, eval |

---

## Building with AI coding tools?

See [CLAUDE.md](CLAUDE.md) — a ready-made prompt that gives Claude Code, Cursor,
or any AI coding assistant full context on the project before you start a session.

---

## Author

Started by **rsmed31** — March 2026.

*If you're building something in this space, let's talk.*

---

## License

Apache 2.0 — see [LICENSE](LICENSE)