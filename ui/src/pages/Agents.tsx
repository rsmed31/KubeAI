import { Fragment, useEffect, useState } from 'react'
import { Agent, DashboardState } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { api } from '../api/client'

interface Props {
  state: DashboardState
}

export function Agents({ state }: Props) {
  const [agents, setAgents] = useState<Agent[]>(state.agents)
  const [terminating, setTerminating] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null)

  useEffect(() => {
    setAgents(state.agents)
  }, [state.agents])

  useEffect(() => {
    void api
      .getAgents()
      .then((data) => setAgents(data as Agent[]))
      .catch(() => {
        // Keep websocket-fed state if fetch fails.
      })
  }, [])

  async function handleTerminate(agentId: string) {
    setTerminating(agentId)
    setError(null)
    try {
      await api.terminateAgent(agentId)
      setAgents((current) => current.map((agent) => (
        agent.id === agentId ? { ...agent, state: 'TERMINATED', healthy: false } : agent
      )))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to terminate agent')
    } finally {
      setTerminating(null)
    }
  }

  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-bold text-slate-100">Agents</h2>

      {error && (
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
        {agents.length === 0 ? (
          <p className="p-6 text-slate-500 text-sm">No agents running.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Agent ID</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Blueprint</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">State</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Model</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Tier</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Load</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Healthy</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <Fragment key={agent.id}>
                  <tr
                    className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                    onClick={() => setExpandedAgentId((current) => (current === agent.id ? null : agent.id))}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-slate-300">
                      {agent.id.slice(0, 12)}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{agent.blueprint}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={agent.state} />
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{agent.model_id}</td>
                    <td className="px-4 py-3 text-slate-400">{agent.tier}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-slate-700 rounded-full h-1.5 w-20">
                          <div
                            className="bg-cyan-500 h-1.5 rounded-full"
                            style={{ width: `${Math.min(100, agent.load)}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-400">{Math.round(agent.load)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={agent.healthy ? 'healthy' : 'unhealthy'} />
                    </td>
                    <td className="px-4 py-3" onClick={(event) => event.stopPropagation()}>
                      <button
                        onClick={() => handleTerminate(agent.id)}
                        disabled={terminating === agent.id || agent.state === 'TERMINATED'}
                        className="px-2 py-1 rounded text-xs bg-red-900/50 text-red-300 hover:bg-red-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {terminating === agent.id ? 'Terminating…' : 'Terminate'}
                      </button>
                    </td>
                  </tr>
                  {expandedAgentId === agent.id ? (
                    <tr className="bg-slate-900/60 border-b border-slate-700/50">
                      <td colSpan={8} className="px-5 py-4">
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-sm">
                          <div>
                            <p className="text-xs text-slate-500 mb-2">Connected Tools (MCP)</p>
                            {agent.mcp_servers?.length ? (
                              <div className="flex flex-wrap gap-1">
                                {agent.mcp_servers.map((server) => (
                                  <span key={server} className="px-2 py-0.5 rounded text-xs bg-cyan-900/50 text-cyan-300">{server}</span>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400">No MCP servers attached.</p>
                            )}
                          </div>

                          <div>
                            <p className="text-xs text-slate-500 mb-2">Memory</p>
                            <p className="text-slate-300">Enabled: {agent.memory?.enabled ? 'yes' : 'no'}</p>
                            <p className="text-slate-400 text-xs">Namespace: {agent.memory?.namespace ?? agent.id}</p>
                          </div>

                          <div>
                            <p className="text-xs text-slate-500 mb-2">Metrics</p>
                            <div className="space-y-1 text-slate-300">
                              <p>Total tasks: {agent.metrics?.tasks_total ?? 0}</p>
                              <p>Success: {agent.metrics?.tasks_success ?? 0}</p>
                              <p>Failed: {agent.metrics?.tasks_failed ?? 0}</p>
                              <p>Avg latency: {Math.round(agent.metrics?.avg_latency_ms ?? 0)} ms</p>
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
