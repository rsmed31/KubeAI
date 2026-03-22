-- KubeAI PostgreSQL Schema
-- Tables for framework registry, benchmark results, config store, and skills

-- ── Framework adapter registry ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS framework_registry (
    framework_id   TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    enabled        BOOLEAN DEFAULT TRUE,
    config_json    JSONB DEFAULT '{}',
    updated_at     TIMESTAMP DEFAULT NOW()
);

-- Seed default frameworks
INSERT INTO framework_registry (framework_id, display_name, enabled) VALUES
    ('litellm',     'LiteLLM (Native)',  TRUE),
    ('langchain',   'LangChain',         TRUE),
    ('llamaindex',  'LlamaIndex',        TRUE),
    ('autogen',     'AutoGen',           TRUE),
    ('crewai',      'CrewAI',            TRUE)
ON CONFLICT (framework_id) DO NOTHING;

-- ── Benchmark runs (one per DAG execution) ─────────────────────────────
CREATE TABLE IF NOT EXISTS benchmark_runs (
    run_id         TEXT PRIMARY KEY,
    started_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at    TIMESTAMP,
    status         TEXT DEFAULT 'running'
                   CHECK (status IN ('running', 'completed', 'failed')),
    scenario       TEXT NOT NULL
                   CHECK (scenario IN ('rag', 'codegen', 'research', 'data_analysis')),
    framework_id   TEXT REFERENCES framework_registry(framework_id),
    config_json    JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_benchmark_runs_status ON benchmark_runs(status);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_scenario ON benchmark_runs(scenario);

-- ── Benchmark results (individual measurements) ────────────────────────
CREATE TABLE IF NOT EXISTS benchmark_results (
    result_id      SERIAL PRIMARY KEY,
    run_id         TEXT REFERENCES benchmark_runs(run_id) ON DELETE CASCADE,
    framework_id   TEXT REFERENCES framework_registry(framework_id),
    scenario       TEXT NOT NULL
                   CHECK (scenario IN ('rag', 'codegen', 'research', 'data_analysis')),
    quality_score  REAL CHECK (quality_score >= 0 AND quality_score <= 1),
    latency_ms     REAL CHECK (latency_ms >= 0),
    token_cost     REAL CHECK (token_cost >= 0),
    token_usage    JSONB DEFAULT '{}',
    output_text    TEXT,
    metadata       JSONB DEFAULT '{}',
    recorded_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_benchmark_results_run ON benchmark_results(run_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_framework ON benchmark_results(framework_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_scenario ON benchmark_results(scenario);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_recorded ON benchmark_results(recorded_at DESC);

-- ── Hot-reloadable config store ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS config_store (
    config_key     TEXT PRIMARY KEY,
    config_value   JSONB NOT NULL,
    category       TEXT NOT NULL
                   CHECK (category IN ('rag', 'llm', 'mcp', 'blueprint', 'skill', 'orchestrator', 'general')),
    description    TEXT DEFAULT '',
    updated_at     TIMESTAMP DEFAULT NOW(),
    updated_by     TEXT DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_config_store_category ON config_store(category);
CREATE INDEX IF NOT EXISTS idx_config_store_updated ON config_store(updated_at);

-- Seed default config values
INSERT INTO config_store (config_key, config_value, category, description) VALUES
    ('rag.default_template',      '"basic"',                                          'rag',          'Default RAG template (basic, hybrid, reranking)'),
    ('rag.embedding_provider',    '"fastembed"',                                      'rag',          'Embedding provider (fastembed, openai, cohere)'),
    ('rag.chunking_strategy',     '{"chunk_size": 500, "overlap": 50}',              'rag',          'Document chunking configuration'),
    ('rag.vector_store_backend',  '"in_memory"',                                     'rag',          'Vector store backend (in_memory, chroma, qdrant)'),
    ('rag.reranker_model',        '"cross-encoder/ms-marco-MiniLM-L-6-v2"',          'rag',          'Cross-encoder model for reranking'),
    ('rag.indexing_model',        '"fastembed"',                                      'rag',          'Model used for document indexing'),
    ('orchestrator.min_confidence',       '0.3',                                      'orchestrator', 'Minimum routing confidence threshold'),
    ('orchestrator.routing_model_override', 'null',                                   'orchestrator', 'Override routing model (null = use largest)'),
    ('orchestrator.auto_decompose',       'true',                                     'orchestrator', 'Auto-decompose complex tasks')
ON CONFLICT (config_key) DO NOTHING;

-- ── Skills (MCP tools + system prompts + workflow templates) ───────────
CREATE TABLE IF NOT EXISTS skills (
    skill_id       TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    system_prompt  TEXT NOT NULL DEFAULT '',
    mcp_tools      JSONB DEFAULT '[]',
    workflow_steps JSONB DEFAULT '[]',
    tags           TEXT[] DEFAULT '{}',
    visibility     JSONB DEFAULT '{}',
    enabled        BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT NOW(),
    updated_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skills_enabled ON skills(enabled);
CREATE INDEX IF NOT EXISTS idx_skills_tags ON skills USING GIN(tags);

-- ── Leaderboard view for quick framework comparison ────────────────────
CREATE OR REPLACE VIEW benchmark_leaderboard AS
SELECT
    br.framework_id,
    br.scenario,
    COUNT(*)                          AS run_count,
    ROUND(AVG(br.quality_score)::numeric, 4)  AS avg_quality,
    ROUND(AVG(br.latency_ms)::numeric, 1)     AS avg_latency_ms,
    ROUND(AVG(br.token_cost)::numeric, 6)     AS avg_cost,
    ROUND(STDDEV(br.quality_score)::numeric, 4) AS quality_stddev,
    MAX(br.recorded_at)               AS last_run
FROM benchmark_results br
JOIN benchmark_runs r ON br.run_id = r.run_id
WHERE r.status = 'completed'
GROUP BY br.framework_id, br.scenario
ORDER BY br.scenario, avg_quality DESC;
