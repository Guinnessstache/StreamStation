// StreamStation — Manage Page JS

const $ = id => document.getElementById(id);

// ── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast show ${type === 'error' ? 'error' : ''}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2800);
}

// ── API ───────────────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

// ── Category Filter ───────────────────────────────────────────────────────────
document.querySelectorAll('.cat-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filterTable(btn.dataset.cat);
  });
});

function filterTable(cat) {
  document.querySelectorAll('#channelTbody .ch-row').forEach(row => {
    row.style.display = (cat === 'all' || row.dataset.cat === cat) ? '' : 'none';
  });
}

// ── Search ────────────────────────────────────────────────────────────────────
$('searchInput').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('#channelTbody .ch-row').forEach(row => {
    const name = row.querySelector('.ch-name').textContent.toLowerCase();
    const url  = row.querySelector('.url-text').title.toLowerCase();
    row.style.display = (name.includes(q) || url.includes(q)) ? '' : 'none';
  });
});

// ── Tune ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tune-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const num = btn.dataset.num;
    btn.textContent = '…';
    const r = await api('POST', `/api/tune/${num}`);
    btn.textContent = '▶';
    toast(r.ok ? `Tuned to CH ${num}` : `Error: ${r.error}`, r.ok ? 'ok' : 'error');
  });
});

// ── Toggle ────────────────────────────────────────────────────────────────────
document.querySelectorAll('.toggle-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const id = btn.dataset.id;
    const r  = await api('POST', `/api/channels/${id}/toggle`);
    if (r.ok) {
      toast(r.enabled ? 'Channel enabled' : 'Channel disabled');
      setTimeout(() => location.reload(), 700);
    } else {
      toast(r.error || 'Failed', 'error');
    }
  });
});

// ── Test Stream ───────────────────────────────────────────────────────────────
document.querySelectorAll('.test-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const url = btn.dataset.url;
    btn.textContent = '…';
    const r = await api('POST', '/api/test_stream', { url });
    btn.textContent = '⚡';
    toast(r.ok ? '✓ Stream reachable' : '✗ Stream unreachable', r.ok ? 'ok' : 'error');
  });
});

// ── Delete ────────────────────────────────────────────────────────────────────
document.querySelectorAll('.delete-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const id   = btn.dataset.id;
    const name = btn.dataset.name;
    if (!confirm(`Delete "${name}"?`)) return;
    const r = await api('DELETE', `/api/channels/${id}`);
    if (r.ok) {
      btn.closest('tr').remove();
      toast(`Deleted: ${name}`);
    } else {
      toast(r.error || 'Failed', 'error');
    }
  });
});

// ── Edit ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.edit-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const id  = btn.dataset.id;
    const row = btn.closest('tr');
    openEditModal(id, row);
  });
});

function openEditModal(id, row) {
  $('modalTitle').textContent     = 'EDIT CHANNEL';
  $('editChannelId').value        = id;
  $('chNumber').value             = row.querySelector('.ch-num').textContent.trim();
  $('chName').value               = row.querySelector('.ch-name').textContent.trim();
  $('chUrl').value                = row.querySelector('.url-text').title;
  $('chEnabled').checked          = row.querySelector('.status-badge').classList.contains('enabled');
  // Category: try to match
  const catText = row.querySelector('.cat-badge').textContent.trim();
  const sel     = $('chCategory');
  for (let opt of sel.options) {
    if (opt.value === catText) { sel.value = catText; break; }
  }
  $('channelModal').classList.add('open');
}

// ── Add Channel Button ────────────────────────────────────────────────────────
$('addChannelBtn').addEventListener('click', () => {
  $('modalTitle').textContent = 'ADD CHANNEL';
  $('editChannelId').value    = '';
  ['chNumber','chName','chUrl','chLogo','chNotes'].forEach(id => $(id).value = '');
  $('chEnabled').checked      = true;
  $('testResult').textContent = '';
  $('testResult').className   = 'test-result';
  $('channelModal').classList.add('open');
});

// ── Modal Close ───────────────────────────────────────────────────────────────
['modalClose','cancelModal'].forEach(id =>
  $(id).addEventListener('click', () => $('channelModal').classList.remove('open'))
);
$('channelModal').addEventListener('click', e => {
  if (e.target === $('channelModal')) $('channelModal').classList.remove('open');
});

// ── Test URL Button ───────────────────────────────────────────────────────────
$('testUrlBtn').addEventListener('click', async () => {
  const url = $('chUrl').value.trim();
  if (!url) { toast('Enter a URL first', 'error'); return; }
  const res = $('testResult');
  res.textContent = 'CHECKING...';
  res.className   = 'test-result checking';
  const r = await api('POST', '/api/test_stream', { url });
  res.textContent = r.ok ? '✓ STREAM REACHABLE' : '✗ STREAM UNREACHABLE OR UNSUPPORTED';
  res.className   = `test-result ${r.ok ? 'ok' : 'err'}`;
});

// ── Save Channel ──────────────────────────────────────────────────────────────
$('saveChannel').addEventListener('click', async () => {
  const editId = $('editChannelId').value;
  const body = {
    number:   parseInt($('chNumber').value),
    name:     $('chName').value.trim(),
    category: $('chCategory').value,
    url:      $('chUrl').value.trim(),
    logo:     $('chLogo').value.trim(),
    notes:    $('chNotes').value.trim(),
    enabled:  $('chEnabled').checked,
  };
  if (!body.name || !body.url || !body.number) {
    toast('Channel number, name, and URL are required', 'error');
    return;
  }
  const r = editId
    ? await api('PUT', `/api/channels/${editId}`, body)
    : await api('POST', '/api/channels', body);

  if (r.ok) {
    toast(editId ? 'Channel updated' : 'Channel added');
    setTimeout(() => location.reload(), 700);
  } else {
    toast(r.error || 'Failed to save', 'error');
  }
});

// ── Import M3U ────────────────────────────────────────────────────────────────
$('importM3uBtn').addEventListener('click', () => {
  $('m3uUrl').value  = '';
  $('m3uText').value = '';
  $('importResult').textContent = '';
  $('m3uModal').classList.add('open');
});
['m3uModalClose','cancelM3u'].forEach(id =>
  $(id).addEventListener('click', () => $('m3uModal').classList.remove('open'))
);
$('doImport').addEventListener('click', async () => {
  const url  = $('m3uUrl').value.trim();
  const text = $('m3uText').value.trim();
  if (!url && !text) { toast('Provide a URL or paste M3U content', 'error'); return; }
  $('importResult').textContent = 'IMPORTING...';
  $('importResult').className   = 'test-result checking';
  const r = await api('POST', '/api/import/m3u', { url, text });
  $('importResult').textContent = r.ok
    ? `✓ IMPORTED ${r.imported} CHANNELS (TOTAL: ${r.total})`
    : `✗ ${r.error}`;
  $('importResult').className = `test-result ${r.ok ? 'ok' : 'err'}`;
  if (r.ok) setTimeout(() => location.reload(), 1200);
});

// ── Add Category ──────────────────────────────────────────────────────────────
$('addCatBtn').addEventListener('click', () => {
  $('catName').value = '';
  $('catModal').classList.add('open');
});
['catModalClose','cancelCat'].forEach(id =>
  $(id).addEventListener('click', () => $('catModal').classList.remove('open'))
);
$('saveCat').addEventListener('click', async () => {
  const name = $('catName').value.trim();
  if (!name) { toast('Enter a category name', 'error'); return; }
  const r = await api('POST', '/api/categories', { name });
  if (r.ok) {
    toast(`Category "${name}" added`);
    setTimeout(() => location.reload(), 600);
  } else {
    toast(r.error || 'Failed', 'error');
  }
});

// ── Status Poll ───────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const s = await fetch('/api/status').then(r => r.json());
    if (s.channel) {
      document.querySelector('.now-playing') && (
        document.querySelector('.now-playing').textContent = `▶ CH ${s.channel} — ${s.name}`
      );
    }
  } catch {}
}
setInterval(pollStatus, 5000);

// ── Update Checker ────────────────────────────────────────────────────────────
$('checkUpdateBtn').addEventListener('click', async () => {
  const box = $('updateStatus');
  box.className = 'update-status show checking';
  box.innerHTML = '⟳ CHECKING GITHUB...';
  $('checkUpdateBtn').disabled = true;

  try {
    const r = await fetch('/api/update/check').then(r => r.json());
    if (!r.ok) {
      box.className = 'update-status show error';
      box.innerHTML = `✗ ${r.error || 'Check failed'}`;
    } else if (r.up_to_date) {
      box.className = 'update-status show ok';
      box.innerHTML = `✓ UP TO DATE<br><span style="opacity:0.6">Local: ${r.local}</span>`;
    } else {
      box.className = 'update-status show checking';
      box.innerHTML = `⬆ UPDATE AVAILABLE<br>
        <span style="opacity:0.6">Local: ${r.local} → Remote: ${r.remote}</span>
        <button class="apply-update-btn" id="applyUpdateBtn">INSTALL UPDATE</button>`;
      $('applyUpdateBtn').addEventListener('click', applyUpdate);
    }
  } catch (e) {
    box.className = 'update-status show error';
    box.innerHTML = '✗ Could not reach GitHub';
  }
  $('checkUpdateBtn').disabled = false;
});

async function applyUpdate() {
  const box = $('updateStatus');
  box.className = 'update-status show checking';
  box.innerHTML = '⟳ DOWNLOADING UPDATE...';
  try {
    const r = await fetch('/api/update/apply', { method: 'POST' }).then(r => r.json());
    if (r.ok) {
      box.className = 'update-status show ok';
      box.innerHTML = '✓ UPDATE APPLIED<br>Services restarting — page will reload in 15s';
      setTimeout(() => location.reload(), 15000);
    } else {
      box.className = 'update-status show error';
      box.innerHTML = `✗ ${r.error || 'Update failed'}`;
    }
  } catch (e) {
    box.className = 'update-status show error';
    box.innerHTML = '✗ Update failed — check logs';
  }
}
