"""
Whisper Transkriptions-Tool
===========================
Lokal (Standard):
    pip install openai-whisper
    python transcribe.py

    Öffnet dann automatisch http://127.0.0.1:8765 im Browser.

    Anderer Port:
        python transcribe.py --port 9000

Gehostet (z.B. Docker/Coolify, siehe Dockerfile):
    pip install faster-whisper
    TRANSCRIBE_HOSTED=1 TRANSCRIBE_TOKEN=<geheim> python transcribe.py

    Lauscht auf allen Interfaces, verlangt das Token beim Upload und
    speichert keine Transkripte auf dem Server.
"""

import argparse
import errno
import hmac
import http.server
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
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HOSTED = os.environ.get("TRANSCRIBE_HOSTED") == "1"
TOKEN = os.environ.get("TRANSCRIBE_TOKEN", "")

HOST = "0.0.0.0" if HOSTED else "127.0.0.1"
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
# Gehostet läuft faster-whisper auf der CPU; tiny/base lohnen sich dort nicht.
MODELS = ("small", "medium", "large-v3-turbo") if HOSTED else ("tiny", "base", "small", "medium")
DEFAULT_MODEL = os.environ.get("TRANSCRIBE_MODEL", "large-v3-turbo" if HOSTED else "medium")
LANGUAGES = ("de", "en", "auto")

JOB_TTL = 3600  # Sekunden, die ein fertiges, nicht abgeholtes Ergebnis im Speicher bleibt
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # nur gehostet

STATIC_DIR = Path(__file__).parent / "static"
# Ausgelieferte Dateien: Pfad -> (Datei, Content-Type, Cache-Control)
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8", "no-cache"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json", "no-cache"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8", "no-cache"),
    "/icon.svg": ("icon.svg", "image/svg+xml", "max-age=86400"),
    "/icon-192.png": ("icon-192.png", "image/png", "max-age=86400"),
    "/icon-512.png": ("icon-512.png", "image/png", "max-age=86400"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png", "max-age=86400"),
}
# Die Seite lädt nichts von fremden Servern
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
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


# werden erst in load_whisper() importiert, damit --help nicht auf den Import wartet
whisper = None
WhisperModel = None

_jobs: dict = {}
_jobs_lock = threading.Lock()
_tqdm_local = threading.local()

_models: dict = {}  # zuletzt benutztes Modell, bleibt zwischen den Jobs geladen
_transcribe_lock = threading.Lock()  # immer nur eine Transkription, sonst bremsen sich die Jobs aus


def _set_progress(job_id, pct):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = max(0, min(99, int(pct)))


def load_whisper():
    """Importiert die Whisper-Engine des aktuellen Modus."""
    global whisper, WhisperModel
    if HOSTED:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("=" * 50)
            print("faster-whisper ist nicht installiert.")
            print("Bitte einmalig ausführen:")
            print("    pip install faster-whisper")
            print("=" * 50)
            sys.exit(1)
        return

    try:
        import whisper
        import tqdm as _tqdm_module
    except ImportError:
        print("=" * 50)
        print("Whisper ist nicht installiert.")
        print("Bitte einmalig ausführen:")
        print("    pip install openai-whisper")
        print("=" * 50)
        sys.exit(1)

    # Fortschrittsbalken von openai-whisper an den laufenden Job weiterleiten
    _orig_tqdm = _tqdm_module.tqdm

    class _ProgressTqdm(_orig_tqdm):
        def update(self, n=1):
            result = super().update(n)
            job_id = getattr(_tqdm_local, "job_id", None)
            if job_id and self.total and self.total > 0:
                _set_progress(job_id, self.n / self.total * 100)
            return result

    _tqdm_module.tqdm = _ProgressTqdm


def _get_model(model_name):
    """Lädt das Modell beim ersten Gebrauch und hält es danach im Speicher. Nur mit _transcribe_lock aufrufen."""
    if model_name in _models:
        return _models[model_name]
    _models.clear()  # nur ein Modell im Speicher halten

    print(f"  → Lade Modell '{model_name}'...")
    if HOSTED:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    else:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        # Auf CPU laden und alignment_heads (sparse Tensor) in dense umwandeln,
        # da MPS keine sparse Tensoren unterstützt (siehe pytorch/pytorch#78168).
        model = whisper.load_model(model_name, device="cpu")
        if device != "cpu":
            model.alignment_heads = model.alignment_heads.to_dense()
            model = model.to(device)

    _models[model_name] = model
    return model


def _preload_model(model_name):
    """Lädt das Standardmodell vorab, damit der erste Upload nicht auf den Download wartet."""
    try:
        with _transcribe_lock:
            _get_model(model_name)
        print(f"  ✓ Modell '{model_name}' bereit")
    except Exception as e:
        print(f"  Modell '{model_name}' konnte nicht vorab geladen werden: {e}")


def _transcribe_openai(job_id, model, path, language):
    _tqdm_local.job_id = job_id
    kwargs = {"verbose": False}
    if language != "auto":
        kwargs["language"] = language

    # fp16 nur auf CUDA aktivieren: Apples MPS-Backend liefert bei manchen
    # Whisper-Modellen in fp16 NaN-Logits, daher dort auf fp32 bleiben.
    result = model.transcribe(path, fp16=(model.device.type == "cuda"), **kwargs)

    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        duration = round(float(r.stdout.strip()))
    except Exception:
        duration = "?"

    return result["text"].strip(), result.get("language", "?"), duration


def _decode_audio(path, sampling_rate=16000):
    """Dekodiert die Datei per PyAV zu 16-kHz-Mono, wie es Whisper erwartet.

    Ersetzt faster_whisper.decode_audio: Das übergibt in 1.2.1 `metadata_errors`,
    das PyAV ab Version 15 nicht mehr kennt.
    """
    import av
    import numpy as np
    no_audio = "Die Datei enthält keine Tonspur."
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sampling_rate)
    chunks = []
    try:
        with av.open(path) as container:
            if not container.streams.audio:
                raise RuntimeError(no_audio)
            for frame in container.decode(audio=0):
                chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))  # Rest leeren
    except (av.FFmpegError, ValueError) as e:
        # Die Meldung von PyAV enthält den Pfad der Temp-Datei, daher nicht durchreichen
        raise RuntimeError("Audio konnte nicht gelesen werden (beschädigt oder unbekanntes Format).") from e
    if not chunks:
        raise RuntimeError(no_audio)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def _transcribe_faster(job_id, model, path, language):
    # vad_filter überspringt Stille, in der Whisper sonst gern Text erfindet
    segments, info = model.transcribe(
        _decode_audio(path), language=None if language == "auto" else language, vad_filter=True,
    )
    parts = []
    for segment in segments:  # Generator: transkribiert wird erst beim Durchlaufen
        parts.append(segment.text)
        if info.duration:
            _set_progress(job_id, segment.end / info.duration * 100)
    return "".join(parts).strip(), info.language, round(info.duration)


def _run_transcription(job_id, model_name, tmp_path, language, speaker_name, output_folder, file_name):
    try:
        with _transcribe_lock:
            with _jobs_lock:
                _jobs[job_id]["state"] = "running"
            model = _get_model(model_name)
            # Gehostet keine Dateinamen ins Log schreiben
            print(f"  → Transkribiere {'Job ' + job_id[:8] if HOSTED else repr(file_name)}...")
            transcribe = _transcribe_faster if HOSTED else _transcribe_openai
            text, lang, duration = transcribe(job_id, model, tmp_path, language)

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

        saved_as = None
        if not HOSTED:
            if output_folder and Path(output_folder).is_dir():
                save_dir = Path(output_folder)
            else:
                save_dir = Path(__file__).parent / "transcriptions"
                save_dir.mkdir(exist_ok=True)
            txt_path = save_dir / (Path(file_name).stem + ".txt")
            txt_path.write_text(formatted_text, encoding="utf-8")
            saved_as = str(txt_path)
            print(f"  ✓ Fertig! Gespeichert als: {txt_path}")
        else:
            print(f"  ✓ Job {job_id[:8]} fertig")

        with _jobs_lock:
            _jobs[job_id].update({
                "progress": 100,
                "done": True,
                "finished_at": time.time(),
                "result": {
                    "text": formatted_text,
                    "language": lang,
                    "duration": duration,
                    "saved_as": saved_as,
                },
            })
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id].update({"done": True, "finished_at": time.time(), "error": str(e)})
    finally:
        os.unlink(tmp_path)


def _prune_jobs():
    """Entfernt fertige Jobs, deren Ergebnis nicht innerhalb von JOB_TTL abgeholt wurde."""
    now = time.time()
    with _jobs_lock:
        for job_id in [k for k, j in _jobs.items() if j["done"] and now - j["finished_at"] > JOB_TTL]:
            del _jobs[job_id]


def _prune_jobs_forever():
    while True:
        time.sleep(300)
        _prune_jobs()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Stille Logs

    def _is_local_request(self):
        """Lässt nur Anfragen der eigenen Seite zu, nicht die fremder Webseiten im selben Browser."""
        if HOSTED:
            return True  # gehostet schützt das Token den Upload
        port = self.server.server_address[1]
        names = ("127.0.0.1", "localhost")
        hosts = {f"{name}:{port}" for name in names}
        if port == 80:
            hosts.update(names)
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{host}" for host in hosts}

    def _is_authorized(self):
        if not HOSTED:
            return True
        auth = self.headers.get("Authorization", "")
        return hmac.compare_digest(auth.encode(), f"Bearer {TOKEN}".encode())

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
                "hosted": HOSTED,
                "models": MODELS,
                "default_model": DEFAULT_MODEL,
                "languages": LANGUAGES,
            })
            return

        if parsed.path in STATIC_FILES:
            name, content_type, cache = STATIC_FILES[parsed.path]
            try:
                body = (STATIC_DIR / name).read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
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
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # Reverse-Proxys sollen den Stream nicht puffern
        self.end_headers()
        try:
            while True:
                with _jobs_lock:
                    job = _jobs.get(job_id, {}).copy()
                if not job:
                    payload = {
                        "type": "error",
                        "gone": True,
                        "message": "Job nicht gefunden – abgelaufen oder Server neu gestartet.",
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
        """Die Seite hat das Ergebnis gespeichert, der Server vergisst es."""
        if not self._is_local_request():
            self.send_error(403)
            return
        parsed = urlparse(self.path)
        if parsed.path != "/job":
            self.send_error(404)
            return
        job_id = parse_qs(parsed.query).get("job", [None])[0]
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job and job["done"]:
                del _jobs[job_id]
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if not self._is_local_request():
            self.send_error(403)
            return

        if self.path != "/transcribe":
            self.send_response(404)
            self.end_headers()
            return

        if not self._is_authorized():
            self._json_response({"error": "Ungültiges oder fehlendes Token."}, status=401)
            return

        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        if HOSTED and length > MAX_UPLOAD_BYTES:
            self._json_response(
                {"error": f"Datei zu groß (max. {MAX_UPLOAD_BYTES // 1024 // 1024} MB)."}, status=413,
            )
            return
        body = self.rfile.read(length)

        # Parse multipart
        boundary = content_type.split("boundary=")[-1].strip('"').encode()
        parts = body.split(b"--" + boundary)

        file_data = None
        file_name = "audio.ogg"
        model_name = DEFAULT_MODEL
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
                    file_name = header_str.split('filename="')[1].split('"')[0]
            elif 'name="model"' in header_str:
                model_name = content.decode().strip()
            elif 'name="language"' in header_str:
                language = content.decode().strip()
            elif 'name="speaker_name"' in header_str:
                speaker_name = content.decode().strip()
            elif 'name="output_folder"' in header_str:
                output_folder = content.decode().strip()

        if not file_data:
            self._json_response({"error": "Keine Datei empfangen."})
            return

        if model_name not in MODELS:
            self._json_response({"error": f"Unbekanntes Modell: {model_name}"})
            return

        if language not in LANGUAGES:
            self._json_response({"error": f"Unbekannte Sprache: {language}"})
            return

        if HOSTED:
            output_folder = ""  # gehostet wird nichts gespeichert
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
            args=(job_id, model_name, tmp_path, language, speaker_name, output_folder, file_name),
            daemon=True,
        ).start()

        self._json_response({"job_id": job_id})

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
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


def create_server(port):
    """Startet den Server. Ist der Port nicht verfügbar, wird nach einem anderen gefragt."""
    while True:
        try:
            return bind_server(port)
        except OSError as e:
            if e.errno not in (errno.EADDRINUSE, errno.EACCES):
                print(f"  Server konnte nicht gestartet werden: {e}")
                sys.exit(1)
            print(f"  Port {port} ist nicht verfügbar ({e.strerror}).")
            if not (sys.stdin and sys.stdin.isatty()):
                print("  Mit --port einen anderen Port angeben.")
                sys.exit(1)
            port = ask_port(port)


def main():
    parser = argparse.ArgumentParser(description="Whisper Transkriptions-Tool")
    parser.add_argument(
        "-p", "--port", type=parse_port, default=DEFAULT_PORT,
        help=f"Port für die Weboberfläche (Standard: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Browser beim Start nicht öffnen",
    )
    args = parser.parse_args()

    if DEFAULT_MODEL not in MODELS:
        print(f"  Unbekanntes Standardmodell '{DEFAULT_MODEL}'. Erlaubt: {', '.join(MODELS)}")
        sys.exit(1)

    if HOSTED:
        if not TOKEN:
            print("  TRANSCRIBE_TOKEN ist nicht gesetzt. Ohne Token könnte jeder den Server benutzen.")
            sys.exit(1)
    elif not find_and_add_ffmpeg():
        print("  Warnung: ffmpeg wurde nicht gefunden. Ohne ffmpeg schlägt die Transkription fehl.")
        print("  Installation: brew install ffmpeg (macOS), winget install Gyan.FFmpeg (Windows),")
        print("                sudo apt install ffmpeg (Linux)")

    load_whisper()

    httpd = create_server(args.port)
    url = f"http://{HOST}:{httpd.server_address[1]}"
    open_browser = not (HOSTED or args.no_browser)

    print("=" * 50)
    print("  Whisper Transkriptions-Tool" + (" (gehostet)" if HOSTED else ""))
    print("=" * 50)
    print(f"  Server läuft auf {url}")
    if open_browser:
        print("  Browser öffnet sich automatisch...")
    stop_key = "Strg+C" if sys.platform == "win32" else "Ctrl+C"
    print(f"  Zum Beenden: {stop_key}")
    print("=" * 50)

    threading.Thread(target=_prune_jobs_forever, daemon=True).start()
    if HOSTED:
        threading.Thread(target=_preload_model, args=(DEFAULT_MODEL,), daemon=True).start()
    if open_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

    with httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server gestoppt.")


if __name__ == "__main__":
    main()
