/**
 * KubeAIConnection — WebSocket manager with polling fallback.
 * Analogous to kubectl's watch mechanism: maintains a live connection to the
 * KubeAI control plane and delivers real-time state updates to the UI.
 */
class KubeAIConnection {
  constructor(onMessage) {
    this._onMessage = onMessage;
    this._ws = null;
    this._pollTimer = null;
    this._reconnectTimer = null;
    this._status = 'disconnected';
    this._reconnectDelay = 1000;
    this._maxReconnectDelay = 30000;
  }

  get status() {
    return this._status;
  }

  connect() {
    this._setStatus('connecting');
    this._tryWebSocket();
  }

  disconnect() {
    if (this._ws) {
      this._ws.onclose = null;
      this._ws.close();
      this._ws = null;
    }
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this._setStatus('disconnected');
  }

  _tryWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/ws`;

    try {
      this._ws = new WebSocket(url);
    } catch (e) {
      console.warn('[KubeAIConnection] WebSocket construction failed, falling back to polling.', e);
      this._startPolling();
      return;
    }

    const connectTimeout = setTimeout(() => {
      if (this._ws && this._ws.readyState !== WebSocket.OPEN) {
        console.warn('[KubeAIConnection] WebSocket connect timed out, falling back to polling.');
        this._ws.close();
        this._startPolling();
      }
    }, 5000);

    this._ws.onopen = () => {
      clearTimeout(connectTimeout);
      this._reconnectDelay = 1000;
      this._setStatus('connected');
      console.log('[KubeAIConnection] WebSocket connected.');
    };

    this._ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._onMessage(data);
      } catch (e) {
        console.error('[KubeAIConnection] Failed to parse message:', e);
      }
    };

    this._ws.onerror = (err) => {
      clearTimeout(connectTimeout);
      console.warn('[KubeAIConnection] WebSocket error, falling back to polling.');
      this._startPolling();
    };

    this._ws.onclose = (event) => {
      clearTimeout(connectTimeout);
      if (this._pollTimer) return; // already polling
      console.log('[KubeAIConnection] WebSocket closed, scheduling reconnect...');
      this._setStatus('connecting');
      this._scheduleReconnect();
    };
  }

  _scheduleReconnect() {
    this._reconnectTimer = setTimeout(() => {
      console.log('[KubeAIConnection] Attempting WebSocket reconnect...');
      this._tryWebSocket();
    }, this._reconnectDelay);
    this._reconnectDelay = Math.min(this._reconnectDelay * 1.5, this._maxReconnectDelay);
  }

  _startPolling() {
    if (this._pollTimer) return;
    console.log('[KubeAIConnection] Starting polling fallback (5s interval).');

    const poll = async () => {
      try {
        const [overviewRes, agentsRes, tasksRes, metricsRes] = await Promise.all([
          fetch('/api/overview'),
          fetch('/api/agents'),
          fetch('/api/tasks'),
          fetch('/api/monitoring/metrics'),
        ]);

        if (!overviewRes.ok) throw new Error('API not available');

        const [overview, agents, tasks, metrics] = await Promise.all([
          overviewRes.json(),
          agentsRes.json(),
          tasksRes.json(),
          metricsRes.json(),
        ]);

        this._setStatus('connected');
        this._onMessage({
          type: 'state_update',
          data: { agents, tasks, metrics, overview },
        });
      } catch (e) {
        console.warn('[KubeAIConnection] Poll failed:', e.message);
        this._setStatus('disconnected');
      }
    };

    poll();
    this._pollTimer = setInterval(poll, 5000);
  }

  _setStatus(status) {
    if (this._status === status) return;
    this._status = status;

    // Update header connection badge
    const badge = document.getElementById('connection-status');
    const label = badge?.querySelector('.status-label');
    const wsStatus = document.getElementById('statusbar-ws');

    if (badge) {
      badge.className = `connection-status status-${status}`;
      if (label) {
        label.textContent = {
          connected: 'Connected',
          connecting: 'Connecting...',
          disconnected: 'Disconnected',
        }[status] || status;
      }
    }

    if (wsStatus) {
      const dot = wsStatus.querySelector('.status-dot-sm');
      const text = wsStatus.querySelector('span:last-child');
      if (dot) dot.className = `status-dot-sm ${status}`;
      if (text) text.textContent = `WebSocket: ${status}`;
    }
  }
}
