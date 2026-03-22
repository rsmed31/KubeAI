export interface Agent {
  id: string
  blueprint: string
  state: string
  model_id: string
  tier: string
  load: number
  healthy: boolean
  capabilities?: string[]
  mcp_servers: string[]
  memory?: {
    enabled: boolean
    namespace: string
  }
  metrics?: {
    tasks_total: number
    tasks_success: number
    tasks_failed: number
    avg_latency_ms: number
  }
  metadata?: Record<string, unknown>
}

export interface TaskStage {
  stage: string
  message?: string
  timestamp?: number
  [key: string]: unknown
}

export interface Task {
  id: string
  description: string
  status: string
  blueprint: string
  agent_id: string | null
  latency_ms: number | null
  result_text: string | null
  stages: TaskStage[]
}

export interface PoolModel {
  model_id: string
  provider: string
  tier: string
  load: number
  healthy: boolean
  cost_per_1k: number
  description?: string
  has_key: boolean
  base_url: string
}

export interface MCPServer {
  server_id: string
  endpoint: string
  capabilities: string[]
  healthy: boolean
  description: string
  transport?: string
  timeout_s?: number
  tags?: string[]
}

export interface Cluster {
  name: string
  status: string
  agents: { total: number; running: number; idle: number }
  tasks: { total: number; complete: number; queued: number }
  models: string[]
  blueprint_count: number
}

export interface ClusterStatus {
  name: string
  status: string
  agents: { total: number; running: number; idle: number }
  tasks: { total: number; queued: number; complete: number; failed: number }
  models: Array<{ model_id: string; tier: string; healthy: boolean; load: number }>
  mcps: Array<{ server_id: string; healthy: boolean; capabilities: string[] }>
  blueprints: Array<{ name: string; tier: string; description: string }>
}

export interface ProviderInfo {
  id: string
  name: string
  api_key_env: string | null
  has_key: boolean
  needs_base_url: boolean
  default_base_url: string
  is_local: boolean
  default_models: Record<string, string>
}

export interface PoolsSnapshot {
  models: Array<{
    model_id: string
    provider: string
    tier: string
    cost_per_1k: number
    load: number
    healthy: boolean
    description?: string
    is_local?: boolean
  }>
  mcps: Array<{
    server_id: string
    endpoint: string
    capabilities: string[]
    healthy: boolean
    description?: string
    transport?: string
    timeout_s?: number
    tags?: string[]
  }>
}

export interface OrchestratorConfig {
  routing_model_override: string | null
  effective_routing_model: string
  effective_routing_provider: string
  min_confidence: number
  decompose_enabled: boolean
  available_models: Array<{
    model_id: string
    provider: string
    tier: string
    healthy: boolean
    load: number
  }>
}

export interface RoutingDecision {
  task_id: string
  blueprint: string
  model_id: string
  provider: string
  confidence: number
  cost_hint: number
  latency_ms: number
  timestamp: number
}

export interface RouteTestResult {
  task: string
  routing_model: string
  winner: string | null
  scores: Array<{
    blueprint: string
    description: string
    tier: string
    score: number
  }>
}

export interface BlueprintRecord {
  name: string
  description: string
  tier: string
  version: string
  capabilities: string[]
  system_prompt?: string
}

export interface Metrics {
  tasks_total?: number
  tasks_success?: number
  tasks_failed?: number
  [key: string]: unknown
}

export interface DashboardState {
  agents: Agent[]
  tasks: Task[]
  metrics: Metrics
  pool_models: PoolModel[]
  pool_mcps: MCPServer[]
  clusters: Cluster[]
}
