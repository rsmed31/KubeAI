/**
 * Monitoring Page — the Prometheus + Grafana analogue for KubeAI.
 * Renders real-time line charts for all 6 core KubeAI metrics.
 */
const MonitoringPage = (() => {
  // Chart instances — persist across re-renders to enable update-in-place
  const _charts = {};

  const METRIC_CONFIG = [
    {
      key: 'throughput',
      label: 'Throughput',
      unit: 'tasks/s',
      color: '#06b6d4',
      format: v => v.toFixed(2),
      yLabel: 'tasks/s',
    },
    {
      key: 'latency_ms',
      label: 'Latency',
      unit: 'ms',
      color: '#f59e0b',
      format: v => Math.round(v),
      yLabel: 'ms',
    },
    {
      key: 'cost_usd',
      label: 'Cost',
      unit: 'USD/task',
      color: '#10b981',
      format: v => '$' + v.toFixed(4),
      yLabel: 'USD',
    },
    {
      key: 'eval_score',
      label: 'Eval Score',
      unit: '0–1',
      color: '#8b5cf6',
      format: v => v.toFixed(3),
      yLabel: 'score',
    },
    {
      key: 'pool_utilization',
      label: 'Pool Utilization',
      unit: '%',
      color: '#3b82f6',
      format: v => (v * 100).toFixed(1) + '%',
      yLabel: '%',
    },
    {
      key: 'error_rate',
      label: 'Error Rate',
      unit: '%',
      color: '#ef4444',
      format: v => (v * 100).toFixed(2) + '%',
      yLabel: 'rate',
    },
  ];

  function render(state) {
    const metrics = state.metrics || {};

    // Check if page is already rendered (just update charts)
    const container = document.getElementById('page-container');
    const alreadyRendered = container.querySelector('.chart-grid') !== null;

    if (!alreadyRendered) {
      _buildLayout(container);
    }

    // Update each chart
    METRIC_CONFIG.forEach(cfg => {
      const points = metrics[cfg.key] || [];
      const values = points.map(p => cfg.key === 'pool_utilization' ? p.value * 100 : p.value);
      const labels = points.map(() => '');
      const lastVal = values.length ? values[values.length - 1] : null;
      const prevVal = values.length > 1 ? values[values.length - 2] : null;

      // Update summary values
      const valEl = document.getElementById(`metric-val-${cfg.key}`);
      if (valEl && lastVal !== null) valEl.textContent = cfg.format(cfg.key === 'pool_utilization' ? lastVal / 100 : lastVal);

      const trendEl = document.getElementById(`metric-trend-${cfg.key}`);
      if (trendEl && lastVal !== null && prevVal !== null) {
        const up = lastVal > prevVal;
        const isGoodUp = !['latency_ms', 'cost_usd', 'error_rate'].includes(cfg.key);
        trendEl.textContent = up ? '↑' : '↓';
        trendEl.className = `chart-trend ${up === isGoodUp ? 'trend-up' : 'trend-down'}`;
      }

      // Update or create chart
      if (_charts[cfg.key]) {
        const chart = _charts[cfg.key];
        chart.data.labels = labels;
        chart.data.datasets[0].data = values;
        chart.update('none');
      } else {
        const canvas = document.getElementById(`chart-${cfg.key}`);
        if (!canvas) return;

        _charts[cfg.key] = new Chart(canvas, {
          type: 'line',
          data: {
            labels,
            datasets: [{
              data: values,
              borderColor: cfg.color,
              backgroundColor: cfg.color + '14',
              borderWidth: 2,
              fill: true,
              tension: 0.4,
              pointRadius: 0,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                enabled: true,
                backgroundColor: '#1e2438',
                borderColor: '#2d3748',
                borderWidth: 1,
                titleColor: '#94a3b8',
                bodyColor: '#e2e8f0',
                callbacks: {
                  label: ctx => {
                    const raw = cfg.key === 'pool_utilization' ? ctx.parsed.y / 100 : ctx.parsed.y;
                    return cfg.format(raw);
                  },
                },
              },
            },
            scales: {
              x: { display: false },
              y: {
                display: true,
                grid: { color: 'rgba(45,55,72,0.4)' },
                ticks: {
                  color: '#64748b',
                  font: { size: 10, family: 'monospace' },
                  maxTicksLimit: 5,
                },
              },
            },
            animation: false,
          },
        });
      }
    });
  }

  function _buildLayout(container) {
    // Destroy existing charts if rebuilding
    Object.values(_charts).forEach(c => c.destroy());
    for (const k in _charts) delete _charts[k];

    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Monitoring</h1>
          <p class="page-subtitle">Real-time KubeAI cluster metrics — Prometheus analogue</p>
        </div>
      </div>

      <div class="chart-grid">
        ${METRIC_CONFIG.map(cfg => `
          <div class="chart-card">
            <div class="card-header" style="margin-bottom:8px;">
              <span class="card-title" style="font-size:12px;">${cfg.label.toUpperCase()}</span>
              <span class="text-muted text-sm">${cfg.unit}</span>
            </div>
            <div class="chart-summary">
              <span class="chart-current-value" id="metric-val-${cfg.key}">—</span>
              <span class="chart-unit">${cfg.unit}</span>
              <span class="chart-trend" id="metric-trend-${cfg.key}"></span>
            </div>
            <div class="chart-canvas-wrap">
              <canvas id="chart-${cfg.key}"></canvas>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    window.refreshIcons?.();
  }

  return { render };
})();
