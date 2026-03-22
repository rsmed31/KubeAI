# KubeAI Deployment Guide

This guide covers running the full KubeAI stack locally using Docker Compose.
The compose file starts every infrastructure dependency (PostgreSQL, Redis,
ChromaDB, Prometheus, Grafana, Airflow) so you can run the API server against
real backends without manual service setup.

---

## Prerequisites

- Docker 24+ and Docker Compose v2 (bundled with Docker Desktop)
- Python 3.11+ (for the KubeAI API server, run on the host)
- At least one LLM provider API key

---

## Quick start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/KubeAI.git
cd KubeAI

# 2. Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set one LLM API key (e.g. ANTHROPIC_API_KEY)

# 3. Start all infrastructure services
docker compose up -d

# 4. Install Python dependencies
pip install -e ".[all]"

# 5. Start the KubeAI API server
python -m uvicorn KubeAI.dashboard.server:app --port 8080 --reload

# 6. Verify everything is running
agentctl status
```

The dashboard UI is available at `http://localhost:5173` after running
`npm run dev` inside the `ui/` directory.

---

## Services

| Service       | Container name           | Default port | Purpose                                      |
|---------------|--------------------------|--------------|----------------------------------------------|
| PostgreSQL    | `kubeai-postgres`        | 5432         | Config store, skill registry, Airflow DB     |
| Redis         | `kubeai-redis`           | 6379         | Short-term agent memory, task queues         |
| ChromaDB      | `kubeai-chromadb`        | 8000         | Persistent vector store for RAG              |
| Prometheus    | `kubeai-prometheus`      | 9090         | Metrics scraping from the API server         |
| Grafana       | `kubeai-grafana`         | 3000         | Dashboards (default login: admin / admin)    |
| Airflow UI    | `kubeai-airflow-webserver`| 8081        | Scheduled benchmark DAG execution            |
| KubeAI API   | host process             | 8080         | REST API + WebSocket (run on host)           |
| KubeAI UI    | Vite dev server          | 5173         | React dashboard (run on host)                |

---

## Environment variables

Copy `.env.example` to `.env` and set the values for your environment.

### Infrastructure

| Variable            | Default        | Description                              |
|---------------------|----------------|------------------------------------------|
| `POSTGRES_DB`       | `kubeai`       | PostgreSQL database name                 |
| `POSTGRES_USER`     | `kubeai`       | PostgreSQL username                      |
| `POSTGRES_PASSWORD` | `kubeai_dev`   | PostgreSQL password — change in production|
| `POSTGRES_PORT`     | `5432`         | Host port mapped to PostgreSQL           |
| `REDIS_PORT`        | `6379`         | Host port mapped to Redis                |
| `CHROMA_PORT`       | `8000`         | Host port mapped to ChromaDB             |
| `PROMETHEUS_PORT`   | `9090`         | Host port mapped to Prometheus           |
| `GRAFANA_PORT`      | `3000`         | Host port mapped to Grafana              |
| `GRAFANA_USER`      | `admin`        | Grafana admin username                   |
| `GRAFANA_PASSWORD`  | `admin`        | Grafana admin password                   |
| `AIRFLOW_PORT`      | `8081`         | Host port mapped to Airflow webserver    |
| `AIRFLOW_USER`      | `admin`        | Airflow admin username                   |
| `AIRFLOW_PASSWORD`  | `admin`        | Airflow admin password                   |
| `AIRFLOW_FERNET_KEY`| _(empty)_      | Fernet key for Airflow secret encryption |

### KubeAI runtime

| Variable             | Default | Description                                          |
|----------------------|---------|------------------------------------------------------|
| `KUBEAI_API_PORT`    | `8080`  | Port the API server listens on                       |
| `KUBEAI_API_URL`     | _(none)_| Used by the CLI to locate the server (default: `http://localhost:8080`) |
| `KUBEAI_MODELS_CONFIG`| _(none)_| Path to a YAML file pre-loading the LLM pool        |

### LLM provider API keys

Set the keys for every provider you want to use. Only the keys you provide are
active — unused providers are simply unavailable in the LLM pool.

| Variable            | Provider            |
|---------------------|---------------------|
| `ANTHROPIC_API_KEY` | Anthropic (Claude)  |
| `OPENAI_API_KEY`    | OpenAI (GPT-4, etc.)|
| `GOOGLE_API_KEY`    | Google (Gemini)     |
| `GROQ_API_KEY`      | Groq                |
| `MISTRAL_API_KEY`   | Mistral AI          |
| `COHERE_API_KEY`    | Cohere              |

---

## Starting individual services

```bash
# Start only the data-layer services (skip Airflow)
docker compose up -d postgres redis chromadb

# Start monitoring stack
docker compose up -d prometheus grafana

# Start everything
docker compose up -d

# Stop everything and remove containers (volumes are preserved)
docker compose down

# Stop and wipe all data volumes
docker compose down -v
```

---

## Connecting the API server to infrastructure

Export the connection strings before starting the API server:

```bash
export POSTGRES_DSN="postgresql://kubeai:kubeai_dev@localhost:5432/kubeai"
export REDIS_URL="redis://localhost:6379"
export CHROMA_HOST="localhost"
export CHROMA_PORT="8000"

python -m uvicorn KubeAI.dashboard.server:app --port 8080 --reload
```

When `POSTGRES_DSN` is set, `ConfigStore` and `SkillRegistry` persist to the
database and hot-reload changes within 2 seconds of a write.

---

## Prometheus scrape target

Prometheus is pre-configured (via `infra/prometheus/prometheus.yml`) to scrape
the KubeAI API server at `http://host.docker.internal:8080/metrics`. This works
on Docker Desktop. On Linux set `extra_hosts` or use the host's LAN IP.

Metrics exposed:

```
kubeai_tasks_total{blueprint, status}
kubeai_task_latency_ms{blueprint}
kubeai_agent_spawns_total{blueprint}
kubeai_agent_pool_size{blueprint, state}
kubeai_routing_confidence{blueprint}
kubeai_eval_score{blueprint}
kubeai_token_cost_total{blueprint, provider}
kubeai_memory_entries{tier, domain}
```

---

## Grafana dashboards

Pre-built dashboards are provisioned automatically from
`infra/grafana/dashboards/`. Open `http://localhost:3000` (admin / admin) to
view:

- **Workflow Overview** — tasks/min, avg eval score, token cost per domain.
- **Agent Pool** — pool utilisation, spawn rate, GC events.
- **LLM Pool** — per-model latency, cost, health status.

---

## Airflow benchmark DAGs

The Airflow webserver at `http://localhost:8081` provides the `kubeai_benchmark`
DAG. It calls `/api/benchmarks/run` for each scenario on a daily schedule by
default. Enable the DAG from the UI or via the CLI:

```bash
# Enable via Airflow CLI inside the container
docker exec kubeai-airflow-webserver airflow dags unpause kubeai_benchmark
```

---

## Production considerations

- Set strong passwords for `POSTGRES_PASSWORD`, `GRAFANA_PASSWORD`, and
  `AIRFLOW_PASSWORD` before exposing any port externally.
- Generate a random `AIRFLOW_FERNET_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- Place the KubeAI API server behind a reverse proxy (nginx / Caddy) for TLS.
- Use a managed PostgreSQL service (RDS, Cloud SQL) instead of the compose
  container for production workloads.
- Scale the API server horizontally — all shared state lives in PostgreSQL and
  Redis, so multiple replicas work without coordination.
