import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { DashboardState, OrchestratorConfig, PoolModel, ProviderInfo, RouteTestResult, RoutingDecision } from '../types'
import { StatusBadge } from '../components/StatusBadge'

interface Props {
  state: DashboardState
}

export function Pools({ state }: Props) {
  const [tab, setTab] = useState<'models' | 'mcps' | 'orchestrator'>('models')
  const [models, setModels] = useState<PoolModel[]>(state.pool_models ?? [])
  const [mcps, setMcps] = useState(state.pool_mcps ?? [])
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [error, setError] = useState<string | null>(null)

  const [provider, setProvider] = useState('')
  const [modelId, setModelId] = useState('')
  const [tier, setTier] = useState('')
  const [modelDescription, setModelDescription] = useState('')
  const [cost, setCost] = useState(0.003)
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')

  const [serverId, setServerId] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [capabilities, setCapabilities] = useState('')
  const [mcpDescription, setMcpDescription] = useState('')
  const [mcpTransport, setMcpTransport] = useState('http')
  const [mcpTimeout, setMcpTimeout] = useState(15)
  const [mcpTags, setMcpTags] = useState('')
  const [mcpAuthHeaders, setMcpAuthHeaders] = useState('')

  const [orchConfig, setOrchConfig] = useState<OrchestratorConfig | null>(null)
  const [minConfidence, setMinConfidence] = useState(0)
  const [routingModelOverride, setRoutingModelOverride] = useState('')
  const [decomposeEnabled, setDecomposeEnabled] = useState(true)
  const [routingDecisions, setRoutingDecisions] = useState<RoutingDecision[]>([])
  const [testTask, setTestTask] = useState('')
  const [testResult, setTestResult] = useState<RouteTestResult | null>(null)

  const selectedProvider = useMemo(
    () => providers.find((entry) => entry.id === provider) ?? null,
    [provider, providers]
  )

  async function refreshPools() {
    try {
      const pools = (await api.getPools()) as {
        models: PoolModel[]
        mcps: typeof mcps
      }
      setModels(pools.models)
      setMcps(pools.mcps)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load pools')
    }
  }

  async function refreshOrchestrator() {
    try {
      const [cfg, decisions] = await Promise.all([
        api.getOrchestrator() as Promise<OrchestratorConfig>,
        api.getRoutingDecisions(100) as Promise<RoutingDecision[]>,
      ])
      setOrchConfig(cfg)
      setMinConfidence(cfg.min_confidence)
      setRoutingModelOverride(cfg.routing_model_override ?? '')
      setDecomposeEnabled(cfg.decompose_enabled)
      setRoutingDecisions(decisions)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load orchestrator state')
    }
  }

  useEffect(() => {
    setModels(state.pool_models ?? [])
    setMcps(state.pool_mcps ?? [])
  }, [state.pool_models, state.pool_mcps])

  useEffect(() => {
    void refreshPools()
    void api
      .getProviders()
      .then((data) => setProviders(data as ProviderInfo[]))
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'Failed to load providers')
      })
    void refreshOrchestrator()
  }, [])

  async function handleRegisterModel() {
    if (!provider || !modelId.trim()) {
      setError('Provider and model ID are required')
      return
    }
    setError(null)
    try {
      await api.registerModel({
        model_id: modelId.trim(),
        provider,
        tier: tier || undefined,
        cost_per_1k_tokens: cost,
        description: modelDescription.trim(),
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
      })
      setModelId('')
      setModelDescription('')
      setApiKey('')
      await refreshPools()
      await refreshOrchestrator()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to register model')
    }
  }

  async function handleRemoveModel(id: string) {
    const confirmed = window.confirm(`Remove model ${id}?`)
    if (!confirmed) {
      return
    }
    try {
      await api.removeModel(id)
      await refreshPools()
      await refreshOrchestrator()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove model')
    }
  }

  async function handleRegisterMcp() {
    if (!serverId.trim() || !endpoint.trim()) {
      setError('Server ID and endpoint are required')
      return
    }
    const parsedCaps = capabilities
      .split(',')
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0)
    try {
      let parsedHeaders: Record<string, string> = {}
      if (mcpAuthHeaders.trim()) {
        parsedHeaders = JSON.parse(mcpAuthHeaders)
      }
      await api.registerMCP({
        server_id: serverId.trim(),
        endpoint: endpoint.trim(),
        capabilities: parsedCaps,
        description: mcpDescription.trim(),
        transport: mcpTransport,
        timeout_s: mcpTimeout,
        tags: mcpTags.split(',').map((entry) => entry.trim()).filter((entry) => entry.length > 0),
        auth_headers: parsedHeaders,
      })
      setServerId('')
      setEndpoint('')
      setCapabilities('')
      setMcpDescription('')
      setMcpTransport('http')
      setMcpTimeout(15)
      setMcpTags('')
      setMcpAuthHeaders('')
      await refreshPools()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to register MCP server')
    }
  }

  async function handleRemoveMcp(id: string) {
    const confirmed = window.confirm(`Remove MCP server ${id}?`)
    if (!confirmed) {
      return
    }
    try {
      await api.removeMCP(id)
      await refreshPools()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove MCP server')
    }
  }

  async function handleApplyOrchestrator() {
    try {
      await api.updateOrchestrator({
        routing_model_override: routingModelOverride || null,
        min_confidence: minConfidence,
        decompose_enabled: decomposeEnabled,
      })
      await refreshOrchestrator()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update orchestrator config')
    }
  }

  async function handleTestRoute() {
    if (!testTask.trim()) {
      return
    }
    try {
      const result = (await api.testRoute(testTask.trim())) as RouteTestResult
      setTestResult(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to test route')
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-slate-100">Pools</h2>

      <div className="flex gap-2">
        <button className={`px-3 py-1.5 rounded text-sm ${tab === 'models' ? 'bg-cyan-700 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`} onClick={() => setTab('models')}>Models</button>
        <button className={`px-3 py-1.5 rounded text-sm ${tab === 'mcps' ? 'bg-cyan-700 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`} onClick={() => setTab('mcps')}>MCP Servers</button>
        <button className={`px-3 py-1.5 rounded text-sm ${tab === 'orchestrator' ? 'bg-cyan-700 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`} onClick={() => setTab('orchestrator')}>Orchestrator</button>
      </div>

      {error ? (
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {tab === 'models' ? (
        <section className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Register LLM Model</h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <select className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="">Select provider</option>
                {providers.map((entry) => (
                  <option key={entry.id} value={entry.id}>{entry.name}{entry.has_key ? ' ✓' : ''}</option>
                ))}
              </select>
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="Model ID" value={modelId} onChange={(event) => setModelId(event.target.value)} />
              <input
                className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
                placeholder="Model description (used by orchestrator)"
                value={modelDescription}
                onChange={(event) => setModelDescription(event.target.value)}
              />
              <select className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" value={tier} onChange={(event) => setTier(event.target.value)}>
                <option value="">auto (infer from description)</option>
                <option value="fast">fast (hint)</option>
                <option value="capable">capable (hint)</option>
                <option value="best">best (hint)</option>
              </select>
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" type="number" step={0.001} min={0} value={cost} onChange={(event) => setCost(Number(event.target.value))} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" type="password" placeholder="API key (optional if env is set)" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder={selectedProvider?.default_base_url || 'Base URL (optional)'} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
            </div>
            <button className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm" onClick={() => void handleRegisterModel()}>Register model</button>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            {models.length === 0 ? (
              <p className="p-4 text-slate-500 text-sm">No LLM models registered.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Model ID</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Provider</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Description</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Tier</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Load</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Healthy</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Cost / 1K</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((model) => (
                    <tr key={model.model_id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-mono text-xs text-cyan-400">{model.model_id}</td>
                      <td className="px-4 py-3 text-slate-300">{model.provider}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{model.description || '—'}</td>
                      <td className="px-4 py-3"><span className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">{model.tier}</span></td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{Math.round(model.load * 100)}%</td>
                      <td className="px-4 py-3"><StatusBadge status={model.healthy ? 'healthy' : 'unhealthy'} /></td>
                      <td className="px-4 py-3 text-slate-300">${model.cost_per_1k.toFixed(4)}</td>
                      <td className="px-4 py-3">
                        <button className="px-2 py-1 rounded text-xs bg-red-900/50 text-red-300 hover:bg-red-900" onClick={() => void handleRemoveModel(model.model_id)}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      ) : null}

      {tab === 'mcps' ? (
        <section className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Register MCP Server</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="Server ID" value={serverId} onChange={(event) => setServerId(event.target.value)} />
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="Endpoint URL" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="cap1, cap2" value={capabilities} onChange={(event) => setCapabilities(event.target.value)} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="Description" value={mcpDescription} onChange={(event) => setMcpDescription(event.target.value)} />
              <select className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" value={mcpTransport} onChange={(event) => setMcpTransport(event.target.value)}>
                <option value="http">http</option>
                <option value="stdio">stdio</option>
                <option value="websocket">websocket</option>
              </select>
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" type="number" min={1} step={1} placeholder="Timeout (s)" value={mcpTimeout} onChange={(event) => setMcpTimeout(Number(event.target.value))} />
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="tag1, tag2" value={mcpTags} onChange={(event) => setMcpTags(event.target.value)} />
            </div>
            <input
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100 font-mono"
              placeholder='Optional auth headers JSON, e.g. {"Authorization":"Bearer ..."}'
              value={mcpAuthHeaders}
              onChange={(event) => setMcpAuthHeaders(event.target.value)}
            />
            <button className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm" onClick={() => void handleRegisterMcp()}>Register MCP</button>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            {mcps.length === 0 ? (
              <p className="p-4 text-slate-500 text-sm">No MCP servers registered.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Server ID</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Endpoint</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Capabilities</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Healthy</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {mcps.map((mcp) => (
                    <tr key={mcp.server_id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-mono text-xs text-cyan-400">{mcp.server_id}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">{mcp.endpoint}</td>
                      <td className="px-4 py-3 text-slate-300 text-xs">{mcp.capabilities.join(', ') || '—'}</td>
                      <td className="px-4 py-3"><StatusBadge status={mcp.healthy ? 'healthy' : 'unhealthy'} /></td>
                      <td className="px-4 py-3">
                        <button className="px-2 py-1 rounded text-xs bg-red-900/50 text-red-300 hover:bg-red-900" onClick={() => void handleRemoveMcp(mcp.server_id)}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      ) : null}

      {tab === 'orchestrator' ? (
        <section className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Orchestrator Configuration</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <select className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" value={routingModelOverride} onChange={(event) => setRoutingModelOverride(event.target.value)}>
                <option value="">Auto-select largest model</option>
                {(orchConfig?.available_models ?? []).map((entry) => (
                  <option key={entry.model_id} value={entry.model_id}>{entry.model_id}</option>
                ))}
              </select>
              <input className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" type="number" min={0} max={1} step={0.05} value={minConfidence} onChange={(event) => setMinConfidence(Number(event.target.value))} />
              <label className="flex items-center gap-2 text-sm text-slate-300 px-3 py-2 bg-slate-900 border border-slate-700 rounded">
                <input type="checkbox" checked={decomposeEnabled} onChange={(event) => setDecomposeEnabled(event.target.checked)} />
                Decomposition
              </label>
              <button className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm" onClick={() => void handleApplyOrchestrator()}>Apply</button>
            </div>
            <div className="text-xs text-slate-400">
              Effective routing model: <span className="font-mono text-cyan-300">{orchConfig?.effective_routing_model ?? '—'}</span>
            </div>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Test Routing</h3>
            <div className="flex gap-2">
              <input className="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100" placeholder="Describe a task" value={testTask} onChange={(event) => setTestTask(event.target.value)} />
              <button className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm" onClick={() => void handleTestRoute()}>Test</button>
            </div>
            {testResult ? (
              <div className="bg-slate-900 border border-slate-700 rounded p-3">
                <p className="text-xs text-slate-500 mb-2">Winner: <span className="text-cyan-300">{testResult.winner ?? '—'}</span></p>
                <div className="space-y-1">
                  {testResult.scores.map((score) => (
                    <div key={score.blueprint} className="flex items-center justify-between text-sm">
                      <span className="text-slate-300">{score.blueprint}</span>
                      <span className="text-slate-400">{(score.score * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            {routingDecisions.length === 0 ? (
              <p className="p-4 text-slate-500 text-sm">No routing decisions recorded.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Task ID</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Blueprint</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Model</th>
                    <th className="px-4 py-3 text-left text-slate-400 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {[...routingDecisions].reverse().slice(0, 50).map((decision) => (
                    <tr key={`${decision.task_id}-${decision.timestamp}`} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="px-4 py-3 font-mono text-xs text-slate-300">{decision.task_id}</td>
                      <td className="px-4 py-3 text-slate-300">{decision.blueprint}</td>
                      <td className="px-4 py-3 font-mono text-xs text-cyan-400">{decision.model_id}</td>
                      <td className="px-4 py-3 text-slate-300">{(decision.confidence * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      ) : null}
    </div>
  )
}
