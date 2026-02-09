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

function toggleFabric(name) {
  const panel = document.getElementById(`detail-${name}`);
  if (!panel) return;
  panel.classList.toggle('hidden');
}

function filterFabrics() {
  const term = (document.getElementById('fabric-filter')?.value || '').toLowerCase();
  document.querySelectorAll('.fabric-card').forEach((card) => {
    const name = card.dataset.fabric?.toLowerCase() || '';
    card.style.display = name.includes(term) ? 'block' : 'none';
  });
}

function expandAll(expand) {
  document.querySelectorAll('.fabric-card-detail').forEach((panel) => {
    panel.classList.toggle('hidden', !expand);
  });
}

window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-count]').forEach(animateCount);
  document.querySelectorAll('.ring-progress').forEach(animateProgressRing);
  document.querySelectorAll('.progress-fill').forEach(animateProgressBar);
});
