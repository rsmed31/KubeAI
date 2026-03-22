# KubeAI Benchmarks

The `BenchmarkEngine` runs standardised scenarios against every registered
framework adapter and produces a quality leaderboard. Think of it as a
Kubernetes conformance test suite for agent execution backends.

---

## Available scenarios

| Scenario        | Key              | What it tests                                          | Scoring method                          |
|-----------------|------------------|--------------------------------------------------------|-----------------------------------------|
| RAG             | `rag`            | Retrieval-augmented Q&A factual accuracy               | Semantic overlap with reference answer  |
| Code generation | `codegen`        | Python function correctness and structure              | Keyword presence (`def`, `return`, etc.)|
| Research        | `research`       | Structured multi-section research summaries            | Section keyword coverage fraction       |
| Data analysis   | `data_analysis`  | Numerical reasoning over CSV data                      | Presence of correct answer + keyword    |

Each scenario follows the same three-step lifecycle:

1. `prepare()` — build a deterministic, I/O-free setup dict (question, reference data, etc.).
2. `execute(adapter, setup)` — call the adapter and capture an `AdapterResult`.
3. `evaluate(result, setup)` — score output quality in `[0.0, 1.0]`.

---

## Running benchmarks

### Via the CLI

```bash
# Run all registered adapters against the rag scenario (3 runs each)
agentctl benchmarks run --scenario rag

# Target a specific adapter and run it 5 times
agentctl benchmarks run --scenario codegen --framework litellm --num-runs 5

# List raw run records (newest first)
agentctl benchmarks list

# Show the aggregated leaderboard
agentctl benchmarks leaderboard
```

### Via the REST API

```bash
# Trigger a run
curl -X POST http://localhost:8080/api/benchmarks/run \
  -H "Content-Type: application/json" \
  -d '{"scenario": "research", "framework": "langchain", "num_runs": 3}'

# List all stored runs
curl http://localhost:8080/api/benchmarks/runs

# Leaderboard
curl http://localhost:8080/api/benchmarks/leaderboard

# Best framework per scenario (used by the routing layer)
curl http://localhost:8080/api/benchmarks/recommendations
```

### Via Airflow DAG

The `infra/airflow/dags/` directory contains a scheduled DAG that calls the
benchmark API on a configurable interval. It reads `KUBEAI_API_URL` from the
Airflow environment (set to `http://host.docker.internal:8080` by default in
`docker-compose.yml`).

To enable scheduled benchmarking:

1. Start the full stack: `docker compose up -d`
2. Open the Airflow UI at `http://localhost:8081`.
3. Enable the `kubeai_benchmark` DAG.
4. The DAG will POST to `/api/benchmarks/run` for each scenario on its schedule.

---

## Reading the leaderboard

The leaderboard endpoint aggregates all stored runs by `(framework, scenario)`
pair and returns:

| Field               | Description                                         |
|---------------------|-----------------------------------------------------|
| `framework`         | Adapter name (e.g. `litellm`, `langchain`)          |
| `scenario`          | Scenario key (e.g. `rag`, `codegen`)                |
| `avg_quality_score` | Mean quality score across all runs (0.0 – 1.0)      |
| `avg_latency_ms`    | Mean wall-clock invocation time in milliseconds      |
| `avg_token_cost`    | Mean estimated USD cost per invocation               |
| `num_runs`          | Total number of individual runs included             |

Rows are sorted by `avg_quality_score` descending.

CLI output example:

```
#    FRAMEWORK      SCENARIO       AVG QUALITY    AVG LATENCY ms   AVG COST  RUNS
--------------------------------------------------------------------------------
1    litellm        rag                  0.8700           823.4   0.000410     3
2    langchain      rag                  0.8200           910.1   0.000390     3
3    litellm        codegen              0.6667           755.2   0.000310     3
```

---

## How benchmark scores influence routing

The `/api/benchmarks/recommendations` endpoint returns the best framework for
each scenario type:

```json
{
  "rag": "litellm",
  "codegen": "langchain",
  "research": "litellm",
  "data_analysis": "langchain"
}
```

The `AgentExecutor` can read this map to auto-select the adapter with the
highest historical quality score for the task type at hand. This is controlled
by the config key `orchestrator.adapter_selection_mode`:

- `"static"` (default) — always use the adapter in `orchestrator.adapter`.
- `"benchmark"` — consult the recommendations map and pick the best adapter
  per detected task category before invocation.

Change the mode without restarting the server:

```bash
agentctl config set orchestrator.adapter_selection_mode benchmark
```

---

## Extending scenarios

Create a subclass of `BenchmarkScenario` in
`KubeAI/benchmarks/scenarios/my_scenario.py`:

```python
from KubeAI.benchmarks.scenarios.base import BenchmarkScenario
from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter

class MySummaryScenario(BenchmarkScenario):

    @property
    def name(self) -> str:
        return "summary"

    def prepare(self):
        return {
            "document": "KubeAI is a Kubernetes-inspired runtime for AI agents.",
            "expected_keywords": ["kubernetes", "runtime", "agents"],
        }

    def execute(self, adapter: OrchestrationAdapter, setup) -> AdapterResult:
        return adapter.invoke(
            task=f"Summarise this document: {setup['document']}",
            system_prompt="Be concise.",
            model_id="claude-haiku-4-5-20251001",
        )

    def evaluate(self, result: AdapterResult, setup) -> float:
        text = result.text.lower()
        keywords = setup["expected_keywords"]
        return sum(1 for kw in keywords if kw in text) / len(keywords)
```

Then register it in the API router's `_get_scenario_registry()` function in
`KubeAI/dashboard/api/benchmarks.py`.
