/**
 * Pools Page — manage LLM model pool and MCP server pool.
 * Kubernetes analogue: Node pool management + Service mesh registry.
 * Shows both pools in same page with different tabbed views.
 */
const PoolsPage = (() => {
  let _view = 'models'; // 'models' | 'mcps'
  let _isRegistering = false;

  function render(state) {
    const poolModels = state.pool_models || [];
    const container = document.getElementById('page-container');

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Pools</h1>
          <p class="page-subtitle">Manage LLM model pool and MCP server pool</p>
        </div>
      </div>

      <!-- Tabs -->
      <div class="filter-bar" style="margin-bottom:20px;">
        <button class="filter-btn ${_view === 'models' ? 'active' : ''}" onclick="PoolsPage._setView('models')">
          <i data-lucide="cpu" class="icon-sm"></i> LLM Models (${poolModels.length})
        </button>
        <button class="filter-btn ${_view === 'mcps' ? 'active' : ''}" onclick="PoolsPage._setView('mcps')">
          <i data-lucide="plug" class="icon-sm"></i> MCP Servers
        </button>
      </div>

      ${_view === 'models' ? renderModelsView(poolModels) : renderMCPsView()}
    `;

    window.refreshIcons?.();
  }

  function renderModelsView(models) {
    return `
      <!-- Register model form -->
      <div class="card" style="margin-bottom:20px;">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="plus-circle" class="icon-sm"></i>
            Register Model
          </span>
        </div>
        <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;gap:10px;align-items:end;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Model ID (LiteLLM format)</label>
            <input type="text" id="model-id" class="form-input" placeholder="claude-sonnet-4-5 or ollama/llama3" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Provider</label>
            <input type="text" id="model-provider" class="form-input" placeholder="anthropic" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Tier</label>
            <select id="model-tier" class="form-select">
              <option value="fast">Fast</option>
              <option value="capable" selected>Capable</option>
              <option value="best">Best</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Cost/1k tokens</label>
            <input type="number" id="model-cost" class="form-input" value="0.003" step="0.001" min="0" />
          </div>
          <button class="btn btn-primary" onclick="PoolsPage._registerModel()" style="height:38px;">
            <i data-lucide="plus" class="icon-sm"></i> Register
          </button>
        </div>
        <div id="model-feedback" style="margin-top:8px;"></div>
      </div>

      <!-- Models table -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Registered Models (${models.length})</span>
        </div>
        <div class="table-container">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>Model ID</th>
                <th>Provider</th>
                <th>Tier</th>
                <th>Cost/1k</th>
                <th>Load</th>
                <th>Health</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${models.length === 0
                ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px;">No models registered</td></tr>`
                : models.map(m => `
                  <tr>
                    <td class="mono">${escHtml(m.model_id)}</td>
                    <td class="mono">${escHtml(m.provider)}</td>
                    <td>${tierBadge(m.tier)}</td>
                    <td class="mono">$${escHtml(String(m.cost_per_1k))}</td>
                    <td>
                      <div style="display:flex;align-items:center;gap:6px;">
                        <div style="flex:1;background:var(--border-color);border-radius:2px;height:4px;">
                          <div style="width:${Math.round((m.load||0)*100)}%;background:${(m.load||0) > 0.85 ? 'var(--accent-red)' : 'var(--accent-cyan)'};height:4px;border-radius:2px;"></div>
                        </div>
                        <span class="mono" style="font-size:10px;">${Math.round((m.load||0)*100)}%</span>
                      </div>
                    </td>
                    <td>${m.healthy
                      ? '<span style="color:var(--accent-green);font-size:12px;">● Healthy</span>'
                      : '<span style="color:var(--accent-red);font-size:12px;">● Unhealthy</span>'
                    }</td>
                    <td>
                      <button class="btn btn-sm" style="font-size:11px;padding:2px 8px;background:var(--accent-red);color:white;border:none;border-radius:4px;cursor:pointer;"
                        onclick="PoolsPage._removeModel('${escHtml(m.model_id)}')">
                        Remove
                      </button>
                    </td>
                  </tr>
                `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderMCPsView() {
    return `
      <!-- Register MCP form -->
      <div class="card" style="margin-bottom:20px;">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="plus-circle" class="icon-sm"></i>
            Register MCP Server
          </span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 2fr 2fr auto;gap:10px;align-items:end;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Server ID</label>
            <input type="text" id="mcp-id" class="form-input" placeholder="my_tool" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Endpoint URL</label>
            <input type="text" id="mcp-endpoint" class="form-input" placeholder="http://localhost:9001/mcp" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Capabilities (comma-separated)</label>
            <input type="text" id="mcp-capabilities" class="form-input" placeholder="web_search, fetch_url" />
          </div>
          <button class="btn btn-primary" onclick="PoolsPage._registerMCP()" style="height:38px;">
            <i data-lucide="plus" class="icon-sm"></i> Register
          </button>
        </div>
        <div id="mcp-feedback" style="margin-top:8px;"></div>
      </div>

      <!-- MCPs are loaded from /api/pools — fetch them live -->
      <div class="card" id="mcps-card">
        <div class="card-header">
          <span class="card-title">Registered MCP Servers</span>
        </div>
        <div id="mcps-list" style="padding:12px;color:var(--text-muted);font-size:13px;">Loading...</div>
      </div>
    `;

    // Fetch MCPs after render
    setTimeout(() => _loadMCPs(), 0);
  }

  async function _loadMCPs() {
    try {
      const res = await fetch('/api/pools');
      if (!res.ok) return;
      const data = await res.json();
      const mcps = data.mcps || [];
      const container = document.getElementById('mcps-list');
      if (!container) return;

      if (mcps.length === 0) {
        container.innerHTML = '<p style="text-align:center;padding:24px;color:var(--text-muted);">No MCP servers registered</p>';
        return;
      }

      container.innerHTML = `
        <table class="k8s-table">
          <thead>
            <tr><th>Server ID</th><th>Endpoint</th><th>Capabilities</th><th>Health</th></tr>
          </thead>
          <tbody>
            ${mcps.map(m => `
              <tr>
                <td class="mono">${escHtml(m.server_id)}</td>
                <td class="mono" style="font-size:11px;">${escHtml(m.endpoint)}</td>
                <td>${(m.capabilities || []).map(c => `<span style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:3px;padding:1px 6px;font-size:11px;margin-right:3px;">${escHtml(c)}</span>`).join('')}</td>
                <td>${m.healthy
                  ? '<span style="color:var(--accent-green);font-size:12px;">● Healthy</span>'
                  : '<span style="color:var(--accent-red);font-size:12px;">● Unhealthy</span>'
                }</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      window.refreshIcons?.();
    } catch (e) {
      const container = document.getElementById('mcps-list');
      if (container) container.textContent = 'Failed to load MCPs.';
    }
  }

  function tierBadge(tier) {
    const colors = { fast: 'var(--accent-cyan)', capable: 'var(--accent-yellow, #f59e0b)', best: 'var(--accent-purple, #8b5cf6)' };
    const color = colors[tier] || 'var(--text-muted)';
    return `<span style="color:${color};font-size:11px;font-weight:600;text-transform:uppercase;">${escHtml(tier || '—')}</span>`;
  }

  async function _registerModel() {
    if (_isRegistering) return;
    const modelId = document.getElementById('model-id')?.value?.trim();
    const provider = document.getElementById('model-provider')?.value?.trim();
    const tier = document.getElementById('model-tier')?.value;
    const cost = parseFloat(document.getElementById('model-cost')?.value || '0.003');
    const feedback = document.getElementById('model-feedback');

    if (!modelId || !provider) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Model ID and Provider are required.</span>`;
      return;
    }

    _isRegistering = true;
    try {
      const res = await fetch('/api/pools/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId, provider, tier, cost_per_1k_tokens: cost }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Error: ${escHtml(data.detail || res.status)}</span>`;
      } else {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);font-size:12px;">Model ${escHtml(modelId)} registered (tier: ${escHtml(tier)})</span>`;
        document.getElementById('model-id').value = '';
        document.getElementById('model-provider').value = '';
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Network error: ${escHtml(e.message)}</span>`;
    } finally {
      _isRegistering = false;
    }
  }

  async function _registerMCP() {
    const serverId = document.getElementById('mcp-id')?.value?.trim();
    const endpoint = document.getElementById('mcp-endpoint')?.value?.trim();
    const capabilitiesRaw = document.getElementById('mcp-capabilities')?.value?.trim();
    const feedback = document.getElementById('mcp-feedback');

    if (!serverId || !endpoint) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Server ID and Endpoint are required.</span>`;
      return;
    }

    const capabilities = capabilitiesRaw ? capabilitiesRaw.split(',').map(s => s.trim()).filter(Boolean) : [];

    try {
      const res = await fetch('/api/pools/mcps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_id: serverId, endpoint, capabilities }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Error: ${escHtml(data.detail || res.status)}</span>`;
      } else {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);font-size:12px;">MCP server ${escHtml(serverId)} registered.</span>`;
        document.getElementById('mcp-id').value = '';
        document.getElementById('mcp-endpoint').value = '';
        document.getElementById('mcp-capabilities').value = '';
        _loadMCPs();
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Network error: ${escHtml(e.message)}</span>`;
    }
  }

  async function _removeModel(modelId) {
    if (!confirm(`Remove model ${modelId}?`)) return;
    try {
      const res = await fetch(`/api/pools/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(`Error: ${data.detail || res.status}`);
      }
    } catch (e) {
      alert(`Network error: ${e.message}`);
    }
  }

  function _setView(view) {
    _view = view;
    const state = window.AppState || { pool_models: [] };
    render(state);
  }

  return { render, _setView, _registerModel, _registerMCP, _removeModel };
})();
