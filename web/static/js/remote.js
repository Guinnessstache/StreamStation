// StreamStation — Remote Control JS

// ── State ─────────────────────────────────────────────────────────────────────
let currentChannel = null;
let currentVolume  = 80;
let isMuted        = false;
let entryBuffer    = '';
let entryTimer     = null;
let drawerOpen     = false;
const ENTRY_TIMEOUT = 2500; // ms to wait before tuning after digit entry

// ── DOM Refs ──────────────────────────────────────────────────────────────────
const displayNumber  = document.getElementById('displayNumber');
const displayName    = document.getElementById('displayName');
const powerIndicator = document.getElementById('powerIndicator');
const muteIndicator  = document.getElementById('muteIndicator');
const signalIndicator= document.getElementById('signalIndicator');
const entryOverlay   = document.getElementById('entryOverlay');
const entryDisplay   = document.getElementById('entryDisplay');
const entryTimerFill = document.getElementById('entryTimerFill');
const infoOverlay    = document.getElementById('infoOverlay');
const drawerHandle   = document.getElementById('drawerHandle');
const drawerContent  = document.getElementById('drawerContent');

// ── API ───────────────────────────────────────────────────────────────────────
async function apiPost(path) {
  try {
    const r = await fetch(path, { method: 'POST' });
    return r.json();
  } catch { return null; }
}

// ── Display Update ────────────────────────────────────────────────────────────
function updateDisplay(ch, name) {
  currentChannel = ch;
  displayNumber.textContent = ch ? String(ch).padStart(2, '0') : '--';
  displayName.textContent   = name || 'NO SIGNAL';
  signalIndicator.classList.toggle('active', !!ch);
  // Update drawer highlight
  document.querySelectorAll('.drawer-ch-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.num) === ch);
  });
}

// ── Status Poll ───────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const s = await fetch('/api/status').then(r => r.json());
    updateDisplay(s.channel, s.name);
    powerIndicator.classList.toggle('active', s.engine_running);
  } catch {}
}
setInterval(pollStatus, 4000);
pollStatus();

// ── Tune ──────────────────────────────────────────────────────────────────────
async function tune(num) {
  const r = await apiPost(`/api/tune/${num}`);
  if (r && r.ok) {
    // Status will catch up via poll; optimistic update
    const ch = CHANNELS.find(c => c.number === num);
    updateDisplay(num, ch ? ch.name : `CH ${num}`);
  }
}

// ── Channel Up/Down ───────────────────────────────────────────────────────────
document.getElementById('chUpBtn').addEventListener('click', async () => {
  await apiPost('/api/channel/up');
  setTimeout(pollStatus, 400);
});
document.getElementById('chDownBtn').addEventListener('click', async () => {
  await apiPost('/api/channel/down');
  setTimeout(pollStatus, 400);
});
document.getElementById('lastChBtn').addEventListener('click', async () => {
  await apiPost('/api/channel/last');
  setTimeout(pollStatus, 400);
});

// ── Volume ────────────────────────────────────────────────────────────────────
document.getElementById('volUpBtn').addEventListener('click', async () => {
  currentVolume = Math.min(100, currentVolume + 10);
  await apiPost(`/api/volume/${currentVolume}`);
});
document.getElementById('volDownBtn').addEventListener('click', async () => {
  currentVolume = Math.max(0, currentVolume - 10);
  await apiPost(`/api/volume/${currentVolume}`);
});

// ── Mute ──────────────────────────────────────────────────────────────────────
document.getElementById('muteBtn').addEventListener('click', () => {
  isMuted = !isMuted;
  muteIndicator.classList.toggle('active', isMuted);
  // Send volume 0 or restore
  apiPost(`/api/volume/${isMuted ? 0 : currentVolume}`);
});

// ── Power Button ──────────────────────────────────────────────────────────────
document.getElementById('powerBtn').addEventListener('click', async () => {
  const r = await fetch('/api/status').then(r => r.json());
  if (r.engine_running) {
    // Can't stop engine from remote (safety) — just show info
    displayName.textContent = 'ENGINE RUNNING';
  }
  powerIndicator.classList.toggle('active');
});

// ── Info Overlay ──────────────────────────────────────────────────────────────
document.getElementById('infoBtn').addEventListener('click', showInfo);
document.getElementById('infoClose').addEventListener('click', () => {
  infoOverlay.classList.remove('show');
});
infoOverlay.addEventListener('click', () => infoOverlay.classList.remove('show'));

function showInfo() {
  const ch  = CHANNELS.find(c => c.number === currentChannel);
  document.getElementById('infoCh').textContent   = currentChannel ? `CH ${currentChannel}` : 'CH --';
  document.getElementById('infoName').textContent  = ch ? ch.name : (displayName.textContent || 'NO SIGNAL');
  document.getElementById('infoCat').textContent   = ch ? ch.category.toUpperCase() : '';
  infoOverlay.classList.add('show');
  setTimeout(() => infoOverlay.classList.remove('show'), 4000);
}

// ── Number Pad Entry ──────────────────────────────────────────────────────────
document.querySelectorAll('.num-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const digit = btn.dataset.digit;
    if (digit === '*') { apiPost('/api/channel/down'); setTimeout(pollStatus, 400); return; }
    if (digit === '#') { apiPost('/api/channel/up');   setTimeout(pollStatus, 400); return; }
    handleDigit(digit);
  });
});

function handleDigit(d) {
  entryBuffer += d;
  entryDisplay.textContent = entryBuffer.padStart(2, ' ');
  entryOverlay.classList.add('show');

  // Reset timer bar animation
  entryTimerFill.style.transition = 'none';
  entryTimerFill.style.transform  = 'scaleX(1)';
  requestAnimationFrame(() => {
    entryTimerFill.style.transition = `transform ${ENTRY_TIMEOUT}ms linear`;
    entryTimerFill.style.transform  = 'scaleX(0)';
  });

  clearTimeout(entryTimer);

  // If 3 digits entered, tune immediately
  if (entryBuffer.length >= 3) {
    commitEntry();
    return;
  }

  entryTimer = setTimeout(commitEntry, ENTRY_TIMEOUT);
}

function commitEntry() {
  clearTimeout(entryTimer);
  const num = parseInt(entryBuffer);
  entryBuffer = '';
  entryOverlay.classList.remove('show');
  if (num > 0) tune(num);
}

// ── Category Quick Jump ───────────────────────────────────────────────────────
document.querySelectorAll('.cat-jump-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const cat    = btn.dataset.cat;
    const match  = CHANNELS.filter(c => c.category === cat && c.enabled);
    if (match.length) tune(match[0].number);
  });
});

// ── Channel Drawer ────────────────────────────────────────────────────────────
drawerHandle.addEventListener('click', () => {
  drawerOpen = !drawerOpen;
  drawerContent.classList.toggle('open', drawerOpen);
  drawerHandle.classList.toggle('open', drawerOpen);
  drawerHandle.textContent = drawerOpen ? '▼ CHANNEL LIST' : '▲ CHANNEL LIST';
});

document.querySelectorAll('.drawer-ch-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    tune(parseInt(btn.dataset.num));
    drawerOpen = false;
    drawerContent.classList.remove('open');
    drawerHandle.classList.remove('open');
    drawerHandle.textContent = '▲ CHANNEL LIST';
  });
});

// ── Haptic feedback for mobile ────────────────────────────────────────────────
document.querySelectorAll('.rmt-btn, .num-btn, .cat-jump-btn, .drawer-ch-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (navigator.vibrate) navigator.vibrate(12);
  });
});

// ── Prevent scroll bounce on iOS ─────────────────────────────────────────────
document.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
