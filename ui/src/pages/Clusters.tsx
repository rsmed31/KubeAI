import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { Cluster, ClusterStatus, DashboardState, Task } from '../types'
import { StatusBadge } from '../components/StatusBadge'

interface Props {
  state: DashboardState
}

export function Clusters({ state }: Props) {
  const [clusters, setClusters] = useState<Cluster[]>(state.clusters ?? [])
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedCluster, setSelectedCluster] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<'tasks' | 'agents' | 'pools'>('tasks')
  const [clusterStatus, setClusterStatus] = useState<ClusterStatus | null>(null)
  const [clusterAgents, setClusterAgents] = useState<Array<Record<string, unknown>>>([])
  const [clusterTasks, setClusterTasks] = useState<Task[]>([])
  const [quickTask, setQuickTask] = useState('')

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [workers, setWorkers] = useState(4)
  const [inheritModels, setInheritModels] = useState(true)
  const [inheritMcps, setInheritMcps] = useState(true)
  const [inheritBlueprints, setInheritBlueprints] = useState(true)

  const selected = useMemo(
    () => clusters.find((cluster) => cluster.name === selectedCluster) ?? null,
    [clusters, selectedCluster]
  )

  async function refreshClusters() {
    try {
      const data = (await api.getClusters()) as Cluster[]
      setClusters(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load clusters')
    }
  }

  async function loadClusterDetail(clusterName: string) {
    try {
      const [status, agents, tasks] = await Promise.all([
        api.getClusterStatus(clusterName) as Promise<ClusterStatus>,
        api.getClusterAgents(clusterName) as Promise<Array<Record<string, unknown>>>,
        api.getClusterTasks(clusterName) as Promise<Task[]>,
      ])
      setClusterStatus(status)
      setClusterAgents(agents)
      setClusterTasks(tasks)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load cluster detail')
    }
  }

  useEffect(() => {
    setClusters(state.clusters ?? [])
  }, [state.clusters])

  useEffect(() => {
    void refreshClusters()
  }, [])

  useEffect(() => {
    if (!selectedCluster) {
      return
    }
    void loadClusterDetail(selectedCluster)
  }, [selectedCluster])

  async function handleCreateCluster() {
    if (!name.trim()) {
      setError('Cluster name is required')
      return
    }
    setCreating(true)
    setError(null)
    try {
      await api.createCluster({
        name: name.trim(),
        description: description.trim(),
        num_workers: workers,
        inherit_models: inheritModels,
        inherit_mcps: inheritMcps,
        inherit_blueprints: inheritBlueprints,
      })
      setShowCreate(false)
      setName('')
      setDescription('')
      setWorkers(4)
      await refreshClusters()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create cluster')
    } finally {
      setCreating(false)
    }
  }

  async function handleDeleteCluster(clusterName: string) {
    const confirmed = window.confirm(`Delete cluster "${clusterName}"?`)
    if (!confirmed) {
      return
    }
    setError(null)
    try {
      await api.deleteCluster(clusterName)
      if (selectedCluster === clusterName) {
        setSelectedCluster(null)
        setClusterStatus(null)
        setClusterAgents([])
        setClusterTasks([])
      }
      await refreshClusters()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete cluster')
    }
  }

  async function handleQuickSubmit() {
    if (!selectedCluster || !quickTask.trim()) {
      return
    }
    const formData = new FormData()
    formData.append('description', quickTask.trim())
    try {
      await api.submitClusterTask(selectedCluster, formData)
      setQuickTask('')
      await loadClusterDetail(selectedCluster)
      await refreshClusters()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit task')
    }
  }

  if (selectedCluster && selected) {
    return (
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <button
              className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm"
              onClick={() => setSelectedCluster(null)}
            >
              Back
            </button>
            <h2 className="text-2xl font-bold text-slate-100">Cluster: {selected.name}</h2>
            {selected.name === 'default' ? (
              <span className="px-2 py-0.5 rounded text-xs bg-cyan-900/60 text-cyan-300">default</span>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <input
              className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100 w-72"
              placeholder="Quick task for this cluster"
              value={quickTask}
              onChange={(event) => setQuickTask(event.target.value)}
            />
            <button
              className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-sm text-white"
              onClick={() => void handleQuickSubmit()}
            >
              Submit
            </button>
          </div>
        </div>

        {error ? (
          <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="bg-slate-800 border border-slate-700 rounded p-3">
            <div className="text-xs text-slate-500">Agents</div>
            <div className="text-2xl font-bold text-slate-100">{clusterStatus?.agents.total ?? 0}</div>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded p-3">
            <div className="text-xs text-slate-500">Tasks</div>
            <div className="text-2xl font-bold text-slate-100">{clusterStatus?.tasks.total ?? 0}</div>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded p-3">
            <div className="text-xs text-slate-500">Models</div>
            <div className="text-2xl font-bold text-slate-100">{clusterStatus?.models.length ?? 0}</div>
          </div>
          <div className="bg-slate-800 border border-slate-700 rounded p-3">
            <div className="text-xs text-slate-500">MCP Servers</div>
            <div className="text-2xl font-bold text-slate-100">{clusterStatus?.mcps.length ?? 0}</div>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setDetailTab('tasks')}
            className={`px-3 py-1.5 rounded text-sm ${detailTab === 'tasks' ? 'bg-cyan-700 text-white' : 'bg-slate-800 text-slate-300 border border-slate-700'}`}
          >
            Tasks
          </button>
          <button
            onClick={() => setDetailTab('agents')}
            className={`px-3 py-1.5 rounded text-sm ${detailTab === 'agents' ? 'bg-cyan-700 text-white' : 'bg-slate-800 text-slate-300 border border-slate-700'}`}
          >
            Agents
          </button>
          <button
            onClick={() => setDetailTab('pools')}
            className={`px-3 py-1.5 rounded text-sm ${detailTab === 'pools' ? 'bg-cyan-700 text-white' : 'bg-slate-800 text-slate-300 border border-slate-700'}`}
          >
            Pools
          </button>
        </div>

        {detailTab === 'tasks' ? (
          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="px-4 py-2 text-left text-slate-400">ID</th>
                  <th className="px-4 py-2 text-left text-slate-400">Description</th>
                  <th className="px-4 py-2 text-left text-slate-400">Status</th>
                  <th className="px-4 py-2 text-left text-slate-400">Blueprint</th>
                </tr>
              </thead>
              <tbody>
                {clusterTasks.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-slate-500 text-center">No tasks</td>
                  </tr>
                ) : (
                  clusterTasks.map((task) => (
                    <tr key={task.id} className="border-b border-slate-700/40">
                      <td className="px-4 py-2 text-xs font-mono text-slate-300">{task.id}</td>
                      <td className="px-4 py-2 text-slate-300">{task.description}</td>
                      <td className="px-4 py-2"><StatusBadge status={task.status} /></td>
                      <td className="px-4 py-2 text-slate-400">{task.blueprint}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        {detailTab === 'agents' ? (
          <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="px-4 py-2 text-left text-slate-400">ID</th>
                  <th className="px-4 py-2 text-left text-slate-400">Blueprint</th>
                  <th className="px-4 py-2 text-left text-slate-400">State</th>
                  <th className="px-4 py-2 text-left text-slate-400">Model</th>
                </tr>
              </thead>
              <tbody>
                {clusterAgents.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-slate-500 text-center">No agents</td>
                  </tr>
                ) : (
                  clusterAgents.map((agent) => (
                    <tr key={String(agent.id)} className="border-b border-slate-700/40">
                      <td className="px-4 py-2 text-xs font-mono text-slate-300">{String(agent.id ?? '—')}</td>
                      <td className="px-4 py-2 text-slate-300">{String(agent.blueprint ?? '—')}</td>
                      <td className="px-4 py-2"><StatusBadge status={String(agent.state ?? 'unknown')} /></td>
                      <td className="px-4 py-2 text-slate-400 text-xs">{String(agent.model_id ?? '—')}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ) : null}

        {detailTab === 'pools' ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-slate-200 mb-3">Models</h3>
              {(clusterStatus?.models.length ?? 0) === 0 ? (
                <p className="text-sm text-slate-500">No models.</p>
              ) : (
                <ul className="space-y-2">
                  {clusterStatus?.models.map((model) => (
                    <li key={model.model_id} className="text-sm text-slate-300 flex items-center justify-between">
                      <span className="font-mono text-xs text-cyan-300">{model.model_id}</span>
                      <span className="text-xs text-slate-400">{model.tier}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-slate-200 mb-3">MCP Servers</h3>
              {(clusterStatus?.mcps.length ?? 0) === 0 ? (
                <p className="text-sm text-slate-500">No MCP servers.</p>
              ) : (
                <ul className="space-y-2">
                  {clusterStatus?.mcps.map((mcp) => (
                    <li key={mcp.server_id} className="text-sm text-slate-300 flex items-center justify-between">
                      <span className="font-mono text-xs text-cyan-300">{mcp.server_id}</span>
                      <span className="text-xs text-slate-400">{mcp.capabilities.length} caps</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-slate-100">Clusters</h2>
        <button
          className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm"
          onClick={() => setShowCreate((current) => !current)}
        >
          {showCreate ? 'Close' : 'New Cluster'}
        </button>
      </div>

      {showCreate ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
              placeholder="Cluster name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <input
              className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
              placeholder="Description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
            <input
              className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
              type="number"
              min={1}
              value={workers}
              onChange={(event) => setWorkers(Number(event.target.value))}
            />
          </div>

          <div className="flex flex-wrap gap-3 text-sm text-slate-300">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={inheritModels} onChange={(event) => setInheritModels(event.target.checked)} />
              Inherit models
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={inheritMcps} onChange={(event) => setInheritMcps(event.target.checked)} />
              Inherit MCPs
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={inheritBlueprints} onChange={(event) => setInheritBlueprints(event.target.checked)} />
              Inherit blueprints
            </label>
          </div>

          <button
            className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-sm text-white disabled:opacity-50"
            disabled={creating}
            onClick={() => void handleCreateCluster()}
          >
            {creating ? 'Creating...' : 'Create Cluster'}
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {clusters.length === 0 ? (
        <p className="text-slate-500 text-sm">No clusters registered.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {clusters.map((cluster) => (
            <div
              key={cluster.name}
              className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-4"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-100">{cluster.name}</h3>
                <StatusBadge status={cluster.status} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-900/50 rounded p-3">
                  <div className="text-xs text-slate-500 mb-1">Agents</div>
                  <div className="text-xl font-bold text-slate-100">{cluster.agents.total}</div>
                  <div className="text-xs text-slate-400 mt-1 space-y-0.5">
                    <div className="flex justify-between">
                      <span>Running</span>
                      <span className="text-green-400">{cluster.agents.running}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Idle</span>
                      <span className="text-slate-300">{cluster.agents.idle}</span>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-900/50 rounded p-3">
                  <div className="text-xs text-slate-500 mb-1">Tasks</div>
                  <div className="text-xl font-bold text-slate-100">{cluster.tasks.total}</div>
                  <div className="text-xs text-slate-400 mt-1 space-y-0.5">
                    <div className="flex justify-between">
                      <span>Complete</span>
                      <span className="text-green-400">{cluster.tasks.complete}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Queued</span>
                      <span className="text-yellow-400">{cluster.tasks.queued}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <div className="text-xs text-slate-500 mb-1">
                  Blueprints: {cluster.blueprint_count}
                </div>
                {cluster.models.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-500 mb-1">Models</div>
                    <div className="flex flex-wrap gap-1">
                      {cluster.models.map((model) => (
                        <span
                          key={model}
                          className="px-1.5 py-0.5 rounded text-xs bg-cyan-900/50 text-cyan-300"
                        >
                          {model}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between gap-2 pt-1">
                <button
                  className="px-2.5 py-1 rounded bg-slate-700 text-slate-200 text-xs hover:bg-slate-600"
                  onClick={() => setSelectedCluster(cluster.name)}
                >
                  Manage
                </button>
                {cluster.name !== 'default' ? (
                  <button
                    className="px-2.5 py-1 rounded bg-red-900/50 text-red-300 text-xs hover:bg-red-900"
                    onClick={() => void handleDeleteCluster(cluster.name)}
                  >
                    Delete
                  </button>
                ) : (
                  <span className="text-xs text-slate-500">Protected</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
