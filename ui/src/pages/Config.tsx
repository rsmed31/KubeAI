import { useState, useEffect } from 'react'
import { api } from '../api/client'

interface ConfigEntry {
  key: string
  value: unknown
  category?: string
}

type ConfigData = Record<string, unknown>

function groupByCategory(data: ConfigData): Record<string, ConfigEntry[]> {
  const groups: Record<string, ConfigEntry[]> = {}
  for (const [key, value] of Object.entries(data)) {
    const category = key.includes('.') ? key.split('.')[0] : 'general'
    if (!groups[category]) groups[category] = []
    groups[category].push({ key, value, category })
  }
  return groups
}

export function Config() {
  const [config, setConfig] = useState<ConfigData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<Record<string, string>>({})

  useEffect(() => {
    api
      .getConfig()
      .then((data) => setConfig(data as ConfigData))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'Failed to load config')
      )
      .finally(() => setLoading(false))
  }, [])

  function startEdit(key: string, currentValue: unknown) {
    setEditing((prev) => ({
      ...prev,
      [key]: typeof currentValue === 'string' ? currentValue : JSON.stringify(currentValue),
    }))
  }

  function cancelEdit(key: string) {
    setEditing((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
    setSaveError((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  async function saveEdit(key: string) {
    setSaving(key)
    setSaveError((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
    try {
      let value: unknown = editing[key]
      try {
        value = JSON.parse(editing[key])
      } catch {
        // keep as string
      }
      await api.setConfig(key, value)
      setConfig((prev) => (prev ? { ...prev, [key]: value } : prev))
      cancelEdit(key)
    } catch (e) {
      setSaveError((prev) => ({
        ...prev,
        [key]: e instanceof Error ? e.message : 'Save failed',
      }))
    } finally {
      setSaving(null)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold text-slate-100 mb-4">Config</h2>
        <p className="text-slate-400 text-sm">Loading configuration…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold text-slate-100 mb-4">Config</h2>
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      </div>
    )
  }

  if (!config || Object.keys(config).length === 0) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold text-slate-100 mb-4">Config</h2>
        <p className="text-slate-500 text-sm">No configuration entries found.</p>
      </div>
    )
  }

  const groups = groupByCategory(config)

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-slate-100">Config</h2>

      {Object.entries(groups).map(([category, entries]) => (
        <div key={category} className="bg-slate-800 border border-slate-700 rounded-lg">
          <div className="px-4 py-3 border-b border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300 capitalize">{category}</h3>
          </div>
          <div className="divide-y divide-slate-700">
            {entries.map(({ key, value }) => (
              <div key={key} className="px-4 py-3">
                <div className="flex items-start gap-4">
                  <div className="flex-1">
                    <div className="text-xs font-mono text-cyan-400 mb-1">{key}</div>
                    {editing[key] !== undefined ? (
                      <div className="space-y-2">
                        <input
                          type="text"
                          value={editing[key]}
                          onChange={(e) =>
                            setEditing((prev) => ({ ...prev, [key]: e.target.value }))
                          }
                          className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 font-mono focus:outline-none focus:border-cyan-500"
                        />
                        {saveError[key] && (
                          <p className="text-xs text-red-400">{saveError[key]}</p>
                        )}
                        <div className="flex gap-2">
                          <button
                            onClick={() => saveEdit(key)}
                            disabled={saving === key}
                            className="px-3 py-1 rounded text-xs bg-cyan-700 hover:bg-cyan-600 text-white disabled:opacity-50 transition-colors"
                          >
                            {saving === key ? 'Saving…' : 'Save'}
                          </button>
                          <button
                            onClick={() => cancelEdit(key)}
                            className="px-3 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-slate-300 font-mono break-all">
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </p>
                    )}
                  </div>
                  {editing[key] === undefined && (
                    <button
                      onClick={() => startEdit(key, value)}
                      className="px-2 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors shrink-0 mt-4"
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
