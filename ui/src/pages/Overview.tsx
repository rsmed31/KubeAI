import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { DashboardState } from '../types'
import { MetricsCard } from '../components/MetricsCard'
import { StatusBadge } from '../components/StatusBadge'

interface Props {
  state: DashboardState
}

export function Overview({ state }: Props) {
  const { agents, tasks, metrics, pool_models, clusters } = state
  const [scope, setScope] = useState('all')
  const [scopedAgents, setScopedAgents] = useState<typeof agents>(agents)
  const [scopedTasks, setScopedTasks] = useState<typeof tasks>(tasks)

  const clusterNames = useMemo(
    () => (clusters ?? []).map((cluster) => cluster.name),
    [clusters]
  )

  useEffect(() => {
    if (scope === 'all') {
      setScopedAgents(agents)
      setScopedTasks(tasks)
      return
    }

    void Promise.all([
      api.getClusterAgents(scope),
      api.getClusterTasks(scope, 200),
    ])
      .then(([clusterAgents, clusterTasks]) => {
        setScopedAgents(clusterAgents as typeof agents)
        setScopedTasks(clusterTasks as typeof tasks)
      })
      .catch(() => {
        setScopedAgents([])
        setScopedTasks([])
      })
  }, [scope, agents, tasks])

  const activeAgents = scopedAgents.filter((a) => a.state === 'RUNNING').length
  const totalTasks = scope === 'all' ? (metrics.tasks_total ?? scopedTasks.length) : scopedTasks.length
  const successTasks =
    scope === 'all'
      ? (metrics.tasks_success ?? scopedTasks.filter((t) => t.status === 'SUCCESS').length)
      : scopedTasks.filter((t) => t.status === 'SUCCESS').length

  const completedTasks = scopedTasks.filter((t) => t.latency_ms !== null && t.latency_ms !== undefined)
  const avgLatency =
    completedTasks.length > 0
      ? Math.round(
          completedTasks.reduce((sum, t) => sum + (t.latency_ms ?? 0), 0) /
            completedTasks.length
        )
      : 0

  const recentTasks = [...scopedTasks].slice(-10).reverse()

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-2xl font-bold text-slate-100">Overview</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 uppercase tracking-wide">Scope</span>
          <button
            className={`px-2.5 py-1 rounded text-xs ${scope === 'all' ? 'bg-cyan-700 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`}
            onClick={() => setScope('all')}
          >
            All clusters
          </button>
          {clusterNames.map((name) => (
            <button
              key={name}
              className={`px-2.5 py-1 rounded text-xs ${scope === name ? 'bg-cyan-700 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`}
              onClick={() => setScope(name)}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      {scopedAgents.length === 0 && pool_models.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 text-sm text-slate-300">
          <p className="font-semibold text-slate-100 mb-1">Clean start detected</p>
          <p className="text-slate-400">
            No models and no agents are registered yet. Register a model in Pools, then submit a task.
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricsCard label="Active Agents" value={activeAgents} sub={`${scopedAgents.length} total`} />
        <MetricsCard
          label="Tasks"
          value={`${successTasks} / ${totalTasks}`}
          sub="success / total"
        />
        <MetricsCard
          label="Avg Latency"
          value={avgLatency > 0 ? `${avgLatency} ms` : '—'}
          sub="completed tasks"
        />
        <MetricsCard
          label="Failed Tasks"
          value={scope === 'all' ? (metrics.tasks_failed ?? scopedTasks.filter((t) => t.status === 'FAILED').length) : scopedTasks.filter((t) => t.status === 'FAILED').length}
          sub="total failures"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="bg-slate-800 border border-slate-700 rounded-lg">
          <div className="px-4 py-3 border-b border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300">Agents</h3>
          </div>
          {scopedAgents.length === 0 ? (
            <p className="p-4 text-slate-500 text-sm">No agents running.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="px-4 py-2 text-left text-slate-400 font-medium">ID</th>
                    <th className="px-4 py-2 text-left text-slate-400 font-medium">Blueprint</th>
                    <th className="px-4 py-2 text-left text-slate-400 font-medium">State</th>
                    <th className="px-4 py-2 text-left text-slate-400 font-medium">Model</th>
                  </tr>
                </thead>
                <tbody>
                  {scopedAgents.map((agent) => (
                    <tr
                      key={agent.id}
                      className="border-b border-slate-700/50 hover:bg-slate-700/30"
                    >
                      <td className="px-4 py-2 font-mono text-xs text-slate-300">
                        {agent.id.slice(0, 8)}
                      </td>
                      <td className="px-4 py-2 text-slate-300">{agent.blueprint}</td>
                      <td className="px-4 py-2">
                        <StatusBadge status={agent.state} />
                      </td>
                      <td className="px-4 py-2 text-slate-400 text-xs">{agent.model_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg">
          <div className="px-4 py-3 border-b border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300">Recent Tasks</h3>
          </div>
          {recentTasks.length === 0 ? (
            <p className="p-4 text-slate-500 text-sm">No tasks yet.</p>
          ) : (
            <ul className="divide-y divide-slate-700/50">
              {recentTasks.map((task) => (
                <li key={task.id} className="px-4 py-3 hover:bg-slate-700/30">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm text-slate-300 truncate flex-1">{task.description}</p>
                    <StatusBadge status={task.status} />
                  </div>
                  <div className="flex gap-3 mt-1 text-xs text-slate-500">
                    <span>{task.blueprint}</span>
                    {task.latency_ms !== null && (
                      <span>{Math.round(task.latency_ms)} ms</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
