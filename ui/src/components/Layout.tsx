import { NavLink, Outlet } from 'react-router-dom'
import {
  Activity,
  Bot,
  CheckSquare,
  Database,
  Layout as LayoutIcon,
  Monitor,
  Server,
  Layers,
  Settings,
  BarChart2,
  Zap,
} from 'lucide-react'

interface LayoutProps {
  connected: boolean
}

export function Layout({ connected }: LayoutProps) {
  const navItems = [
    { to: '/', label: 'Overview', icon: LayoutIcon, end: true },
    { to: '/agents', label: 'Agents', icon: Bot, end: false },
    { to: '/tasks', label: 'Tasks', icon: CheckSquare, end: false },
    { to: '/memory', label: 'Memory', icon: Database, end: false },
    { to: '/blueprints', label: 'Blueprints', icon: Layers, end: false },
    { to: '/monitoring', label: 'Monitoring', icon: Monitor, end: false },
    { to: '/clusters', label: 'Clusters', icon: Server, end: false },
    { to: '/pools', label: 'Pools', icon: Activity, end: false },
    { to: '/config', label: 'Config', icon: Settings, end: false },
    { to: '/skills', label: 'Skills', icon: Zap, end: false },
    { to: '/benchmarks', label: 'Benchmarks', icon: BarChart2, end: false },
  ]

  return (
    <div className="flex h-screen bg-slate-900">
      <aside className="w-56 bg-slate-800 border-r border-slate-700 flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <h1 className="text-xl font-bold text-cyan-400">KubeAI</h1>
          <div className="flex items-center gap-2 mt-1">
            <div
              className={`w-2 h-2 rounded-full ${
                connected ? 'bg-green-400' : 'bg-red-400'
              }`}
            />
            <span className="text-xs text-slate-400">
              {connected ? 'Live' : 'Disconnected'}
            </span>
          </div>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-cyan-900 text-cyan-300'
                    : 'text-slate-400 hover:bg-slate-700 hover:text-slate-100'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
