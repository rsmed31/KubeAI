/**
 * Tasks Page — the kubectl get jobs / kubectl apply Job analogue.
 * Submit new tasks, track live status, and inspect results.
 */
const TasksPage = (() => {
  let _filter = 'ALL';
  let _expandedId = null;
  let _isSubmitting = false;

  function render(state) {
    const tasks = state.tasks || [];
    const blueprints = state.blueprints || AppState.blueprints || [];

    const filtered = _filter === 'ALL'
      ? tasks
      : tasks.filter(t => {
          if (_filter === 'RUNNING') return ['RUNNING', 'ROUTING', 'ASSIGNED', 'QUEUED'].includes(t.status);
          return t.status === _filter;
        });

    const sorted = [...filtered].sort((a, b) => (b.submitted_at || 0) - (a.submitted_at || 0));

    const container = document.getElementById('page-container');
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Tasks</h1>
          <p class="page-subtitle">${tasks.length} total tasks in cluster</p>
        </div>
      </div>

      <!-- Submit form -->
      <div class="card" style="margin-bottom: 20px;">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="send" class="icon-sm"></i>
            Submit Task
          </span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr auto auto; gap: 12px; align-items: end;">
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Task Description</label>
            <textarea id="task-description" class="form-textarea" rows="2"
              placeholder="Describe what the agent should do..."></textarea>
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Blueprint (optional)</label>
            <select id="task-blueprint" class="form-select" style="width:180px;">
              <option value="">Auto-route</option>
              ${blueprints.map(b => `<option value="${escHtml(b.name)}">${escHtml(b.name)}</option>`).join('')}
            </select>
          </div>
          <button id="submit-task-btn" class="btn btn-primary" onclick="TasksPage._submitTask()">
            <i data-lucide="send" class="icon-sm"></i>
            Submit
          </button>
        </div>
        <div id="submit-feedback" style="margin-top:8px;"></div>
      </div>

      <!-- Filter -->
      <div class="filter-bar">
        ${['ALL', 'RUNNING', 'COMPLETE', 'FAILED'].map(f => `
          <button class="filter-btn ${_filter === f ? 'active' : ''}" data-filter="${f}">${f}</button>
        `).join('')}
      </div>

      <!-- Task table -->
      <div class="table-container">
        <table class="k8s-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Description</th>
              <th>Status</th>
              <th>Blueprint</th>
              <th>Agent</th>
              <th>Submitted</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody id="tasks-tbody">
            ${sorted.length === 0
              ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:32px;">No tasks match filter</td></tr>`
              : sorted.map(t => renderTaskRow(t)).join('')}
          </tbody>
        </table>
      </div>
    `;

    container.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        _filter = btn.dataset.filter;
        render(state);
      });
    });

    // Re-attach expand listeners
    container.querySelectorAll('tr[data-task-id]').forEach(row => {
      row.addEventListener('click', () => {
        const id = row.dataset.taskId;
        const task = tasks.find(t => t.id === id);
        if (!task || task.status !== 'COMPLETE') return;
        _expandedId = _expandedId === id ? null : id;
        render(state);
      });
    });

    window.refreshIcons?.();
  }

  function renderTaskRow(t) {
    const isExpanded = _expandedId === t.id && t.status === 'COMPLETE';
    const expandable = t.status === 'COMPLETE'
      ? 'style="cursor:pointer;" title="Click to expand result"'
      : '';

    let rows = `
      <tr data-task-id="${escHtml(t.id)}" ${expandable}>
        <td class="mono">${escHtml(t.id)}</td>
        <td class="truncate">${escHtml(t.description)}</td>
        <td>${stateBadge(t.status)}</td>
        <td class="mono">${escHtml(t.blueprint || '—')}</td>
        <td class="mono">${escHtml(t.agent_id || '—')}</td>
        <td class="text-sm text-muted">${formatRelativeTime(t.submitted_at)}</td>
        <td class="mono">${t.latency_ms ? Math.round(t.latency_ms) + ' ms' : '—'}</td>
      </tr>`;

    if (isExpanded) {
      rows += `
        <tr class="expand-row">
          <td colspan="7">
            <div class="expand-content">
              <strong style="color:var(--accent-cyan);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">Result</strong>
              <p style="margin-top:6px;">${escHtml(t.result || 'No result')}</p>
            </div>
          </td>
        </tr>`;
    }

    return rows;
  }

  async function _submitTask() {
    if (_isSubmitting) return;
    const desc = document.getElementById('task-description')?.value?.trim();
    const blueprint = document.getElementById('task-blueprint')?.value || null;
    const feedback = document.getElementById('submit-feedback');
    const btn = document.getElementById('submit-task-btn');

    if (!desc) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Please enter a task description.</span>`;
      return;
    }

    _isSubmitting = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Submitting...'; }

    try {
      const res = await fetch('/api/tasks/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: desc, blueprint: blueprint || null }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Error: ${escHtml(err.detail || res.status)}</span>`;
      } else {
        const task = await res.json();
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);font-size:12px;">Task submitted: <code>${escHtml(task.id)}</code></span>`;
        const textarea = document.getElementById('task-description');
        if (textarea) textarea.value = '';
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Network error: ${escHtml(e.message)}</span>`;
    } finally {
      _isSubmitting = false;
      if (btn) { btn.disabled = false; btn.innerHTML = '<i data-lucide="send" class="icon-sm"></i> Submit'; }
      window.refreshIcons?.();
    }
  }

  return { render, _submitTask };
})();
