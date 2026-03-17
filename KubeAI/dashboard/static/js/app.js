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
  pool_mcps: [],
  clusters: [],
  activeCluster: 'default',
  lastState: {},
  _currentPage: null,
};

// ── Router ────────────────────────────────────────────────────────────────────
const routes = {
  '#clusters': () => ClustersPage.render(AppState),
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

  // Reset cluster detail view when navigating away from #clusters
  if (h !== '#clusters' && typeof ClustersPage !== 'undefined') {
    ClustersPage._resetView();
  }

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
  if (data.pool_mcps !== undefined) AppState.pool_mcps = data.pool_mcps;
  if (data.clusters !== undefined) AppState.clusters = data.clusters;
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

function setActiveCluster(name) {
  AppState.activeCluster = name;
  updateClusterContext();
  closeClusterDropdown();
}

function updateClusterContext() {
  const name = AppState.activeCluster || 'default';
  const topbar = document.getElementById('topbar-cluster-name');
  if (topbar) topbar.textContent = name;
  const statusbar = document.getElementById('statusbar-cluster-name');
  if (statusbar) statusbar.textContent = name;
  const badge = document.getElementById('topbar-cluster-badge');
  if (badge) {
    badge.style.borderColor = name !== 'default' ? 'var(--accent-cyan)' : '';
    badge.style.background  = name !== 'default' ? 'rgba(6,182,212,0.1)' : '';
  }
}

function toggleClusterDropdown() {
  const dd = document.getElementById('cluster-dropdown');
  if (!dd) return;
  if (dd.style.display === 'none') {
    // Build list from AppState.clusters
    const clusters = AppState.clusters || [];
    const names = clusters.length > 0 ? clusters.map(c => c.name) : ['default'];
    dd.innerHTML = `
      <div style="padding:6px 10px;font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid var(--border-color);">Switch context</div>
      ${names.map(n => `
        <div onclick="setActiveCluster('${escHtml(n)}')" style="padding:8px 12px;cursor:pointer;font-size:13px;display:flex;align-items:center;gap:8px;${n === AppState.activeCluster ? 'color:var(--accent-cyan);font-weight:600;' : ''}"
          onmouseenter="this.style.background='var(--bg-elevated)'" onmouseleave="this.style.background=''">
          <i data-lucide="server" style="width:13px;height:13px;"></i>
          ${escHtml(n)}
          ${n === AppState.activeCluster ? '<span style="margin-left:auto;font-size:10px;">✓ active</span>' : ''}
        </div>
      `).join('')}
      <div style="border-top:1px solid var(--border-color);padding:6px 12px;">
        <a href="#clusters" style="font-size:12px;color:var(--accent-cyan);text-decoration:none;">Manage clusters →</a>
      </div>
    `;
    dd.style.display = 'block';
    window.refreshIcons?.();
    // Close on outside click
    setTimeout(() => document.addEventListener('click', closeClusterDropdownOnOutside), 0);
  } else {
    closeClusterDropdown();
  }
}

function closeClusterDropdown() {
  const dd = document.getElementById('cluster-dropdown');
  if (dd) dd.style.display = 'none';
  document.removeEventListener('click', closeClusterDropdownOnOutside);
}

function closeClusterDropdownOnOutside(e) {
  const badge = document.getElementById('topbar-cluster-badge');
  const dd    = document.getElementById('cluster-dropdown');
  if (dd && badge && !badge.contains(e.target) && !dd.contains(e.target)) {
    closeClusterDropdown();
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
