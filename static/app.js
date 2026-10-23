const $ = (id) => document.getElementById(id);

const PENDING_KEY = 'pendingJobs';
const SETTINGS_KEY = 'settings';
const PENDING_MAX_AGE = 2 * 60 * 60 * 1000;  // danach hat der Server das Ergebnis längst verworfen
const MAX_RETRIES = 20;

const MODEL_INFO = {
  tiny: ['tiny — schnell, ~75 MB', 'Schnellste Option — für kurze Nachrichten gut geeignet.'],
  base: ['base — gut, ~140 MB', 'Gute Balance aus Geschwindigkeit und Qualität.'],
  small: ['small — besser, ~460 MB', 'Bessere Genauigkeit, dauert etwas länger.'],
  medium: ['medium — sehr gut, ~1,5 GB', 'Sehr hohe Genauigkeit, gut bei Dialekt/Umgangssprache — empfohlen.'],
  'large-v3-turbo': ['large-v3-turbo — groß, ~1,6 GB', 'Neuestes Modell, schnell; je nach Aufnahme etwas besser oder schlechter als medium.'],
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

let config = { engines: [], default_engine: null };
let modelChoice = {};  // gewähltes Modell je Engine
let selectedFile = null;
const watchers = new Map();  // job_id -> laufende Verbindung

const engineSelect = $('engine');
const modelSelect = $('model');
const languageSelect = $('language');
const outputFolderInput = $('outputFolder');
const speakerNameInput = $('speakerName');
const fileInput = $('fileInput');
const dropZone = $('dropZone');
const startBtn = $('startBtn');
const jobsEl = $('jobs');

// ---------- Einstellungen ----------

function option(value, label) {
  return Object.assign(document.createElement('option'), { value, textContent: label });
}

const currentEngine = () => config.engines.find((e) => e.id === engineSelect.value) || config.engines[0];

function applyConfig() {
  engineSelect.replaceChildren(...config.engines.map((e) => option(e.id, e.label)));
  $('engineField').hidden = config.engines.length < 2;
  // Die App speichert immer in ihrem eigenen Ordner und kann ihre Daten komplett löschen
  $('outputFolderField').hidden = !!config.app;
  $('resetBtn').hidden = !config.app;
  if (config.output_dir) $('dataHint').textContent = `Transkripte: ${config.output_dir}`;
}

function fillModels() {
  const engine = currentEngine();
  if (!engine) return;
  modelSelect.replaceChildren(...engine.models.map((name) => option(name, (MODEL_INFO[name] || [name])[0])));
  const preferred = modelChoice[engine.id];
  modelSelect.value = engine.models.includes(preferred) ? preferred : engine.default_model;
}

function loadSettings() {
  const s = store.get(SETTINGS_KEY, {});
  modelChoice = s.models || {};
  engineSelect.value = config.engines.some((e) => e.id === s.engine) ? s.engine : config.default_engine;
  fillModels();
  languageSelect.value = LANGUAGE_NAMES[s.language] ? s.language : 'de';
  outputFolderInput.value = s.outputFolder || '';
  updateSummary();
}

function saveSettings() {
  modelChoice[engineSelect.value] = modelSelect.value;
  store.set(SETTINGS_KEY, {
    engine: engineSelect.value,
    models: modelChoice,
    language: languageSelect.value,
    outputFolder: outputFolderInput.value.trim(),
  });
  updateSummary();
}

function updateSummary() {
  const hint = (MODEL_INFO[modelSelect.value] || [])[1] || '';
  $('modelHint').textContent = `Beim ersten Mal wird das Modell heruntergeladen. ${hint}`;
  const engine = currentEngine();
  const engineName = engine ? ` (${engine.label.split(' (')[0]})` : '';
  const summary = $('summary');
  summary.replaceChildren(
    `Modell: ${modelSelect.value}${engineName} · Sprache: ${LANGUAGE_NAMES[languageSelect.value]} · `,
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
outputFolderInput.addEventListener('input', saveSettings);
[modelSelect, languageSelect].forEach((el) => el.addEventListener('change', saveSettings));
engineSelect.addEventListener('change', () => {
  fillModels();
  saveSettings();
});

// ---------- Verlauf ----------

// Der Verlauf sind die gespeicherten .txt-Dateien; der Server liest sie aus dem Transkript-Ordner
let history = [];
let historySignature = null;
const HISTORY_REFRESH = 5000;  // ms; übernimmt Änderungen am Ordner, z.B. im Finder gelöschte .txt

// Ohne Server zeigt die Seite nur noch den letzten Stand; das soll man sehen statt still nichts passiert
function setOffline(offline) {
  $('offline').hidden = !offline;
}

async function loadHistory(freshId) {
  try {
    const response = await fetch('/transcripts');
    setOffline(false);
    if (!response.ok) return;
    const list = await response.json();
    const signature = JSON.stringify(list);
    // Unverändert: Liste nicht neu aufbauen, sonst klappen offene Karten zu und Markierungen gehen verloren
    if (signature === historySignature && !freshId) return;
    history = list;
    historySignature = signature;
  } catch {
    setOffline(true);
    return;
  }
  renderHistory(freshId);
}

async function deleteTranscript(id) {
  try {
    const response = await fetch(`/transcripts?id=${encodeURIComponent(id)}`, { method: 'DELETE' });
    // 404: schon weg, z.B. im Finder gelöscht; dann reicht neu laden
    if (!response.ok && response.status !== 404) throw new Error(`HTTP ${response.status}`);
  } catch (err) {
    // fetch meldet fehlende Verbindung als TypeError
    createStatus().fail('Löschen fehlgeschlagen', err instanceof TypeError ? 'Keine Verbindung zum Transcribe-Server.' : err.message);
  }
  loadHistory();
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

// ---------- Abspielen ----------

// Ein Player für alle Karten: Startet eine andere Karte, stoppt die vorige
const player = { audio: new Audio(), id: null, segments: [], raf: 0 };
player.audio.preload = 'metadata';

const cardById = (id) => $('historyList').querySelector(`.card[data-id="${CSS.escape(id)}"]`);

function currentSegment(segments, time) {
  // Der Abschnitt bleibt markiert, bis der nächste beginnt (auch über kurze Pausen hinweg)
  let index = -1;
  for (let i = 0; i < segments.length && segments[i][0] <= time + 0.05; i++) index = i;
  return index;
}

function updatePlayerUI() {
  const card = player.id && cardById(player.id);
  if (!card) return;
  const { audio } = player;
  const total = Number.isFinite(audio.duration) ? audio.duration : Number(card.dataset.duration) || 0;
  // Nur ändern, was sich geändert hat: Wird der Button-Text während eines Klicks ersetzt
  // (das hier läuft bis zu 60-mal pro Sekunde), verwirft WebKit den Klick.
  const btn = card.querySelector('.play-btn');
  const label = audio.paused ? '▶' : '❚❚';
  if (btn.textContent !== label) {
    btn.textContent = label;
    btn.setAttribute('aria-label', audio.paused ? 'Abspielen' : 'Pause');
  }
  const time = card.querySelector('.player-time');
  const timeText = `${formatDuration(Math.floor(audio.currentTime))} / ${formatDuration(Math.round(total))}`;
  if (time.textContent !== timeText) time.textContent = timeText;
  card.querySelector('.player-fill').style.width = total ? `${Math.min(100, (audio.currentTime / total) * 100)}%` : '0%';

  const index = audio.ended ? -1 : currentSegment(player.segments, audio.currentTime);
  const previous = card.querySelector('.seg.spoken');
  const next = index >= 0 && (audio.currentTime > 0 || !audio.paused) ? card.querySelector(`.seg[data-index="${index}"]`) : null;
  if (previous !== next) {
    previous?.classList.remove('spoken');
    next?.classList.add('spoken');
    if (next && !audio.paused) {
      const rect = next.getBoundingClientRect();
      if (rect.top < 0 || rect.bottom > window.innerHeight) next.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
}

function tick() {
  updatePlayerUI();
  if (!player.audio.paused) player.raf = requestAnimationFrame(tick);
}

player.audio.addEventListener('play', () => {
  cancelAnimationFrame(player.raf);
  player.raf = requestAnimationFrame(tick);
});
['pause', 'seeked', 'loadedmetadata', 'timeupdate'].forEach((event) => player.audio.addEventListener(event, updatePlayerUI));
player.audio.addEventListener('ended', () => {
  updatePlayerUI();
  player.audio.currentTime = 0;  // bereit zum erneuten Abspielen
});
player.audio.addEventListener('error', () => {
  const card = player.id && cardById(player.id);
  if (card && player.audio.getAttribute('src')) card.querySelector('.player-time').textContent = 'Abspielen nicht möglich';
});

function stopPlayer() {
  player.audio.pause();
  player.audio.removeAttribute('src');
  player.audio.load();
  player.id = null;
  player.segments = [];
}

function playFrom(t, time) {
  if (player.id !== t.id) {
    const previous = player.id && cardById(player.id);
    stopPlayer();
    if (previous) {
      previous.querySelector('.seg.spoken')?.classList.remove('spoken');
      previous.querySelector('.play-btn').textContent = '▶';
      previous.querySelector('.player-fill').style.width = '0%';
    }
    player.id = t.id;
    player.segments = t.segments || [];
    // Die Original-Aufnahme abspielen; nur wenn das Fenster ihr Format nicht kann, eine umgewandelte Fassung
    const playable = t.audio_type && player.audio.canPlayType(t.audio_type) !== '';
    player.audio.src = `/audio?id=${encodeURIComponent(t.id)}${playable ? '' : '&compat=1'}`;
  }
  if (time !== undefined) {
    // Vor dem Laden der Metadaten lässt sich die Position noch nicht setzen
    if (player.audio.readyState >= 1) player.audio.currentTime = time;
    else player.audio.addEventListener('loadedmetadata', () => { player.audio.currentTime = time; }, { once: true });
  }
  cardById(t.id)?.querySelector('.card-text').classList.remove('clamped');
  player.audio.play().catch(() => {});
  updatePlayerUI();
}

function togglePlay(t) {
  if (player.id === t.id && !player.audio.paused) player.audio.pause();
  else playFrom(t);
}

function createPlayer(t) {
  const row = document.createElement('div');
  row.className = 'player';
  const btn = Object.assign(document.createElement('button'), {
    className: 'ghost-btn play-btn', type: 'button', textContent: '▶',
  });
  btn.setAttribute('aria-label', 'Abspielen');
  btn.addEventListener('click', () => togglePlay(t));
  const track = document.createElement('div');
  track.className = 'player-track';
  track.title = 'Klicken, um zu dieser Stelle zu springen';
  const bar = document.createElement('div');
  bar.className = 'player-bar';
  const fill = document.createElement('div');
  fill.className = 'player-fill';
  bar.append(fill);
  track.append(bar);
  track.addEventListener('click', (e) => {
    const rect = bar.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const total = player.id === t.id && Number.isFinite(player.audio.duration) ? player.audio.duration : t.duration || 0;
    playFrom(t, fraction * total);
  });
  const time = document.createElement('span');
  time.className = 'player-time';
  time.textContent = `0:00 / ${formatDuration(t.duration) || '–'}`;
  row.append(btn, track, time);
  return row;
}

function fillText(textEl, t) {
  const segments = t.segments || [];
  // Abschnitte nur nutzen, wenn sie zum Text passen (die .txt kann im Finder bearbeitet worden sein)
  const start = segments.length ? (t.text || '').indexOf(segments[0][2]) : -1;
  if (start < 0 || !t.audio) {
    textEl.textContent = t.text || '(kein Text erkannt)';
    return;
  }
  textEl.append(t.text.slice(0, start));  // Präfix mit Zeitstempel/Name
  segments.forEach(([from, , words], index) => {
    const span = Object.assign(document.createElement('span'), { className: 'seg', textContent: words });
    span.dataset.index = index;
    span.title = 'Ab hier abspielen';
    span.addEventListener('click', (e) => {
      if (window.getSelection().toString()) return;  // Text markieren statt springen
      e.stopPropagation();
      playFrom(t, from);
    });
    textEl.append(span, index < segments.length - 1 ? ' ' : '');
  });
}

function renderHistory(freshId) {
  const list = history;
  if (player.id && !list.some((t) => t.id === player.id)) stopPlayer();  // abspielendes Transkript gelöscht
  $('emptyState').hidden = list.length > 0;
  $('historyCount').textContent = list.length ? `${list.length} gespeichert` : '';
  $('historyList').replaceChildren(...list.map((t) => {
    const li = document.createElement('li');
    li.className = 'card' + (t.id === freshId ? ' fresh' : '');
    li.dataset.id = t.id;
    if (t.duration) li.dataset.duration = t.duration;

    const meta = document.createElement('div');
    meta.className = 'card-meta';
    const when = document.createElement('span');
    when.className = 'when';
    when.textContent = [formatDate(t.date), formatDuration(t.duration)].filter(Boolean).join(' · ');
    meta.append(when);
    if (t.file_name) {
      const file = document.createElement('span');
      file.className = 'file';
      file.textContent = `· ${t.file_name}`;
      file.title = t.file_name;
      meta.append(file);
    }

    const text = document.createElement('p');
    const open = t.id === freshId || t.id === player.id;
    text.className = 'card-text' + (open ? '' : ' clamped');
    fillText(text, t);
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
      if (confirm('Dieses Transkript löschen? Die .txt-Datei wird mit gelöscht.')) deleteTranscript(t.id);
    });
    actions.append(copy, del);

    li.append(meta);
    if (t.audio) li.append(createPlayer(t));
    li.append(text);
    if (t.saved_as && !config.app) {
      const saved = document.createElement('div');
      saved.className = 'card-saved';
      saved.textContent = `Gespeichert als: ${t.saved_as}`;
      li.append(saved);
    }
    li.append(actions);
    return li;
  }));

  updatePlayerUI();  // neu aufgebaute Karte wieder an die laufende Wiedergabe binden

  if (freshId) {
    const card = $('historyList').querySelector('.card.fresh');
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => card.classList.remove('fresh'), 4000);
    }
  }
}

// ---------- Daten ----------

$('openFolderBtn').addEventListener('click', () => {
  fetch('/open-folder', { method: 'POST' }).catch(() => {});
});

$('resetBtn').addEventListener('click', async () => {
  const question = 'Alle App-Daten löschen?\n\n'
    + 'Das löscht alle Transkripte, den Verlauf und die heruntergeladenen Whisper-Modelle. '
    + 'Das lässt sich nicht rückgängig machen.';
  if (!confirm(question)) return;
  const msg = $('settingsMsg');
  msg.classList.remove('error');
  try {
    const response = await fetch('/reset', { method: 'POST' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    for (const watcher of watchers.values()) {
      if (watcher.es) watcher.es.close();
      clearTimeout(watcher.timer);
    }
    watchers.clear();
    jobsEl.replaceChildren();
    try { localStorage.clear(); } catch {}
    loadSettings();
    loadHistory();
    msg.textContent = 'Alle App-Daten wurden gelöscht. Du kannst Transcribe jetzt beenden und in den Papierkorb ziehen.';
  } catch (err) {
    msg.classList.add('error');
    msg.textContent = `Löschen fehlgeschlagen: ${err.message}`;
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
  for (const job of getPending()) {
    if (Date.now() - job.startedAt > PENDING_MAX_AGE) {
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
  let cancelBtn = null;

  return {
    el,
    busy(text) {
      const spinner = document.createElement('span');
      spinner.className = 'spinner';
      title.replaceChildren(spinner, text);
    },
    detail(text) { detail.textContent = text; },
    progress(value) { fill.style.width = `${value}%`; },
    cancellable(onCancel) {
      cancelBtn = Object.assign(document.createElement('button'), {
        className: 'ghost-btn danger', type: 'button', textContent: 'Abbrechen',
      });
      cancelBtn.addEventListener('click', onCancel);
      el.append(cancelBtn);
    },
    fail(heading, message) {
      if (cancelBtn) cancelBtn.remove();
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

  // Löscht den Job auf dem Server: Wartet er noch, startet er nicht mehr,
  // läuft er schon, hört der Server nach dem aktuellen Abschnitt (ca. 30 s Audio) auf.
  status.cancellable(() => {
    if (!confirm('Transkription abbrechen?')) return;
    stop();
    removePending(job.id);
    fetch(`/job?job=${encodeURIComponent(job.id)}`, { method: 'DELETE' }).catch(() => {});
    status.el.remove();
  });

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
        else if (msg.state === 'downloading') status.detail('Modell wird heruntergeladen (einmalig, bis zu ca. 1,6 GB) …');
        else if (msg.value > 0) status.detail(`Fortschritt: ${msg.value}%`);
        else status.detail('Modell wird geladen & Transkription läuft …');
      } else if (msg.type === 'done') {
        // Der Server hat die .txt schon gespeichert; Ergebnis bestätigen und Verlauf neu laden
        stop();
        removePending(job.id);
        fetch(`/job?job=${encodeURIComponent(job.id)}`, { method: 'DELETE' }).catch(() => {});
        status.el.remove();
        loadHistory(msg.id);
      } else if (msg.type === 'error') {
        stop();
        removePending(job.id);
        status.fail('Fehler', msg.message);
        if (msg.gone) loadHistory();  // z.B. in einem anderen Tab schon fertig geworden
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
  const name = document.createElement('span');
  name.textContent = `${file.name} (${mb} MB)`;
  const remove = Object.assign(document.createElement('button'), {
    type: 'button', className: 'file-remove', textContent: '✕', title: 'Auswahl entfernen',
  });
  remove.setAttribute('aria-label', 'Auswahl entfernen');
  remove.addEventListener('click', (e) => {
    e.stopPropagation();  // sonst öffnet sich die Dateiauswahl der Ablagefläche
    clearSelection();
  });
  $('fileInfo').replaceChildren(name, remove);
  startBtn.disabled = false;
  // file.path is available in some local/Electron environments
  if (file.path) {
    const sep = file.path.includes('/') ? '/' : '\\';
    outputFolderInput.value = file.path.substring(0, file.path.lastIndexOf(sep));
  }
}

function clearSelection() {
  selectedFile = null;
  fileInput.value = '';
  $('fileInfo').replaceChildren();
  startBtn.disabled = true;
}

startBtn.addEventListener('click', async () => {
  if (!selectedFile) return;

  const file = selectedFile;
  startBtn.disabled = true;
  const upload = createStatus();
  upload.busy(file.name);
  upload.detail('Datei wird übertragen …');
  const controller = new AbortController();
  upload.cancellable(() => controller.abort());

  const formData = new FormData();
  formData.append('file', file);
  formData.append('engine', engineSelect.value);
  formData.append('model', modelSelect.value);
  formData.append('language', languageSelect.value);
  formData.append('speaker_name', speakerNameInput.value.trim());
  formData.append('output_folder', outputFolderInput.value.trim());

  try {
    const response = await fetch('/transcribe', {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    const data = await response.json();
    if (data.error) {
      upload.fail('Fehler', data.error);
      startBtn.disabled = false;
      return;
    }
    upload.el.remove();
    const job = { id: data.job_id, fileName: file.name, startedAt: Date.now() };
    addPending(job);
    watchJob(job);
    clearSelection();
    speakerNameInput.value = '';
  } catch (err) {
    if (err.name === 'AbortError') upload.el.remove();
    else upload.fail('Verbindungsfehler', err.message);
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
  if (config.version) $('version').textContent = `Transcribe ${config.version}`;
  loadSettings();
  loadHistory();

  resumePending();

  // Eine frühere Version hat einen Service Worker registriert, der nicht mehr gebraucht wird
  navigator.serviceWorker?.getRegistrations()
    .then((regs) => regs.forEach((reg) => reg.unregister()))
    .catch(() => {});
}

// Browser pausieren Hintergrund-Tabs; beim Zurückkehren offene Jobs wieder aufnehmen
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    loadHistory();
    resumePending();
  }
});

// Ein Wechsel zum Finder und zurück macht das Fenster nicht unsichtbar, daher auch bei Fokus und regelmäßig
window.addEventListener('focus', () => loadHistory());
setInterval(() => {
  if (document.visibilityState === 'visible') loadHistory();
}, HISTORY_REFRESH);

init();
