"""
Lokales Whisper Transkriptions-Tool
====================================
Einmalige Installation (einmal ausführen):
    pip install openai-whisper
    pip install mlx-whisper     # zusätzlich auf Macs mit Apple Silicon, deutlich schneller

Danach einfach starten:
    python transcribe.py

Öffnet dann automatisch http://127.0.0.1:8765 im Browser.

Anderer Port:
    python transcribe.py --port 9000
"""

import argparse
import errno
import http.server
import importlib
import socketserver
import json
import locale
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import glob
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

VERSION = "1.2.0"  # muss zum Release-Tag vX.Y.Z passen

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_SUGGESTIONS = 3  # Anzahl freier Ports, die bei belegtem Port angeboten werden
# Ports, die Browser nicht öffnen (ERR_UNSAFE_PORT)
BROWSER_BLOCKED_PORTS = frozenset({
    1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95,
    101, 102, 103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161,
    179, 389, 427, 465, 512, 513, 514, 515, 526, 530, 531, 532, 540, 548, 554, 556, 563,
    587, 601, 636, 989, 990, 993, 995, 1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060,
    5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6679, 6697, 10080,
})
# Whisper-Engines in der Reihenfolge, in der sie als Standard bevorzugt werden.
# mlx-whisper rechnet auf der GPU von Apple Silicon, openai-whisper läuft überall (CUDA, MPS, CPU).
# Beide nutzen dieselben Modelle von OpenAI; "models" bildet den Namen in der Oberfläche
# auf den Namen der jeweiligen Engine ab.
ENGINES = {
    "mlx": {
        "label": "mlx-whisper (Apple Silicon)",
        "module": "mlx_whisper",
        "models": {
            "tiny": "mlx-community/whisper-tiny-mlx",
            "base": "mlx-community/whisper-base-mlx",
            "small": "mlx-community/whisper-small-mlx",
            "medium": "mlx-community/whisper-medium-mlx",
            "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        },
        "default_model": "medium",
    },
    "openai": {
        "label": "openai-whisper",
        "module": "whisper",
        "models": {name: name for name in ("tiny", "base", "small", "medium", "large-v3-turbo")},
        "default_model": "medium",
    },
}
LANGUAGES = ("de", "en", "auto")

JOB_TTL = 15 * 60  # Sekunden, die ein fertiges, nicht abgeholtes Ergebnis im Speicher bleibt
SOCKET_TIMEOUT = 60  # Sekunden ohne Datenfluss, bevor eine Verbindung aufgegeben wird
MAX_FILE_NAME = 200
MAX_UPLOAD = 2 * 1024 ** 3  # Bytes; der Upload wird komplett im Speicher gelesen (gut 3 Stunden WAV)

# In der Mac-App (PyInstaller) liegen die Dateien unter sys._MEIPASS
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
STATIC_DIR = BASE_DIR / "static"
# Die Mac-App legt alle ihre Daten in einen eigenen Ordner (TRANSCRIBE_DATA_DIR), damit
# „Alle App-Daten löschen“ sie gesammelt entfernen kann. Das Skript speichert im Projektordner.
APP_DATA_DIR = Path(os.environ["TRANSCRIBE_DATA_DIR"]) if os.environ.get("TRANSCRIBE_DATA_DIR") else None
DEFAULT_OUTPUT_DIR = APP_DATA_DIR / "Transcripts" if APP_DATA_DIR else Path(__file__).parent / "transcriptions"
# Merkt sich zu jedem Transkript Datum, Dauer und Originaldatei für den Verlauf
HISTORY_INDEX = DEFAULT_OUTPUT_DIR / ".history.json"
# Namen bis Version 1.1.0, migrate_legacy_names() übernimmt die Daten
LEGACY_OUTPUT_DIR = APP_DATA_DIR / "Transkripte" if APP_DATA_DIR else None
LEGACY_HISTORY_INDEX = DEFAULT_OUTPUT_DIR / ".verlauf.json"
# Original-Audiodateien für den Player im Verlauf
AUDIO_DIR = DEFAULT_OUTPUT_DIR / ".audio"
AUDIO_TYPES = {
    ".opus": "audio/ogg; codecs=opus", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".webm": "audio/webm",
    ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".flac": "audio/flac", ".aiff": "audio/aiff", ".aif": "audio/aiff", ".caf": "audio/x-caf",
}
COMPAT_SUFFIX = ".compat.m4a"  # M4A-Fassung für Fenster, die das Originalformat nicht abspielen
# Ausgelieferte Dateien: Pfad -> (Datei, Content-Type)
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}
# Die Seite lädt nichts von fremden Servern und führt keine eingebetteten Scripts aus
CSP = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def _language_of(value):
    return "de" if value.lower().startswith(("de", "german")) else "en"


def _system_language():
    """'de' bei deutscher Systemsprache, sonst 'en'. Gilt fürs Terminal, das Log und als Voreinstellung der Seite."""
    for name in ("TRANSCRIBE_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return _language_of(value)
    try:
        if sys.platform == "darwin":
            # Aus dem Finder gestartete Apps bekommen kein LANG
            r = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=5)
            match = re.search(r'\(\s*"?([A-Za-z]+)', r.stdout)
            if match:
                return _language_of(match.group(1))
        elif sys.platform == "win32":
            import ctypes
            return _language_of(locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), ""))
    except (OSError, subprocess.SubprocessError):
        pass
    return _language_of(locale.getlocale()[0] or "")


UI_LANGUAGE = _system_language()

# Meldungen im Terminal bzw. im Log der Mac-App als (Deutsch, Englisch). Die Weboberfläche übersetzt
# sich selbst (static/app.js); der Server schickt ihr nur Fehlercodes (Handler._json_error).
MESSAGES = {
    "ffmpeg_found": ("ffmpeg gefunden: {path}", "Found ffmpeg: {path}"),
    "ffmpeg_missing": (
        "Warnung: ffmpeg wurde nicht gefunden. Ohne ffmpeg schlägt die Transkription fehl.",
        "Warning: ffmpeg was not found. Transcriptions will fail without it.",
    ),
    "ffmpeg_install": ("Installation:", "To install it:"),
    "engine_broken": (
        "{label} ist installiert, lässt sich aber nicht laden: {error}",
        "{label} is installed but cannot be loaded: {error}",
    ),
    "whisper_missing": ("Whisper ist nicht installiert.", "Whisper is not installed."),
    "run_once": ("Bitte einmalig ausführen:", "Run this once:"),
    "mlx_faster": ("(Apple Silicon, deutlich schneller)", "(Apple Silicon, much faster)"),
    "loading_model": ("→ Lade Modell '{model}'...", "→ Loading model '{model}'..."),
    "downloading_model": ("→ Lade Modell {model} herunter...", "→ Downloading model {model}..."),
    "transcribing": ("→ Transkribiere '{file}' mit {engine}/{model}...", "→ Transcribing '{file}' with {engine}/{model}..."),
    "done": ("✓ Fertig! Gespeichert als: {path}", "✓ Done! Saved as: {path}"),
    "cancelled": ("⏹ '{file}' abgebrochen", "⏹ '{file}' cancelled"),
    "audio_not_kept": ("Audio konnte nicht aufbewahrt werden: {error}", "Could not keep the audio file: {error}"),
    "compat_failed": ("Umwandeln zum Abspielen fehlgeschlagen: {error}", "Converting the audio for playback failed: {error}"),
    "reset_refused": (
        "App-Daten nicht gelöscht: {folder} ist kein eigener Ordner der App",
        "App data not deleted: {folder} is not the app's own folder",
    ),
    "reset_done": ("Alle App-Daten gelöscht", "All app data deleted"),
    "migrated": ("Daten früherer Versionen übernommen: {path}", "Moved data of an earlier version: {path}"),
    "migration_failed": ("Daten früherer Versionen nicht übernommen: {error}", "Could not move data of an earlier version: {error}"),
    "not_a_number": ("'{value}' ist keine Zahl", "'{value}' is not a number"),
    "port_range": ("Port muss zwischen 1 und 65535 liegen", "The port must be between 1 and 65535"),
    "port_blocked": ("Port {port} wird von Browsern blockiert", "Browsers block port {port}"),
    "free_ports": ("Freie Ports:", "Free ports:"),
    "choose_port": ("Auswahl oder eigener Port (Enter = {port}): ", "Pick one or type a port (Enter = {port}): "),
    "enter_port": ("Anderen Port eingeben: ", "Enter another port: "),
    "invalid_input": ("Ungültige Eingabe: {error}", "Invalid input: {error}"),
    "server_failed": ("Server konnte nicht gestartet werden: {error}", "Could not start the server: {error}"),
    "port_unavailable": ("Port {port} ist nicht verfügbar ({reason}).", "Port {port} is not available ({reason})."),
    "no_free_port": ("Kein freier Port gefunden.", "No free port found."),
    "use_port_option": ("Mit --port einen anderen Port angeben.", "Use --port to choose another port."),
    "description": ("Lokales Whisper-Transkriptions-Tool", "Local Whisper transcription tool"),
    "help_port": ("Port für die Weboberfläche (Standard: {port})", "Port for the web UI (default: {port})"),
    "help_no_browser": ("Browser beim Start nicht öffnen", "Do not open the browser at startup"),
    "running_on": ("Server läuft auf {url}", "Server running at {url}"),
    "opening_browser": ("Browser öffnet sich automatisch...", "Opening the browser..."),
    "stop_with": ("Zum Beenden: {key}", "To stop: {key}"),
    "stopped": ("Server gestoppt.", "Server stopped."),
}


def tr(key, **values):
    """Meldung fürs Terminal bzw. Log in der Systemsprache."""
    return MESSAGES[key][0 if UI_LANGUAGE == "de" else 1].format(**values)

# ffmpeg automatisch finden (PATH, Windows WinGet + macOS Homebrew)
def find_and_add_ffmpeg():
    if shutil.which("ffmpeg"):
        return True

    if sys.platform == "darwin":
        candidates = [
            "/opt/homebrew/bin",   # Apple Silicon
            "/usr/local/bin",      # Intel Mac
        ]
        for path in candidates:
            if Path(path, "ffmpeg").exists():
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
                print("  " + tr("ffmpeg_found", path=path))
                return True
        return False

    if sys.platform != "win32":
        return False

    # Windows: WinGet-Installationspfade
    winget_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    patterns = [
        str(winget_base / "Gyan.FFmpeg_*" / "ffmpeg-*" / "bin"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        for match in matches:
            if Path(match).exists():
                os.environ["PATH"] = match + os.pathsep + os.environ.get("PATH", "")
                print("  " + tr("ffmpeg_found", path=match))
                return True
    return False


# Installierte Engines (Name -> Modul), erst in load_engines() importiert,
# damit --help nicht auf den Import wartet
_engines: dict = {}

_jobs: dict = {}
_jobs_lock = threading.Lock()
_tqdm_local = threading.local()

_history_lock = threading.Lock()

_models: dict = {}  # zuletzt benutztes openai-whisper-Modell; mlx-whisper hält seins selbst
_transcribe_lock = threading.Lock()  # immer nur eine Transkription, sonst bremsen sich die Jobs aus


class JobCancelled(Exception):
    """Der Job wurde per DELETE /job abgebrochen, während er wartete oder lief."""


def _raise_if_cancelled(job_id):
    """Ein abgebrochener Job ist nicht mehr in _jobs. Aufruf mit gehaltenem _jobs_lock."""
    if job_id not in _jobs:
        raise JobCancelled


def _set_progress(job_id, pct):
    """Meldet den Fortschritt und bricht die Transkription ab, falls der Job gelöscht wurde.

    Beide Engines rufen das nach jedem Abschnitt (ca. 30 s Audio) auf, darum greift ein
    Abbruch spätestens nach dem aktuellen Abschnitt.
    """
    with _jobs_lock:
        _raise_if_cancelled(job_id)
        _jobs[job_id]["progress"] = max(0, min(99, int(pct)))


def load_engines():
    """Importiert die installierten Engines und leitet ihre Fortschrittsbalken an den laufenden Job weiter."""
    import tqdm as _tqdm_module

    for name, engine in ENGINES.items():
        try:
            _engines[name] = importlib.import_module(engine["module"])
        except ImportError as e:
            if e.name != engine["module"]:  # installiert, aber eine Abhängigkeit fehlt
                print("  " + tr("engine_broken", label=engine["label"], error=e))
        except Exception as e:
            print("  " + tr("engine_broken", label=engine["label"], error=e))

    if not _engines:
        print("=" * 50)
        print(tr("whisper_missing"))
        print(tr("run_once"))
        print("    pip install openai-whisper")
        if sys.platform == "darwin" and os.uname().machine == "arm64":
            print("    pip install mlx-whisper   " + tr("mlx_faster"))
        print("=" * 50)
        sys.exit(1)

    if "openai" in _engines:
        # Für die Wort-Zeitstempel wandelt openai-whisper erst in float64 um und holt die Daten dann
        # auf die CPU; float64 gibt es auf MPS (Apple-GPU) nicht, also vorher auf die CPU holen
        import whisper.timing as whisper_timing
        original_dtw = whisper_timing.dtw

        def dtw_on_cpu(x):
            return original_dtw(x.cpu())

        whisper_timing.dtw = dtw_on_cpu

    # Beide Engines zeigen ihren Fortschritt über tqdm.tqdm an
    _orig_tqdm = _tqdm_module.tqdm

    class _ProgressTqdm(_orig_tqdm):
        def update(self, n=1):
            result = super().update(n)
            job_id = getattr(_tqdm_local, "job_id", None)
            if job_id and self.total and self.total > 0:
                _set_progress(job_id, self.n / self.total * 100)
            return result

    _tqdm_module.tqdm = _ProgressTqdm


def _load_openai_model(model_name):
    """Lädt das Modell beim ersten Gebrauch und hält es danach im Speicher. Nur mit _transcribe_lock aufrufen."""
    if model_name in _models:
        return _models[model_name]
    _models.clear()  # nur ein Modell im Speicher halten

    import torch
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    print("  " + tr("loading_model", model=model_name))
    # Auf CPU laden und alignment_heads (sparse Tensor) für den Umzug in dense umwandeln,
    # da MPS keine sparse Tensoren unterstützt (siehe pytorch/pytorch#78168).
    model = _engines["openai"].load_model(model_name, device="cpu")
    if device != "cpu":
        heads = model.alignment_heads
        model.alignment_heads = heads.to_dense()
        model = model.to(device)
        # Die Wort-Zeitstempel lesen daraus nur die Indizes (.indices()), dafür genügt sparse auf der CPU
        model.alignment_heads = heads

    _models[model_name] = model
    return model


def _transcribe_openai(job_id, model_name, path, kwargs):
    model = _load_openai_model(model_name)
    # fp16 nur auf CUDA aktivieren: Apples MPS-Backend liefert bei manchen
    # Whisper-Modellen in fp16 NaN-Logits, daher dort auf fp32 bleiben.
    return model.transcribe(path, fp16=(model.device.type == "cuda"), **kwargs)


def _ensure_mlx_model(job_id, repo):
    """Lädt ein noch nicht vorhandenes Modell vorab herunter, damit die Oberfläche das anzeigen kann."""
    from huggingface_hub import snapshot_download
    try:
        snapshot_download(repo, local_files_only=True)
        return
    except Exception:
        pass  # noch nicht im Cache
    with _jobs_lock:
        _raise_if_cancelled(job_id)
        _jobs[job_id]["state"] = "downloading"
    print("  " + tr("downloading_model", model=repo))
    snapshot_download(repo)
    with _jobs_lock:
        _raise_if_cancelled(job_id)
        _jobs[job_id]["state"] = "running"


def _transcribe_mlx(job_id, model_name, path, kwargs):
    # mlx-whisper hält das geladene Modell danach selbst im Speicher
    repo = ENGINES["mlx"]["models"][model_name]
    _ensure_mlx_model(job_id, repo)
    return _engines["mlx"].transcribe(path, path_or_hf_repo=repo, **kwargs)


def _audio_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        return round(float(r.stdout.strip()))
    except Exception:
        return "?"


def _run_transcription(job_id, engine, model_name, tmp_path, language, speaker_name, output_folder, file_name):
    _tqdm_local.job_id = job_id
    try:
        with _transcribe_lock:
            with _jobs_lock:
                _raise_if_cancelled(job_id)  # schon abgebrochen, während der Job wartete
                _jobs[job_id]["state"] = "running"
            print("  " + tr("transcribing", file=file_name, engine=engine, model=model_name))
            # verbose=False zeigt den tqdm-Fortschritt, über den Fortschritt und Abbruch laufen
            # word_timestamps: genaue Zeiten für die Hervorhebung beim Abspielen (dauert etwa doppelt so lang)
            kwargs = {"verbose": False, "word_timestamps": True}
            if language != "auto":
                kwargs["language"] = language
            transcribe = _transcribe_mlx if engine == "mlx" else _transcribe_openai
            result = transcribe(job_id, model_name, tmp_path, kwargs)

        text = result["text"].strip()
        lang = result.get("language", "?")
        duration = _audio_duration(tmp_path)

        ts_match = re.search(r'(\d{4}-\d{2}-\d{2})\s+at\s+(\d{2}\.\d{2}\.\d{2})', file_name)
        timestamp = f"{ts_match.group(1)} - {ts_match.group(2)}" if ts_match else None

        if timestamp and speaker_name:
            prefix = f"{timestamp} - {speaker_name}"
        elif timestamp:
            prefix = timestamp
        elif speaker_name:
            prefix = speaker_name
        else:
            prefix = None

        formatted_text = f"{prefix}: {text}" if prefix else text

        with _jobs_lock:
            _raise_if_cancelled(job_id)  # kurz vor Schluss abgebrochen: nichts mehr speichern

        if output_folder and Path(output_folder).is_dir():
            save_dir = Path(output_folder)
        else:
            save_dir = DEFAULT_OUTPUT_DIR
            save_dir.mkdir(parents=True, exist_ok=True)
        txt_path = save_dir / (Path(file_name).stem + ".txt")
        txt_path.write_text(formatted_text, encoding="utf-8")
        transcript_id = uuid.uuid4().hex
        segments = _passages(result)
        audio = _keep_original_audio(tmp_path, transcript_id)
        _add_to_history(transcript_id, txt_path, file_name, lang, duration, segments, audio)
        print("  " + tr("done", path=txt_path))

        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update({
                    "progress": 100,
                    "done": True,
                    "finished_at": time.time(),
                    "result": {
                        "id": transcript_id,
                        "text": formatted_text,
                        "language": lang,
                        "duration": duration,
                        "saved_as": str(txt_path),
                    },
                })
    except JobCancelled:
        print("  " + tr("cancelled", file=file_name))
    except Exception as e:
        error, detail = "failed", str(e)
        if detail.startswith("Failed to load audio"):
            # Beide Engines hängen die komplette ffmpeg-Ausgabe an, die gehört nur ins Log
            print(f"  ✗ '{file_name}': {detail}")
            error, detail = "unreadable_audio", None
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update({"done": True, "finished_at": time.time(), "error": error, "detail": detail})
    finally:
        os.unlink(tmp_path)


def _load_history_index():
    try:
        return json.loads(HISTORY_INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_history_index(index):
    HISTORY_INDEX.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(HISTORY_INDEX)


def migrate_legacy_names():
    """Übernimmt die Daten von Version 1.1.0 und älter: Ordner „Transkripte“ und Verlauf „.verlauf.json“.

    Vor dem Start des Servers aufrufen. Die Pfade im Verlauf zeigen danach in den neuen Ordner.
    """
    try:
        if LEGACY_OUTPUT_DIR and LEGACY_OUTPUT_DIR.is_dir() and not DEFAULT_OUTPUT_DIR.exists():
            LEGACY_OUTPUT_DIR.rename(DEFAULT_OUTPUT_DIR)
            print("  " + tr("migrated", path=DEFAULT_OUTPUT_DIR))
        if LEGACY_HISTORY_INDEX.is_file() and not HISTORY_INDEX.exists():
            index = json.loads(LEGACY_HISTORY_INDEX.read_text(encoding="utf-8"))
            for meta in index.values():
                path = Path(meta.get("path", ""))
                if LEGACY_OUTPUT_DIR and path.is_relative_to(LEGACY_OUTPUT_DIR):
                    meta["path"] = str(DEFAULT_OUTPUT_DIR / path.relative_to(LEGACY_OUTPUT_DIR))
            _save_history_index(index)
            LEGACY_HISTORY_INDEX.unlink()
            print("  " + tr("migrated", path=HISTORY_INDEX))
    except (OSError, ValueError) as e:
        print("  " + tr("migration_failed", error=e))  # dann eben mit leerem Verlauf


PASSAGE_SPLIT_AFTER = 8   # Sekunden; danach wird ein langer Satz an einem Komma geteilt
PASSAGE_MAX = 15          # Sekunden; spätestens dann beginnt ein neuer Abschnitt


def _passages(result):
    """Abschnitte für die Hervorhebung beim Abspielen: [start, ende, text], meist ganze Sätze.

    Die Zeiten kommen aus den Wort-Zeitstempeln. Whispers eigene Abschnitte sind deutlich ungenauer
    (teils über eine Sekunde daneben) und enden oft mitten im Satz.
    """
    passages, words = [], []

    def flush():
        if words:
            text = "".join(w["word"] for w in words).strip()
            passages.append([round(words[0]["start"], 2), round(words[-1]["end"], 2), text])
            words.clear()

    for segment in result.get("segments", []):
        if not segment.get("words"):  # ohne Wortzeiten Whispers Abschnitt übernehmen
            flush()
            if segment.get("text", "").strip():
                passages.append([round(segment["start"], 2), round(segment["end"], 2), segment["text"].strip()])
            continue
        for word in segment["words"]:
            words.append(word)
            token = word["word"].strip()
            length = word["end"] - words[0]["start"]
            if (token.endswith((".", "?", "!", "…"))
                    or (length > PASSAGE_SPLIT_AFTER and token.endswith((",", ";", ":")))
                    or length > PASSAGE_MAX):
                flush()
    flush()
    return passages


def _keep_original_audio(src, transcript_id):
    """Bewahrt die Original-Audiodatei für den Player im Verlauf auf und gibt ihren Dateinamen zurück."""
    suffix = Path(src).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", suffix):
        suffix = ""
    name = f"{transcript_id}{suffix}"
    try:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, AUDIO_DIR / name)
    except OSError as e:
        print("  " + tr("audio_not_kept", error=e))  # dann eben ohne Player
        return None
    return name


_compat_lock = threading.Lock()


def _compat_audio(path):
    """M4A/AAC-Fassung des Originals für Fenster, die dessen Format nicht abspielen können.

    Auf aktuellen macOS-Versionen spielt WebKit auch Ogg/Opus aus WhatsApp; ältere tun das
    womöglich nicht. Die Umwandlung passiert nur dann, einmalig, und wird neben dem Original abgelegt.
    """
    target = path.with_name(path.stem + COMPAT_SUFFIX)
    with _compat_lock:  # WebKit fragt Ausschnitte parallel an
        if not target.is_file():
            tmp = target.with_name(target.name + ".part")
            r = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1",
                 "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", "-f", "ipod", str(tmp)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                print("  " + tr("compat_failed", error=r.stderr.strip()[-300:]))
                tmp.unlink(missing_ok=True)
                return None
            tmp.replace(target)
    return target


def _audio_file(meta):
    """Pfad der aufbewahrten Audiodatei eines Index-Eintrags, oder None."""
    name = meta.get("audio")
    if not name or Path(name).name != name:
        return None
    return AUDIO_DIR / name


def _remove_audio(meta):
    path = _audio_file(meta)
    if path:
        path.unlink(missing_ok=True)
        path.with_name(path.stem + COMPAT_SUFFIX).unlink(missing_ok=True)


def _add_to_history(transcript_id, txt_path, file_name, language, duration, segments, audio):
    """Trägt ein gespeichertes Transkript samt Abschnitten und Audiodatei in den Verlauf ein."""
    with _history_lock:
        index = {}
        for key, meta in _load_history_index().items():
            if meta.get("path") == str(txt_path):
                _remove_audio(meta)  # gleicher Dateiname überschreibt die .txt, der alte Eintrag fällt weg
            else:
                index[key] = meta
        index[transcript_id] = {
            "path": str(txt_path),
            "date": datetime.now().astimezone().isoformat(timespec="seconds"),
            "file_name": file_name,
            "language": language,
            "duration": duration,
            "segments": segments,
            "audio": audio,
        }
        _save_history_index(index)


def _audio_path(transcript_id):
    """Audiodatei zu einer Verlaufs-ID, nur über den Index aufgelöst."""
    with _history_lock:
        meta = _load_history_index().get(transcript_id)
    path = _audio_file(meta) if meta else None
    return path if path and path.is_file() else None


def _list_history():
    """Alle vorhandenen Transkripte, neueste zuerst.

    Grundlage sind die .txt-Dateien: Im Finder gelöschte verschwinden aus dem Verlauf, und
    .txt im Standardordner ohne Eintrag (z.B. ältere) erscheinen mit dem Datum der Datei.
    """
    with _history_lock:
        index = _load_history_index()
    entries, seen = [], set()
    for transcript_id, meta in index.items():
        path = Path(meta.get("path", ""))
        if path.is_file():
            audio = _audio_file(meta)
            has_audio = bool(audio and audio.is_file())
            entries.append({
                **meta, "id": transcript_id, "audio": has_audio,
                "audio_type": AUDIO_TYPES.get(audio.suffix.lower(), "") if has_audio else "",
            })
            seen.add(path.resolve())
    if DEFAULT_OUTPUT_DIR.is_dir():
        for path in DEFAULT_OUTPUT_DIR.glob("*.txt"):
            if path.resolve() not in seen:
                entries.append({
                    "id": "file:" + path.name,
                    "path": str(path),
                    "date": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                    "file_name": path.name,
                })
    for entry in entries:
        try:
            entry["text"] = Path(entry["path"]).read_text(encoding="utf-8")
        except OSError:
            entry["text"] = ""
        entry["saved_as"] = entry.pop("path")
    return sorted(entries, key=lambda e: e["date"], reverse=True)


def _delete_from_history(transcript_id):
    """Löscht das Transkript samt .txt-Datei. Gibt False zurück, wenn es nicht existiert."""
    with _history_lock:
        index = _load_history_index()
        if transcript_id in index:
            meta = index.pop(transcript_id)
            path = Path(meta["path"])
            _remove_audio(meta)
            _save_history_index(index)
        elif transcript_id.startswith("file:"):
            name = transcript_id[len("file:"):]
            if Path(name).name != name or not name.endswith(".txt"):
                return False  # nur Dateien direkt im Standardordner
            path = DEFAULT_OUTPUT_DIR / name
        else:
            return False
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return True


def _open_in_file_manager(folder):
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.run(["open", str(folder)])
    elif sys.platform == "win32":
        os.startfile(folder)
    else:
        subprocess.run(["xdg-open", str(folder)])


def _is_own_data_dir(folder):
    """Schutz gegen ein falsch gesetztes TRANSCRIBE_DATA_DIR: nie das Home-Verzeichnis oder einen Ordner darüber leeren."""
    folder, home = folder.resolve(), Path.home().resolve()
    return folder != home and folder not in home.parents


def _reset_app_data():
    """Löscht alles im App-Datenordner: Transkripte, Verlauf, Modelle, Caches, Log.

    Gibt False zurück, ohne etwas zu löschen, wenn der Ordner nicht nur der App gehören kann.
    """
    if not _is_own_data_dir(APP_DATA_DIR):
        print("  " + tr("reset_refused", folder=APP_DATA_DIR))
        return False
    with _jobs_lock:
        _jobs.clear()  # laufende Transkriptionen brechen beim nächsten Abschnitt ab
    with _history_lock:
        for child in APP_DATA_DIR.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    print("  " + tr("reset_done"))
    return True


def _prune_jobs():
    """Entfernt fertige Jobs, deren Ergebnis nicht innerhalb von JOB_TTL abgeholt wurde."""
    now = time.time()
    with _jobs_lock:
        for job_id in [k for k, j in _jobs.items() if j["done"] and now - j["finished_at"] > JOB_TTL]:
            del _jobs[job_id]


def _prune_jobs_forever():
    while True:
        time.sleep(60)
        _prune_jobs()


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = SOCKET_TIMEOUT  # hängende Verbindungen nicht ewig offen halten

    def log_message(self, format, *args):
        pass  # Stille Logs

    def version_string(self):
        return "Transcribe"  # statt Python-Version im Server-Header

    def end_headers(self):
        # Gilt für alle Antworten, auch für Fehlerseiten von send_error
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _is_local_request(self):
        """Lässt nur Anfragen der eigenen Seite zu, nicht die fremder Webseiten im selben Browser."""
        port = self.server.server_address[1]
        names = ("127.0.0.1", "localhost")
        hosts = {f"{name}:{port}" for name in names}
        if port == 80:
            hosts.update(names)
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{host}" for host in hosts}

    def do_GET(self):
        if not self._is_local_request():
            self.send_error(403)
            return

        parsed = urlparse(self.path)
        if parsed.path == "/progress":
            self._stream_progress(parse_qs(parsed.query).get("job", [None])[0])
            return

        if parsed.path == "/config":
            self._json_response({
                "engines": [
                    {
                        "id": name,
                        "label": ENGINES[name]["label"],
                        "models": list(ENGINES[name]["models"]),
                        "default_model": ENGINES[name]["default_model"],
                    }
                    for name in _engines
                ],
                "default_engine": next(iter(_engines)),
                "languages": LANGUAGES,
                "ui_language": UI_LANGUAGE,
                "version": VERSION,
                "app": APP_DATA_DIR is not None,
                "output_dir": str(DEFAULT_OUTPUT_DIR).replace(str(Path.home()), "~", 1),
            })
            return

        if parsed.path == "/transcripts":
            self._json_response(_list_history())
            return

        if parsed.path == "/audio":
            query = parse_qs(parsed.query)
            path = _audio_path(query.get("id", [""])[0])
            if path is not None and "compat" in query:
                path = _compat_audio(path)
            if path is None:
                self.send_error(404)
                return
            if path.name.endswith(COMPAT_SUFFIX):
                content_type = "audio/mp4"
            else:
                content_type = AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")
            self._send_file(path, content_type)
            return

        if parsed.path in STATIC_FILES:
            name, content_type = STATIC_FILES[parsed.path]
            try:
                body = (STATIC_DIR / name).read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", "no-cache")
            if name == "index.html":
                self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)

    def _stream_progress(self, job_id):
        """Schickt Fortschritt und Ergebnis eines Jobs als Server-Sent Events."""
        if not job_id:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                with _jobs_lock:
                    job = _jobs.get(job_id, {}).copy()
                if not job:
                    # abgebrochen, abgelaufen oder Server neu gestartet
                    payload = {"type": "error", "error": "job_gone"}
                elif job.get("done"):
                    if job.get("error"):
                        payload = {"type": "error", "error": job["error"], "detail": job["detail"]}
                    else:
                        # Der Job bleibt bestehen, bis die Seite das Ergebnis per DELETE /job
                        # bestätigt; so geht es nicht verloren, wenn die Verbindung abreißt.
                        payload = {"type": "done", "file_name": job["file_name"], **job["result"]}
                else:
                    payload = {
                        "type": "progress",
                        "state": job["state"],
                        "value": job.get("progress", 0),
                        "file_name": job["file_name"],
                    }
                self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                if payload["type"] != "progress":
                    break
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True  # Stream ist zu Ende, nicht auf weitere Anfragen warten

    def do_DELETE(self):
        """Die Seite hat das Ergebnis gespeichert oder bricht den Job ab: Der Server vergisst ihn.

        Ein wartender Job startet dann nicht mehr, ein laufender hört nach dem aktuellen Abschnitt auf.
        """
        if not self._is_local_request():
            self.send_error(403)
            return
        parsed = urlparse(self.path)
        if parsed.path == "/transcripts":
            transcript_id = parse_qs(parsed.query).get("id", [""])[0]
            self.send_response(204 if _delete_from_history(transcript_id) else 404)
            self.end_headers()
            return
        if parsed.path != "/job":
            self.send_error(404)
            return
        job_id = parse_qs(parsed.query).get("job", [None])[0]
        with _jobs_lock:
            _jobs.pop(job_id, None)
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if not self._is_local_request():
            self.send_error(403)
            return

        if self.path == "/open-folder":
            _open_in_file_manager(DEFAULT_OUTPUT_DIR)
            self._json_response({"ok": True})
            return

        if self.path == "/reset" and APP_DATA_DIR:
            if _reset_app_data():
                self._json_response({"ok": True})
            else:
                self._json_error("unsafe_data_dir", 500)
            return

        if self.path != "/transcribe":
            self.send_response(404)
            self.end_headers()
            return

        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            self._json_error("bad_request", 400, "multipart/form-data")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if length < 0:
            self._json_error("bad_request", 411, "Content-Length")
            return
        if length > MAX_UPLOAD:
            self._json_error("too_large", 413, MAX_UPLOAD // 1024 ** 3)
            return
        body = self.rfile.read(length)

        # Parse multipart
        boundary = content_type.split("boundary=")[-1].split(";")[0].strip().strip('"').encode()
        parts = body.split(b"--" + boundary)

        file_data = None
        file_name = "audio.ogg"
        engine = next(iter(_engines))
        model_name = ""
        language = "de"
        speaker_name = ""
        output_folder = ""

        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header, _, content = part.partition(b"\r\n\r\n")
            if content.endswith(b"\r\n"):
                content = content[:-2]
            header_str = header.decode("utf-8", errors="ignore")

            if 'name="file"' in header_str:
                file_data = content
                if 'filename="' in header_str:
                    name = header_str.split('filename="')[1].split('"')[0]
                    file_name = Path(name).name[:MAX_FILE_NAME] or file_name
            elif 'name="engine"' in header_str:
                engine = content.decode(errors="replace").strip()
            elif 'name="model"' in header_str:
                model_name = content.decode(errors="replace").strip()
            elif 'name="language"' in header_str:
                language = content.decode(errors="replace").strip()
            elif 'name="speaker_name"' in header_str:
                speaker_name = content.decode(errors="replace").strip()[:MAX_FILE_NAME]
            elif 'name="output_folder"' in header_str:
                output_folder = content.decode(errors="replace").strip()

        if not file_data:
            self._json_error("no_file", 400)
            return

        if engine not in _engines:
            self._json_error("unknown_engine", 400, ", ".join(_engines))
            return

        models = ENGINES[engine]["models"]
        model_name = model_name or ENGINES[engine]["default_model"]
        if model_name not in models:
            self._json_error("unknown_model", 400, ", ".join(models))
            return

        if language not in LANGUAGES:
            self._json_error("unknown_language", 400, ", ".join(LANGUAGES))
            return

        if APP_DATA_DIR:
            output_folder = ""  # die App speichert immer in ihrem eigenen Ordner
        elif output_folder:
            output_dir = Path(output_folder).expanduser()
            if not output_dir.is_dir():
                self._json_error("folder_not_found", 400, output_folder)
                return
            output_folder = str(output_dir)

        suffix = Path(file_name).suffix or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        _prune_jobs()
        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {
                "state": "queued",
                "progress": 0,
                "done": False,
                "finished_at": None,
                "file_name": file_name,
                "result": None,
                "error": None,
                "detail": None,
            }

        threading.Thread(
            target=_run_transcription,
            args=(job_id, engine, model_name, tmp_path, language, speaker_name, output_folder, file_name),
            daemon=True,
        ).start()

        self._json_response({"job_id": job_id})

    def _send_file(self, path, content_type):
        """Schickt eine Datei, auf Wunsch nur einen Ausschnitt (Range).

        WebKit fragt Audio in Ausschnitten an und spielt ohne Range-Unterstützung nicht bzw. kann nicht spulen.
        """
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
            if match and match.group(1):
                start = int(match.group(1))
                end = min(int(match.group(2)), size - 1) if match.group(2) else size - 1
            elif match and match.group(2):
                start = max(0, size - int(match.group(2)))  # bytes=-N: die letzten N Bytes
            if not match or not (match.group(1) or match.group(2)) or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", end - start + 1)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # der Browser bricht Ausschnitte oft ab, sobald er genug hat

    def _json_error(self, error, status, detail=None):
        """Fehler als Code; die Seite zeigt ihn in ihrer Sprache an (error_* in static/app.js)."""
        self._json_response({"error": error, "detail": detail}, status=status)

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True  # Ctrl+C soll nicht auf offene Fortschritts-Streams warten


def parse_port(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(tr("not_a_number", value=value))
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(tr("port_range"))
    if port in BROWSER_BLOCKED_PORTS:
        raise argparse.ArgumentTypeError(tr("port_blocked", port=port))
    return port


def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def is_listening(port):
    """Prüft, ob auf dem Port tatsächlich ein Programm Verbindungen annimmt."""
    try:
        with socket.create_connection((HOST, port), timeout=0.5):
            return True
    except ConnectionRefusedError:
        return False
    except OSError:
        return True


def find_free_ports(start, count=PORT_SUGGESTIONS):
    """Liefert die nächsten freien Ports ab `start`."""
    ports = []
    for port in range(start, 65536):
        if port not in BROWSER_BLOCKED_PORTS and is_port_free(port):
            ports.append(port)
            if len(ports) == count:
                break
    return ports


def ask_port(busy_port):
    """Bietet die nächsten freien Ports nach `busy_port` zur Auswahl an; eigene Eingabe ist auch möglich."""
    suggestions = find_free_ports(busy_port + 1)
    if suggestions:
        print("  " + tr("free_ports"))
        for i, port in enumerate(suggestions, 1):
            print(f"    [{i}] {port}")
        prompt = "  " + tr("choose_port", port=suggestions[0])
    else:
        prompt = "  " + tr("enter_port")

    while True:
        try:
            value = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(1)
        if not value and suggestions:
            return suggestions[0]
        if value.isdecimal() and 1 <= int(value) <= len(suggestions):
            return suggestions[int(value) - 1]
        try:
            return parse_port(value)
        except argparse.ArgumentTypeError as e:
            print("  " + tr("invalid_input", error=e))


def bind_server(port):
    """Bindet den Server an den Port. Wirft OSError, wenn das nicht möglich ist."""
    try:
        return Server((HOST, port), Handler)
    except OSError as e:
        # Kurz nach dem Beenden hält das System den Port noch fest, obwohl niemand mehr lauscht.
        # Nur in diesem Fall mit SO_REUSEADDR erneut binden: Generell gesetzt würde es unter
        # macOS einen fremden Listener auf *:port überdecken.
        if e.errno != errno.EADDRINUSE or sys.platform == "win32" or is_listening(port):
            raise

    httpd = Server((HOST, port), Handler, bind_and_activate=False)
    httpd.allow_reuse_address = True
    try:
        httpd.server_bind()
        httpd.server_activate()
    except OSError:
        httpd.server_close()
        raise
    return httpd


def create_server(port, interactive=True):
    """Startet den Server. Ist der Port nicht verfügbar, wird nach einem anderen gefragt,
    oder ohne Rückfrage (interactive=False, z.B. in der Mac-App) der nächste freie genommen."""
    while True:
        try:
            return bind_server(port)
        except OSError as e:
            if e.errno not in (errno.EADDRINUSE, errno.EACCES):
                print("  " + tr("server_failed", error=e))
                sys.exit(1)
            print("  " + tr("port_unavailable", port=port, reason=e.strerror))
            if not interactive:
                free = find_free_ports(port + 1, count=1)
                if not free:
                    print("  " + tr("no_free_port"))
                    sys.exit(1)
                port = free[0]
                continue
            if not (sys.stdin and sys.stdin.isatty()):
                print("  " + tr("use_port_option"))
                sys.exit(1)
            port = ask_port(port)


def main():
    parser = argparse.ArgumentParser(description=tr("description"))
    parser.add_argument(
        "-p", "--port", type=parse_port, default=DEFAULT_PORT,
        help=tr("help_port", port=DEFAULT_PORT),
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help=tr("help_no_browser"),
    )
    args = parser.parse_args()

    if not find_and_add_ffmpeg():
        print("  " + tr("ffmpeg_missing"))
        print("  " + tr("ffmpeg_install"))
        print("    brew install ffmpeg          (macOS)")
        print("    winget install Gyan.FFmpeg   (Windows)")
        print("    sudo apt install ffmpeg      (Linux)")

    load_engines()
    migrate_legacy_names()

    httpd = create_server(args.port)
    url = f"http://{HOST}:{httpd.server_address[1]}"

    print("=" * 50)
    print("  " + tr("description"))
    print("=" * 50)
    print("  " + tr("running_on", url=url))
    print(f"  Engines: {', '.join(ENGINES[name]['label'] for name in _engines)}")
    if not args.no_browser:
        print("  " + tr("opening_browser"))
    # Deutsche Windows-Tastaturen beschriften die Taste mit „Strg“
    stop_key = "Strg+C" if sys.platform == "win32" and UI_LANGUAGE == "de" else "Ctrl+C"
    print("  " + tr("stop_with", key=stop_key))
    print("=" * 50)

    threading.Thread(target=_prune_jobs_forever, daemon=True).start()
    if not args.no_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

    with httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  " + tr("stopped"))


if __name__ == "__main__":
    main()
