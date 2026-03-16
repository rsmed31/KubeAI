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
cp .env.example .env        # add ANTHROPIC_API_KEY

# run the demo
python examples/demo.py

# CLI usage
agentctl run "Explain how transformers work"
agentctl run "Write a Python binary search" --rag basic
agentctl run "Summarize this doc" --rag reranking --memory summarizing
agentctl blueprints register ./my_blueprint.yaml
agentctl blueprints list
agentctl templates list
agentctl mcps register ./mcp/postgres.yaml
agentctl mcps list
agentctl demo
agentctl status
```

---

## Project Structure

```
KubeAI/
├── KubeAI/
│   ├── runtime.py              # main entrypoint — wires all components
│   ├── orchestrator.py         # semantic routing + task decomposition
│   ├── scheduler.py            # agent lifecycle management
│   ├── memory.py               # shared data plane (3-tier)
│   ├── registry.py             # blueprint storage + versioning
│   ├── agent.py                # agent base class + lifecycle states
│   ├── eval_loop.py            # quality-based health checks
│   ├── cli.py                  # agentctl
│   └── templates/
│       ├── base.py             # template interface
│       ├── rag/
│       │   ├── basic.py        # vector search
│       │   ├── hybrid.py       # BM25 + vector
│       │   └── reranking.py    # hybrid + cross-encoder rerank
│       └── memory/
│           ├── sliding_window.py
│           ├── summarizing.py
│           └── episodic.py
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
├── examples/
│   └── demo.py
├── tests/
├── CLAUDE.md                   # prompt for Claude Code / Cursor
├── DESIGN.md                   # full architecture rationale
├── README.md
└── pyproject.toml
```

---

## Roadmap

- [x] Core runtime: orchestrator, scheduler, memory, eval loop
- [x] Blueprint registry with built-in agent types
- [x] Semantic routing via LLM scoring
- [x] Agent GC with memory snapshots
- [ ] Templates: RAG (basic, hybrid, reranking)
- [ ] Templates: Memory (sliding window, summarizing, episodic)
- [ ] `agentctl` CLI with `--rag` and `--memory` flags
- [ ] Skill writer (agent that generates new blueprints from description)
- [ ] Persistent memory backend (Redis / SQLite)
- [ ] REST API + web dashboard
- [ ] Kubernetes operator (run KubeAI itself on K8s)
- [ ] CNCF sandbox proposal

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