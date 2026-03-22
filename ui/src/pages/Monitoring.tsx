import { useEffect, useRef, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { DashboardState, Metrics } from '../types'

interface Props {
  state: DashboardState
}

interface Snapshot extends Metrics {
  timestamp: string
}

const MAX_SNAPSHOTS = 30

export function Monitoring({ state }: Props) {
  const [history, setHistory] = useState<Snapshot[]>([])
  const prevMetricsRef = useRef<string>('')

  useEffect(() => {
    const serialized = JSON.stringify(state.metrics)
    if (serialized === prevMetricsRef.current) return
    prevMetricsRef.current = serialized

    const snapshot: Snapshot = {
      ...state.metrics,
      timestamp: new Date().toLocaleTimeString(),
    }
    setHistory((prev) => [...prev.slice(-(MAX_SNAPSHOTS - 1)), snapshot])
  }, [state.metrics])

  const metricKeys = Object.keys(state.metrics).filter(
    (k) => k !== 'timestamp' && typeof state.metrics[k] === 'number'
  )

  const lineColors = [
    '#22d3ee',
    '#34d399',
    '#f59e0b',
    '#f87171',
    '#a78bfa',
    '#fb923c',
  ]

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-slate-100">Monitoring</h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Metrics Over Time</h3>
        {history.length < 2 ? (
          <p className="text-slate-500 text-sm">Collecting data… waiting for more snapshots.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="timestamp"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                interval="preserveStartEnd"
              />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '0.5rem',
                  color: '#e2e8f0',
                }}
              />
              <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
              {metricKeys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={lineColors[i % lineColors.length]}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-lg">
        <div className="px-4 py-3 border-b border-slate-700">
          <h3 className="text-sm font-semibold text-slate-300">Current Metrics</h3>
        </div>
        {Object.keys(state.metrics).length === 0 ? (
          <p className="p-4 text-slate-500 text-sm">No metrics available.</p>
        ) : (
          <div className="divide-y divide-slate-700">
            {Object.entries(state.metrics).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between px-4 py-3">
                <span className="text-sm font-mono text-slate-400">{key}</span>
                <span className="text-sm font-semibold text-slate-100">
                  {value !== undefined ? String(value) : '—'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
