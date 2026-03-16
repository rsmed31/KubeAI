/**
 * Blueprints Page — the kubectl get deployments / Helm chart analogue.
 * Browse registered agent blueprints and generate new ones from descriptions.
 */
const BlueprintsPage = (() => {
  let _generatedYaml = null;
  let _isGenerating = false;
  let _isRegistering = false;

  function render(state) {
    const blueprints = AppState.blueprints || state.blueprints || [];

    const container = document.getElementById('page-container');
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Blueprints</h1>
          <p class="page-subtitle">${blueprints.length} registered blueprints — Container Image analogues</p>
        </div>
      </div>

      <div class="blueprint-grid">
        ${blueprints.length === 0
          ? `<div style="color:var(--text-muted);padding:24px;">No blueprints registered.</div>`
          : blueprints.map(b => renderBlueprintCard(b)).join('')}
      </div>

      <!-- Generate Blueprint Panel -->
      <div class="card" style="margin-top: 8px;">
        <div class="card-header">
          <span class="card-title">
            <i data-lucide="wand-2" class="icon-sm"></i>
            Generate Blueprint
          </span>
        </div>
        <div class="form-group">
          <label class="form-label">Describe the Agent</label>
          <textarea id="blueprint-desc" class="form-textarea" rows="3"
            placeholder="e.g. A code review agent that analyzes pull requests and suggests improvements..."></textarea>
        </div>
        <div style="display:flex;gap:10px;align-items:center;">
          <button id="generate-btn" class="btn btn-primary" onclick="BlueprintsPage._generate()">
            <i data-lucide="wand-2" class="icon-sm"></i>
            Generate YAML
          </button>
          <span id="generate-status" style="font-size:12px;color:var(--text-muted);"></span>
        </div>

        <div id="yaml-preview-container" style="display:none;margin-top:16px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:12px;font-weight:600;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">
              Generated YAML
            </span>
            <button id="register-btn" class="btn btn-ghost btn-sm" onclick="BlueprintsPage._register()">
              <i data-lucide="upload" class="icon-sm"></i>
              Register Blueprint
            </button>
          </div>
          <div class="yaml-preview" id="yaml-output"></div>
          <div id="register-feedback" style="margin-top:8px;font-size:12px;"></div>
        </div>
      </div>
    `;

    window.refreshIcons?.();
  }

  function renderBlueprintCard(b) {
    const caps = (b.capabilities || []);
    return `
      <div class="blueprint-card">
        <div class="blueprint-card-header">
          <span class="blueprint-name">${escHtml(b.name)}</span>
          <div style="display:flex;gap:6px;align-items:center;">
            ${tierBadge(b.tier)}
            <span class="badge badge-pending" style="font-size:10px;">v${escHtml(b.version || '1.0')}</span>
          </div>
        </div>
        <p class="blueprint-desc">${escHtml(b.description)}</p>
        <div class="blueprint-caps">
          ${caps.length
            ? caps.map(c => `<span class="cap-chip">${escHtml(c)}</span>`).join('')
            : '<span style="font-size:11px;color:var(--text-muted);">No capabilities</span>'}
        </div>
      </div>`;
  }

  async function _generate() {
    if (_isGenerating) return;
    const desc = document.getElementById('blueprint-desc')?.value?.trim();
    const status = document.getElementById('generate-status');
    const btn = document.getElementById('generate-btn');

    if (!desc) {
      if (status) status.textContent = 'Please enter a description.';
      return;
    }

    _isGenerating = true;
    _generatedYaml = null;
    if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
    if (status) status.textContent = '';

    try {
      const res = await fetch('/api/blueprints/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: desc }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (status) status.textContent = `Error: ${err.detail || res.status}`;
        return;
      }

      const data = await res.json();
      _generatedYaml = data.yaml;

      const container = document.getElementById('yaml-preview-container');
      const output = document.getElementById('yaml-output');
      const feedback = document.getElementById('register-feedback');

      if (container) container.style.display = 'block';
      if (feedback) feedback.innerHTML = '';
      if (output) {
        output.innerHTML = _generatedYaml
          .split('\n')
          .map(line => {
            if (line.startsWith('#')) return `<span class="yaml-line yaml-comment">${escHtml(line)}</span>`;
            return `<span class="yaml-line yaml-added">+ ${escHtml(line)}</span>`;
          })
          .join('\n');
      }
    } catch (e) {
      if (status) status.textContent = `Network error: ${e.message}`;
    } finally {
      _isGenerating = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="wand-2" class="icon-sm"></i> Generate YAML';
        window.refreshIcons?.();
      }
    }
  }

  async function _register() {
    if (!_generatedYaml || _isRegistering) return;
    const feedback = document.getElementById('register-feedback');
    const btn = document.getElementById('register-btn');
    const desc = document.getElementById('blueprint-desc')?.value?.trim() || 'Custom agent';

    // Parse name from YAML (simple extraction)
    const nameMatch = _generatedYaml.match(/name:\s*(\S+)/);
    const name = nameMatch ? nameMatch[1] : 'custom_agent';
    const tierMatch = _generatedYaml.match(/tier:\s*(\S+)/);
    const tier = tierMatch ? tierMatch[1] : 'capable';

    _isRegistering = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Registering...'; }

    try {
      const res = await fetch('/api/blueprints/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: desc, tier, version: '1.0', capabilities: [] }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Error: ${escHtml(err.detail || res.status)}</span>`;
      } else {
        if (feedback) feedback.innerHTML = `<span style="color:var(--accent-green);">Blueprint "${escHtml(name)}" registered successfully!</span>`;
        // Refresh blueprints list
        const bpRes = await fetch('/api/blueprints');
        if (bpRes.ok) AppState.blueprints = await bpRes.json();
      }
    } catch (e) {
      if (feedback) feedback.innerHTML = `<span style="color:var(--accent-red);">Error: ${escHtml(e.message)}</span>`;
    } finally {
      _isRegistering = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="upload" class="icon-sm"></i> Register Blueprint';
        window.refreshIcons?.();
      }
    }
  }

  return { render, _generate, _register };
})();
