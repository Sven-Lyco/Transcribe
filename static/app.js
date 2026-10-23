const $ = (id) => document.getElementById(id);

const HISTORY_KEY = 'transcripts';
const PENDING_KEY = 'pendingJobs';
const SETTINGS_KEY = 'settings';
const HISTORY_MAX = 200;
const PENDING_MAX_AGE = 2 * 60 * 60 * 1000;  // länger hält der Server kein Ergebnis vor
const MAX_RETRIES = 20;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const MODEL_INFO = {
  tiny: ['tiny — schnell, ~75 MB', 'Schnellste Option — für kurze Nachrichten gut geeignet.'],
  base: ['base — gut, ~140 MB', 'Gute Balance aus Geschwindigkeit und Qualität.'],
  small: ['small — besser, ~460 MB', 'Bessere Genauigkeit, dauert etwas länger.'],
  medium: ['medium — sehr gut, ~1,4 GB', 'Sehr hohe Genauigkeit — empfohlen für Dialekt/Umgangssprache.'],
  'large-v3-turbo': ['large-v3-turbo — am besten, ~1,6 GB', 'Höchste Genauigkeit, auch bei Dialekt und Umgangssprache.'],
};
const LANGUAGE_NAMES = { de: 'Deutsch', en: 'English', auto: 'Auto-detect' };

// localStorage kann fehlen oder werfen (privater Modus, gesperrte Website-Daten)
const store = {
  get(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : JSON.parse(value);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch { return false; }
  },
};

let config = { hosted: false, models: ['tiny', 'base', 'small', 'medium'], default_model: 'medium' };
let selectedFile = null;
const watchers = new Map();  // job_id -> laufende Verbindung

const tokenInput = $('token');
const modelSelect = $('model');
const languageSelect = $('language');
const outputFolderInput = $('outputFolder');
const speakerNameInput = $('speakerName');
const fileInput = $('fileInput');
const dropZone = $('dropZone');
const startBtn = $('startBtn');
const jobsEl = $('jobs');

// ---------- Einstellungen ----------

function applyConfig() {
  modelSelect.replaceChildren(...config.models.map((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = (MODEL_INFO[name] || [name])[0];
    return option;
  }));
  $('tokenField').hidden = !config.hosted;
  $('outputFolderField').hidden = config.hosted;
  $('subtitle').textContent = config.hosted
    ? '// eigener Server · Verlauf nur in diesem Browser'
    : '// lokal · kein API-Key · kein Internet';
  if (config.hosted) {
    $('emptyHint').textContent = 'Teile eine WhatsApp-Sprachnachricht über den Kurzbefehl oder wähle oben eine Audiodatei aus.';
  }
  // iOS graut .opus-Dateien aus, wenn accept gesetzt ist
  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (isIOS) fileInput.removeAttribute('accept');
}

function loadSettings() {
  const s = store.get(SETTINGS_KEY, {});
  tokenInput.value = s.token || '';
  modelSelect.value = config.models.includes(s.model) ? s.model : config.default_model;
  languageSelect.value = LANGUAGE_NAMES[s.language] ? s.language : 'de';
  outputFolderInput.value = s.outputFolder || '';
  updateSummary();
}

function saveSettings() {
  store.set(SETTINGS_KEY, {
    token: tokenInput.value.trim(),
    model: modelSelect.value,
    language: languageSelect.value,
    outputFolder: outputFolderInput.value.trim(),
  });
  updateSummary();
}

function updateSummary() {
  const hint = (MODEL_INFO[modelSelect.value] || [])[1] || '';
  $('modelHint').textContent = config.hosted
    ? `Läuft auf dem Server. ${hint}`
    : `Beim ersten Mal wird das Modell heruntergeladen. ${hint}`;
  const summary = $('summary');
  summary.replaceChildren(
    `Modell: ${modelSelect.value} · Sprache: ${LANGUAGE_NAMES[languageSelect.value]} · `,
    Object.assign(document.createElement('button'), {
      className: 'link-btn', type: 'button', textContent: 'ändern', onclick: () => toggleSettings(true),
    }),
  );
}

function toggleSettings(open) {
  const panel = $('settings');
  panel.hidden = open === undefined ? !panel.hidden : !open;
  $('settingsBtn').setAttribute('aria-expanded', String(!panel.hidden));
  if (!panel.hidden) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

$('settingsBtn').addEventListener('click', () => toggleSettings());
[tokenInput, outputFolderInput].forEach((el) => el.addEventListener('input', saveSettings));
[modelSelect, languageSelect].forEach((el) => el.addEventListener('change', saveSettings));

// ---------- Verlauf ----------

function getHistory() {
  const list = store.get(HISTORY_KEY, []);
  return Array.isArray(list) ? list : [];
}

function saveTranscript(entry) {
  const list = getHistory().filter((t) => t.id !== entry.id);
  list.unshift(entry);
  return store.set(HISTORY_KEY, list.slice(0, HISTORY_MAX));
}

function deleteTranscript(id) {
  store.set(HISTORY_KEY, getHistory().filter((t) => t.id !== id));
  renderHistory();
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const sameYear = d.getFullYear() === new Date().getFullYear();
  const date = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: sameYear ? undefined : '2-digit' });
  const time = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  return `${date} ${time}`;
}

function formatDuration(seconds) {
  if (typeof seconds !== 'number') return '';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

async function copyText(text, button) {
  const label = button.textContent;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = 'Kopiert!';
  } catch {
    button.textContent = 'Fehlgeschlagen';
  }
  setTimeout(() => { button.textContent = label; }, 2000);
}

function renderHistory(freshId) {
  const list = getHistory();
  $('emptyState').hidden = list.length > 0;
  $('historyCount').textContent = list.length ? `${list.length} gespeichert` : '';
  $('historyList').replaceChildren(...list.map((t) => {
    const li = document.createElement('li');
    li.className = 'card' + (t.id === freshId ? ' fresh' : '');
    li.dataset.id = t.id;

    const meta = document.createElement('div');
    meta.className = 'card-meta';
    const when = document.createElement('span');
    when.className = 'when';
    when.textContent = [formatDate(t.date), formatDuration(t.duration)].filter(Boolean).join(' · ');
    meta.append(when);
    if (t.fileName) {
      const file = document.createElement('span');
      file.className = 'file';
      file.textContent = `· ${t.fileName}`;
      file.title = t.fileName;
      meta.append(file);
    }

    const text = document.createElement('p');
    text.className = 'card-text' + (t.id === freshId ? '' : ' clamped');
    text.textContent = t.text || '(kein Text erkannt)';
    text.title = 'Antippen zum Auf-/Zuklappen';
    text.addEventListener('click', () => {
      if (!window.getSelection().toString()) text.classList.toggle('clamped');
    });

    const actions = document.createElement('div');
    actions.className = 'card-actions';
    const copy = Object.assign(document.createElement('button'), {
      className: 'ghost-btn copy', type: 'button', textContent: 'Kopieren',
    });
    copy.addEventListener('click', () => copyText(t.text, copy));
    const del = Object.assign(document.createElement('button'), {
      className: 'ghost-btn danger', type: 'button', textContent: 'Löschen',
    });
    del.addEventListener('click', () => {
      if (confirm('Dieses Transkript löschen?')) deleteTranscript(t.id);
    });
    actions.append(copy, del);

    li.append(meta, text);
    if (t.savedAs) {
      const saved = document.createElement('div');
      saved.className = 'card-saved';
      saved.textContent = `Gespeichert als: ${t.savedAs}`;
      li.append(saved);
    }
    li.append(actions);
    return li;
  }));

  if (freshId) {
    const card = $('historyList').querySelector('.card.fresh');
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => card.classList.remove('fresh'), 4000);
    }
  }
}

// ---------- Export / Import ----------

$('exportBtn').addEventListener('click', async () => {
  const list = getHistory();
  if (!list.length) { $('settingsMsg').textContent = 'Der Verlauf ist leer.'; return; }
  const name = `transkripte-${new Date().toISOString().slice(0, 10)}.json`;
  const data = JSON.stringify({ version: 1, exported_at: new Date().toISOString(), transcripts: list }, null, 2);
  const file = new File([data], name, { type: 'application/json' });

  // Auf dem iPhone über das Teilen-Menü (z.B. „In Dateien sichern“), sonst als Download
  if (matchMedia('(pointer: coarse)').matches && navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file] }); return; }
    catch (e) { if (e.name === 'AbortError') return; }
  }
  const url = URL.createObjectURL(file);
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

$('importInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const msg = $('settingsMsg');
  msg.classList.remove('error');
  try {
    const parsed = JSON.parse(await file.text());
    const incoming = (Array.isArray(parsed) ? parsed : parsed.transcripts || [])
      .filter((t) => t && typeof t.id === 'string' && typeof t.text === 'string');
    const byId = new Map(getHistory().map((t) => [t.id, t]));
    let added = 0;
    for (const t of incoming) {
      if (!byId.has(t.id)) added++;
      byId.set(t.id, t);
    }
    const merged = [...byId.values()]
      .sort((a, b) => String(b.date).localeCompare(String(a.date)))
      .slice(0, HISTORY_MAX);
    if (!store.set(HISTORY_KEY, merged)) throw new Error('Speichern im Browser nicht möglich.');
    renderHistory();
    msg.textContent = `${added} Transkript(e) importiert.`;
  } catch (err) {
    msg.classList.add('error');
    msg.textContent = `Import fehlgeschlagen: ${err.message}`;
  }
});

// ---------- Jobs ----------

function getPending() {
  const list = store.get(PENDING_KEY, []);
  return Array.isArray(list) ? list : [];
}

function addPending(job) {
  store.set(PENDING_KEY, [...getPending().filter((j) => j.id !== job.id), job]);
}

function removePending(id) {
  store.set(PENDING_KEY, getPending().filter((j) => j.id !== id));
}

function resumePending() {
  const known = new Set(getHistory().map((t) => t.id));
  for (const job of getPending()) {
    if (known.has(job.id) || Date.now() - job.startedAt > PENDING_MAX_AGE) {
      removePending(job.id);
    } else if (!watchers.has(job.id)) {
      watchJob(job);
    }
  }
}

function createStatus() {
  const el = document.createElement('div');
  el.className = 'status';
  const title = document.createElement('div');
  title.className = 'progress';
  const detail = document.createElement('div');
  detail.className = 'status-detail';
  const bar = document.createElement('div');
  bar.className = 'prog-bar';
  const fill = document.createElement('div');
  fill.className = 'prog-fill';
  bar.append(fill);
  el.append(title, detail, bar);
  jobsEl.append(el);

  return {
    el,
    busy(text) {
      const spinner = document.createElement('span');
      spinner.className = 'spinner';
      title.replaceChildren(spinner, text);
    },
    detail(text) { detail.textContent = text; },
    progress(value) { fill.style.width = `${value}%`; },
    fail(heading, message) {
      el.classList.add('failed');
      title.textContent = `❌ ${heading}`;
      detail.textContent = message;
      bar.hidden = true;
      const close = Object.assign(document.createElement('button'), {
        className: 'ghost-btn', type: 'button', textContent: 'Schließen',
      });
      close.addEventListener('click', () => el.remove());
      el.append(close);
    },
  };
}

function watchJob(job) {
  const status = createStatus();
  const name = () => job.fileName || 'Sprachnachricht';
  status.busy(name());
  status.detail('Verbindung zum Server …');

  const watcher = { es: null, retries: 0, timer: null };
  watchers.set(job.id, watcher);

  const stop = () => {
    if (watcher.es) watcher.es.close();
    clearTimeout(watcher.timer);
    watchers.delete(job.id);
  };

  const connect = () => {
    watcher.es = new EventSource(`/progress?job=${encodeURIComponent(job.id)}`);

    watcher.es.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      watcher.retries = 0;
      if (msg.file_name && !job.fileName) {
        job.fileName = msg.file_name;
        addPending(job);
        status.busy(name());
      }

      if (msg.type === 'progress') {
        status.progress(msg.value);
        if (msg.state === 'queued') status.detail('In der Warteschlange …');
        else if (msg.value > 0) status.detail(`Fortschritt: ${msg.value}%`);
        else status.detail('Modell wird geladen & Transkription läuft … Beim ersten Mal kann das 1–2 Minuten dauern.');
      } else if (msg.type === 'done') {
        stop();
        const entry = {
          id: job.id,
          date: new Date().toISOString(),
          fileName: job.fileName,
          text: msg.text,
          language: msg.language,
          duration: msg.duration,
          savedAs: msg.saved_as || undefined,
        };
        if (saveTranscript(entry)) {
          removePending(job.id);
          fetch(`/job?job=${encodeURIComponent(job.id)}`, { method: 'DELETE' }).catch(() => {});
          status.el.remove();
          renderHistory(job.id);
        } else {
          status.fail('Nicht gespeichert', 'Der Browser erlaubt keinen Speicher (privater Modus?). Text hier kopieren:');
          const copy = Object.assign(document.createElement('button'), {
            className: 'ghost-btn', type: 'button', textContent: 'Text kopieren',
          });
          copy.addEventListener('click', () => copyText(msg.text, copy));
          status.el.append(copy);
        }
      } else if (msg.type === 'error') {
        stop();
        removePending(job.id);
        // Ein anderer Tab hat das Ergebnis schon abgeholt und gespeichert
        if (msg.gone && getHistory().some((t) => t.id === job.id)) {
          status.el.remove();
          renderHistory();
          return;
        }
        status.fail('Fehler', msg.message);
      }
    };

    watcher.es.onerror = () => {
      watcher.es.close();
      if (watcher.retries++ < MAX_RETRIES) {
        status.detail('Verbindung unterbrochen – neuer Versuch …');
        watcher.timer = setTimeout(connect, 3000);
      } else {
        stop();  // bleibt in pendingJobs und wird beim nächsten Öffnen fortgesetzt
        status.fail('Verbindungsfehler', 'Server nicht erreichbar. Beim nächsten Öffnen der Seite wird es erneut versucht.');
      }
    };
  };

  connect();
}

// ---------- Datei auswählen & hochladen ----------

fileInput.addEventListener('change', (e) => {
  if (e.target.files[0]) selectFile(e.target.files[0]);
});

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
});

function selectFile(file) {
  selectedFile = file;
  const mb = (file.size / 1024 / 1024).toFixed(1);
  $('fileInfo').textContent = `${file.name} (${mb} MB)`;
  startBtn.disabled = false;
  // file.path is available in some local/Electron environments
  if (file.path && !config.hosted) {
    const sep = file.path.includes('/') ? '/' : '\\';
    outputFolderInput.value = file.path.substring(0, file.path.lastIndexOf(sep));
  }
}

startBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  const token = tokenInput.value.trim();
  if (config.hosted && !token) {
    toggleSettings(true);
    tokenInput.focus();
    $('settingsMsg').textContent = 'Bitte zuerst das Token eintragen.';
    return;
  }

  const file = selectedFile;
  startBtn.disabled = true;
  const upload = createStatus();
  upload.busy(file.name);
  upload.detail('Datei wird übertragen …');

  const formData = new FormData();
  formData.append('file', file);
  formData.append('model', modelSelect.value);
  formData.append('language', languageSelect.value);
  formData.append('speaker_name', speakerNameInput.value.trim());
  if (!config.hosted) formData.append('output_folder', outputFolderInput.value.trim());

  try {
    const response = await fetch('/transcribe', {
      method: 'POST',
      body: formData,
      headers: config.hosted ? { Authorization: `Bearer ${token}` } : {},
    });
    const data = await response.json();
    if (data.error) {
      upload.fail('Fehler', data.error);
      if (response.status === 401) toggleSettings(true);
      startBtn.disabled = false;
      return;
    }
    upload.el.remove();
    const job = { id: data.job_id, fileName: file.name, startedAt: Date.now() };
    addPending(job);
    watchJob(job);
    selectedFile = null;
    fileInput.value = '';
    $('fileInfo').textContent = '';
    speakerNameInput.value = '';
  } catch (err) {
    upload.fail('Verbindungsfehler', err.message);
    startBtn.disabled = false;
  }
});

// ---------- Start ----------

async function init() {
  try {
    const response = await fetch('/config');
    if (response.ok) config = await response.json();
  } catch {}
  applyConfig();
  loadSettings();
  renderHistory();

  // Vom Kurzbefehl geöffnet: /?job=<id>
  const jobId = new URLSearchParams(location.search).get('job');
  if (jobId && UUID_RE.test(jobId)) {
    addPending({ id: jobId, fileName: '', startedAt: Date.now() });
  }
  if (location.search) history.replaceState(null, '', location.pathname);
  resumePending();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}

// Safari pausiert Hintergrund-Tabs; beim Zurückkehren offene Jobs wieder aufnehmen
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    renderHistory();
    resumePending();
  }
});

window.addEventListener('storage', (e) => {
  if (e.key === HISTORY_KEY) renderHistory();
});

init();
