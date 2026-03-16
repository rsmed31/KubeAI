/**
 * Tasks Page — submit tasks with optional file/URL, track live stage progression.
 * Stages: QUEUED → ROUTING → ASSIGNED → DATA_PROBING → SCRAPING → RAG_LOADED → EXECUTING → COMPLETE
 */
const TasksPage = (() => {
  let _filter = 'ALL';
  let _expandedId = null;
  let _isSubmitting = false;

  // Stage ordering for timeline display
  const STAGE_ORDER = [
    'queued', 'routing', 'assigned', 'data_probing',
    'scraping', 'rag_loaded', 'executing', 'complete', 'failed'
  ];

  const STAGE_LABELS = {
    queued: 'Queued',
    routing: 'Routing',
    assigned: 'Assigned',
    data_probing: 'Probing Data',
    scraping: 'Scraping URLs',
    rag_loaded: 'RAG Loaded',
    executing: 'Executing',
    complete: 'Complete',
    failed: 'Failed',
  };

  function render(state) {
    const tasks = state.tasks || [];
    const blueprints = state.blueprints || AppState.blueprints || [];

    const filtered = _filter === 'ALL'
      ? tasks
      : tasks.filter(t => {
          if (_filter === 'RUNNING') return ['RUNNING', 'ROUTING', 'ASSIGNED', 'QUEUED', 'EXECUTING'].includes(t.status);
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
        <div style="display: grid; gap: 12px;">
          <div style="display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start;">
            <div class="form-group" style="margin-bottom:0;">
              <label class="form-label">Task Description</label>
              <textarea id="task-description" class="form-textarea" rows="2"
                placeholder="Describe what the agent should do... Include URLs to scrape them automatically."></textarea>
            </div>
            <div class="form-group" style="margin-bottom:0;">
              <label class="form-label">Blueprint (optional)</label>
              <select id="task-blueprint" class="form-select" style="width:180px;">
                <option value="">Auto-route</option>
                ${blueprints.map(b => `<option value="${escHtml(b.name)}">${escHtml(b.name)}</option>`).join('')}
              </select>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end;">
            <div class="form-group" style="margin-bottom:0;">
              <label class="form-label">
                <i data-lucide="upload" class="icon-sm" style="vertical-align:middle;"></i>
                Upload Document (optional)
              </label>
              <input type="file" id="task-file" class="form-input"
                accept=".txt,.md,.csv,.json,.pdf,.py,.js,.ts,.html,.xml"
                onchange="TasksPage._onFileChange(this)" style="padding: 6px;" />
              <div id="file-info" style="font-size:11px;color:var(--text-muted);margin-top:4px;"></div>
            </div>
            <div class="form-group" style="margin-bottom:0;">
              <label class="form-label">
                <i data-lucide="link" class="icon-sm" style="vertical-align:middle;"></i>
                URL to Scrape (optional)
              </label>
              <input type="text" id="task-url" class="form-input"
                placeholder="https://example.com/docs" />
            </div>
            <button id="submit-task-btn" class="btn btn-primary" onclick="TasksPage._submitTask()" style="height:38px;">
              <i data-lucide="send" class="icon-sm"></i>
              Submit
            </button>
          </div>
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
              <th>Latency</th>
              <th>Progress</th>
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

    container.querySelectorAll('tr[data-task-id]').forEach(row => {
      row.addEventListener('click', () => {
        const id = row.dataset.taskId;
        _expandedId = _expandedId === id ? null : id;
        render(state);
      });
    });

    window.refreshIcons?.();
  }

  function renderStagePipeline(task) {
    const stages = task.stages || [];
    const stageNames = stages.map(s => s.stage.toLowerCase());
    const status = (task.status || '').toLowerCase();

    // Determine current stage
    let activeStage = 'queued';
    if (stageNames.length > 0) {
      activeStage = stageNames[stageNames.length - 1];
    }

    // Build mini timeline — only show relevant stages
    const relevantStages = stages.length > 0
      ? ['queued', ...stageNames.filter(s => s !== 'queued')]
      : ['queued'];

    const uniqueStages = [...new Set(relevantStages)];

    if (uniqueStages.length <= 1 && status === 'queued') {
      return `<span style="color:var(--text-muted);font-size:11px;">Waiting...</span>`;
    }

    return `<div style="display:flex;align-items:center;gap:2px;flex-wrap:wrap;">
      ${uniqueStages.map((s, i) => {
        const isActive = s === activeStage && status !== 'complete' && status !== 'failed';
        const isDone = STAGE_ORDER.indexOf(s) < STAGE_ORDER.indexOf(activeStage) || status === 'complete';
        const label = STAGE_LABELS[s] || s;
        let color = 'var(--text-muted)';
        if (status === 'complete' || isDone) color = 'var(--accent-green)';
        else if (isActive) color = 'var(--accent-cyan)';
        else if (s === 'failed') color = 'var(--accent-red)';

        return `<span style="font-size:10px;color:${color};white-space:nowrap;">${
          isActive ? '⟳ ' : isDone ? '✓ ' : ''
        }${label}${i < uniqueStages.length - 1 ? ' →' : ''}</span>`;
      }).join(' ')}
    </div>`;
  }

  function renderTaskRow(t) {
    const isExpanded = _expandedId === t.id;

    let rows = `
      <tr data-task-id="${escHtml(t.id)}" style="cursor:pointer;" title="Click to expand">
        <td class="mono" style="font-size:11px;">${escHtml(t.id)}</td>
        <td class="truncate" style="max-width:200px;">${escHtml(t.description || t.id)}</td>
        <td>${stateBadge(t.status)}</td>
        <td class="mono">${escHtml(t.blueprint || '—')}</td>
        <td class="mono" style="font-size:11px;">${escHtml(t.agent_id || '—')}</td>
        <td class="mono">${t.latency_ms ? Math.round(t.latency_ms) + ' ms' : '—'}</td>
        <td>${renderStagePipeline(t)}</td>
      </tr>`;

    if (isExpanded) {
      const hasResult = t.result_text && t.result_text.trim();
      const hasStages = t.stages && t.stages.length > 0;

      rows += `
        <tr class="expand-row">
          <td colspan="7">
            <div class="expand-content">
              ${hasStages ? `
                <div style="margin-bottom:12px;">
                  <strong style="color:var(--accent-cyan);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">
                    Stage History
                  </strong>
                  <div style="margin-top:6px;display:flex;flex-direction:column;gap:3px;">
                    ${t.stages.map(s => `
                      <div style="display:flex;gap:8px;align-items:baseline;font-size:11px;">
                        <span style="color:var(--text-muted);min-width:80px;">${escHtml(s.stage)}</span>
                        <span style="color:var(--text-secondary);">${escHtml(s.message || '')}</span>
                      </div>
                    `).join('')}
                  </div>
                </div>
              ` : ''}
              <div>
                <strong style="color:var(--accent-cyan);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">
                  Result
                </strong>
                <p style="margin-top:6px;white-space:pre-wrap;font-size:13px;">
                  ${hasResult ? escHtml(t.result_text) : '<em style="color:var(--text-muted)">No result yet</em>'}
                </p>
              </div>
            </div>
          </td>
        </tr>`;
    }

    return rows;
  }

  function _onFileChange(input) {
    const info = document.getElementById('file-info');
    if (!info) return;
    if (input.files && input.files[0]) {
      const f = input.files[0];
      const kb = (f.size / 1024).toFixed(1);
      const strategy = f.size > 10000 ? 'RAG+Chunking' : f.size > 2000 ? 'RAG' : 'Inline context';
      info.innerHTML = `${escHtml(f.name)} (${kb} KB) — Strategy: <strong>${strategy}</strong>`;
    } else {
      info.textContent = '';
    }
  }

  async function _submitTask() {
    if (_isSubmitting) return;
    const desc = document.getElementById('task-description')?.value?.trim();
    const blueprint = document.getElementById('task-blueprint')?.value || null;
    const fileInput = document.getElementById('task-file');
    const urlInput = document.getElementById('task-url');
    const feedback = document.getElementById('submit-feedback');
    const btn = document.getElementById('submit-task-btn');

    if (!desc) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Please enter a task description.</span>`;
      return;
    }

    _isSubmitting = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Submitting...'; }

    try {
      const hasFile = fileInput?.files?.length > 0;
      const hasUrl = urlInput?.value?.trim();

      let res;
      if (hasFile || hasUrl) {
        // Use multipart form for file/URL upload
        const fd = new FormData();
        fd.append('description', desc);
        if (blueprint) fd.append('blueprint', blueprint);
        if (hasFile) fd.append('file', fileInput.files[0]);
        if (hasUrl) fd.append('url', urlInput.value.trim());

        res = await fetch('/api/tasks/submit-with-data', {
          method: 'POST',
          body: fd,
        });
      } else {
        res = await fetch('/api/tasks/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: desc, blueprint: blueprint || null }),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Error: ${escHtml(err.detail || res.status)}</span>`;
      } else {
        const task = await res.json();
        const tid = task.task_id || task.id || '?';
        let extra = '';
        if (task.file_name) extra += ` · File: ${escHtml(task.file_name)} (${(task.file_size/1024).toFixed(1)}KB)`;
        if (task.url) extra += ` · URL: ${escHtml(task.url)}`;
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);font-size:12px;">Task submitted: <code>${escHtml(tid)}</code>${extra} — Watch the Progress column for live stages.</span>`;

        // Clear form
        const textarea = document.getElementById('task-description');
        if (textarea) textarea.value = '';
        if (fileInput) { fileInput.value = ''; }
        if (urlInput) urlInput.value = '';
        const fileInfo = document.getElementById('file-info');
        if (fileInfo) fileInfo.textContent = '';
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);font-size:12px;">Network error: ${escHtml(e.message)}</span>`;
    } finally {
      _isSubmitting = false;
      if (btn) { btn.disabled = false; btn.innerHTML = '<i data-lucide="send" class="icon-sm"></i> Submit'; }
      window.refreshIcons?.();
    }
  }

  return { render, _submitTask, _onFileChange };
})();
