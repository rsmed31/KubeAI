/**
 * Memory Page — the kubectl describe pv / PersistentVolume status analogue.
 * Visualizes the 3-tier KubeAI shared data plane: working, short-term, long-term memory.
 */
const MemoryPage = (() => {
  function render(state) {
    const memory = state.memory || AppState.memory || {};
    const working = memory.working || {};
    const shortTerm = memory.short_term || {};
    const longTerm = memory.long_term || {};

    const workingPct = Math.min(100, ((working.size_bytes || 0) / 65536 * 100)).toFixed(0);
    const shortPct = Math.min(100, ((shortTerm.size_bytes || 0) / 524288 * 100)).toFixed(0);
    const longPct = Math.min(100, ((longTerm.size_bytes || 0) / 4194304 * 100)).toFixed(0);

    const container = document.getElementById('page-container');
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Memory</h1>
          <p class="page-subtitle">3-tier shared data plane — etcd analogue for agent state</p>
        </div>
      </div>

      <div class="memory-grid">
        <!-- Working Memory -->
        <div class="memory-card" style="border-top: 3px solid var(--accent-cyan);">
          <div class="memory-card-title">Working Memory</div>
          <div class="memory-card-sub">In-process agent context — volatile, per-agent</div>

          <div class="memory-stat">
            <span class="memory-stat-label">Agent Contexts</span>
            <span class="memory-stat-value">${working.agent_contexts ?? '—'}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Size</span>
            <span class="memory-stat-value">${formatBytes(working.size_bytes || 0)}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Tier</span>
            <span class="memory-stat-value">
              <span class="badge tier-fast">fast</span>
            </span>
          </div>

          <div style="margin-top:16px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:4px;">
              <span>Utilization</span>
              <span>${workingPct}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill cyan" style="width:${workingPct}%;"></div>
            </div>
          </div>
        </div>

        <!-- Short-Term Memory -->
        <div class="memory-card" style="border-top: 3px solid var(--accent-green);">
          <div class="memory-card-title">Short-Term Memory</div>
          <div class="memory-card-sub">Redis-backed sliding window — shared across agents</div>

          <div class="memory-stat">
            <span class="memory-stat-label">Keys</span>
            <span class="memory-stat-value">${shortTerm.keys ?? '—'}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Avg TTL</span>
            <span class="memory-stat-value">${shortTerm.ttl_avg_s ? shortTerm.ttl_avg_s + 's' : '—'}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Size</span>
            <span class="memory-stat-value">${formatBytes(shortTerm.size_bytes || 0)}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Tier</span>
            <span class="memory-stat-value">
              <span class="badge tier-capable">capable</span>
            </span>
          </div>

          <div style="margin-top:16px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:4px;">
              <span>Utilization</span>
              <span>${shortPct}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill green" style="width:${shortPct}%;"></div>
            </div>
          </div>
        </div>

        <!-- Long-Term Memory -->
        <div class="memory-card" style="border-top: 3px solid var(--accent-purple);">
          <div class="memory-card-title">Long-Term Memory</div>
          <div class="memory-card-sub">SQLite-backed persistent facts & blueprints</div>

          <div class="memory-stat">
            <span class="memory-stat-label">Blueprints</span>
            <span class="memory-stat-value">${longTerm.blueprints ?? '—'}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Fact Entries</span>
            <span class="memory-stat-value">${longTerm.fact_entries ?? '—'}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Size</span>
            <span class="memory-stat-value">${formatBytes(longTerm.size_bytes || 0)}</span>
          </div>
          <div class="memory-stat">
            <span class="memory-stat-label">Tier</span>
            <span class="memory-stat-value">
              <span class="badge tier-best">best</span>
            </span>
          </div>

          <div style="margin-top:16px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:4px;">
              <span>Utilization</span>
              <span>${longPct}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill purple" style="width:${longPct}%;"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="info" class="icon-sm"></i>
            Memory Architecture
          </span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; font-size: 13px; color: var(--text-secondary);">
          <div>
            <strong style="color:var(--accent-cyan);">Working</strong>
            <p style="margin-top:6px;">Per-agent in-process context. Lost on agent restart. Analogous to CPU cache — fastest access, smallest capacity.</p>
          </div>
          <div>
            <strong style="color:var(--accent-green);">Short-Term</strong>
            <p style="margin-top:6px;">Shared Redis store with TTL. Survives agent restarts within a session. Analogous to Node memory — fast, bounded.</p>
          </div>
          <div>
            <strong style="color:var(--accent-purple);">Long-Term</strong>
            <p style="margin-top:6px;">Persistent SQLite facts and blueprints. Analogous to PersistentVolume — durable, unlimited, slower access.</p>
          </div>
        </div>
      </div>
    `;

    window.refreshIcons?.();
  }

  return { render };
})();
