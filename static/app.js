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

async function loadFabric(name) {
  const title = document.getElementById('detail-title');
  const meta = document.getElementById('detail-meta');
  const body = document.getElementById('detail-body');
  if (name === 'all') {
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
  meta.textContent = `APIC ${data.cisco_limits?.cluster_size || 'n/a'}-node · ${data.cisco_limits?.release || 'n/a'}`;

  const summary = data.summary || {};
  const headroom = data.headroom || {};
  const ports = data.ports || {};
  const limits = data.cisco_limits || {};

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
        <h4>Actions</h4>
        <div class=\"panel-actions\">
          <button class=\"ghost small\" onclick=\"selectFabric('${name}')\">Focus</button>
          <a class=\"primary small\" href=\"/api/export/excel/${name}\">Export Excel</a>
          <button class=\"danger small\" onclick=\"deleteFabric('${name}')\">Delete</button>
        </div>
      </div>
    </div>
  `;
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-count]').forEach(animateCount);
  document.querySelectorAll('.ring-progress').forEach(animateProgressRing);
  document.querySelectorAll('.progress-fill').forEach(animateProgressBar);
});
