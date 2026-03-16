/**
 * Agents Page — the kubectl get pods analogue.
 * Lists all running agent instances with live state, tier, and lifecycle controls.
 */
const AgentsPage = (() => {
  let _filter = 'ALL';

  function render(state) {
    const agents = state.agents || [];
    const filtered = _filter === 'ALL'
      ? agents
      : agents.filter(a => a.state === _filter);

    const container = document.getElementById('page-container');
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Agents</h1>
          <p class="page-subtitle">${agents.length} total &bull; ${agents.filter(a => a.state === 'RUNNING').length} running</p>
        </div>
      </div>

      <div class="filter-bar">
        ${['ALL', 'RUNNING', 'IDLE', 'PENDING', 'TERMINATED'].map(f => `
          <button class="filter-btn ${_filter === f ? 'active' : ''}" data-filter="${f}">${f}</button>
        `).join('')}
      </div>

      <div class="table-container">
        <table class="k8s-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Blueprint</th>
              <th>State</th>
              <th>Tier</th>
              <th>Model</th>
              <th>Tasks Done</th>
              <th>MCP Servers</th>
              <th>Last Active</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.length === 0
              ? `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:32px;">No agents match filter</td></tr>`
              : filtered.map(a => `
              <tr>
                <td class="mono">${escHtml(a.id)}</td>
                <td class="mono">${escHtml(a.blueprint)}</td>
                <td>${stateBadge(a.state)}</td>
                <td>${tierBadge(a.tier)}</td>
                <td class="mono">${escHtml(a.model_id)}</td>
                <td class="mono" style="text-align:center;">${a.task_count}</td>
                <td>
                  ${a.mcp_servers && a.mcp_servers.length
                    ? a.mcp_servers.map(s => `<span class="cap-chip">${escHtml(s)}</span>`).join(' ')
                    : '<span class="text-muted text-sm">none</span>'}
                </td>
                <td class="text-sm text-muted">${formatRelativeTime(a.last_active)}</td>
                <td>
                  ${a.state !== 'TERMINATED'
                    ? `<button class="btn btn-danger btn-sm" data-agent-id="${escHtml(a.id)}" onclick="AgentsPage._terminate(this)">
                        Terminate
                       </button>`
                    : `<span class="text-muted text-sm">—</span>`}
                </td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
    `;

    // Attach filter buttons
    container.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        _filter = btn.dataset.filter;
        render(state);
      });
    });

    window.refreshIcons?.();
  }

  async function _terminate(btn) {
    const agentId = btn.dataset.agentId;
    btn.disabled = true;
    btn.textContent = 'Terminating...';
    try {
      const res = await fetch(`/api/agents/${encodeURIComponent(agentId)}/terminate`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(`Failed to terminate agent: ${err.detail || res.status}`);
        btn.disabled = false;
        btn.textContent = 'Terminate';
      }
      // State will update via WebSocket broadcast
    } catch (e) {
      alert(`Error: ${e.message}`);
      btn.disabled = false;
      btn.textContent = 'Terminate';
    }
  }

  // Expose for inline onclick
  return { render, _terminate };
})();
