function animateCount(el) {
  const target = Number(el.dataset.count || 0);
  const duration = 1200;
  const start = performance.now();
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const value = Math.floor(target * progress);
    el.textContent = value;
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function animateProgressRing(el) {
  const progress = Number(el.dataset.progress || 0);
  const circumference = 314;
  const offset = circumference - (progress / 100) * circumference;
  el.style.strokeDashoffset = offset;
}

function animateProgressBar(el) {
  const progress = Number(el.dataset.progress || 0);
  el.style.width = `${progress}%`;
}

function openFabricModal() {
  document.getElementById('fabric-modal').classList.remove('hidden');
}

function closeFabricModal() {
  document.getElementById('fabric-modal').classList.add('hidden');
}

async function createFabric() {
  const name = document.getElementById('fabric-name').value.trim();
  const description = document.getElementById('fabric-desc').value.trim();
  if (!name) return alert('Fabric name required');
  const res = await fetch('/fabrics', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, description })
  });
  const data = await res.json();
  if (!data.success) return alert(data.error || 'Create failed');
  location.reload();
}

async function selectFabric(name) {
  await fetch(`/fabrics/${name}/select`, { method: 'POST' });
  location.reload();
}

async function deleteFabric(name) {
  const ok = confirm(`Delete fabric "${name}"? This removes all datasets.`);
  if (!ok) return;
  const res = await fetch(`/fabrics/${name}`, { method: 'DELETE' });
  const data = await res.json().catch(() => ({}));
  if (!data.success) return alert(data.error || 'Delete failed');
  location.reload();
}

async function resetFabrics() {
  const ok = confirm('Reset all fabrics? This deletes all datasets.');
  if (!ok) return;
  const res = await fetch('/fabrics/reset', { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  if (!data.success) return alert(data.error || 'Reset failed');
  location.reload();
}

async function rebuildCache(name) {
  const ok = confirm(`Rebuild cache for "${name}"?`);
  if (!ok) return;
  const res = await fetch(`/fabrics/${name}/rebuild-cache`, { method: 'POST' });
  const data = await res.json().catch(() => ({}));
  if (!data.success) return alert(data.error || 'Rebuild failed');
  alert('Cache rebuilt');
}

async function saveUplinks(name, value) {
  const res = await fetch(`/fabrics/${name}/meta`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uplinks_per_leaf: value || "" })
  });
  const data = await res.json().catch(() => ({}));
  if (!data.success) alert(data.error || 'Update failed');
}

async function saveScaleProfile(name, value) {
  const res = await fetch(`/fabrics/${name}/meta`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scale_profile: value })
  });
  const data = await res.json().catch(() => ({}));
  if (!data.success) alert(data.error || 'Update failed');
}

async function saveEndpointProfile(name, value) {
  const res = await fetch(`/fabrics/${name}/meta`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint_profile: value })
  });
  const data = await res.json().catch(() => ({}));
  if (!data.success) alert(data.error || 'Update failed');
}

async function saveUplinkSpeed(name, value) {
  const res = await fetch(`/fabrics/${name}/meta`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uplink_speed: value })
  });
  const data = await res.json().catch(() => ({}));
  if (!data.success) alert(data.error || 'Update failed');
}

function toggleFabric(name) {
  const panel = document.getElementById(`detail-${name}`);
  if (!panel) return;
  panel.classList.toggle('hidden');
}

function filterFabrics() {
  const term = (document.getElementById('fabric-filter')?.value || '').toLowerCase();
  document.querySelectorAll('.fabric-item').forEach((card) => {
    const name = card.dataset.fabric?.toLowerCase() || '';
    card.style.display = name.includes(term) ? 'block' : 'none';
  });
}

function setSummaryHeader(title, subtitle) {
  const titleEl = document.getElementById('summary-title');
  const subEl = document.getElementById('summary-sub');
  if (titleEl) titleEl.textContent = title;
  if (subEl) subEl.textContent = subtitle;
}

function fabricId(name) {
  return (name || '').replace(/[^a-zA-Z0-9_-]/g, '_');
}

function renderUtilRows(rows, keyLabel) {
  if (!rows || rows.length === 0) {
    return '<tr><td colspan="5" class="text-muted text-center">No data</td></tr>';
  }
  return rows.slice(0, 12).map((row) => {
    const total = row.total || 0;
    const up = row.up || 0;
    const down = row.down || 0;
    const unknown = row.unknown || 0;
    return `<tr><td>${row[keyLabel]}</td><td>${total}</td><td>${up}</td><td>${down}</td><td>${unknown}</td></tr>`;
  }).join('');
}

function computeInsights(data) {
  const insights = [];
  const headroom = data.headroom || {};
  const completeness = data.completeness || {};
  const spine = data.spine_capacity || {};
  const insights = computeInsights(data);
  const ports = data.ports || {};

  const add = (severity, title, detail) => {
    insights.push({ severity, title, detail });
  };

  const headroomCheck = (key, label, threshold = 85) => {
    const row = headroom[key];
    if (!row || row.pct == null) return;
    if (row.pct >= threshold) {
      add('warning', `${label} near limit`, `${row.current} / ${row.maximum} used (${row.pct}%).`);
    }
  };

  headroomCheck('leafs', 'Leaf switches', 85);
  headroomCheck('spines', 'Spine switches', 85);
  headroomCheck('tenants', 'Tenants', 90);
  headroomCheck('vrfs', 'VRFs', 90);
  headroomCheck('bds', 'Bridge domains', 90);
  headroomCheck('epgs', 'EPGs', 90);
  headroomCheck('contracts', 'Contracts', 90);
  headroomCheck('ports', 'Physical ports', 85);

  if (typeof spine.remaining_leafs_before_linecards === 'number' && spine.remaining_leafs_before_linecards <= 2) {
    add('critical', 'Spine port capacity tight', `Only ${spine.remaining_leafs_before_linecards} leaf(s) remaining before more spine ports are required.`);
  }

  if (ports.total && ports.ports_with_epg != null) {
    const pct = Math.round((ports.ports_with_epg / Math.max(ports.total, 1)) * 100);
    if (pct >= 90) {
      add('warning', 'High port utilization', `${ports.ports_with_epg} / ${ports.total} ports assigned to EPGs (${pct}%).`);
    }
  }

  if ((completeness.missing_required || []).length) {
    add('critical', 'Missing required datasets', `Missing: ${(completeness.missing_required || []).join(', ')}`);
  } else if ((completeness.missing_optional || []).length) {
    add('info', 'Optional datasets missing', `Missing: ${(completeness.missing_optional || []).join(', ')}`);
  }

  if (insights.length === 0) {
    add('info', 'No critical risks detected', 'Current dataset shows healthy headroom across key limits.');
  }
  return insights;
}

function renderInsightCards(insights) {
  const badgeMap = {
    critical: 'text-bg-danger',
    warning: 'text-bg-warning',
    info: 'text-bg-primary'
  };
  return insights.map((item) => `
    <div class="col-12 col-lg-6">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <h6 class="card-title mb-0">${item.title}</h6>
            <span class="badge ${badgeMap[item.severity] || 'text-bg-secondary'} text-uppercase">${item.severity}</span>
          </div>
          <div class="text-muted small">${item.detail}</div>
        </div>
      </div>
    </div>
  `).join('');
}

function filterTableRows(inputEl, tableId) {
  const term = (inputEl.value || '').toLowerCase();
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = table.querySelectorAll('tbody tr');
  rows.forEach((row) => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(term) ? '' : 'none';
  });
}

async function loadFabricSummaryDetail(name, targetId) {
  const target = document.getElementById(targetId);
  if (!target || target.dataset.loaded === 'true') return;
  target.innerHTML = '<div class="text-center text-muted py-3">Loading details...</div>';
  const res = await fetch(`/api/analysis/${name}`);
  const data = await res.json();
  if (data.error) {
    target.innerHTML = `<div class="text-danger py-2">${data.error}</div>`;
    return;
  }
  const headroom = data.headroom || {};
  const ports = data.ports || {};
  const completeness = data.completeness || {};
  const spine = data.spine_capacity || {};
  const pct = Math.round(((ports.ports_with_epg || 0) / (ports.total || 1)) * 100);
  target.innerHTML = `
    <div class="row g-3">
      <div class="col-12 col-md-6">
        <div class="border rounded-3 p-3 bg-light">
          <div class="fw-semibold mb-2">Headroom</div>
          <div class="d-flex justify-content-between"><span>Tenants</span><span>${headroom.tenants?.current || 0} / ${headroom.tenants?.maximum || 'n/a'}</span></div>
          <div class="d-flex justify-content-between"><span>VRFs</span><span>${headroom.vrfs?.current || 0} / ${headroom.vrfs?.maximum || 'n/a'}</span></div>
          <div class="d-flex justify-content-between"><span>BDs</span><span>${headroom.bds?.current || 0} / ${headroom.bds?.maximum || 'n/a'}</span></div>
          <div class="d-flex justify-content-between"><span>EPGs</span><span>${headroom.epgs?.current || 0} / ${headroom.epgs?.maximum || 'n/a'}</span></div>
        </div>
      </div>
      <div class="col-12 col-md-6">
        <div class="border rounded-3 p-3 bg-light">
          <div class="fw-semibold mb-2">Spine Capacity</div>
          <div class="d-flex justify-content-between"><span>Leafs Supported</span><span>${spine.leafs_supported_by_spines ?? 'n/a'}</span></div>
          <div class="d-flex justify-content-between"><span>Remaining Leafs</span><span>${spine.remaining_leafs_before_linecards ?? 'n/a'}</span></div>
          <div class="d-flex justify-content-between"><span>Uplink Speed</span><span>${spine.uplink_speed || 'n/a'}</span></div>
          <div class="d-flex justify-content-between"><span>Recommended Card</span><span>${spine.linecard_recommendation?.model || 'n/a'}</span></div>
        </div>
      </div>
      <div class="col-12">
        <div class="border rounded-3 p-3 bg-light">
          <div class="fw-semibold mb-2">Ports</div>
          <div class="progress" role="progressbar" aria-label="Port utilization">
            <div class="progress-bar" style="width:${pct}%"></div>
          </div>
          <div class="text-muted small mt-2">${ports.ports_with_epg || 0} / ${ports.total || 0} ports with EPG</div>
        </div>
      </div>
      <div class="col-12">
        <div class="border rounded-3 p-3 bg-light">
          <div class="fw-semibold mb-2">Dataset Completeness</div>
          <div class="d-flex justify-content-between"><span>Score</span><span>${completeness.completeness_score ?? 'n/a'}%</span></div>
          <div class="text-muted small">Missing required: ${(completeness.missing_required || []).join(', ') || 'none'}</div>
        </div>
      </div>
    </div>
  `;
  target.dataset.loaded = 'true';
}

async function loadFabric(name) {
  const title = document.getElementById('detail-title');
  const meta = document.getElementById('detail-meta');
  const body = document.getElementById('detail-body');
  if (name === 'all') {
    setSummaryHeader('Fabric Summary', 'Key metrics per fabric. Select a fabric for full detail.');
    title.textContent = 'All Fabrics';
    meta.textContent = 'Summary only';
    body.innerHTML = '<div class=\"empty\">Select a fabric to view full details.</div>';
    return;
  }
  title.textContent = `Loading ${name}...`;
  meta.textContent = 'Fetching analysis';
  body.innerHTML = '<div class=\"empty\">Loading analysis...</div>';
  const res = await fetch(`/api/analysis/${name}`);
  const data = await res.json();
  if (data.error) {
    title.textContent = name;
    meta.textContent = 'Error';
    body.innerHTML = `<div class=\"empty\">${data.error}</div>`;
    return;
  }
  title.textContent = name;
  meta.textContent = `APIC ${data.cisco_limits?.cluster_size || 'n/a'}-node - ${data.cisco_limits?.release || 'n/a'}`;

  const summary = data.summary || {};
  const headroom = data.headroom || {};
  const ports = data.ports || {};
  const limits = data.cisco_limits || {};
  const tenants = (data.tenants?.rows || []).slice(0, 10);
  const util = data.port_utilization || {};
  const spine = data.spine_capacity || {};
  const headroomDefs = [
    { key: 'leafs', label: 'Leaf switches' },
    { key: 'spines', label: 'Spine switches' },
    { key: 'leafs_by_spine_ports', label: 'Leafs by spine ports' },
    { key: 'tenants', label: 'Tenants' },
    { key: 'vrfs', label: 'VRFs' },
    { key: 'bds', label: 'Bridge domains' },
    { key: 'epgs', label: 'EPGs' },
    { key: 'contracts', label: 'Contracts' },
    { key: 'fex', label: 'FEX' },
    { key: 'ports', label: 'Physical ports' }
  ];
  const headroomRows = headroomDefs.map((item) => {
    const row = headroom[item.key] || {};
    const current = row.current ?? 0;
    const maximum = row.maximum ?? 'n/a';
    const remaining = row.remaining ?? 'n/a';
    const pct = row.pct ?? 'n/a';
    return `<tr><td>${item.label}</td><td>${current}</td><td>${maximum}</td><td>${remaining}</td><td>${pct}%</td></tr>`;
  }).join('');
  const tenantRows = tenants.length
    ? tenants.map((row) => `<tr><td>${row.tenant || ''}</td><td>${row.vrfs || 0}</td><td>${row.bds || 0}</td><td>${row.epgs || 0}</td><td>${row.subnets || 0}</td></tr>`).join('')
    : '<tr><td colspan="5" class="text-muted text-center">No tenant rollups</td></tr>';
  setSummaryHeader('Fabric Summary', 'Key metrics per fabric. Select a fabric for full detail.');

  body.innerHTML = `
    <div class="row g-3">
      <div class="col-12">
        <div class="row g-3">
          <div class="col-6 col-lg-3">
            <div class="card metric-card h-100">
              <div class="card-body">
                <div class="text-muted small">Leafs</div>
                <div class="metric-value">${summary.leafs || 0}</div>
                <div class="text-muted small">Spines ${summary.spines || 0}</div>
              </div>
            </div>
          </div>
          <div class="col-6 col-lg-3">
            <div class="card metric-card h-100">
              <div class="card-body">
                <div class="text-muted small">Tenants</div>
                <div class="metric-value">${summary.tenants || 0}</div>
                <div class="text-muted small">VRFs ${summary.vrfs || 0}</div>
              </div>
            </div>
          </div>
          <div class="col-6 col-lg-3">
            <div class="card metric-card h-100">
              <div class="card-body">
                <div class="text-muted small">EPGs</div>
                <div class="metric-value">${summary.epgs || 0}</div>
                <div class="text-muted small">BDs ${summary.bds || 0}</div>
              </div>
            </div>
          </div>
          <div class="col-6 col-lg-3">
            <div class="card metric-card h-100">
              <div class="card-body">
                <div class="text-muted small">Ports</div>
                <div class="metric-value">${ports.total || 0}</div>
                <div class="text-muted small">Ports w/ EPG ${ports.ports_with_epg || 0}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="col-12">
        <ul class="nav nav-pills gap-2" role="tablist">
          <li class="nav-item" role="presentation">
            <button class="nav-link active" data-bs-toggle="pill" data-bs-target="#tab-overview" type="button" role="tab">Overview</button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-capacity" type="button" role="tab">Capacity</button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-util" type="button" role="tab">Utilization</button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-insights" type="button" role="tab">Insights</button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-tenants" type="button" role="tab">Tenants</button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-actions" type="button" role="tab">Actions</button>
          </li>
        </ul>
      </div>

      <div class="col-12">
        <div class="tab-content">
          <div class="tab-pane fade show active" id="tab-overview" role="tabpanel">
            <div class="row g-3">
              <div class="col-12 col-lg-6">
                <div class="card h-100">
                  <div class="card-body">
                    <h6 class="card-title">Key Limits</h6>
                    <div class="table-responsive">
                      <table class="table table-sm align-middle mb-0">
                        <thead><tr><th>Metric</th><th>Current</th><th>Max</th><th>Remaining</th><th>%</th></tr></thead>
                        <tbody>${headroomRows}</tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
              <div class="col-12 col-lg-6">
                <div class="card h-100">
                  <div class="card-body">
                    <h6 class="card-title">Spine Capacity Insight</h6>
                    <div class="d-flex justify-content-between"><span>Uplink speed</span><span>${spine.uplink_speed || 'n/a'}</span></div>
                    <div class="d-flex justify-content-between"><span>Leafs supported</span><span>${spine.leafs_supported_by_spines ?? 'n/a'}</span></div>
                    <div class="d-flex justify-content-between"><span>Remaining leafs</span><span>${spine.remaining_leafs_before_linecards ?? 'n/a'}</span></div>
                    <div class="d-flex justify-content-between"><span>Card recommendation</span><span>${spine.linecard_recommendation?.model || 'n/a'}</span></div>
                    <div class="d-flex justify-content-between"><span>Cards needed</span><span>${spine.linecard_recommendation?.count ?? 'n/a'}</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="tab-pane fade" id="tab-capacity" role="tabpanel">
            <div class="card">
              <div class="card-body">
                <h6 class="card-title">Fabric Capacity Overview</h6>
                <div class="progress mb-2" role="progressbar" aria-label="Port utilization">
                  <div class="progress-bar" style="width:${Math.round(((ports.ports_with_epg || 0) / (ports.total || 1)) * 100)}%"></div>
                </div>
                <div class="text-muted small">${ports.ports_with_epg || 0} / ${ports.total || 0} ports with EPG</div>
                <div class="mt-3">
                  <div class="text-muted small">APIC release: ${limits.release || 'n/a'}</div>
                  <div class="text-muted small">APIC cluster size: ${limits.cluster_size || 'n/a'}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="tab-pane fade" id="tab-util" role="tabpanel">
            <div class="row g-3">
              <div class="col-12 col-lg-4">
                <div class="card h-100">
                  <div class="card-body">
                    <h6 class="card-title">Leaf Ports</h6>
                    <input class="form-control form-control-sm mb-2" placeholder="Filter leaf..." oninput="filterTableRows(this, 'leaf-util-table')">
                    <div class="table-responsive">
                      <table class="table table-sm mb-0" id="leaf-util-table">
                        <thead><tr><th>Leaf</th><th>Total</th><th>Up</th><th>Down</th><th>Unknown</th></tr></thead>
                        <tbody>${renderUtilRows(util.leafs || [], 'node')}</tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
              <div class="col-12 col-lg-4">
                <div class="card h-100">
                  <div class="card-body">
                    <h6 class="card-title">Spine Ports</h6>
                    <input class="form-control form-control-sm mb-2" placeholder="Filter spine..." oninput="filterTableRows(this, 'spine-util-table')">
                    <div class="table-responsive">
                      <table class="table table-sm mb-0" id="spine-util-table">
                        <thead><tr><th>Spine</th><th>Total</th><th>Up</th><th>Down</th><th>Unknown</th></tr></thead>
                        <tbody>${renderUtilRows(util.spines || [], 'node')}</tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
              <div class="col-12 col-lg-4">
                <div class="card h-100">
                  <div class="card-body">
                    <h6 class="card-title">FEX Ports</h6>
                    <input class="form-control form-control-sm mb-2" placeholder="Filter FEX..." oninput="filterTableRows(this, 'fex-util-table')">
                    <div class="table-responsive">
                      <table class="table table-sm mb-0" id="fex-util-table">
                        <thead><tr><th>FEX</th><th>Total</th><th>Up</th><th>Down</th><th>Unknown</th></tr></thead>
                        <tbody>${renderUtilRows(util.fex || [], 'fex')}</tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="tab-pane fade" id="tab-insights" role="tabpanel">
            <div class="row g-3">
              ${renderInsightCards(insights)}
            </div>
          </div>

          <div class="tab-pane fade" id="tab-tenants" role="tabpanel">
            <div class="card">
              <div class="card-body">
                <h6 class="card-title">Top Tenants by Scale</h6>
                <input class="form-control form-control-sm mb-2" placeholder="Filter tenant..." oninput="filterTableRows(this, 'tenant-table')">
                <div class="table-responsive">
                  <table class="table table-sm mb-0" id="tenant-table">
                    <thead><tr><th>Tenant</th><th>VRFs</th><th>BDs</th><th>EPGs</th><th>Subnets</th></tr></thead>
                    <tbody>${tenantRows}</tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <div class="tab-pane fade" id="tab-actions" role="tabpanel">
            <div class="card">
              <div class="card-body">
                <div class="d-flex flex-wrap gap-2 mb-3">
                  <button class="btn btn-outline-primary" onclick="selectFabric('${name}')">Focus</button>
                  <a class="btn btn-primary" href="/api/export/excel/${name}">Export Excel</a>
                  <a class="btn btn-outline-primary" href="/report/${name}" target="_blank">Executive PDF</a>
                  <button class="btn btn-outline-secondary" onclick="rebuildCache('${name}')">Rebuild Cache</button>
                  <button class="btn btn-outline-danger" onclick="deleteFabric('${name}')">Delete</button>
                </div>
                <div class="row g-2">
                  <div class="col-12 col-md-6">
                    <label class="form-label small">Uplinks per leaf</label>
                    <input class="form-control form-control-sm" type="number" min="1" max="16" placeholder="auto" onblur="saveUplinks('${name}', this.value)">
                  </div>
                  <div class="col-12 col-md-6">
                    <label class="form-label small">Uplink speed</label>
                    <select class="form-select form-select-sm" onchange="saveUplinkSpeed('${name}', this.value)">
                      <option value="100G">100G</option>
                      <option value="40G">40G</option>
                      <option value="400G">400G</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-count]').forEach(animateCount);
  document.querySelectorAll('.ring-progress').forEach(animateProgressRing);
  document.querySelectorAll('.progress-fill').forEach(animateProgressBar);
  loadSummaries();
});

async function loadSummaries() {
  const grid = document.getElementById('fabric-summary-grid');
  if (grid) grid.innerHTML = '';
  const buttons = document.querySelectorAll('.fabric-item');
  const res = await fetch('/api/summary');
  const all = await res.json();
  if (grid && buttons.length === 0) {
    grid.innerHTML = '<div class="empty">No fabrics yet.</div>';
    return;
  }
  for (const btn of buttons) {
    const name = btn.dataset.fabric;
    const data = all[name] || {};
    const summary = data.summary || {};
    const ports = data.ports || {};
    btn.querySelector('[data-fabric-metric="leafs"]').textContent = `${summary.leafs || 0} leafs`;
    btn.querySelector('[data-fabric-metric="epgs"]').textContent = `${summary.epgs || 0} epgs`;
    btn.querySelector('[data-fabric-metric="ports"]').textContent = `${ports.ports_with_epg || 0} ports w/ epg`;
    if (grid) {
      const col = document.createElement('div');
      col.className = 'col-12 col-md-6 col-xl-4';
      const card = document.createElement('div');
      card.className = 'card fabric-summary-card h-100';
      card.role = 'button';
      card.tabIndex = 0;
      card.onclick = () => loadFabric(name);
      card.onkeypress = (evt) => { if (evt.key === 'Enter') loadFabric(name); };
      const safeId = fabricId(name);
      const detailsId = `fabric-details-${safeId}`;
      card.innerHTML = `
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <h5 class="card-title mb-1">${name}</h5>
              <div class="text-muted small">${summary.leafs || 0} leafs - ${summary.spines || 0} spines - ${summary.fex || 0} fex</div>
            </div>
            <button class="btn btn-sm btn-outline-primary" data-bs-toggle="collapse" data-bs-target="#${detailsId}" aria-expanded="false" aria-controls="${detailsId}" onclick="loadFabricSummaryDetail('${name}', '${detailsId}')">Details</button>
          </div>
          <div class="row g-2 fabric-summary-metrics">
            <div class="col-6"><div class="text-muted small">Tenants</div><div class="fw-semibold">${summary.tenants || 0}</div></div>
            <div class="col-6"><div class="text-muted small">VRFs</div><div class="fw-semibold">${summary.vrfs || 0}</div></div>
            <div class="col-6"><div class="text-muted small">BDs</div><div class="fw-semibold">${summary.bds || 0}</div></div>
            <div class="col-6"><div class="text-muted small">EPGs</div><div class="fw-semibold">${summary.epgs || 0}</div></div>
            <div class="col-6"><div class="text-muted small">Ports</div><div class="fw-semibold">${ports.total || 0}</div></div>
            <div class="col-6"><div class="text-muted small">Ports w/ EPG</div><div class="fw-semibold">${ports.ports_with_epg || 0}</div></div>
            <div class="col-6"><div class="text-muted small">Endpoints</div><div class="fw-semibold">${summary.endpoints || 0}</div></div>
            <div class="col-6"><div class="text-muted small">Contracts</div><div class="fw-semibold">${summary.contracts || 0}</div></div>
          </div>
          <div class="collapse mt-3" id="${detailsId}"></div>
        </div>
      `;
      col.appendChild(card);
      grid.appendChild(col);
    }
  }
  setSummaryHeader('Fabric Summary', 'Key metrics per fabric. Select a fabric for full detail.');
}
