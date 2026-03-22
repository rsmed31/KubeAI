import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import { Layout } from './components/Layout'
import { Overview } from './pages/Overview'
import { Agents } from './pages/Agents'
import { Tasks } from './pages/Tasks'
import { Memory } from './pages/Memory'
import { Blueprints } from './pages/Blueprints'
import { Monitoring } from './pages/Monitoring'
import { Clusters } from './pages/Clusters'
import { Pools } from './pages/Pools'
import { Config } from './pages/Config'
import { Benchmarks } from './pages/Benchmarks'
import { Skills } from './pages/Skills'

export default function App() {
  const { state, connected } = useWebSocket()
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout connected={connected} />}>
          <Route index element={<Overview state={state} />} />
          <Route path="agents" element={<Agents state={state} />} />
          <Route path="tasks" element={<Tasks state={state} />} />
          <Route path="memory" element={<Memory />} />
          <Route path="blueprints" element={<Blueprints />} />
          <Route path="monitoring" element={<Monitoring state={state} />} />
          <Route path="clusters" element={<Clusters state={state} />} />
          <Route path="pools" element={<Pools state={state} />} />
          <Route path="config" element={<Config />} />
          <Route path="benchmarks" element={<Benchmarks />} />
          <Route path="skills" element={<Skills />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
