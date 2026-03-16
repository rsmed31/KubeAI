/**
 * Overview Page — the kubectl cluster-info / dashboard home analogue.
 * Provides a high-level summary of cluster health, agent states, and recent tasks.
 */
const OverviewPage = (() => {
  let _agentChart = null;

  function render(state) {
    const agents = state.agents || [];
    const tasks = state.tasks || [];
    const metrics = state.metrics || {};

    const running = agents.filter(a => a.state === 'RUNNING').length;
    const idle = agents.filter(a => a.state === 'IDLE').length;
    const terminated = agents.filter(a => a.state === 'TERMINATED').length;
    const pending = agents.filter(a => a.state === 'PENDING').length;

    const activeTasks = tasks.filter(t => ['RUNNING', 'ROUTING', 'ASSIGNED', 'QUEUED'].includes(t.status)).length;
    const memKeys = state.memory?.short_term?.keys || '—';
    const utilPts = metrics.pool_utilization || [];
    const lastUtil = utilPts.length ? (utilPts[utilPts.length - 1].value * 100).toFixed(1) : '—';

    const health = (running > 0 && agents.filter(a => a.state !== 'TERMINATED').length > 0)
      ? 'healthy' : 'degraded';

    const recentTasks = [...tasks]
      .sort((a, b) => (b.submitted_at || 0) - (a.submitted_at || 0))
      .slice(0, 5);

    const container = document.getElementById('page-container');
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Cluster Overview</h1>
          <p class="page-subtitle">kubeai-cluster-1 &mdash; Real-time agent runtime status</p>
        </div>
      </div>

      <div class="health-banner ${health}">
        <i data-lucide="${health === 'healthy' ? 'check-circle-2' : 'alert-triangle'}" class="icon-md"></i>
        <span>Cluster status: <strong>${health.toUpperCase()}</strong> &mdash;
          ${running} agent${running !== 1 ? 's' : ''} running,
          ${activeTasks} active task${activeTasks !== 1 ? 's' : ''}
        </span>
      </div>

      <div class="stat-grid">
        <div class="stat-card cyan">
          <div class="stat-label">Running Agents</div>
          <div class="stat-value">${running}</div>
          <div class="stat-sub">${idle} idle &bull; ${pending} pending</div>
        </div>
        <div class="stat-card green">
          <div class="stat-label">Active Tasks</div>
          <div class="stat-value">${activeTasks}</div>
          <div class="stat-sub">${tasks.filter(t => t.status === 'COMPLETE').length} completed</div>
        </div>
        <div class="stat-card blue">
          <div class="stat-label">Memory Keys</div>
          <div class="stat-value">${memKeys}</div>
          <div class="stat-sub">short-term store</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-label">Pool Utilization</div>
          <div class="stat-value">${lastUtil}%</div>
          <div class="stat-sub">current load</div>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <i data-lucide="pie-chart" class="icon-sm"></i>
              Agent State Distribution
            </span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 10px;">
            ${renderStateBar('RUNNING', running, agents.length, 'green')}
            ${renderStateBar('IDLE', idle, agents.length, 'yellow')}
            ${renderStateBar('PENDING', pending, agents.length, 'blue')}
            ${renderStateBar('TERMINATED', terminated, agents.length, 'gray')}
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <span class="card-title">
              <i data-lucide="activity" class="icon-sm"></i>
              Throughput (last 30 points)
            </span>
          </div>
          <div style="height: 140px; position: relative;">
            <canvas id="overview-throughput-chart"></canvas>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="list-checks" class="icon-sm"></i>
            Recent Tasks
          </span>
          <a href="#tasks" class="btn btn-ghost btn-sm">View All</a>
        </div>
        <div class="table-container">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Description</th>
                <th>Status</th>
                <th>Blueprint</th>
                <th>Submitted</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              ${recentTasks.length === 0
                ? `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px;">No tasks yet</td></tr>`
                : recentTasks.map(t => `
                <tr>
                  <td class="mono">${escHtml(t.id)}</td>
                  <td class="truncate" style="max-width:220px;">${escHtml(t.description)}</td>
                  <td>${stateBadge(t.status)}</td>
                  <td class="mono">${escHtml(t.blueprint || '—')}</td>
                  <td class="text-muted text-sm">${formatRelativeTime(t.submitted_at)}</td>
                  <td class="mono">${t.latency_ms ? Math.round(t.latency_ms) + ' ms' : '—'}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

    window.refreshIcons?.();
    _drawThroughputChart(metrics.throughput || []);
  }

  function renderStateBar(label, count, total, color) {
    const pct = total > 0 ? (count / total * 100).toFixed(0) : 0;
    const colorVar = {
      green: 'var(--accent-green)',
      yellow: 'var(--accent-yellow)',
      blue: 'var(--accent-blue)',
      gray: 'var(--text-muted)',
    }[color];

    return `
      <div>
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
          <span style="font-size:12px;color:var(--text-secondary);">${label}</span>
          <span style="font-size:12px;font-family:var(--font-mono);color:var(--text-primary);">${count} (${pct}%)</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width:${pct}%;background:${colorVar};"></div>
        </div>
      </div>`;
  }

  function _drawThroughputChart(points) {
    const canvas = document.getElementById('overview-throughput-chart');
    if (!canvas) return;

    if (_agentChart) {
      _agentChart.destroy();
      _agentChart = null;
    }

    const labels = points.map(() => '');
    const data = points.map(p => p.value.toFixed(2));

    _agentChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data,
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6,182,212,0.08)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: {
            display: true,
            grid: { color: 'rgba(45,55,72,0.5)' },
            ticks: { color: '#64748b', font: { size: 10 } },
          },
        },
        animation: false,
      },
    });
  }

  return { render };
})();
