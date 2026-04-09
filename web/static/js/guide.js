// StreamStation — Guide Page JS

const $ = id => document.getElementById(id);

// ── Clock ─────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  let h = now.getHours();
  const m = String(now.getMinutes()).padStart(2, '0');
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  $('guideClock').textContent = `${h}:${m} ${ampm}`;
}
setInterval(updateClock, 1000);
updateClock();

// ── Category Filter ───────────────────────────────────────────────────────────
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const cat = btn.dataset.cat;
    document.querySelectorAll('.guide-row').forEach(row => {
      row.style.display = (cat === 'all' || row.dataset.cat === cat) ? '' : 'none';
    });
  });
});

// ── Tune ──────────────────────────────────────────────────────────────────────
function toast(msg, type = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast show ${type === 'error' ? 'error' : ''}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2500);
}

document.querySelectorAll('.guide-tune-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const num = btn.dataset.num;
    btn.textContent = 'TUNING...';
    try {
      const r = await fetch(`/api/tune/${num}`, { method: 'POST' }).then(r => r.json());
      if (r.ok) {
        toast(`Tuned to CH ${num}`);
        // Update on-air highlighting
        document.querySelectorAll('.guide-row').forEach(row => {
          row.classList.toggle('on-air', row.dataset.num == num);
          const badge = row.querySelector('.on-air-badge');
          if (row.dataset.num == num) {
            if (!badge) {
              const b = document.createElement('span');
              b.className = 'on-air-badge';
              b.textContent = 'ON AIR';
              row.querySelector('.ch-info-cell').appendChild(b);
            }
          } else {
            badge && badge.remove();
          }
        });
      } else {
        toast(r.error || 'Failed', 'error');
      }
    } catch (e) {
      toast('Engine not reachable', 'error');
    }
    btn.textContent = 'TUNE ▶';
  });
});

// ── Auto-refresh status ───────────────────────────────────────────────────────
async function refreshStatus() {
  try {
    const s = await fetch('/api/status').then(r => r.json());
    const label = document.querySelector('.status-label');
    if (label) {
      label.textContent = s.channel
        ? `▶ CH ${s.channel} — ${s.name}`
        : 'NO SIGNAL';
    }
    if (s.channel) {
      document.querySelectorAll('.guide-row').forEach(row => {
        row.classList.toggle('on-air', parseInt(row.dataset.num) === s.channel);
      });
    }
    $('lastRefresh').textContent = `LAST UPDATE: ${new Date().toTimeString().slice(0,8)}`;
  } catch {}
}
setInterval(refreshStatus, 15000);
refreshStatus();
