# KubeAI Config

`ConfigStore` is a PostgreSQL-backed configuration service with an in-memory
cache and hot-reload. It works without a database (all defaults are in-process)
and upgrades to live persistence when a PostgreSQL DSN is provided.

Source: `KubeAI/config/store.py`

---

## Key format

All config keys follow the `category.key_name` convention:

```
rag.default_template
orchestrator.min_confidence
```

This makes grouped listing (`agentctl config list`) readable and allows
category-scoped queries via the API.

---

## Config categories

| Category       | Description                                     |
|----------------|-------------------------------------------------|
| `rag`          | RAG pipeline: embedding, chunking, vector store |
| `llm`          | LLM pool: model selection, cost ceilings        |
| `mcp`          | MCP server endpoint overrides                   |
| `blueprint`    | Agent blueprint configuration                   |
| `skill`        | Skill and workflow configuration                |
| `orchestrator` | Routing thresholds, adapter selection           |
| `general`      | Catch-all for system-level settings             |

---

## Default config keys

### RAG (`rag.*`)

| Key                       | Default                                          | Description                               |
|---------------------------|--------------------------------------------------|-------------------------------------------|
| `rag.default_template`    | `"basic"`                                        | Default RAG template at agent spawn       |
| `rag.embedding_provider`  | `"fastembed"`                                    | Embedding backend (`fastembed`, `openai`) |
| `rag.chunking_strategy`   | `{"chunk_size": 500, "overlap": 50}`             | Document chunking parameters              |
| `rag.vector_store_backend`| `"in_memory"`                                    | Vector store (`in_memory`, `chroma`, `qdrant`) |
| `rag.reranker_model`      | `"cross-encoder/ms-marco-MiniLM-L-6-v2"`         | Cross-encoder reranker model              |
| `rag.indexing_model`      | `"fastembed"`                                    | Model used to index documents             |

### Orchestrator (`orchestrator.*`)

| Key                                  | Default  | Description                                          |
|--------------------------------------|----------|------------------------------------------------------|
| `orchestrator.min_confidence`        | `0.3`    | Minimum routing confidence to accept a route         |
| `orchestrator.routing_model_override`| `null`   | Force a specific routing model (null = use largest)  |
| `orchestrator.auto_decompose`        | `true`   | Auto-decompose complex tasks via the decomposer      |
| `orchestrator.adapter`               | `"litellm"` | Active framework adapter name                     |
| `orchestrator.adapter_selection_mode`| `"static"` | `"static"` or `"benchmark"` (auto from leaderboard) |

---

## CLI usage

```bash
# Get a single value
agentctl config get rag.default_template

# Set a value (JSON-parsed automatically)
agentctl config set rag.default_template reranking
agentctl config set orchestrator.min_confidence 0.5
agentctl config set rag.chunking_strategy '{"chunk_size": 800, "overlap": 100}'

# List all config grouped by category
agentctl config list
```

---

## REST API endpoints

All endpoints are mounted at `/api/config`.

| Method   | Path                | Description                           |
|----------|---------------------|---------------------------------------|
| `GET`    | `/api/config`       | All config entries grouped by category|
| `GET`    | `/api/config/{key}` | Single key value                      |
| `PUT`    | `/api/config/{key}` | Update a key                          |
| `DELETE` | `/api/config/{key}` | Remove a key                          |

### PUT request body

```json
{
  "value": "reranking",
  "category": "rag",
  "description": "Use reranking template by default"
}
```

`category` and `description` are optional on update — existing values are
preserved if omitted.

### Example

```bash
curl -X PUT http://localhost:8080/api/config/rag.default_template \
  -H "Content-Type: application/json" \
  -d '{"value": "hybrid"}'
```

---

## Hot-reload behavior

When a PostgreSQL DSN is set (via the `POSTGRES_DSN` environment variable or
passed directly to `ConfigStore`), the store:

1. Loads all rows from the `config_store` table on startup, overriding in-memory
   defaults with database values.
2. Starts a background thread (`config-watcher`) that polls the database every
   `poll_interval` seconds (default: 2 s).
3. Fires registered change callbacks for any key whose value changed since the
   last poll.

Components that depend on a config key should register a callback:

```python
config_store.on_change(lambda key, old, new: reload_if_needed(key, new))
```

Without a PostgreSQL DSN the store operates entirely in-process. Changes made
via the API survive for the lifetime of the server process only — they are lost
on restart.

---

## PostgreSQL schema

The `infra/postgres/init.sql` file creates the required table on first startup:

```sql
CREATE TABLE IF NOT EXISTS config_store (
    config_key   TEXT PRIMARY KEY,
    config_value JSONB NOT NULL,
    category     TEXT NOT NULL DEFAULT 'general',
    description  TEXT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by   TEXT NOT NULL DEFAULT 'system'
);
```

---

## Environment variables

| Variable       | Purpose                                      | Example                               |
|----------------|----------------------------------------------|---------------------------------------|
| `POSTGRES_DSN` | Full PostgreSQL DSN for config persistence   | `postgresql://kubeai:pw@localhost/kubeai` |
| `KUBEAI_API_URL` | Base URL for CLI commands that call the API | `http://localhost:8080`              |
