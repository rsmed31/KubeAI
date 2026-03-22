import { useState, useEffect } from 'react'
import { api } from '../api/client'

interface LeaderboardEntry {
  framework: string
  scenario: string
  quality_score: number
  latency_ms?: number
  runs?: number
}

type Leaderboard = LeaderboardEntry[] | Record<string, Record<string, number>>

const SCENARIOS = ['research', 'coding', 'writing', 'data_analysis', 'multi_agent']
const FRAMEWORKS = ['langchain', 'litellm', 'langgraph', 'custom']

export function Benchmarks() {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scenario, setScenario] = useState(SCENARIOS[0])
  const [framework, setFramework] = useState(FRAMEWORKS[0])
  const [numRuns, setNumRuns] = useState(3)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runSuccess, setRunSuccess] = useState(false)

  useEffect(() => {
    loadLeaderboard()
  }, [])

  function loadLeaderboard() {
    setLoading(true)
    setError(null)
    api
      .getLeaderboard()
      .then((data) => {
        const raw = data as Leaderboard
        if (Array.isArray(raw)) {
          setLeaderboard(raw)
        } else {
          const entries: LeaderboardEntry[] = []
          for (const [fw, scenarios] of Object.entries(raw)) {
            for (const [sc, score] of Object.entries(scenarios)) {
              entries.push({ framework: fw, scenario: sc, quality_score: score })
            }
          }
          setLeaderboard(entries)
        }
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'Failed to load leaderboard')
      )
      .finally(() => setLoading(false))
  }

  async function handleRunBenchmark() {
    setRunning(true)
    setRunError(null)
    setRunSuccess(false)
    try {
      await api.triggerBenchmark(scenario, framework, numRuns)
      setRunSuccess(true)
      setTimeout(() => {
        setRunSuccess(false)
        loadLeaderboard()
      }, 2000)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Benchmark failed')
    } finally {
      setRunning(false)
    }
  }

  const allFrameworks = [...new Set(leaderboard.map((e) => e.framework))]
  const allScenarios = [...new Set(leaderboard.map((e) => e.scenario))]

  function getScore(fw: string, sc: string): number | null {
    const entry = leaderboard.find((e) => e.framework === fw && e.scenario === sc)
    return entry ? entry.quality_score : null
  }

  function scoreColor(score: number | null): string {
    if (score === null) return 'text-slate-600'
    if (score >= 0.8) return 'text-green-400'
    if (score >= 0.6) return 'text-yellow-400'
    return 'text-red-400'
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-slate-100">Benchmarks</h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Run Benchmark</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Scenario</label>
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
            >
              {SCENARIOS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Framework</label>
            <select
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
            >
              {FRAMEWORKS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Runs</label>
            <input
              type="number"
              min={1}
              max={10}
              value={numRuns}
              onChange={(e) => setNumRuns(Number(e.target.value))}
              className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 w-20 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            onClick={handleRunBenchmark}
            disabled={running}
            className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm transition-colors"
          >
            {running ? 'Running…' : 'Run Benchmark'}
          </button>
        </div>
        {runError && (
          <p className="mt-2 text-sm text-red-400">{runError}</p>
        )}
        {runSuccess && (
          <p className="mt-2 text-sm text-green-400">Benchmark queued successfully.</p>
        )}
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-lg">
        <div className="px-4 py-3 border-b border-slate-700">
          <h3 className="text-sm font-semibold text-slate-300">Leaderboard</h3>
        </div>

        {loading && <p className="p-4 text-slate-400 text-sm">Loading leaderboard…</p>}

        {error && (
          <div className="p-4">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {!loading && !error && leaderboard.length === 0 && (
          <p className="p-4 text-slate-500 text-sm">No benchmark results yet.</p>
        )}

        {!loading && !error && leaderboard.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="px-4 py-3 text-left text-slate-400 font-medium">Framework</th>
                  {allScenarios.map((sc) => (
                    <th key={sc} className="px-4 py-3 text-left text-slate-400 font-medium">
                      {sc}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allFrameworks.map((fw) => (
                  <tr
                    key={fw}
                    className="border-b border-slate-700/50 hover:bg-slate-700/30"
                  >
                    <td className="px-4 py-3 font-medium text-slate-300">{fw}</td>
                    {allScenarios.map((sc) => {
                      const score = getScore(fw, sc)
                      return (
                        <td
                          key={sc}
                          className={`px-4 py-3 font-mono font-semibold ${scoreColor(score)}`}
                        >
                          {score !== null ? score.toFixed(3) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
