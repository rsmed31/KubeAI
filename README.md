# KubeAI — Kubernetes-Style Runtime Infrastructure for AI Agents

> *Kubernetes taught us how to manage containers at scale. **KubeAI** does the same for AI agents.*

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status: Experimental](https://img.shields.io/badge/Status-Experimental-orange.svg)]()
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)]()

KubeAI is NOT a framework for building agents — LangChain, AutoGen, and CrewAI already do that. KubeAI IS the runtime infrastructure that manages agents at scale: the layer above your agent code that handles everything Kubernetes handles for containers. Every concept maps directly: blueprints are container images, the orchestrator is Ingress+Istio, the scheduler is the controller-manager, shared memory is etcd, the control-plane API is the Kubernetes API server, and the dashboard is the Kubernetes Dashboard.

| Kubernetes            | KubeAI                                        |
|-----------------------|-----------------------------------------------|
| Pod                   | Agent instance                                |
| Deployment            | KubeAI Deployment (desired-state spec)        |
| Scheduler             | AgentScheduler / AgentLifecycleManager        |
| etcd                  | SharedMemory (3-tier data plane)              |
| Ingress + Istio       | Orchestrator (semantic task router)           |
| Container Image       | Blueprint (prompt + tools + LLM tier)         |
| Health Check          | Eval Loop (quality-based probes)              |
| kubectl               | agentctl CLI                                  |
| Namespace             | Agent Domain                                  |
| Helm Chart            | KubeAI Template (RAG, memory, tools)          |
| Prometheus + Grafana  | Observability stack (MetricsStore + Tracer)   |

---

## Quick Start

```bash
git clone https://github.com/yourname/KubeAI
cd KubeAI
pip install -e .

# Set your provider key (LiteLLM-compatible)
export ANTHROPIC_API_KEY=sk-ant-...

# Run the end-to-end demo
python examples/demo.py

# Or use the CLI
agentctl blueprints list
agentctl run "Write a Python quicksort"
agentctl demo
```

---

## Architecture

| Component           | File                                      | K8s Analogue              |
|---------------------|-------------------------------------------|---------------------------|
| LLMPool             | `orchestrator/llm_pool.py`                | Node pool                 |
| MCPPool             | `orchestrator/mcp_pool.py`                | Service mesh registry     |
| AssignmentPolicy    | `orchestrator/assignment.py`              | kube-scheduler            |
| Orchestrator        | `orchestrator/orchestrator.py`            | Ingress + Istio           |
| SharedMemory        | `memory/shared_memory.py`                 | etcd / PersistentVolume   |
| ControlPlaneAPI     | `api/control_plane.py`                    | Kubernetes API server     |
| AgentLifecycleManager | `scheduler/lifecycle.py`               | ReplicaSet controller     |
| Dashboard           | `dashboard/server.py`                     | Kubernetes Dashboard      |
| Observability       | `observability/`                          | Prometheus + Jaeger       |
| Templates           | `templates/rag/`, `templates/memory/`     | Helm Chart capabilities   |

---

## Running the Dashboard

```bash
python -c "from KubeAI.dashboard.server import serve; serve()"
```

Open `http://localhost:8000` to view live agent pool status, routing decisions, memory usage, cost per agent, eval scores, and task history.

---

## CLI Reference

```bash
agentctl run "Summarise Q3 report" --rag basic --memory summarizing
agentctl blueprints list
agentctl blueprints register ./my_blueprint.yaml
agentctl templates list
agentctl mcps list
agentctl mcps register ./mcp/postgres.yaml
agentctl status
agentctl demo
```

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run all tests
pytest

# Run with verbose output
pytest -v tests/test_e2e_lifecycle.py
```

---

## Project Status

**Implemented:**
- Semantic orchestrator with LLM/MCP/A2A pools and AssignmentPolicy
- File-based pool loading via JSON (`examples/pools.sample.json`)
- RAG templates: basic, hybrid, reranking, scraper, knowledge_graph
- Memory templates: sliding_window, summarizing, episodic
- SharedMemory backends: in-memory, SQLite, and etcd
- ControlPlaneAPI with MetricsStore and EventStreamHub
- FastAPI dashboard with WebSocket streaming and static UI
- AgentLifecycleManager with spawn/idle/terminate lifecycle sync
- Observability package: structured JSON logging + in-process span tracing
- CLI surface: run, blueprints, templates, MCP registry, status, demo
- E2E integration tests (no network required, injected score/decompose fns)

**In Progress:**
- Wiring orchestrator/scheduler lifecycle into real LLM execution flows
- Hardening API contracts and expanding deployment lifecycle management

**Planned:**
- Kubernetes operator and cluster-native deployment workflows
- Full autoscaling on queue depth and token cost signals
- Production-grade distributed tracing (OpenTelemetry export)
- Agent eval loop with automatic underperformer replacement

---

## Difference from Existing Projects

| Project      | What it does                          | What KubeAI adds                    |
|--------------|---------------------------------------|-------------------------------------|
| kagent       | Deploy agents ON Kubernetes           | Runtime layer above the infra       |
| LangGraph    | Define agent graphs in code           | Infrastructure, not a framework     |
| AutoGen      | Multi-agent conversations             | Lifecycle + scheduling + memory     |
| OpenAI Swarm | Lightweight handoff pattern           | Full runtime: schedule, route, eval |

---

## Author

Started by **rsmed31** — March 2026.

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
