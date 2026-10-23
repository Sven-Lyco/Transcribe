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

VERSION = "1.0.1"  # muss zum Release-Tag vX.Y.Z passen

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
        "default_model": "large-v3-turbo",
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

# In der Mac-App (PyInstaller) liegen die Dateien unter sys._MEIPASS
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
STATIC_DIR = BASE_DIR / "static"
# Die Mac-App legt alle ihre Daten in einen eigenen Ordner (TRANSCRIBE_DATA_DIR), damit
# „Alle App-Daten löschen“ sie gesammelt entfernen kann. Das Skript speichert im Projektordner.
APP_DATA_DIR = Path(os.environ["TRANSCRIBE_DATA_DIR"]) if os.environ.get("TRANSCRIBE_DATA_DIR") else None
DEFAULT_OUTPUT_DIR = APP_DATA_DIR / "Transkripte" if APP_DATA_DIR else Path(__file__).parent / "transcriptions"
# Merkt sich zu jedem Transkript Datum, Dauer und Originaldatei für den Verlauf
HISTORY_INDEX = DEFAULT_OUTPUT_DIR / ".verlauf.json"
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
                print(f"  ffmpeg gefunden: {path}")
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
                print(f"  ffmpeg gefunden: {match}")
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
                print(f"  {engine['label']} ist installiert, lässt sich aber nicht laden: {e}")
        except Exception as e:
            print(f"  {engine['label']} ist installiert, lässt sich aber nicht laden: {e}")

    if not _engines:
        print("=" * 50)
        print("Whisper ist nicht installiert.")
        print("Bitte einmalig ausführen:")
        print("    pip install openai-whisper")
        if sys.platform == "darwin" and os.uname().machine == "arm64":
            print("    pip install mlx-whisper   (Apple Silicon, deutlich schneller)")
        print("=" * 50)
        sys.exit(1)

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

    print(f"  → Lade Modell '{model_name}'...")
    # Auf CPU laden und alignment_heads (sparse Tensor) in dense umwandeln,
    # da MPS keine sparse Tensoren unterstützt (siehe pytorch/pytorch#78168).
    model = _engines["openai"].load_model(model_name, device="cpu")
    if device != "cpu":
        model.alignment_heads = model.alignment_heads.to_dense()
        model = model.to(device)

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
    print(f"  → Lade Modell {repo} herunter...")
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
            print(f"  → Transkribiere '{file_name}' mit {engine}/{model_name}...")
            # verbose=False zeigt den tqdm-Fortschritt, über den Fortschritt und Abbruch laufen
            kwargs = {"verbose": False}
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
        transcript_id = _add_to_history(txt_path, file_name, lang, duration)
        print(f"  ✓ Fertig! Gespeichert als: {txt_path}")

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
        print(f"  ⏹ '{file_name}' abgebrochen")
    except Exception as e:
        message = str(e)
        if message.startswith("Failed to load audio"):
            # Beide Engines hängen die komplette ffmpeg-Ausgabe an, die gehört nur ins Log
            print(f"  ✗ '{file_name}': {message}")
            message = "Audio konnte nicht gelesen werden (beschädigt, unbekanntes Format oder keine Tonspur)."
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update({"done": True, "finished_at": time.time(), "error": message})
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


def _add_to_history(txt_path, file_name, language, duration):
    """Trägt ein gespeichertes Transkript in den Verlauf ein und gibt seine ID zurück."""
    transcript_id = uuid.uuid4().hex
    with _history_lock:
        # Gleicher Dateiname überschreibt die .txt, dann auch den alten Eintrag ersetzen
        index = {k: v for k, v in _load_history_index().items() if v.get("path") != str(txt_path)}
        index[transcript_id] = {
            "path": str(txt_path),
            "date": datetime.now().astimezone().isoformat(timespec="seconds"),
            "file_name": file_name,
            "language": language,
            "duration": duration,
        }
        _save_history_index(index)
    return transcript_id


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
            entries.append({**meta, "id": transcript_id})
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
            path = Path(index.pop(transcript_id)["path"])
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


def _reset_app_data():
    """Löscht alles im App-Datenordner: Transkripte, Verlauf, Modelle, Caches, Log."""
    with _jobs_lock:
        _jobs.clear()  # laufende Transkriptionen brechen beim nächsten Abschnitt ab
    with _history_lock:
        for child in APP_DATA_DIR.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    print("  Alle App-Daten gelöscht")


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
                "version": VERSION,
                "app": APP_DATA_DIR is not None,
                "output_dir": str(DEFAULT_OUTPUT_DIR).replace(str(Path.home()), "~", 1),
            })
            return

        if parsed.path == "/transcripts":
            self._json_response(_list_history())
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
                    payload = {
                        "type": "error",
                        "gone": True,
                        "message": "Job nicht gefunden – abgebrochen, abgelaufen oder Server neu gestartet.",
                    }
                elif job.get("done"):
                    if job.get("error"):
                        payload = {"type": "error", "message": job["error"]}
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
            _reset_app_data()
            self._json_response({"ok": True})
            return

        if self.path != "/transcribe":
            self.send_response(404)
            self.end_headers()
            return

        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            self._json_response({"error": "Erwartet multipart/form-data."}, status=400)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if length < 0:
            self._json_response({"error": "Content-Length fehlt."}, status=411)
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
            self._json_response({"error": "Keine Datei empfangen."}, status=400)
            return

        if engine not in _engines:
            self._json_response({"error": f"Engine nicht installiert. Verfügbar: {', '.join(_engines)}"}, status=400)
            return

        models = ENGINES[engine]["models"]
        model_name = model_name or ENGINES[engine]["default_model"]
        if model_name not in models:
            self._json_response({"error": f"Unbekanntes Modell. Erlaubt: {', '.join(models)}"}, status=400)
            return

        if language not in LANGUAGES:
            self._json_response({"error": f"Unbekannte Sprache. Erlaubt: {', '.join(LANGUAGES)}"}, status=400)
            return

        if APP_DATA_DIR:
            output_folder = ""  # die App speichert immer in ihrem eigenen Ordner
        elif output_folder:
            output_dir = Path(output_folder).expanduser()
            if not output_dir.is_dir():
                self._json_response({"error": f"Ausgabeordner nicht gefunden: {output_folder}"})
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
            }

        threading.Thread(
            target=_run_transcription,
            args=(job_id, engine, model_name, tmp_path, language, speaker_name, output_folder, file_name),
            daemon=True,
        ).start()

        self._json_response({"job_id": job_id})

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
        raise argparse.ArgumentTypeError(f"'{value}' ist keine Zahl")
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port muss zwischen 1 und 65535 liegen")
    if port in BROWSER_BLOCKED_PORTS:
        raise argparse.ArgumentTypeError(f"Port {port} wird von Browsern blockiert")
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
        print("  Freie Ports:")
        for i, port in enumerate(suggestions, 1):
            print(f"    [{i}] {port}")
        prompt = f"  Auswahl oder eigener Port (Enter = {suggestions[0]}): "
    else:
        prompt = "  Anderen Port eingeben: "

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
            print(f"  Ungültige Eingabe: {e}")


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
                print(f"  Server konnte nicht gestartet werden: {e}")
                sys.exit(1)
            print(f"  Port {port} ist nicht verfügbar ({e.strerror}).")
            if not interactive:
                free = find_free_ports(port + 1, count=1)
                if not free:
                    print("  Kein freier Port gefunden.")
                    sys.exit(1)
                port = free[0]
                continue
            if not (sys.stdin and sys.stdin.isatty()):
                print("  Mit --port einen anderen Port angeben.")
                sys.exit(1)
            port = ask_port(port)


def main():
    parser = argparse.ArgumentParser(description="Lokales Whisper Transkriptions-Tool")
    parser.add_argument(
        "-p", "--port", type=parse_port, default=DEFAULT_PORT,
        help=f"Port für die Weboberfläche (Standard: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Browser beim Start nicht öffnen",
    )
    args = parser.parse_args()

    if not find_and_add_ffmpeg():
        print("  Warnung: ffmpeg wurde nicht gefunden. Ohne ffmpeg schlägt die Transkription fehl.")
        print("  Installation: brew install ffmpeg (macOS), winget install Gyan.FFmpeg (Windows),")
        print("                sudo apt install ffmpeg (Linux)")

    load_engines()

    httpd = create_server(args.port)
    url = f"http://{HOST}:{httpd.server_address[1]}"

    print("=" * 50)
    print("  Whisper Transkriptions-Tool")
    print("=" * 50)
    print(f"  Server läuft auf {url}")
    print(f"  Engines: {', '.join(ENGINES[name]['label'] for name in _engines)}")
    if not args.no_browser:
        print("  Browser öffnet sich automatisch...")
    stop_key = "Strg+C" if sys.platform == "win32" else "Ctrl+C"
    print(f"  Zum Beenden: {stop_key}")
    print("=" * 50)

    threading.Thread(target=_prune_jobs_forever, daemon=True).start()
    if not args.no_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

    with httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server gestoppt.")


if __name__ == "__main__":
    main()
