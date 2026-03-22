import { useState, useEffect } from 'react'
import { api } from '../api/client'

interface Skill {
  skill_id: string
  name: string
  description: string
  system_prompt: string
  mcp_tools: string[]
  tags: string[]
  enabled: boolean
}

export function Skills() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [editing, setEditing] = useState<Skill | null>(null)
  const [saving, setSaving] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newSkill, setNewSkill] = useState<Partial<Skill>>({
    name: '',
    description: '',
    system_prompt: '',
    mcp_tools: [],
    tags: [],
    enabled: true,
  })

  useEffect(() => {
    loadSkills()
  }, [])

  function loadSkills() {
    setLoading(true)
    api
      .getSkills()
      .then((data) => setSkills(data as Skill[]))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load skills'))
      .finally(() => setLoading(false))
  }

  async function handleUpdate(skill: Skill) {
    setSaving(true)
    try {
      await api.updateSkill(skill.skill_id, skill)
      setSkills((prev) => prev.map((s) => (s.skill_id === skill.skill_id ? skill : s)))
      setEditing(null)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(skillId: string) {
    if (!confirm('Delete this skill?')) return
    try {
      await api.deleteSkill(skillId)
      setSkills((prev) => prev.filter((s) => s.skill_id !== skillId))
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  async function handleCreate() {
    if (!newSkill.name || !newSkill.system_prompt) {
      alert('Name and system prompt are required')
      return
    }
    setSaving(true)
    try {
      const created = await api.createSkill(newSkill)
      setSkills((prev) => [...prev, created as Skill])
      setCreating(false)
      setNewSkill({ name: '', description: '', system_prompt: '', mcp_tools: [], tags: [], enabled: true })
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Create failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold text-slate-100 mb-4">Skills</h2>
        <p className="text-slate-400 text-sm">Loading skills…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold text-slate-100 mb-4">Skills</h2>
        <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">{error}</div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-slate-100">Skills</h2>
        <button
          onClick={() => setCreating(!creating)}
          className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-white rounded-lg text-sm transition-colors"
        >
          {creating ? 'Cancel' : '+ New Skill'}
        </button>
      </div>

      {creating && (
        <div className="bg-slate-800 border border-cyan-700 rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-semibold text-cyan-400">New Skill</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Name *</label>
              <input
                value={newSkill.name ?? ''}
                onChange={(e) => setNewSkill((p) => ({ ...p, name: e.target.value }))}
                className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Description</label>
              <input
                value={newSkill.description ?? ''}
                onChange={(e) => setNewSkill((p) => ({ ...p, description: e.target.value }))}
                className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">System Prompt *</label>
            <textarea
              rows={4}
              value={newSkill.system_prompt ?? ''}
              onChange={(e) => setNewSkill((p) => ({ ...p, system_prompt: e.target.value }))}
              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 font-mono focus:outline-none focus:border-cyan-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Tags (comma-separated)</label>
            <input
              value={(newSkill.tags ?? []).join(', ')}
              onChange={(e) =>
                setNewSkill((p) => ({
                  ...p,
                  tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
                }))
              }
              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={saving}
              className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-white rounded-lg text-sm transition-colors"
            >
              {saving ? 'Creating…' : 'Create'}
            </button>
            <button
              onClick={() => setCreating(false)}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {skills.length === 0 ? (
        <p className="text-slate-500 text-sm">No skills registered. Create one to get started.</p>
      ) : (
        <div className="space-y-2">
          {skills.map((skill) => (
            <div key={skill.skill_id} className="bg-slate-800 border border-slate-700 rounded-lg">
              <div
                className="flex items-center justify-between px-4 py-3 cursor-pointer"
                onClick={() => setExpanded(expanded === skill.skill_id ? null : skill.skill_id)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-slate-200">{skill.name}</span>
                  {skill.tags.map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-400">
                      {tag}
                    </span>
                  ))}
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${
                      skill.enabled ? 'bg-green-900 text-green-300' : 'bg-slate-700 text-slate-400'
                    }`}
                  >
                    {skill.enabled ? 'enabled' : 'disabled'}
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditing(skill)
                    }}
                    className="px-2 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(skill.skill_id)
                    }}
                    className="px-2 py-1 rounded text-xs bg-red-900 hover:bg-red-800 text-red-300 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {expanded === skill.skill_id && editing?.skill_id !== skill.skill_id && (
                <div className="px-4 pb-3 border-t border-slate-700">
                  <p className="text-sm text-slate-400 mt-2 mb-1">{skill.description}</p>
                  <pre className="text-xs text-slate-300 bg-slate-900 rounded p-2 overflow-auto max-h-40 font-mono">
                    {skill.system_prompt}
                  </pre>
                  {skill.mcp_tools.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {skill.mcp_tools.map((tool) => (
                        <span key={tool} className="px-2 py-0.5 rounded text-xs bg-cyan-900 text-cyan-300">
                          {tool}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {editing?.skill_id === skill.skill_id && (
                <div className="px-4 pb-4 border-t border-slate-700 space-y-3 pt-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Name</label>
                      <input
                        value={editing.name}
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Description</label>
                      <input
                        value={editing.description}
                        onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                        className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">System Prompt</label>
                    <textarea
                      rows={5}
                      value={editing.system_prompt}
                      onChange={(e) => setEditing({ ...editing, system_prompt: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 font-mono focus:outline-none focus:border-cyan-500 resize-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Tags (comma-separated)</label>
                    <input
                      value={editing.tags.join(', ')}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
                        })
                      }
                      className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id={`enabled-${skill.skill_id}`}
                      checked={editing.enabled}
                      onChange={(e) => setEditing({ ...editing, enabled: e.target.checked })}
                      className="rounded"
                    />
                    <label htmlFor={`enabled-${skill.skill_id}`} className="text-sm text-slate-300">
                      Enabled
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleUpdate(editing)}
                      disabled={saving}
                      className="px-4 py-2 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-white rounded-lg text-sm transition-colors"
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={() => setEditing(null)}
                      className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
