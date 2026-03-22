import { Fragment, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { BlueprintRecord, DashboardState } from '../types'
import { StatusBadge } from '../components/StatusBadge'

interface Props {
  state: DashboardState
}

export function Tasks({ state }: Props) {
  const [description, setDescription] = useState('')
  const [selectedBlueprint, setSelectedBlueprint] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [targetUrls, setTargetUrls] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [filter, setFilter] = useState<'ALL' | 'RUNNING' | 'COMPLETE' | 'FAILED'>('ALL')
  const [blueprints, setBlueprints] = useState<BlueprintRecord[]>([])

  const tasks = state.tasks ?? []
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    void api
      .getBlueprints()
      .then((data) => {
        const list = Array.isArray(data)
          ? (data as BlueprintRecord[])
          : Object.values(data as Record<string, BlueprintRecord>)
        setBlueprints(list)
      })
      .catch(() => {
        setBlueprints([])
      })
  }, [])

  const filteredTasks = useMemo(() => {
    if (filter === 'ALL') {
      return tasks
    }
    if (filter === 'RUNNING') {
      const runningStatuses = new Set(['QUEUED', 'ROUTING', 'ASSIGNED', 'DATA_PROBING', 'SCRAPING', 'RAG_LOADED', 'SPAWNED', 'EXECUTING', 'RUNNING'])
      return tasks.filter((task) => runningStatuses.has(task.status))
    }
    if (filter === 'COMPLETE') {
      return tasks.filter((task) => task.status === 'COMPLETE' || task.status === 'SUCCESS')
    }
    return tasks.filter((task) => task.status === 'FAILED')
  }, [filter, tasks])

  async function handleSubmit() {
    if (!description.trim()) {
      setFeedback('Task description is required')
      return
    }

    setSubmitting(true)
    setFeedback(null)
    try {
      if (selectedFiles.length > 0 || targetUrls.trim()) {
        const formData = new FormData()
        formData.append('description', description.trim())
        if (selectedBlueprint.trim()) {
          formData.append('blueprint', selectedBlueprint.trim())
        }
        selectedFiles.forEach((file) => {
          formData.append('files', file)
        })

        const parsedUrls = targetUrls
          .split(/[\n,]/)
          .map((entry) => entry.trim())
          .filter((entry) => entry.length > 0)
        parsedUrls.forEach((url) => {
          formData.append('urls', url)
        })
        if (parsedUrls.length === 1) {
          formData.append('url', parsedUrls[0])
        }
        await api.submitTaskWithData(formData)
      } else {
        await api.submitTask(description.trim(), selectedBlueprint.trim() || undefined)
      }

      setDescription('')
      setSelectedBlueprint('')
      setSelectedFiles([])
      setTargetUrls('')
      setFeedback('Task submitted successfully. Watch stage progression below.')
    } catch (e) {
      setFeedback(e instanceof Error ? e.message : 'Task submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  function renderStagePipeline(taskStages: Array<{ stage: string }>) {
    if (!taskStages || taskStages.length === 0) {
      return <span className="text-xs text-slate-500">Queued</span>
    }

    const order = ['queued', 'routing', 'assigned', 'data_probing', 'scraping', 'rag_loaded', 'executing', 'complete']
    const seen = new Set(taskStages.map((item) => item.stage.toLowerCase()))

    return (
      <div className="flex flex-wrap gap-1">
        {order
          .filter((stage) => seen.has(stage))
          .map((stage) => (
            <span key={stage} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-700 text-slate-300 uppercase tracking-wide">
              {stage}
            </span>
          ))}
      </div>
    )
  }

  function toggleExpand(id: string) {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-bold text-slate-100">Tasks</h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-200">Submit Task</h3>
        <textarea
          className="w-full min-h-24 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
          placeholder="Describe the task"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
            value={selectedBlueprint}
            onChange={(event) => setSelectedBlueprint(event.target.value)}
          >
            <option value="">Auto-route blueprint</option>
            {blueprints.map((blueprint) => (
              <option key={blueprint.name} value={blueprint.name}>
                {blueprint.name}
              </option>
            ))}
          </select>

          <textarea
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100"
            placeholder="Optional URLs to scrape (comma or newline separated)"
            value={targetUrls}
            onChange={(event) => setTargetUrls(event.target.value)}
          />

          <input
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100 file:mr-2 file:rounded file:border-0 file:bg-slate-700 file:px-2 file:py-1 file:text-xs file:text-slate-200"
            type="file"
            multiple
            onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))}
          />
        </div>

        {selectedFiles.length > 0 ? (
          <p className="text-xs text-slate-400">Attached files: {selectedFiles.map((file) => file.name).join(', ')}</p>
        ) : null}

        <div className="flex items-center gap-2">
          <button
            className="px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm disabled:opacity-50"
            disabled={submitting}
            onClick={() => void handleSubmit()}
          >
            {submitting ? 'Submitting...' : 'Submit task'}
          </button>
          {feedback ? <span className="text-xs text-slate-300">{feedback}</span> : null}
        </div>
      </div>

      <div className="flex gap-2">
        {(['ALL', 'RUNNING', 'COMPLETE', 'FAILED'] as const).map((value) => (
          <button
            key={value}
            className={`px-3 py-1.5 rounded text-sm ${filter === value ? 'bg-cyan-700 text-white' : 'bg-slate-800 border border-slate-700 text-slate-300'}`}
            onClick={() => setFilter(value)}
          >
            {value}
          </button>
        ))}
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-x-auto">
        {filteredTasks.length === 0 ? (
          <p className="p-6 text-slate-500 text-sm">No tasks recorded.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="px-4 py-3 text-left text-slate-400 font-medium">ID</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Description</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Status</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Blueprint</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Latency</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Result</th>
                <th className="px-4 py-3 text-left text-slate-400 font-medium">Stages</th>
              </tr>
            </thead>
            <tbody>
              {[...filteredTasks].reverse().map((task) => (
                <Fragment key={task.id}>
                  <tr
                    className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                    onClick={() => toggleExpand(task.id)}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-slate-300">
                      {task.id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-xs truncate">
                      {task.description}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={task.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-400">{task.blueprint}</td>
                    <td className="px-4 py-3 text-slate-400">
                      {task.latency_ms !== null ? `${Math.round(task.latency_ms)} ms` : '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-xs truncate">
                      {task.result_text ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      {renderStagePipeline(task.stages)}
                    </td>
                  </tr>
                  {expandedId === task.id ? (
                    <tr key={`${task.id}-detail`} className="bg-slate-900/50">
                      <td colSpan={7} className="px-6 py-4">
                        <div className="space-y-2">
                          {task.agent_id && (
                            <p className="text-xs text-slate-400">
                              <span className="text-slate-500">Agent: </span>
                              <span className="font-mono">{task.agent_id}</span>
                            </p>
                          )}
                          {task.result_text && (
                            <div>
                              <p className="text-xs text-slate-500 mb-1">Result</p>
                              <p className="text-sm text-slate-300 whitespace-pre-wrap">
                                {task.result_text}
                              </p>
                            </div>
                          )}
                          {task.stages && task.stages.length > 0 && (
                            <div>
                              <p className="text-xs text-slate-500 mb-1">Stages</p>
                              <ul className="space-y-1">
                                {task.stages.map((stage, i) => (
                                  <li
                                    key={`${task.id}-${stage.stage}-${i}`}
                                    className="text-xs text-slate-400 flex items-center gap-2"
                                  >
                                    <span className="w-4 h-4 rounded-full bg-cyan-900 text-cyan-300 flex items-center justify-center text-[10px] shrink-0">
                                      {i + 1}
                                    </span>
                                    <span className="uppercase">{stage.stage}</span>
                                    {stage.message ? <span> - {stage.message}</span> : null}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
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
