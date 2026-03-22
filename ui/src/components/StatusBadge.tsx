interface Props {
  status: string
}

export function StatusBadge({ status }: Props) {
  const colors: Record<string, string> = {
    RUNNING: 'bg-green-900 text-green-300',
    IDLE: 'bg-slate-700 text-slate-300',
    SUCCESS: 'bg-green-900 text-green-300',
    QUEUED: 'bg-yellow-900 text-yellow-300',
    FAILED: 'bg-red-900 text-red-300',
    TERMINATED: 'bg-slate-700 text-slate-400',
    healthy: 'bg-green-900 text-green-300',
    unhealthy: 'bg-red-900 text-red-300',
  }
  const cls = colors[status] ?? 'bg-slate-700 text-slate-300'
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}
    >
      {status}
    </span>
  )
}
