const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  const hasBody = options?.body !== undefined && options?.body !== null
  const isFormData = typeof FormData !== 'undefined' && options?.body instanceof FormData

  if (hasBody && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  getOverview: () => request('/overview'),
  getAgents: () => request('/agents'),
  getTasks: () => request('/tasks'),

  submitTask: (description: string, blueprint?: string) =>
    request('/tasks/submit', {
      method: 'POST',
      body: JSON.stringify({ description, blueprint }),
    }),

  submitTaskWithData: (formData: FormData) =>
    request('/tasks/submit-with-data', {
      method: 'POST',
      body: formData,
    }),

  getMemory: (domain = 'default') => request(`/memory/${domain}`),

  getBlueprints: () => request('/blueprints'),
  generateBlueprint: (description: string) =>
    request('/blueprints/generate', {
      method: 'POST',
      body: JSON.stringify({ description }),
    }),
  registerBlueprint: (body: {
    name: string
    description: string
    tier?: string
    version?: string
    capabilities?: string[]
  }) =>
    request('/blueprints/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getClusters: () => request('/clusters'),
  createCluster: (body: {
    name: string
    description?: string
    num_workers?: number
    inherit_models?: boolean
    inherit_mcps?: boolean
    inherit_blueprints?: boolean
  }) =>
    request('/clusters', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteCluster: (name: string) => request(`/clusters/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  getClusterStatus: (name: string) => request(`/clusters/${encodeURIComponent(name)}/status`),
  getClusterAgents: (name: string) => request(`/clusters/${encodeURIComponent(name)}/agents`),
  getClusterTasks: (name: string, limit = 100) =>
    request(`/clusters/${encodeURIComponent(name)}/tasks?limit=${limit}`),
  submitClusterTask: (name: string, formData: FormData) =>
    request(`/clusters/${encodeURIComponent(name)}/tasks`, {
      method: 'POST',
      body: formData,
    }),

  getProviders: () => request('/providers'),
  getPools: () => request('/pools'),
  registerModel: (body: {
    model_id: string
    provider: string
    tier?: string
    cost_per_1k_tokens?: number
    description?: string
    is_local?: boolean
    api_key?: string
    base_url?: string
  }) =>
    request('/pools/models', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  removeModel: (modelId: string) => request(`/pools/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' }),
  registerMCP: (body: {
    server_id: string
    endpoint: string
    capabilities: string[]
    description?: string
    transport?: string
    timeout_s?: number
    tags?: string[]
    auth_headers?: Record<string, string>
  }) =>
    request('/pools/mcps', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  removeMCP: (serverId: string) => request(`/pools/mcps/${encodeURIComponent(serverId)}`, { method: 'DELETE' }),

  getOrchestrator: () => request('/orchestrator'),
  updateOrchestrator: (body: {
    routing_model_override?: string | null
    min_confidence?: number | null
    decompose_enabled?: boolean | null
  }) =>
    request('/orchestrator', {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  testRoute: (task: string, blueprint?: string) =>
    request('/orchestrator/test', {
      method: 'POST',
      body: JSON.stringify({ task, blueprint }),
    }),
  getRoutingDecisions: (limit = 100) => request(`/orchestrator/decisions?limit=${limit}`),

  terminateAgent: (agentId: string) =>
    request(`/agents/${encodeURIComponent(agentId)}/terminate`, { method: 'POST' }),

  getConfig: () => request('/config'),
  setConfig: (key: string, value: unknown) =>
    request(`/config/${key}`, { method: 'PUT', body: JSON.stringify({ value }) }),

  getSkills: () => request('/skills'),
  createSkill: (skill: unknown) =>
    request('/skills', { method: 'POST', body: JSON.stringify(skill) }),
  updateSkill: (id: string, skill: unknown) =>
    request(`/skills/${id}`, { method: 'PUT', body: JSON.stringify(skill) }),
  deleteSkill: (id: string) =>
    request(`/skills/${id}`, { method: 'DELETE' }),

  getBenchmarkRuns: () => request('/benchmarks/runs'),
  triggerBenchmark: (scenario: string, framework: string, num_runs = 3) =>
    request('/benchmarks/run', {
      method: 'POST',
      body: JSON.stringify({ scenario, framework, num_runs }),
    }),
  getLeaderboard: () => request('/benchmarks/leaderboard'),
}
