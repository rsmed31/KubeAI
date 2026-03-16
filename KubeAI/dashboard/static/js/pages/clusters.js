/**
 * Clusters Page — high-level view of all KubeAI clusters.
 * Kubernetes analogue: multi-cluster management (like Lens or Rancher).
 *
 * High-level: card grid showing each cluster's health, agent count, task count.
 * Drill-down: click a cluster card to see its agents + tasks.
 * Create: "New Cluster" button opens a form.
 */
const ClustersPage = (() => {
  let _view = 'overview';          // 'overview' | 'detail'
  let _activeCluster = null;       // cluster name when in detail view
  let _detailTab = 'tasks';        // 'tasks' | 'agents' | 'pools'
  let _isCreating = false;
  let _showCreateForm = false;

  function render(state) {
    const clusters = state.clusters || [];
    const container = document.getElementById('page-container');

    if (_view === 'detail' && _activeCluster) {
      // Don't clobber the detail view on WS updates — it fetches its own data
      return;
    }
    renderOverview(container, clusters);
    window.refreshIcons?.();
  }

  // ── Overview ──────────────────────────────────────────────────────────────

  function renderOverview(container, clusters) {
    // Preserve form input values across WS-triggered re-renders
    const savedName    = document.getElementById('new-cluster-name')?.value ?? '';
    const savedDesc    = document.getElementById('new-cluster-desc')?.value ?? '';
    const savedWorkers = document.getElementById('new-cluster-workers')?.value ?? '4';

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Clusters</h1>
          <p class="page-subtitle">${clusters.length} cluster${clusters.length !== 1 ? 's' : ''} registered</p>
        </div>
        <button class="btn btn-primary" onclick="ClustersPage._toggleCreateForm()" style="align-self:center;">
          <i data-lucide="plus" class="icon-sm"></i>
          New Cluster
        </button>
      </div>

      ${_showCreateForm ? renderCreateForm() : ''}

      <!-- Cluster cards -->
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:8px;">
        ${clusters.length === 0
          ? `<div style="grid-column:1/-1;text-align:center;color:var(--text-muted);padding:48px;">
               No clusters yet. Create one to get started.
             </div>`
          : clusters.map(c => renderClusterCard(c)).join('')
        }
      </div>
    `;
    window.refreshIcons?.();

    // Restore form input values after innerHTML replacement
    if (_showCreateForm) {
      const nameEl    = document.getElementById('new-cluster-name');
      const descEl    = document.getElementById('new-cluster-desc');
      const workersEl = document.getElementById('new-cluster-workers');
      if (nameEl    && savedName)    nameEl.value    = savedName;
      if (descEl    && savedDesc)    descEl.value    = savedDesc;
      if (workersEl && savedWorkers) workersEl.value = savedWorkers;
    }

    // Attach card click listeners
    container.querySelectorAll('[data-cluster-name]').forEach(card => {
      card.addEventListener('click', () => {
        _activeCluster = card.dataset.clusterName;
        _view = 'detail';
        _detailTab = 'tasks';
        _fetchAndRenderDetail(_activeCluster);
      });
    });
  }

  function renderClusterCard(c) {
    const agentTotal = c.agents?.total ?? 0;
    const agentRunning = c.agents?.running ?? 0;
    const agentIdle = c.agents?.idle ?? 0;
    const taskTotal = c.tasks?.total ?? 0;
    const taskComplete = c.tasks?.complete ?? 0;
    const taskQueued = c.tasks?.queued ?? 0;
    const models = (c.models || []).slice(0, 3);
    const isDefault = c.name === 'default';

    return `
      <div class="card" data-cluster-name="${escHtml(c.name)}"
        style="cursor:pointer;transition:border-color 0.15s;border:1px solid var(--border-color);"
        onmouseenter="this.style.borderColor='var(--accent-cyan)'"
        onmouseleave="this.style.borderColor='var(--border-color)'">
        <div class="card-header" style="justify-content:space-between;">
          <span class="card-title" style="display:flex;align-items:center;gap:8px;">
            <i data-lucide="server" class="icon-sm" style="color:var(--accent-cyan);"></i>
            ${escHtml(c.name)}
            ${isDefault ? `<span style="font-size:10px;background:var(--accent-cyan);color:#000;padding:1px 6px;border-radius:3px;font-weight:600;">DEFAULT</span>` : ''}
          </span>
          <span style="display:flex;gap:6px;align-items:center;">
            ${stateBadge(c.status === 'healthy' ? 'HEALTHY' : 'ERROR')}
            ${!isDefault ? `<button class="btn" style="font-size:11px;padding:2px 8px;background:transparent;border:1px solid var(--accent-red);color:var(--accent-red);border-radius:4px;"
              onclick="event.stopPropagation();ClustersPage._deleteCluster('${escHtml(c.name)}')"
              title="Delete cluster">✕</button>` : ''}
          </span>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px;">
          <!-- Agents -->
          <div style="background:var(--bg-elevated);border-radius:6px;padding:10px;">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">
              <i data-lucide="cpu" class="icon-xs"></i> Agents
            </div>
            <div style="font-size:22px;font-weight:700;color:var(--text-primary);">${agentTotal}</div>
            <div style="font-size:11px;color:var(--text-muted);">
              <span style="color:var(--accent-green);">${agentRunning} running</span>
              · ${agentIdle} idle
            </div>
          </div>
          <!-- Tasks -->
          <div style="background:var(--bg-elevated);border-radius:6px;padding:10px;">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">
              <i data-lucide="list-checks" class="icon-xs"></i> Tasks
            </div>
            <div style="font-size:22px;font-weight:700;color:var(--text-primary);">${taskTotal}</div>
            <div style="font-size:11px;color:var(--text-muted);">
              <span style="color:var(--accent-green);">${taskComplete} complete</span>
              ${taskQueued > 0 ? `· <span style="color:var(--accent-yellow,#f59e0b);">${taskQueued} queued</span>` : ''}
            </div>
          </div>
        </div>

        ${models.length > 0 ? `
          <div style="margin-top:10px;display:flex;gap:4px;flex-wrap:wrap;">
            ${models.map(m => `<span style="font-size:10px;background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:3px;padding:2px 6px;color:var(--text-muted);">${escHtml(m)}</span>`).join('')}
            ${c.blueprint_count ? `<span style="font-size:10px;color:var(--text-muted);padding:2px 4px;">${c.blueprint_count} blueprints</span>` : ''}
          </div>
        ` : ''}

        <div style="margin-top:10px;font-size:11px;color:var(--accent-cyan);display:flex;align-items:center;gap:4px;">
          <i data-lucide="arrow-right" class="icon-xs"></i> Click to manage
        </div>
      </div>
    `;
  }

  function renderCreateForm() {
    return `
      <div class="card" style="margin-bottom:16px;border:1px solid var(--accent-cyan);">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="plus-circle" class="icon-sm"></i>
            Create New Cluster
          </span>
          <button class="btn" style="font-size:12px;" onclick="ClustersPage._toggleCreateForm()">✕ Cancel</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Cluster Name *</label>
            <input type="text" id="new-cluster-name" class="form-input"
              placeholder="my-cluster" pattern="[a-zA-Z0-9_-]+" />
            <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Letters, numbers, hyphens, underscores</div>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Workers</label>
            <input type="number" id="new-cluster-workers" class="form-input" value="4" min="1" max="16" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Description</label>
            <input type="text" id="new-cluster-desc" class="form-input" placeholder="Optional description" />
          </div>
        </div>
        <div style="display:flex;gap:16px;margin-bottom:12px;">
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="new-cluster-models" checked /> Inherit default models
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="new-cluster-mcps" checked /> Inherit MCP servers
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="new-cluster-blueprints" checked /> Inherit blueprints
          </label>
        </div>
        <div style="display:flex;gap:10px;align-items:center;">
          <button class="btn btn-primary" onclick="ClustersPage._createCluster()">
            <i data-lucide="plus" class="icon-sm"></i> Create Cluster
          </button>
          <div id="create-cluster-feedback" style="font-size:12px;"></div>
        </div>
      </div>
    `;
  }

  // ── Cluster detail ────────────────────────────────────────────────────────

  async function _fetchAndRenderDetail(clusterName) {
    // Set as active context whenever you enter a cluster's detail view
    if (typeof setActiveCluster === 'function') setActiveCluster(clusterName);

    const container = document.getElementById('page-container');
    if (!container) return;

    // Show loading state
    container.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;padding:24px;color:var(--text-muted);">
        <div class="spinner" style="width:16px;height:16px;"></div>
        Loading cluster ${escHtml(clusterName)}...
      </div>
    `;

    try {
      const [statusRes, tasksRes, agentsRes] = await Promise.all([
        fetch(`/api/clusters/${encodeURIComponent(clusterName)}/status`),
        fetch(`/api/clusters/${encodeURIComponent(clusterName)}/tasks?limit=100`),
        fetch(`/api/clusters/${encodeURIComponent(clusterName)}/agents`),
      ]);
      const clusterStatus = statusRes.ok ? await statusRes.json() : null;
      const tasks = tasksRes.ok ? await tasksRes.json() : [];
      const agents = agentsRes.ok ? await agentsRes.json() : [];

      renderDetail(container, clusterName, { tasks, agents, clusterStatus });
    } catch (e) {
      container.innerHTML = `<div style="color:var(--accent-red);padding:24px;">Failed to load cluster: ${escHtml(e.message)}</div>`;
    }
    window.refreshIcons?.();
  }

  function renderDetail(container, clusterName, data) {
    const tasks = data.tasks || [];
    const agents = data.agents || [];
    const cs = data.clusterStatus || {};

    container.innerHTML = `
      <!-- Back + title -->
      <div class="page-header" style="margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <button class="btn" onclick="ClustersPage._backToOverview()" style="padding:4px 10px;">
            <i data-lucide="arrow-left" class="icon-sm"></i> All Clusters
          </button>
          <div>
            <h1 class="page-title" style="display:flex;align-items:center;gap:8px;">
              <i data-lucide="server" class="icon-sm" style="color:var(--accent-cyan);"></i>
              ${escHtml(clusterName)}
              ${clusterName === 'default' ? `<span style="font-size:10px;background:var(--accent-cyan);color:#000;padding:1px 6px;border-radius:3px;">DEFAULT</span>` : ''}
            </h1>
            <p class="page-subtitle" style="display:flex;align-items:center;gap:8px;">
              ${agents.length} agents · ${tasks.length} tasks
              <span id="active-context-badge" style="font-size:10px;background:rgba(6,182,212,0.15);border:1px solid var(--accent-cyan);color:var(--accent-cyan);padding:1px 7px;border-radius:10px;display:none;">
                ✓ active context
              </span>
            </p>
          </div>
        </div>
        <!-- Quick submit for this cluster -->
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="text" id="cluster-quick-task" class="form-input" style="width:280px;"
            placeholder="Quick task description..." />
          <button class="btn btn-primary" onclick="ClustersPage._quickSubmit('${escHtml(clusterName)}')">
            <i data-lucide="send" class="icon-sm"></i> Submit
          </button>
        </div>
      </div>

      <!-- Stats row -->
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
        ${[
          ['cpu', 'Agents', agents.length, agents.filter(a=>a.state==='RUNNING').length + ' running'],
          ['list-checks', 'Tasks', tasks.length, tasks.filter(t=>t.status==='COMPLETE').length + ' complete'],
          ['zap', 'Models', cs.models?.length ?? 0, 'in pool'],
          ['plug', 'MCPs', cs.mcps?.length ?? 0, 'registered'],
        ].map(([icon, label, val, sub]) => `
          <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:6px;padding:12px;">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:flex;align-items:center;gap:4px;">
              <i data-lucide="${icon}" class="icon-xs"></i> ${label}
            </div>
            <div style="font-size:24px;font-weight:700;">${val}</div>
            <div style="font-size:11px;color:var(--text-muted);">${sub}</div>
          </div>
        `).join('')}
      </div>

      <!-- Tabs -->
      <div class="filter-bar" style="margin-bottom:16px;">
        ${['tasks','agents','pools'].map(tab => `
          <button class="filter-btn ${_detailTab === tab ? 'active' : ''}"
            onclick="ClustersPage._setDetailTab('${tab}','${escHtml(clusterName)}',${JSON.stringify({tasks,agents,clusterStatus:cs})})">
            ${tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        `).join('')}
      </div>

      <!-- Tab content -->
      <div id="cluster-detail-content">
        ${renderDetailTab(clusterName, _detailTab, tasks, agents, cs)}
      </div>
    `;
    window.refreshIcons?.();
  }

  function renderDetailTab(clusterName, tab, tasks, agents, clusterStatus) {
    if (tab === 'tasks') return renderDetailTasks(tasks);
    if (tab === 'agents') return renderDetailAgents(agents);
    if (tab === 'pools') return renderDetailPools(clusterStatus);
    return '';
  }

  function renderDetailTasks(tasks) {
    if (tasks.length === 0) {
      return `<div style="text-align:center;color:var(--text-muted);padding:32px;">No tasks yet in this cluster</div>`;
    }
    return `
      <div class="table-container">
        <table class="k8s-table">
          <thead><tr><th>ID</th><th>Description</th><th>Status</th><th>Blueprint</th><th>Agent</th><th>Latency</th></tr></thead>
          <tbody>
            ${[...tasks].sort((a,b) => (b.timestamp||0)-(a.timestamp||0)).map(t => `
              <tr>
                <td class="mono" style="font-size:11px;">${escHtml(t.id)}</td>
                <td style="max-width:240px;" class="truncate">${escHtml(t.description || t.id)}</td>
                <td>${stateBadge(t.status)}</td>
                <td class="mono">${escHtml(t.blueprint||'—')}</td>
                <td class="mono" style="font-size:11px;">${escHtml(t.agent_id||'—')}</td>
                <td class="mono">${t.latency_ms ? Math.round(t.latency_ms)+'ms' : '—'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderDetailAgents(agents) {
    if (agents.length === 0) {
      return `<div style="text-align:center;color:var(--text-muted);padding:32px;">No agents running in this cluster</div>`;
    }
    return `
      <div class="table-container">
        <table class="k8s-table">
          <thead><tr><th>ID</th><th>Blueprint</th><th>State</th><th>Model</th><th>Load</th><th>Capabilities</th></tr></thead>
          <tbody>
            ${agents.map(a => `
              <tr>
                <td class="mono" style="font-size:11px;">${escHtml(a.id)}</td>
                <td class="mono">${escHtml(a.blueprint||'—')}</td>
                <td>${stateBadge(a.state)}</td>
                <td class="mono" style="font-size:11px;">${escHtml(a.model_id||'—')}</td>
                <td><div style="background:var(--border-color);border-radius:2px;height:4px;width:60px;">
                  <div style="width:${Math.round((a.load||0)*100)}%;background:var(--accent-cyan);height:4px;border-radius:2px;"></div>
                </div></td>
                <td style="font-size:11px;">${(a.capabilities||[]).join(', ')||'—'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderDetailPools(cs) {
    const models = cs.models || [];
    const mcps = cs.mcps || [];
    return `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div class="card">
          <div class="card-header"><span class="card-title">LLM Models (${models.length})</span></div>
          ${models.length === 0 ? '<p style="padding:12px;color:var(--text-muted);">None</p>' : `
            <table class="k8s-table"><thead><tr><th>Model</th><th>Tier</th><th>Load</th><th>Health</th></tr></thead>
            <tbody>${models.map(m => `
              <tr>
                <td class="mono" style="font-size:11px;">${escHtml(m.model_id)}</td>
                <td style="font-size:11px;text-transform:uppercase;color:var(--accent-cyan);">${escHtml(m.tier)}</td>
                <td><div style="background:var(--border-color);border-radius:2px;height:4px;width:50px;">
                  <div style="width:${Math.round((m.load||0)*100)}%;background:var(--accent-cyan);height:4px;border-radius:2px;"></div>
                </div></td>
                <td style="color:${m.healthy?'var(--accent-green)':'var(--accent-red)'};font-size:11px;">
                  ${m.healthy?'● OK':'● Down'}
                </td>
              </tr>
            `).join('')}</tbody></table>
          `}
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">MCP Servers (${mcps.length})</span></div>
          ${mcps.length === 0 ? '<p style="padding:12px;color:var(--text-muted);">None</p>' : `
            <table class="k8s-table"><thead><tr><th>Server</th><th>Capabilities</th><th>Health</th></tr></thead>
            <tbody>${mcps.map(s => `
              <tr>
                <td class="mono" style="font-size:11px;">${escHtml(s.server_id)}</td>
                <td style="font-size:11px;">${(s.capabilities||[]).join(', ')||'—'}</td>
                <td style="color:${s.healthy?'var(--accent-green)':'var(--accent-red)'};font-size:11px;">
                  ${s.healthy?'● OK':'● Down'}
                </td>
              </tr>
            `).join('')}</tbody></table>
          `}
        </div>
      </div>
    `;
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  function _backToOverview() {
    _view = 'overview';
    _activeCluster = null;
    const state = window.AppState || { clusters: [] };
    render(state);
  }

  function _toggleCreateForm() {
    _showCreateForm = !_showCreateForm;
    const state = window.AppState || { clusters: [] };
    render(state);
  }

  async function _createCluster() {
    if (_isCreating) return;
    const name = document.getElementById('new-cluster-name')?.value?.trim();
    const workers = parseInt(document.getElementById('new-cluster-workers')?.value || '4');
    const desc = document.getElementById('new-cluster-desc')?.value?.trim() || '';
    const models = document.getElementById('new-cluster-models')?.checked ?? true;
    const mcps = document.getElementById('new-cluster-mcps')?.checked ?? true;
    const blueprints = document.getElementById('new-cluster-blueprints')?.checked ?? true;
    const feedback = document.getElementById('create-cluster-feedback');

    if (!name) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Name is required.</span>`;
      return;
    }

    _isCreating = true;
    try {
      const res = await fetch('/api/clusters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, description: desc, num_workers: workers,
          inherit_models: models, inherit_mcps: mcps, inherit_blueprints: blueprints,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Error: ${escHtml(data.detail || res.status)}</span>`;
      } else {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);">Cluster "${escHtml(name)}" created!</span>`;
        _showCreateForm = false;
        // Auto-navigate to the new cluster
        setTimeout(() => {
          _activeCluster = name;
          _view = 'detail';
          _fetchAndRenderDetail(name);
        }, 800);
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Network error: ${escHtml(e.message)}</span>`;
    } finally {
      _isCreating = false;
    }
  }

  async function _deleteCluster(name) {
    if (!confirm(`Delete cluster "${name}"? This cannot be undone.`)) return;
    try {
      const res = await fetch(`/api/clusters/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        alert(`Error: ${d.detail || res.status}`);
      }
    } catch (e) {
      alert(`Network error: ${e.message}`);
    }
  }

  function _setDetailTab(tab, clusterName, data) {
    _detailTab = tab;
    const content = document.getElementById('cluster-detail-content');
    if (content) {
      content.innerHTML = renderDetailTab(clusterName, tab, data.tasks||[], data.agents||[], data.clusterStatus||{});
      window.refreshIcons?.();
    }
  }

  async function _quickSubmit(clusterName) {
    const input = document.getElementById('cluster-quick-task');
    const desc = input?.value?.trim();
    if (!desc) return;

    const fd = new FormData();
    fd.append('description', desc);

    try {
      const res = await fetch(`/api/clusters/${encodeURIComponent(clusterName)}/tasks`, {
        method: 'POST', body: fd,
      });
      if (res.ok) {
        if (input) input.value = '';
        // Refresh detail view
        setTimeout(() => _fetchAndRenderDetail(clusterName), 500);
      }
    } catch (e) {
      console.warn('Quick submit failed:', e.message);
    }
  }

  return { render, _backToOverview, _toggleCreateForm, _createCluster,
           _deleteCluster, _setDetailTab, _quickSubmit };
})();
