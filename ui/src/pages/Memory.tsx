import { useState } from 'react'
import { api } from '../api/client'

export function Memory() {
  const [domain, setDomain] = useState('default')
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFetch() {
    setLoading(true)
    setError(null)
    try {
      const result = await api.getMemory(domain)
      setData(result as Record<string, unknown>)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch memory')
    } finally {
      setLoading(false)
    }
  }

  function renderValue(value: unknown): string {
    if (typeof value === 'string') return value
    return JSON.stringify(value, null, 2)
  }

  const entries = data ? Object.entries(data) : []

  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-bold text-slate-100">Memory</h2>

      <div className="flex gap-3">
        <input
          type="text"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="Domain (e.g. default)"
          className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 w-48"
        />
        <button
          onClick={handleFetch}
          disabled={loading}
          className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm transition-colors"
        >
          {loading ? 'Loading…' : 'Fetch'}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {data !== null && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg">
          {entries.length === 0 ? (
            <p className="p-6 text-slate-500 text-sm">No memory entries for domain "{domain}".</p>
          ) : (
            <div className="divide-y divide-slate-700">
              {entries.map(([key, value]) => (
                <div key={key} className="px-4 py-3">
                  <div className="text-xs font-mono text-cyan-400 mb-1">{key}</div>
                  <pre className="text-sm text-slate-300 whitespace-pre-wrap break-words">
                    {renderValue(value)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {data === null && !loading && !error && (
        <p className="text-slate-500 text-sm">
          Enter a domain name and click Fetch to browse memory.
        </p>
      )}
    </div>
  )
}
