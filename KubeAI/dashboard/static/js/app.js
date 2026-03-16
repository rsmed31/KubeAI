/**
 * KubeAI Dashboard — SPA Router + Global State Manager
 * Analogous to the Kubernetes API machinery: routes requests to the correct
 * controller and maintains a consistent view of cluster state.
 */

// ── Global State ──────────────────────────────────────────────────────────────
const AppState = {
  agents: [],
  tasks: [],
  metrics: {},
  overview: {},
  blueprints: [],
  memory: {},
  pool_models: [],
  lastState: {},
  _currentPage: null,
};

// ── Router ────────────────────────────────────────────────────────────────────
const routes = {
  '#overview': () => OverviewPage.render(AppState),
  '#agents': () => AgentsPage.render(AppState),
  '#tasks': () => TasksPage.render(AppState),
  '#memory': () => MemoryPage.render(AppState),
  '#blueprints': () => BlueprintsPage.render(AppState),
  '#monitoring': () => MonitoringPage.render(AppState),
  '#pools': () => PoolsPage.render(AppState),
};

function navigate(hash) {
  const h = hash || '#overview';
  const renderer = routes[h] || routes['#overview'];

  // Update active nav link
  document.querySelectorAll('.nav-link').forEach(el => {
    el.classList.toggle('active', el.getAttribute('href') === h);
  });

  AppState._currentPage = h;
  renderer();
}

// ── WebSocket Message Handler ─────────────────────────────────────────────────
function handleMessage(msg) {
  if (msg.type !== 'state_update') return;
  const data = msg.data;

  if (data.agents !== undefined) AppState.agents = data.agents;
  if (data.tasks !== undefined) AppState.tasks = data.tasks;
  if (data.metrics !== undefined) AppState.metrics = data.metrics;
  if (data.overview !== undefined) AppState.overview = data.overview;
  if (data.pool_models !== undefined) AppState.pool_models = data.pool_models;
  AppState.lastState = data;

  // Re-render current page with updated state
  if (AppState._currentPage) {
    const renderer = routes[AppState._currentPage];
    if (renderer) renderer();
  }

  updateStatusBar();
  updateHeaderAgentCount();
  updateLastUpdated();
}

function updateStatusBar() {
  // Connection status is handled by ws.js
}

function updateHeaderAgentCount() {
  const el = document.getElementById('header-agent-count');
  if (!el) return;
  const running = AppState.agents.filter(a => a.state === 'RUNNING').length;
  const total = AppState.agents.length;
  el.textContent = `${running}/${total} agents`;
}

function updateLastUpdated() {
  const el = document.getElementById('statusbar-updated');
  if (el) {
    const now = new Date();
    el.textContent = `Last updated: ${now.toLocaleTimeString()}`;
  }
}

// ── Utility Helpers ───────────────────────────────────────────────────────────

/**
 * Format bytes to human-readable string.
 */
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Format a Unix timestamp to relative time string.
 */
function formatRelativeTime(ts) {
  if (!ts) return '—';
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

/**
 * Return a badge HTML string for a given state.
 */
function stateBadge(state) {
  if (!state) return '—';
  const cls = `badge badge-${state.toLowerCase()}`;
  return `<span class="${cls}"><span class="badge-dot"></span>${state}</span>`;
}

/**
 * Return a tier badge HTML string.
 */
function tierBadge(tier) {
  if (!tier) return '—';
  return `<span class="badge tier-${tier.toLowerCase()}">${tier}</span>`;
}

/**
 * Escape HTML to prevent XSS.
 */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Initialize Lucide icons
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Prefetch blueprints and memory (not in WS stream)
  const prefetchBlueprints = async () => {
    try {
      const res = await fetch('/api/blueprints');
      if (res.ok) AppState.blueprints = await res.json();
    } catch (e) {
      console.warn('Failed to prefetch blueprints:', e.message);
    }
  };

  const prefetchMemory = async () => {
    try {
      const res = await fetch('/api/memory');
      if (res.ok) AppState.memory = await res.json();
    } catch (e) {
      console.warn('Failed to prefetch memory:', e.message);
    }
  };

  prefetchBlueprints();
  prefetchMemory();

  // Set up periodic refresh for blueprints/memory (not in WS stream)
  setInterval(() => {
    prefetchBlueprints();
    prefetchMemory();
  }, 10000);

  // Connect WebSocket
  const conn = new KubeAIConnection(handleMessage);
  conn.connect();

  // Hash-based routing
  window.addEventListener('hashchange', () => {
    navigate(location.hash);
  });

  // Initial route
  navigate(location.hash || '#overview');

  // Re-create Lucide icons after page renders (called by pages)
  window.refreshIcons = () => {
    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  };
});
