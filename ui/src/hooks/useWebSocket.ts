import { useState, useEffect, useRef } from 'react'
import { DashboardState } from '../types'

const INITIAL_STATE: DashboardState = {
  agents: [],
  tasks: [],
  metrics: {},
  pool_models: [],
  pool_mcps: [],
  clusters: [],
}

export function useWebSocket() {
  const [state, setState] = useState<DashboardState>(INITIAL_STATE)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws`

    function connect() {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 2000)
      }
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as { type: string; data: DashboardState }
          if (msg.type === 'state_update') {
            setState(msg.data)
          }
        } catch {
          // ignore malformed messages
        }
      }
    }

    connect()
    return () => wsRef.current?.close()
  }, [])

  return { state, connected }
}
