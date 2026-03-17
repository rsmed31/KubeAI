/**
 * Pools Page — manage LLM model pool and MCP server pool.
 * Kubernetes analogue: Node pool management + Service mesh registry.
 * Shows both pools in same page with different tabbed views.
 */
const PoolsPage = (() => {
  let _view = 'models'; // 'models' | 'mcps' | 'orchestrator'
  let _isRegistering = false;
  let _providers = [];        // cached from /api/providers
  let _orchConfig = null;     // cached from /api/orchestrator
  let _orchDecisions = [];    // cached from /api/orchestrator/decisions

  function render(state) {
    const poolModels = state.pool_models || [];
    const poolMCPs   = state.pool_mcps   || [];
    const container  = document.getElementById('page-container');

    // Fetch providers once (cache in _providers)
    if (_providers.length === 0) {
      fetch('/api/providers').then(r => r.json()).then(data => {
        _providers = data;
        render(window.AppState || state);
      }).catch(() => {});
    }

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
          <i data-lucide="plug" class="icon-sm"></i> MCP Servers (${poolMCPs.length})
        </button>
        <button class="filter-btn ${_view === 'orchestrator' ? 'active' : ''}" onclick="PoolsPage._setView('orchestrator')">
          <i data-lucide="git-merge" class="icon-sm"></i> Orchestrator
        </button>
      </div>

      ${_view === 'models' ? renderModelsView(poolModels) : _view === 'mcps' ? renderMCPsView(poolMCPs) : renderOrchestratorView()}
    `;

    window.refreshIcons?.();
  }

  function renderModelsView(models) {
    // Build provider options from cache
    const providerOptions = _providers.map(p => {
      const indicator = p.has_key
        ? '<span style="color:var(--accent-green);font-size:10px;">●</span>'
        : '<span style="color:var(--text-muted);font-size:10px;">○</span>';
      return `<option value="${escHtml(p.id)}">${p.name} ${p.has_key ? '✓' : ''}</option>`;
    }).join('');

    // Provider status pills
    const providerPills = _providers.map(p => `
      <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;
        padding:2px 8px;border-radius:10px;border:1px solid ${p.has_key ? 'var(--accent-green)' : 'var(--border-color)'};
        color:${p.has_key ? 'var(--accent-green)' : 'var(--text-muted)'};margin:2px;">
        ${p.has_key ? '●' : '○'} ${escHtml(p.name)}
      </span>
    `).join('');

    return `
      <!-- Provider status strip -->
      ${_providers.length > 0 ? `
        <div class="card" style="margin-bottom:16px;padding:12px 16px;">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em;">Provider status (● key detected in env)</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;">${providerPills}</div>
        </div>
      ` : ''}

      <!-- Register model form -->
      <div class="card" style="margin-bottom:20px;">
        <div class="card-header">
          <span class="card-title"><i data-lucide="plus-circle" class="icon-sm"></i> Register Model</span>
        </div>

        <!-- Row 1: provider + model + tier + cost -->
        <div style="display:grid;grid-template-columns:1fr 2fr 1fr 1fr;gap:10px;margin-bottom:10px;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Provider *</label>
            <select id="model-provider" class="form-select" onchange="PoolsPage._onProviderChange()">
              <option value="">— select —</option>
              ${providerOptions || '<option value="anthropic">Anthropic</option>'}
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Model ID (LiteLLM format) *</label>
            <input type="text" id="model-id" class="form-input" placeholder="e.g. claude-sonnet-4-6" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Tier</label>
            <select id="model-tier" class="form-select" onchange="PoolsPage._onTierChange()">
              <option value="fast">Fast</option>
              <option value="capable" selected>Capable</option>
              <option value="best">Best</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Cost/1k tokens ($)</label>
            <input type="number" id="model-cost" class="form-input" value="0.003" step="0.001" min="0" />
          </div>
        </div>

        <!-- Row 2: API key + base URL (conditional) -->
        <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:10px;align-items:end;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">API Key <span style="font-size:10px;color:var(--text-muted);">(stored in memory only)</span></label>
            <input type="password" id="model-api-key" class="form-input" placeholder="sk-... or leave blank to use env var" />
          </div>
          <div class="form-group" style="margin-bottom:0;" id="base-url-group">
            <label class="form-label">Base URL <span style="font-size:10px;color:var(--text-muted);" id="base-url-hint">(required for Ollama/vLLM/Azure)</span></label>
            <input type="text" id="model-base-url" class="form-input" placeholder="http://localhost:11434" />
          </div>
          <button class="btn btn-primary" onclick="PoolsPage._registerModel()" style="height:38px;white-space:nowrap;">
            <i data-lucide="plus" class="icon-sm"></i> Register
          </button>
        </div>
        <div id="model-feedback" style="margin-top:8px;font-size:12px;"></div>
      </div>

      <!-- Models table -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Registered Models (${models.length})</span>
        </div>
        <div class="table-container">
          <table class="k8s-table">
            <thead>
              <tr><th>Model ID</th><th>Provider</th><th>Tier</th><th>Cost/1k</th><th>Load</th><th>Health</th><th>Key</th><th>Actions</th></tr>
            </thead>
            <tbody>
              ${models.length === 0
                ? `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px;">No models registered</td></tr>`
                : models.map(m => `
                  <tr>
                    <td class="mono" style="font-size:12px;">${escHtml(m.model_id)}</td>
                    <td style="font-size:12px;">${escHtml(m.provider)}</td>
                    <td>${tierBadge(m.tier)}</td>
                    <td class="mono" style="font-size:11px;">$${(m.cost_per_1k||0).toFixed(4)}</td>
                    <td>
                      <div style="display:flex;align-items:center;gap:5px;">
                        <div style="flex:1;background:var(--border-color);border-radius:2px;height:4px;min-width:40px;">
                          <div style="width:${Math.round((m.load||0)*100)}%;background:${(m.load||0)>0.85?'var(--accent-red)':'var(--accent-cyan)'};height:4px;border-radius:2px;"></div>
                        </div>
                        <span class="mono" style="font-size:10px;">${Math.round((m.load||0)*100)}%</span>
                      </div>
                    </td>
                    <td>${m.healthy
                      ? '<span style="color:var(--accent-green);font-size:12px;">● OK</span>'
                      : '<span style="color:var(--accent-red);font-size:12px;">● Down</span>'
                    }</td>
                    <td style="font-size:11px;color:${m.has_key?'var(--accent-green)':'var(--text-muted)'};">${m.has_key?'✓ set':'—'}</td>
                    <td>
                      <button class="btn" style="font-size:11px;padding:2px 8px;background:var(--accent-red);color:white;border:none;border-radius:4px;"
                        onclick="PoolsPage._removeModel('${escHtml(m.model_id)}')">Remove</button>
                    </td>
                  </tr>
                `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderMCPsView(mcps) {
    const mcpRows = mcps.length === 0
      ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:24px;">No MCP servers registered</td></tr>`
      : mcps.map(m => `
          <tr>
            <td class="mono">${escHtml(m.server_id)}</td>
            <td class="mono" style="font-size:11px;">${escHtml(m.endpoint)}</td>
            <td>${(m.capabilities || []).map(c => `<span style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:3px;padding:1px 6px;font-size:11px;margin-right:3px;">${escHtml(c)}</span>`).join('')}</td>
            <td>${m.healthy
              ? '<span style="color:var(--accent-green);font-size:12px;">● Healthy</span>'
              : '<span style="color:var(--accent-red);font-size:12px;">● Unhealthy</span>'
            }</td>
            <td>
              <button class="btn" style="font-size:11px;padding:2px 8px;background:var(--accent-red);color:white;border:none;border-radius:4px;"
                onclick="PoolsPage._removeMCP('${escHtml(m.server_id)}')">Remove</button>
            </td>
          </tr>
        `).join('');

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

      <!-- MCPs table — rendered from WS state, no async fetch needed -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Registered MCP Servers (${mcps.length})</span>
        </div>
        <div class="table-container">
          <table class="k8s-table">
            <thead>
              <tr><th>Server ID</th><th>Endpoint</th><th>Capabilities</th><th>Health</th><th>Actions</th></tr>
            </thead>
            <tbody>${mcpRows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ── Orchestrator view ────────────────────────────────────────────────────

  function renderOrchestratorView() {
    const cfg = _orchConfig;
    if (!cfg) {
      // Fetch and re-render
      fetch('/api/orchestrator').then(r => r.json()).then(data => {
        _orchConfig = data;
        return fetch('/api/orchestrator/decisions?limit=50');
      }).then(r => r.json()).then(decisions => {
        _orchDecisions = decisions;
        const state = window.AppState || {};
        render(state);
      }).catch(() => {});
      return `<div style="padding:40px;text-align:center;color:var(--text-muted);">
        <div class="spinner" style="width:20px;height:20px;margin:0 auto 12px;"></div>
        Loading orchestrator config...
      </div>`;
    }

    const models = cfg.available_models || [];
    const modelOptions = [
      `<option value="">auto (largest registered model)</option>`,
      ...models.map(m => `
        <option value="${escHtml(m.model_id)}" ${cfg.routing_model_override === m.model_id ? 'selected' : ''}>
          ${escHtml(m.model_id)} · ${escHtml(m.tier)} · ${escHtml(m.provider)}
        </option>
      `),
    ].join('');

    // Routing decisions stats
    const decisions = _orchDecisions;
    const avgConf = decisions.length > 0
      ? (decisions.reduce((s, d) => s + (d.confidence || 0), 0) / decisions.length).toFixed(3)
      : '—';
    const blueprintCounts = {};
    decisions.forEach(d => { blueprintCounts[d.blueprint] = (blueprintCounts[d.blueprint] || 0) + 1; });
    const topBlueprint = Object.entries(blueprintCounts).sort((a, b) => b[1] - a[1])[0];

    return `
      <!-- Config card -->
      <div class="card" style="margin-bottom:20px;">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="git-merge" class="icon-sm"></i>
            Routing Configuration
          </span>
          <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted);">
            <i data-lucide="cpu" class="icon-xs"></i>
            Active: <span style="color:var(--accent-cyan);font-weight:600;">${escHtml(cfg.effective_routing_model)}</span>
            <span style="color:var(--text-muted);">(${escHtml(cfg.effective_routing_provider)})</span>
            ${cfg.routing_model_override ? `<span style="background:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid #f59e0b;border-radius:3px;padding:1px 6px;font-size:10px;">PINNED</span>` : `<span style="background:rgba(6,182,212,0.1);color:var(--accent-cyan);border:1px solid var(--accent-cyan);border-radius:3px;padding:1px 6px;font-size:10px;">AUTO</span>`}
          </div>
        </div>

        <div style="display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:12px;align-items:end;margin-bottom:12px;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Routing Model
              <span style="font-size:10px;color:var(--text-muted);">— model used for blueprint scoring (always the largest by default)</span>
            </label>
            <select id="orch-model-override" class="form-select">
              ${modelOptions}
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Min Confidence
              <span style="font-size:10px;color:var(--text-muted);">0.0 = accept all</span>
            </label>
            <input type="number" id="orch-min-confidence" class="form-input"
              value="${cfg.min_confidence ?? 0}" step="0.05" min="0" max="1" />
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Decomposition</label>
            <select id="orch-decompose" class="form-select">
              <option value="true"  ${cfg.decompose_enabled ? 'selected' : ''}>Enabled</option>
              <option value="false" ${!cfg.decompose_enabled ? 'selected' : ''}>Disabled</option>
            </select>
          </div>
          <button class="btn btn-primary" onclick="PoolsPage._saveOrchConfig()" style="height:38px;">
            <i data-lucide="save" class="icon-sm"></i> Apply
          </button>
        </div>
        <div id="orch-feedback" style="font-size:12px;"></div>
      </div>

      <!-- Stats row -->
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">
        ${[
          ['activity', 'Total Decisions', decisions.length, ''],
          ['bar-chart-2', 'Avg Confidence', avgConf, ''],
          ['award', 'Top Blueprint', topBlueprint ? escHtml(topBlueprint[0]) : '—', topBlueprint ? `${topBlueprint[1]} tasks` : ''],
        ].map(([icon, label, val, sub]) => `
          <div style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:6px;padding:14px;">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:flex;align-items:center;gap:4px;">
              <i data-lucide="${icon}" class="icon-xs"></i> ${label}
            </div>
            <div style="font-size:22px;font-weight:700;">${val}</div>
            ${sub ? `<div style="font-size:11px;color:var(--text-muted);">${sub}</div>` : ''}
          </div>
        `).join('')}
      </div>

      <!-- Test routing card -->
      <div class="card" style="margin-bottom:20px;">
        <div class="card-header">
          <span class="card-title"><i data-lucide="flask-conical" class="icon-sm"></i> Test Routing (dry-run)</span>
        </div>
        <div style="display:flex;gap:10px;align-items:flex-end;">
          <div class="form-group" style="margin-bottom:0;flex:1;">
            <label class="form-label">Task description</label>
            <input type="text" id="orch-test-task" class="form-input" placeholder="e.g. Write a sorting algorithm in Python" />
          </div>
          <button class="btn btn-primary" onclick="PoolsPage._testRoute()" style="height:38px;">
            <i data-lucide="play" class="icon-sm"></i> Route
          </button>
        </div>
        <div id="orch-test-result" style="margin-top:12px;"></div>
      </div>

      <!-- Recent decisions table -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Recent Routing Decisions (${decisions.length})</span>
          <button class="btn" style="font-size:11px;" onclick="PoolsPage._refreshOrch()">↻ Refresh</button>
        </div>
        ${decisions.length === 0
          ? `<p style="padding:16px;color:var(--text-muted);text-align:center;">No routing decisions recorded yet.</p>`
          : `<div class="table-container">
              <table class="k8s-table">
                <thead><tr><th>Task ID</th><th>Blueprint</th><th>Model</th><th>Confidence</th><th>Latency</th><th>Time</th></tr></thead>
                <tbody>
                  ${[...decisions].reverse().slice(0, 50).map(d => `
                    <tr>
                      <td class="mono" style="font-size:11px;">${escHtml(d.task_id)}</td>
                      <td><span style="background:var(--bg-elevated);border:1px solid var(--border-color);border-radius:3px;padding:1px 6px;font-size:11px;">${escHtml(d.blueprint)}</span></td>
                      <td class="mono" style="font-size:11px;">${escHtml(d.model_id)}</td>
                      <td>
                        <div style="display:flex;align-items:center;gap:5px;">
                          <div style="width:60px;background:var(--border-color);border-radius:2px;height:4px;">
                            <div style="width:${Math.round((d.confidence||0)*100)}%;background:${(d.confidence||0)>0.7?'var(--accent-green)':(d.confidence||0)>0.4?'var(--accent-yellow,#f59e0b)':'var(--accent-red)'};height:4px;border-radius:2px;"></div>
                          </div>
                          <span class="mono" style="font-size:11px;">${((d.confidence||0)*100).toFixed(0)}%</span>
                        </div>
                      </td>
                      <td class="mono" style="font-size:11px;">${d.latency_ms ? Math.round(d.latency_ms)+'ms' : '—'}</td>
                      <td style="font-size:11px;color:var(--text-muted);">${d.timestamp ? new Date(d.timestamp*1000).toLocaleTimeString() : '—'}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>`
        }
      </div>
    `;
  }

  async function _saveOrchConfig() {
    const modelOverride = document.getElementById('orch-model-override')?.value || null;
    const minConf       = parseFloat(document.getElementById('orch-min-confidence')?.value || '0');
    const decompose     = document.getElementById('orch-decompose')?.value === 'true';
    const feedback      = document.getElementById('orch-feedback');

    try {
      const res = await fetch('/api/orchestrator', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          routing_model_override: modelOverride || null,
          min_confidence: minConf,
          decompose_enabled: decompose,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Error: ${escHtml(data.detail || res.status)}</span>`;
      } else {
        _orchConfig = data;
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);">✓ Config applied — routing via ${escHtml(data.effective_routing_model)}</span>`;
        setTimeout(() => { if(feedback) feedback.innerHTML = ''; }, 3000);
        render(window.AppState || {});
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Network error: ${escHtml(e.message)}</span>`;
    }
  }

  async function _testRoute() {
    const task   = document.getElementById('orch-test-task')?.value?.trim();
    const result = document.getElementById('orch-test-result');
    if (!task || !result) return;

    result.innerHTML = `<div style="color:var(--text-muted);font-size:12px;">Routing... <span class="spinner" style="display:inline-block;width:12px;height:12px;"></span></div>`;
    try {
      const res  = await fetch('/api/orchestrator/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task }),
      });
      const data = await res.json();
      if (!res.ok) {
        result.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">Error: ${escHtml(data.detail || res.status)}</div>`;
        return;
      }
      const rows = (data.scores || []).map((s, i) => `
        <tr style="${i===0?'background:rgba(6,182,212,0.06);':''}">
          <td style="font-size:12px;${i===0?'color:var(--accent-cyan);font-weight:600;':''}">
            ${i===0?'🏆 ':''} ${escHtml(s.blueprint)}
          </td>
          <td style="font-size:11px;color:var(--text-muted);">${escHtml(s.tier)}</td>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <div style="width:80px;background:var(--border-color);border-radius:2px;height:5px;">
                <div style="width:${Math.round(s.score*100)}%;background:${s.score>0.7?'var(--accent-green)':s.score>0.4?'var(--accent-yellow,#f59e0b)':'var(--border-color)'};height:5px;border-radius:2px;"></div>
              </div>
              <span class="mono" style="font-size:12px;">${(s.score*100).toFixed(1)}%</span>
            </div>
          </td>
        </tr>
      `).join('');
      result.innerHTML = `
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">Scored via <span class="mono">${escHtml(data.routing_model)}</span></div>
        <table class="k8s-table" style="max-width:500px;">
          <thead><tr><th>Blueprint</th><th>Tier</th><th>Score</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
      window.refreshIcons?.();
    } catch (e) {
      result.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">Error: ${escHtml(e.message)}</div>`;
    }
  }

  async function _refreshOrch() {
    _orchConfig = null;
    _orchDecisions = [];
    render(window.AppState || {});
  }

  function tierBadge(tier) {
    const colors = { fast: 'var(--accent-cyan)', capable: 'var(--accent-yellow, #f59e0b)', best: 'var(--accent-purple, #8b5cf6)' };
    const color = colors[tier] || 'var(--text-muted)';
    return `<span style="color:${color};font-size:11px;font-weight:600;text-transform:uppercase;">${escHtml(tier || '—')}</span>`;
  }

  function _onProviderChange() {
    const providerEl = document.getElementById('model-provider');
    const modelIdEl  = document.getElementById('model-id');
    const tierEl     = document.getElementById('model-tier');
    const baseUrlEl  = document.getElementById('model-base-url');
    const baseUrlGrp = document.getElementById('base-url-group');
    if (!providerEl) return;

    const pid = providerEl.value;
    const p   = _providers.find(x => x.id === pid);
    if (!p) return;

    // Auto-fill model ID suggestion from tier
    const tier = tierEl?.value || 'capable';
    const suggested = p.default_models?.[tier] || '';
    if (modelIdEl && !modelIdEl.value) modelIdEl.value = suggested;

    // Show/hide base URL field
    if (baseUrlGrp) baseUrlGrp.style.opacity = p.needs_base_url ? '1' : '0.4';
    if (baseUrlEl && p.needs_base_url && p.default_base_url && !baseUrlEl.value) {
      baseUrlEl.placeholder = p.default_base_url;
    }
  }

  function _onTierChange() {
    const providerEl = document.getElementById('model-provider');
    const modelIdEl  = document.getElementById('model-id');
    const tierEl     = document.getElementById('model-tier');
    if (!providerEl || !modelIdEl || !tierEl) return;

    const pid = providerEl.value;
    const p   = _providers.find(x => x.id === pid);
    if (!p) return;

    const suggested = p.default_models?.[tierEl.value] || '';
    if (suggested) modelIdEl.value = suggested;
  }

  async function _registerModel() {
    if (_isRegistering) return;
    const modelId  = document.getElementById('model-id')?.value?.trim();
    const provider = document.getElementById('model-provider')?.value?.trim();
    const tier     = document.getElementById('model-tier')?.value;
    const cost     = parseFloat(document.getElementById('model-cost')?.value || '0.003');
    const apiKey   = document.getElementById('model-api-key')?.value?.trim() || '';
    const baseUrl  = document.getElementById('model-base-url')?.value?.trim() || '';
    const feedback = document.getElementById('model-feedback');

    if (!modelId || !provider) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Model ID and Provider are required.</span>`;
      return;
    }

    _isRegistering = true;
    try {
      const res = await fetch('/api/pools/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_id: modelId, provider, tier,
          cost_per_1k_tokens: cost,
          api_key: apiKey,
          base_url: baseUrl,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Error: ${escHtml(data.detail || res.status)}</span>`;
      } else {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);">✓ ${escHtml(modelId)} registered (${escHtml(tier)})</span>`;
        document.getElementById('model-id').value = '';
        document.getElementById('model-api-key').value = '';
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Network error: ${escHtml(e.message)}</span>`;
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
        // MCPs are refreshed via WebSocket state push
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

  async function _removeMCP(serverId) {
    if (!confirm(`Remove MCP server ${serverId}?`)) return;
    try {
      const res = await fetch(`/api/pools/mcps/${encodeURIComponent(serverId)}`, { method: 'DELETE' });
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
    const state = window.AppState || { pool_models: [], pool_mcps: [] };
    render(state);
  }

  return { render, _setView, _registerModel, _registerMCP, _removeModel, _removeMCP,
           _onProviderChange, _onTierChange, _saveOrchConfig, _testRoute, _refreshOrch };
})();
