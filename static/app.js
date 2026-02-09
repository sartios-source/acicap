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
  setSummaryHeader('Fabric Summary', 'Key metrics per fabric. Select a fabric for full detail.');

  body.innerHTML = `
    <div class=\"detail-grid\">
      <div class=\"detail-block\">
        <h4>Summary</h4>
        <div class=\"pill-row\">
          <span class=\"pill\">Leafs ${summary.leafs || 0}</span>
          <span class=\"pill\">Spines ${summary.spines || 0}</span>
          <span class=\"pill\">FEX ${summary.fex || 0}</span>
          <span class=\"pill\">EPGs ${summary.epgs || 0}</span>
          <span class=\"pill\">Tenants ${summary.tenants || 0}</span>
        </div>
      </div>
      <div class=\"detail-block\">
        <h4>Ports</h4>
        <div class=\"progress-bar\"><div class=\"progress-fill\" style=\"width:${Math.round(((ports.ports_with_epg||0)/(ports.total||1))*100)}%\"></div></div>
        <div class=\"progress-meta\">${ports.ports_with_epg || 0} / ${ports.total || 0} ports with EPG</div>
      </div>
      <div class=\"detail-block\">
        <h4>Headroom (Leafs)</h4>
        <div class=\"limit-grid\">
          <div>APIC Limit</div><div>${headroom.leafs?.current || 0} / ${headroom.leafs?.maximum || 'n/a'}</div><div>${headroom.leafs?.remaining ?? 'n/a'} left</div>
          <div>Spine Ports</div><div>${headroom.leafs_by_spine_ports?.current || 0} / ${headroom.leafs_by_spine_ports?.maximum || 'n/a'}</div><div>${headroom.leafs_by_spine_ports?.remaining ?? 'n/a'} left</div>
        </div>
      </div>
      <div class=\"detail-block\">
        <h4>Cisco Limits (Key)</h4>
        <div class=\"limit-grid\">
          <div>Tenants</div><div>${headroom.tenants?.current || 0} / ${headroom.tenants?.maximum || 'n/a'}</div><div>${headroom.tenants?.remaining ?? 'n/a'} left</div>
          <div>VRFs</div><div>${headroom.vrfs?.current || 0} / ${headroom.vrfs?.maximum || 'n/a'}</div><div>${headroom.vrfs?.remaining ?? 'n/a'} left</div>
          <div>BDs</div><div>${headroom.bds?.current || 0} / ${headroom.bds?.maximum || 'n/a'}</div><div>${headroom.bds?.remaining ?? 'n/a'} left</div>
          <div>EPGs</div><div>${headroom.epgs?.current || 0} / ${headroom.epgs?.maximum || 'n/a'}</div><div>${headroom.epgs?.remaining ?? 'n/a'} left</div>
        </div>
      </div>
      <div class=\"detail-block\">
        <h4>Recommended Spine Card</h4>
        <div class=\"limit-grid\">
          <div>Uplink Speed</div><div>${data.spine_capacity?.uplink_speed || 'n/a'}</div><div>Assumed</div>
          <div>Card Model</div><div>${data.spine_capacity?.linecard_recommendation?.model || 'n/a'}</div><div>${data.spine_capacity?.linecard_recommendation?.speed || ''}</div>
          <div>Cards Needed</div><div>${data.spine_capacity?.linecard_recommendation?.count ?? 'n/a'}</div><div>For headroom</div>
        </div>
      </div>
      <div class=\"detail-block\">
        <h4>Actions</h4>
        <div class=\"panel-actions\">
          <button class=\"ghost small\" onclick=\"selectFabric('${name}')\">Focus</button>
          <a class=\"primary small\" href=\"/api/export/excel/${name}\">Export Excel</a>
          <button class=\"ghost small\" onclick=\"rebuildCache('${name}')\">Rebuild Cache</button>
          <button class=\"danger small\" onclick=\"deleteFabric('${name}')\">Delete</button>
        </div>
        <div class=\"meta-row\" style=\"margin-top:8px;\">
          <label>Uplinks per leaf</label>
          <input type=\"number\" min=\"1\" max=\"16\" placeholder=\"auto\" onblur=\"saveUplinks('${name}', this.value)\">
        </div>
        <div class=\"meta-row\">
          <label>Uplink speed</label>
          <select onchange=\"saveUplinkSpeed('${name}', this.value)\">
            <option value=\"100G\">100G</option>
            <option value=\"40G\">40G</option>
            <option value=\"400G\">400G</option>
          </select>
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
