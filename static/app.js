const $ = (id) => document.getElementById(id);

const PENDING_KEY = 'pendingJobs';
const SETTINGS_KEY = 'settings';
const PENDING_MAX_AGE = 2 * 60 * 60 * 1000;  // danach hat der Server das Ergebnis längst verworfen
const MAX_RETRIES = 20;

const SPOKEN_LANGUAGES = ['de', 'en', 'auto'];

// ---------- Texte ----------

// Alle Texte der Oberfläche; index.html verweist mit data-i18n* auf die Schlüssel.
// Fehler kommen vom Server als Code (error_*), unbekannte zeigen den Text aus `detail`.
const TEXTS = {
  de: {
    title: 'Transcribe',
    subtitle: '// Whisper · lokal · ohne Cloud',
    settings: 'Einstellungen',
    settingsTranscription: 'Transkription',
    settingsApp: 'App',
    model: 'Modell',
    spokenLanguage: 'Gesprochene Sprache',
    language_de: 'Deutsch',
    language_en: 'Englisch',
    language_auto: 'Automatisch erkennen',
    outputFolder: 'Ausgabeordner',
    outputFolderPlaceholder: 'Pfad zum Zielordner (leer = transcriptions/)',
    appLanguage: 'Sprache der App',
    appLanguage_auto: 'Automatisch (System)',
    openFolder: 'Ordner öffnen',
    resetData: 'Alle App-Daten löschen …',
    dropTitle: 'Audiodatei hierher ziehen',
    dropHint: 'oder klicken zum Auswählen',
    chooseFile: 'Audiodatei auswählen',
    speakerName: 'Wer spricht? (optional)',
    speakerNamePlaceholder: 'z.B. Max Mustermann',
    start: 'Starten',
    offlineTitle: 'Keine Verbindung zum Transcribe-Server',
    offlineDetail: 'Der Verlauf ist eventuell nicht aktuell. Bitte Transcribe beenden und neu öffnen.',
    history: 'Verlauf',
    emptyTitle: 'Noch keine Transkripte.',
    emptyHint: 'Wähle oben eine Audiodatei aus.',

    model_tiny: 'tiny — schnell, ~75 MB',
    model_base: 'base — gut, ~140 MB',
    model_small: 'small — besser, ~460 MB',
    model_medium: 'medium — sehr gut, ~1,5 GB',
    'model_large-v3-turbo': 'large-v3-turbo — groß, ~1,6 GB',
    modelHint_tiny: 'Schnellste Option — für kurze Nachrichten gut geeignet.',
    modelHint_base: 'Gute Balance aus Geschwindigkeit und Qualität.',
    modelHint_small: 'Bessere Genauigkeit, dauert etwas länger.',
    modelHint_medium: 'Sehr hohe Genauigkeit, gut bei Dialekt/Umgangssprache — empfohlen.',
    'modelHint_large-v3-turbo': 'Neuestes Modell, schnell; je nach Aufnahme etwas besser oder schlechter als medium.',
    modelDownload: (hint) => `Beim ersten Mal wird das Modell heruntergeladen. ${hint}`,
    transcriptsFolder: (folder) => `Transkripte: ${folder}`,
    summary: (model, language) => `Modell: ${model} · Sprache: ${language} · `,
    change: 'ändern',
    deleteFailed: 'Löschen fehlgeschlagen',
    noConnection: 'Keine Verbindung zum Transcribe-Server.',
    copied: 'Kopiert!',
    copyFailed: 'Fehlgeschlagen',
    play: 'Abspielen',
    pause: 'Pause',
    cannotPlay: 'Abspielen nicht möglich',
    seekHint: 'Klicken, um zu dieser Stelle zu springen',
    position: 'Position',
    playFromHere: 'Ab hier abspielen',
    noSpeech: '(kein Text erkannt)',
    savedCount: (count) => `${count} gespeichert`,
    toggleText: 'Antippen zum Auf-/Zuklappen',
    copy: 'Kopieren',
    delete: 'Löschen',
    confirmDelete: 'Dieses Transkript löschen? Die .txt-Datei wird mit gelöscht.',
    savedAs: (path) => `Gespeichert als: ${path}`,
    confirmReset: 'Alle App-Daten löschen?\n\n'
      + 'Das löscht alle Transkripte, den Verlauf und die heruntergeladenen Whisper-Modelle. '
      + 'Das lässt sich nicht rückgängig machen.',
    resetDone: 'Alle App-Daten wurden gelöscht. Du kannst Transcribe jetzt beenden und in den Papierkorb ziehen.',
    resetFailed: (message) => `Löschen fehlgeschlagen: ${message}`,
    cancel: 'Abbrechen',
    close: 'Schließen',
    voiceMessage: 'Sprachnachricht',
    connecting: 'Verbindung zum Server …',
    confirmCancel: 'Transkription abbrechen?',
    queued: 'In der Warteschlange …',
    downloading: 'Modell wird heruntergeladen (einmalig, bis zu ca. 1,6 GB) …',
    progress: (value) => `Fortschritt: ${value}%`,
    loadingModel: 'Modell wird geladen & Transkription läuft …',
    error: 'Fehler',
    reconnecting: 'Verbindung unterbrochen – neuer Versuch …',
    connectionError: 'Verbindungsfehler',
    serverUnreachable: 'Server nicht erreichbar. Beim nächsten Öffnen der Seite wird es erneut versucht.',
    removeSelection: 'Auswahl entfernen',
    uploading: 'Datei wird übertragen …',

    error_bad_request: (detail) => `Ungültige Anfrage (${detail}).`,
    error_too_large: (gb) => `Datei zu groß (höchstens ${gb} GB).`,
    error_no_file: 'Keine Datei empfangen.',
    error_unknown_engine: (available) => `Engine nicht installiert. Verfügbar: ${available}`,
    error_unknown_model: (allowed) => `Unbekanntes Modell. Erlaubt: ${allowed}`,
    error_unknown_language: (allowed) => `Unbekannte Sprache. Erlaubt: ${allowed}`,
    error_folder_not_found: (folder) => `Ausgabeordner nicht gefunden: ${folder}`,
    error_job_gone: 'Job nicht gefunden – abgebrochen, abgelaufen oder Server neu gestartet.',
    error_unreadable_audio: 'Audio konnte nicht gelesen werden (beschädigt, unbekanntes Format oder keine Tonspur).',
    error_unsafe_data_dir: 'Der Datenordner gehört nicht nur der App.',
  },
  en: {
    title: 'Transcribe',
    subtitle: '// Whisper · local · no cloud',
    settings: 'Settings',
    settingsTranscription: 'Transcription',
    settingsApp: 'App',
    model: 'Model',
    spokenLanguage: 'Spoken language',
    language_de: 'German',
    language_en: 'English',
    language_auto: 'Detect automatically',
    outputFolder: 'Output folder',
    outputFolderPlaceholder: 'Path to the target folder (empty = transcriptions/)',
    appLanguage: 'App language',
    appLanguage_auto: 'Automatic (system)',
    openFolder: 'Open folder',
    resetData: 'Delete all app data …',
    dropTitle: 'Drop an audio file here',
    dropHint: 'or click to choose one',
    chooseFile: 'Choose an audio file',
    speakerName: 'Who is speaking? (optional)',
    speakerNamePlaceholder: 'e.g. Jane Doe',
    start: 'Start',
    offlineTitle: 'No connection to the Transcribe server',
    offlineDetail: 'The history may be out of date. Please quit Transcribe and open it again.',
    history: 'History',
    emptyTitle: 'No transcripts yet.',
    emptyHint: 'Choose an audio file above.',

    model_tiny: 'tiny — fast, ~75 MB',
    model_base: 'base — good, ~140 MB',
    model_small: 'small — better, ~460 MB',
    model_medium: 'medium — very good, ~1.5 GB',
    'model_large-v3-turbo': 'large-v3-turbo — large, ~1.6 GB',
    modelHint_tiny: 'Fastest option — good for short messages.',
    modelHint_base: 'Good balance of speed and quality.',
    modelHint_small: 'Better accuracy, takes a little longer.',
    modelHint_medium: 'Very high accuracy, copes well with dialect and casual speech — recommended.',
    'modelHint_large-v3-turbo': 'Newest model, fast; depending on the recording slightly better or worse than medium.',
    modelDownload: (hint) => `The model is downloaded the first time you use it. ${hint}`,
    transcriptsFolder: (folder) => `Transcripts: ${folder}`,
    summary: (model, language) => `Model: ${model} · Language: ${language} · `,
    change: 'change',
    deleteFailed: 'Delete failed',
    noConnection: 'No connection to the Transcribe server.',
    copied: 'Copied!',
    copyFailed: 'Failed',
    play: 'Play',
    pause: 'Pause',
    cannotPlay: 'Cannot play this recording',
    seekHint: 'Click to jump to this point',
    position: 'Position',
    playFromHere: 'Play from here',
    noSpeech: '(no speech recognized)',
    savedCount: (count) => `${count} saved`,
    toggleText: 'Click to expand or collapse',
    copy: 'Copy',
    delete: 'Delete',
    confirmDelete: 'Delete this transcript? Its .txt file is deleted too.',
    savedAs: (path) => `Saved as: ${path}`,
    confirmReset: 'Delete all app data?\n\n'
      + 'This deletes all transcripts, the history, and the downloaded Whisper models. '
      + 'This cannot be undone.',
    resetDone: 'All app data has been deleted. You can now quit Transcribe and move it to the Trash.',
    resetFailed: (message) => `Delete failed: ${message}`,
    cancel: 'Cancel',
    close: 'Close',
    voiceMessage: 'Voice message',
    connecting: 'Connecting to the server …',
    confirmCancel: 'Cancel this transcription?',
    queued: 'Waiting in line …',
    downloading: 'Downloading the model (once, up to about 1.6 GB) …',
    progress: (value) => `Progress: ${value}%`,
    loadingModel: 'Loading the model and transcribing …',
    error: 'Error',
    reconnecting: 'Connection lost – retrying …',
    connectionError: 'Connection error',
    serverUnreachable: 'Server not reachable. It will be tried again the next time the page is opened.',
    removeSelection: 'Remove selection',
    uploading: 'Uploading the file …',

    error_bad_request: (detail) => `Invalid request (${detail}).`,
    error_too_large: (gb) => `The file is too large (at most ${gb} GB).`,
    error_no_file: 'No file received.',
    error_unknown_engine: (available) => `Engine not installed. Available: ${available}`,
    error_unknown_model: (allowed) => `Unknown model. Allowed: ${allowed}`,
    error_unknown_language: (allowed) => `Unknown language. Allowed: ${allowed}`,
    error_folder_not_found: (folder) => `Output folder not found: ${folder}`,
    error_job_gone: 'Job not found – cancelled, expired, or the server was restarted.',
    error_unreadable_audio: 'The audio could not be read (damaged, unknown format, or no audio track).',
    error_unsafe_data_dir: 'The data folder does not belong to the app alone.',
  },
};

let lang = 'en';

function tr(key, ...args) {
  const text = TEXTS[lang][key] ?? TEXTS.en[key] ?? key;
  return typeof text === 'function' ? text(...args) : text;
}

function errorText(error, detail) {
  return `error_${error}` in TEXTS.en ? tr(`error_${error}`, detail) : detail || error;
}

const languageOf = (code) => (String(code || '').toLowerCase().startsWith('de') ? 'de' : 'en');

// Für Datum und Zahlen die Region des Browsers, wenn sie zur Sprache passt
const locale = () => navigator.languages?.find((l) => l.toLowerCase().startsWith(lang)) || (lang === 'de' ? 'de-DE' : 'en-US');

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
const uiLanguageSelect = $('uiLanguage');
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

// Sprache der Oberfläche: gewählt oder die des Systems (vom Server, sonst vom Browser)
function applyLanguage() {
  const choice = uiLanguageSelect.value;
  lang = choice === 'de' || choice === 'en' ? choice : languageOf(config.ui_language || navigator.language);
  document.documentElement.lang = lang;
  document.title = tr('title');
  for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = tr(el.dataset.i18n);
  for (const el of document.querySelectorAll('[data-i18n-placeholder]')) el.placeholder = tr(el.dataset.i18nPlaceholder);
  for (const el of document.querySelectorAll('[data-i18n-label]')) {
    el.title = tr(el.dataset.i18nLabel);
    el.setAttribute('aria-label', el.title);
  }
  if (config.output_dir) $('dataHint').textContent = tr('transcriptsFolder', config.output_dir);
}

function applyConfig() {
  engineSelect.replaceChildren(...config.engines.map((e) => option(e.id, e.label)));
  $('engineField').hidden = config.engines.length < 2;
  // Die App speichert immer in ihrem eigenen Ordner und kann ihre Daten komplett löschen
  $('outputFolderField').hidden = !!config.app;
  $('resetBtn').hidden = !config.app;
}

function fillModels() {
  const engine = currentEngine();
  if (!engine) return;
  modelSelect.replaceChildren(...engine.models.map((name) => option(name, `model_${name}` in TEXTS.en ? tr(`model_${name}`) : name)));
  const preferred = modelChoice[engine.id];
  modelSelect.value = engine.models.includes(preferred) ? preferred : engine.default_model;
}

function loadSettings() {
  const s = store.get(SETTINGS_KEY, {});
  uiLanguageSelect.value = s.uiLanguage === 'de' || s.uiLanguage === 'en' ? s.uiLanguage : 'auto';
  applyLanguage();
  modelChoice = s.models || {};
  engineSelect.value = config.engines.some((e) => e.id === s.engine) ? s.engine : config.default_engine;
  fillModels();
  languageSelect.value = SPOKEN_LANGUAGES.includes(s.language) ? s.language : lang;
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
    uiLanguage: uiLanguageSelect.value,
  });
  updateSummary();
}

function updateSummary() {
  const hint = `modelHint_${modelSelect.value}` in TEXTS.en ? tr(`modelHint_${modelSelect.value}`) : '';
  $('modelHint').textContent = tr('modelDownload', hint);
  const engine = currentEngine();
  const engineName = engine ? ` (${engine.label.split(' (')[0]})` : '';
  const summary = $('summary');
  summary.replaceChildren(
    tr('summary', modelSelect.value + engineName, tr(`language_${languageSelect.value}`)),
    Object.assign(document.createElement('button'), {
      className: 'link-btn', type: 'button', textContent: tr('change'), onclick: () => toggleSettings(true),
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
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('settings').hidden) {
    toggleSettings(false);
    $('settingsBtn').focus();
  }
});
outputFolderInput.addEventListener('input', saveSettings);
[modelSelect, languageSelect].forEach((el) => el.addEventListener('change', saveSettings));
engineSelect.addEventListener('change', () => {
  fillModels();
  saveSettings();
});
uiLanguageSelect.addEventListener('change', () => {
  saveSettings();
  applyLanguage();
  fillModels();
  updateSummary();
  renderHistory();
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
    createStatus().fail(tr('deleteFailed'), err instanceof TypeError ? tr('noConnection') : err.message);
  }
  loadHistory();
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const sameYear = d.getFullYear() === new Date().getFullYear();
  const date = d.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit', year: sameYear ? undefined : '2-digit' });
  const time = d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
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
    button.textContent = tr('copied');
  } catch {
    button.textContent = tr('copyFailed');
  }
  setTimeout(() => { button.textContent = label; }, 2000);
}

// ---------- Abspielen ----------

// Ein Player für alle Karten: Startet eine andere Karte, stoppt die vorige
const player = { audio: new Audio(), id: null, segments: [], raf: 0 };
player.audio.preload = 'metadata';

const cardById = (id) => $('historyList').querySelector(`.card[data-id="${CSS.escape(id)}"]`);

// Symbole als SVG statt Textzeichen: überall gleich groß und scharf
const ICONS = {
  play: 'M8 5.5v13l10.5-6.5z',
  pause: 'M7 5h3.5v14H7zM13.5 5H17v14h-3.5z',
};

function setPlayIcon(btn, state) {
  // Nur ändern, was sich geändert hat: Wird der Inhalt während eines Klicks ersetzt
  // (updatePlayerUI läuft bis zu 60-mal pro Sekunde), verwirft WebKit den Klick.
  if (btn.dataset.state === state) return;
  btn.dataset.state = state;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'icon icon-solid');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[state]);
  svg.append(path);
  btn.replaceChildren(svg);
  btn.setAttribute('aria-label', tr(state));
}

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
  setPlayIcon(card.querySelector('.play-btn'), audio.paused ? 'play' : 'pause');
  const time = card.querySelector('.player-time');
  const timeText = `${formatDuration(Math.floor(audio.currentTime))} / ${formatDuration(Math.round(total))}`;
  if (time.textContent !== timeText) {
    time.textContent = timeText;
    const track = card.querySelector('.player-track');
    track.setAttribute('aria-valuenow', Math.floor(audio.currentTime));
    track.setAttribute('aria-valuemax', Math.round(total));
    track.setAttribute('aria-valuetext', timeText);
  }
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
  if (card && player.audio.getAttribute('src')) card.querySelector('.player-time').textContent = tr('cannotPlay');
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
      setPlayIcon(previous.querySelector('.play-btn'), 'play');
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
  const btn = Object.assign(document.createElement('button'), { className: 'ghost-btn play-btn', type: 'button' });
  setPlayIcon(btn, 'play');
  btn.addEventListener('click', () => togglePlay(t));
  const track = document.createElement('div');
  track.className = 'player-track';
  track.title = tr('seekHint');
  // Per Tastatur bedienbar: Pfeiltasten springen 5 Sekunden
  track.tabIndex = 0;
  track.setAttribute('role', 'slider');
  track.setAttribute('aria-label', tr('position'));
  track.setAttribute('aria-valuemin', 0);
  track.setAttribute('aria-valuemax', t.duration || 0);
  track.setAttribute('aria-valuenow', 0);
  track.addEventListener('keydown', (e) => {
    const step = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5 }[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const current = player.id === t.id ? player.audio.currentTime : 0;
    playFrom(t, Math.max(0, current + step));
  });
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
    textEl.textContent = t.text || tr('noSpeech');
    return;
  }
  textEl.append(t.text.slice(0, start));  // Präfix mit Zeitstempel/Name
  segments.forEach(([from, , words], index) => {
    const span = Object.assign(document.createElement('span'), { className: 'seg', textContent: words });
    span.dataset.index = index;
    span.title = tr('playFromHere');
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
  $('historyCount').textContent = list.length ? tr('savedCount', list.length) : '';
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
    text.title = tr('toggleText');
    text.addEventListener('click', () => {
      if (!window.getSelection().toString()) text.classList.toggle('clamped');
    });

    const actions = document.createElement('div');
    actions.className = 'card-actions';
    const copy = Object.assign(document.createElement('button'), {
      className: 'ghost-btn copy', type: 'button', textContent: tr('copy'),
    });
    copy.addEventListener('click', () => copyText(t.text, copy));
    const del = Object.assign(document.createElement('button'), {
      className: 'ghost-btn danger', type: 'button', textContent: tr('delete'),
    });
    del.addEventListener('click', () => {
      if (confirm(tr('confirmDelete'))) deleteTranscript(t.id);
    });
    actions.append(copy, del);

    li.append(meta);
    if (t.audio) li.append(createPlayer(t));
    li.append(text);
    if (t.saved_as && !config.app) {
      const saved = document.createElement('div');
      saved.className = 'card-saved';
      saved.textContent = tr('savedAs', t.saved_as);
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
  if (!confirm(tr('confirmReset'))) return;
  const msg = $('settingsMsg');
  msg.classList.remove('error');
  try {
    const response = await fetch('/reset', { method: 'POST' });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error ? errorText(data.error, data.detail) : `HTTP ${response.status}`);
    }
    for (const watcher of watchers.values()) {
      if (watcher.es) watcher.es.close();
      clearTimeout(watcher.timer);
    }
    watchers.clear();
    jobsEl.replaceChildren();
    try { localStorage.clear(); } catch {}
    loadSettings();
    loadHistory();
    msg.textContent = tr('resetDone');
  } catch (err) {
    msg.classList.add('error');
    msg.textContent = tr('resetFailed', err.message);
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
        className: 'ghost-btn danger', type: 'button', textContent: tr('cancel'),
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
        className: 'ghost-btn', type: 'button', textContent: tr('close'),
      });
      close.addEventListener('click', () => el.remove());
      el.append(close);
    },
  };
}

function watchJob(job) {
  const status = createStatus();
  const name = () => job.fileName || tr('voiceMessage');
  status.busy(name());
  status.detail(tr('connecting'));

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
    if (!confirm(tr('confirmCancel'))) return;
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
        if (msg.state === 'queued') status.detail(tr('queued'));
        else if (msg.state === 'downloading') status.detail(tr('downloading'));
        else if (msg.value > 0) status.detail(tr('progress', msg.value));
        else status.detail(tr('loadingModel'));
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
        status.fail(tr('error'), errorText(msg.error, msg.detail));
        if (msg.error === 'job_gone') loadHistory();  // z.B. in einem anderen Tab schon fertig geworden
      }
    };

    watcher.es.onerror = () => {
      watcher.es.close();
      if (watcher.retries++ < MAX_RETRIES) {
        status.detail(tr('reconnecting'));
        watcher.timer = setTimeout(connect, 3000);
      } else {
        stop();  // bleibt in pendingJobs und wird beim nächsten Öffnen fortgesetzt
        status.fail(tr('connectionError'), tr('serverUnreachable'));
      }
    };
  };

  connect();
}

// ---------- Datei auswählen & hochladen ----------

fileInput.addEventListener('change', (e) => {
  if (e.target.files[0]) selectFile(e.target.files[0]);
});

// Dateien überall im Fenster annehmen: Daneben fallen gelassen würde der Browser bzw. das
// App-Fenster die Audiodatei sonst selbst öffnen und die Seite verlassen.
// dragenter/dragleave feuern für jedes Element, darum mitzählen statt relatedTarget (fehlt in WebKit).
let dragDepth = 0;
const isFileDrag = (e) => e.dataTransfer?.types.includes('Files');

window.addEventListener('dragenter', (e) => {
  if (!isFileDrag(e)) return;
  e.preventDefault();
  dragDepth++;
  dropZone.classList.add('dragover');
});

window.addEventListener('dragleave', (e) => {
  if (!isFileDrag(e) || --dragDepth > 0) return;
  dragDepth = 0;
  dropZone.classList.remove('dragover');
});

window.addEventListener('dragover', (e) => {
  if (isFileDrag(e)) e.preventDefault();
});

window.addEventListener('drop', (e) => {
  if (!isFileDrag(e)) return;
  e.preventDefault();
  dragDepth = 0;
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
});

function selectFile(file) {
  selectedFile = file;
  const mb = (file.size / 1024 / 1024).toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const name = document.createElement('span');
  name.textContent = `${file.name} (${mb} MB)`;
  const remove = Object.assign(document.createElement('button'), {
    type: 'button', className: 'file-remove', textContent: '✕', title: tr('removeSelection'),
  });
  remove.setAttribute('aria-label', tr('removeSelection'));
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
  upload.detail(tr('uploading'));
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
      upload.fail(tr('error'), errorText(data.error, data.detail));
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
    else upload.fail(tr('connectionError'), err.message);
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

// Schon vor der Antwort des Servers in der gespeicherten Sprache bzw. der des Browsers anzeigen
uiLanguageSelect.value = store.get(SETTINGS_KEY, {}).uiLanguage || 'auto';
applyLanguage();
init();
