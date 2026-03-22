import { Fragment, useState, useEffect } from 'react'
import { api } from '../api/client'
import { BlueprintRecord } from '../types'

export function Blueprints() {
  const [blueprints, setBlueprints] = useState<BlueprintRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedName, setExpandedName] = useState<string | null>(null)

  const [description, setDescription] = useState('')
  const [generatedYaml, setGeneratedYaml] = useState('')
  const [generating, setGenerating] = useState(false)
  const [registering, setRegistering] = useState(false)

  async function loadBlueprints() {
    setLoading(true)
    try {
      const data = await api.getBlueprints()
      const list = Array.isArray(data)
        ? (data as BlueprintRecord[])
        : Object.values(data as Record<string, BlueprintRecord>)
      setBlueprints(list)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load blueprints')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadBlueprints()
  }, [])

  async function handleGenerate() {
    if (!description.trim()) {
      setError('Blueprint description is required')
      return
    }
    setGenerating(true)
    setError(null)
    try {
      const data = (await api.generateBlueprint(description.trim())) as { yaml: string }
      setGeneratedYaml(data.yaml)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to generate blueprint YAML')
    } finally {
      setGenerating(false)
    }
  }

  async function handleRegisterGenerated() {
    if (!generatedYaml.trim()) {
      return
    }

    const nameMatch = generatedYaml.match(/name:\s*([A-Za-z0-9_-]+)/)
    const tierMatch = generatedYaml.match(/tier:\s*([A-Za-z]+)/)
    const inferredName = nameMatch ? nameMatch[1] : 'custom_agent'
    const inferredTier = tierMatch ? tierMatch[1].toLowerCase() : 'capable'

    setRegistering(true)
    setError(null)
    try {
      await api.registerBlueprint({
        name: inferredName,
        description: description.trim() || 'Custom generated blueprint',
        tier: inferredTier,
        version: '1.0',
        capabilities: [],
      })
      await loadBlueprints()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to register generated blueprint')
    } finally {
      setRegistering(false)
    }
  }

  function toggleExpand(name: string) {
    setExpandedName((prev) => (prev === name ? null : name))
  }

  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-bold text-slate-100">Blueprints</h2>

      {loading && <p className="text-slate-400 text-sm">Loading blueprints…</p>}

      {error && (
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-200">Generate Blueprint</h3>
        <textarea
          className="w-full min-h-24 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
          placeholder="Describe the agent behavior and capabilities"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <div className="flex items-center gap-2">
          <button
            className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm disabled:opacity-50"
            disabled={generating}
            onClick={() => void handleGenerate()}
          >
            {generating ? 'Generating...' : 'Generate YAML'}
          </button>
          <button
            className="px-3 py-2 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-sm disabled:opacity-50"
            disabled={registering || !generatedYaml}
            onClick={() => void handleRegisterGenerated()}
          >
            {registering ? 'Registering...' : 'Register Generated'}
          </button>
        </div>
        {generatedYaml ? (
          <pre className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-900 rounded p-3 border border-slate-700 overflow-auto max-h-72">
            {generatedYaml}
          </pre>
        ) : null}
      </div>

      {!loading && !error && blueprints.length === 0 && (
        <p className="text-slate-500 text-sm">No blueprints registered.</p>
      )}

      {!loading && blueprints.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Name</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Version</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Tier</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Description</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Tags</th>
              </tr>
            </thead>
            <tbody>
              {blueprints.map((bp) => (
                <Fragment key={bp.name}>
                  <tr
                    className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                    onClick={() => toggleExpand(bp.name)}
                  >
                    <td className="px-4 py-3 text-cyan-400 font-medium">{bp.name}</td>
                    <td className="px-4 py-3 text-slate-400 font-mono text-xs">
                      {bp.version ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-400">{bp.tier ?? '—'}</td>
                    <td className="px-4 py-3 text-slate-300 max-w-xs truncate">
                      {bp.description}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(bp.capabilities ?? []).map((tag) => (
                          <span
                            key={tag}
                            className="px-1.5 py-0.5 rounded text-xs bg-slate-700 text-slate-300"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                  {expandedName === bp.name ? (
                    <tr key={`${bp.name}-detail`} className="bg-slate-900/50">
                      <td colSpan={5} className="px-6 py-4">
                        <div className="space-y-2">
                          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">
                            System Prompt
                          </p>
                          {bp.system_prompt ? (
                            <pre className="text-sm text-slate-300 whitespace-pre-wrap bg-slate-800 rounded p-3 border border-slate-700">
                              {bp.system_prompt}
                            </pre>
                          ) : (
                            <p className="text-sm text-slate-500">No system prompt defined.</p>
                          )}
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
