interface Props {
  label: string
  value: string | number
  sub?: string
}

export function MetricsCard({ label, value, sub }: Props) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <div className="text-slate-400 text-sm">{label}</div>
      <div className="text-2xl font-bold text-slate-100 mt-1">{value}</div>
      {sub && <div className="text-slate-500 text-xs mt-1">{sub}</div>}
    </div>
  )
}
