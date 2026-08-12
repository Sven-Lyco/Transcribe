"""
Lokales Whisper Transkriptions-Tool
====================================
Einmalige Installation (einmal ausführen):
    pip install openai-whisper

Danach einfach starten:
    python transcribe.py

Öffnet dann automatisch http://localhost:8765 im Browser.
"""

import http.server
import socketserver
import json
import os
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import glob
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8765

# ffmpeg automatisch finden (Windows WinGet + macOS Homebrew)
def find_and_add_ffmpeg():
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

ffmpeg_found = find_and_add_ffmpeg()

# Prüfe ob whisper installiert ist
try:
    import whisper
    import tqdm as _tqdm_module

    _jobs: dict = {}
    _jobs_lock = threading.Lock()
    _tqdm_local = threading.local()

    _orig_tqdm = _tqdm_module.tqdm

    class _ProgressTqdm(_orig_tqdm):
        def update(self, n=1):
            result = super().update(n)
            job_id = getattr(_tqdm_local, "job_id", None)
            if job_id and self.total and self.total > 0:
                pct = min(99, int(self.n / self.total * 100))
                with _jobs_lock:
                    if job_id in _jobs:
                        _jobs[job_id]["progress"] = pct
            return result

    _tqdm_module.tqdm = _ProgressTqdm

except ImportError:
    print("=" * 50)
    print("Whisper ist nicht installiert.")
    print("Bitte einmalig ausführen:")
    print("    pip install openai-whisper")
    print("=" * 50)
    sys.exit(1)

HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Whisper Transkription</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  :root {
    --bg: #0f0f0f;
    --surface: #1a1a1a;
    --border: #2a2a2a;
    --accent: #e8ff5a;
    --text: #e0e0e0;
    --muted: #666;
    --radius: 4px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 300;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }

  .container {
    width: 100%;
    max-width: 680px;
  }

  h1 {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
  }

  .subtitle {
    color: var(--muted);
    font-size: 0.85rem;
    margin-bottom: 2.5rem;
    font-family: 'IBM Plex Mono', monospace;
  }

  .drop-zone {
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    background: var(--surface);
    position: relative;
  }

  .drop-zone:hover, .drop-zone.dragover {
    border-color: var(--accent);
    background: #1f1f1f;
  }

  .drop-zone input[type="file"] {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
    width: 100%;
    height: 100%;
  }

  .drop-icon {
    font-size: 2rem;
    margin-bottom: 1rem;
    display: block;
  }

  .drop-text {
    font-size: 0.9rem;
    color: var(--muted);
  }

  .drop-text strong {
    color: var(--text);
    font-weight: 600;
  }

  .file-info {
    margin-top: 0.75rem;
    font-size: 0.8rem;
    color: var(--accent);
    font-family: 'IBM Plex Mono', monospace;
  }

  .settings {
    margin-top: 1.5rem;
    display: flex;
    gap: 1rem;
    align-items: flex-end;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    flex: 1;
  }

  label {
    font-size: 0.75rem;
    color: var(--muted);
    font-family: 'IBM Plex Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  select {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 0.6rem 0.75rem;
    border-radius: var(--radius);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.9rem;
    appearance: none;
    cursor: pointer;
    transition: border-color 0.2s;
  }

  select:focus {
    outline: none;
    border-color: var(--accent);
  }

  input[type="text"] {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 0.6rem 0.75rem;
    border-radius: var(--radius);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.9rem;
    transition: border-color 0.2s;
    width: 100%;
  }

  input[type="text"]:focus {
    outline: none;
    border-color: var(--accent);
  }

  input[type="text"]::placeholder {
    color: var(--muted);
  }

  button {
    background: var(--accent);
    color: #0f0f0f;
    border: none;
    padding: 0.65rem 1.5rem;
    border-radius: var(--radius);
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    font-size: 0.85rem;
    cursor: pointer;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    transition: opacity 0.2s;
    white-space: nowrap;
  }

  button:hover { opacity: 0.85; }
  button:disabled { opacity: 0.3; cursor: not-allowed; }

  .status {
    margin-top: 1.5rem;
    padding: 1rem;
    background: var(--surface);
    border-left: 3px solid var(--accent);
    border-radius: 0 var(--radius) var(--radius) 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    color: var(--text);
    display: none;
  }

  .status.visible { display: block; }

  .status .progress {
    color: var(--accent);
    margin-bottom: 0.3rem;
  }

  .result {
    margin-top: 1.5rem;
    display: none;
  }

  .result.visible { display: block; }

  .result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .result-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .copy-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 0.3rem 0.75rem;
    font-size: 0.75rem;
  }

  .copy-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
    opacity: 1;
  }

  textarea {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 1rem;
    border-radius: var(--radius);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.9rem;
    line-height: 1.6;
    resize: vertical;
    min-height: 160px;
  }

  textarea:focus {
    outline: none;
    border-color: var(--accent);
  }

  .model-hint {
    margin-top: 0.4rem;
    font-size: 0.75rem;
    color: var(--muted);
    font-family: 'IBM Plex Mono', monospace;
  }

  .prog-bar {
    margin-top: 0.75rem;
    height: 3px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    display: none;
  }

  .prog-fill {
    height: 100%;
    background: var(--accent);
    width: 0%;
    transition: width 0.4s ease;
  }

  .spinner {
    display: inline-block;
    width: 10px;
    height: 10px;
    border: 2px solid var(--accent);
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 0.5rem;
    vertical-align: middle;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="container">
  <h1>Whisper Transkription</h1>
  <p class="subtitle">// lokal · kein API-Key · kein Internet</p>

  <div class="drop-zone" id="dropZone">
    <input type="file" id="fileInput" accept="audio/*,.ogg,.mp3,.wav,.m4a,.opus,.webm">
    <span class="drop-icon">🎙</span>
    <div class="drop-text"><strong>Audiodatei hierher ziehen</strong><br>oder klicken zum Auswählen</div>
    <div class="file-info" id="fileInfo"></div>
  </div>

  <div class="settings">
    <div class="field">
      <label>Modell</label>
      <select id="model">
        <option value="tiny">tiny — schnell, ~39MB</option>
        <option value="base">base — gut, ~74MB</option>
        <option value="small">small — besser, ~244MB</option>
        <option value="medium" selected>medium — sehr gut, ~769MB</option>
      </select>
      <div class="model-hint" id="modelHint">Beim ersten Mal wird das Modell heruntergeladen.</div>
    </div>
    <div class="field" style="flex:0">
      <label>Sprache</label>
      <select id="language">
        <option value="de" selected>Deutsch</option>
        <option value="en">English</option>
        <option value="auto">Auto-detect</option>
      </select>
    </div>
    <button id="startBtn" disabled>Starten</button>
  </div>

  <div class="settings" style="margin-top: 0.75rem;">
    <div class="field">
      <label>Name (optional)</label>
      <input type="text" id="speakerName" placeholder="z.B. Max Mustermann">
    </div>
    <div class="field">
      <label>Ausgabeordner</label>
      <input type="text" id="outputFolder" placeholder="Pfad zum Zielordner (leer = transcriptions/)">
    </div>
  </div>

  <div class="status" id="status">
    <div class="progress" id="statusText"><span class="spinner"></span> Wird verarbeitet...</div>
    <div id="statusDetail"></div>
    <div class="prog-bar" id="progBar"><div class="prog-fill" id="progFill"></div></div>
  </div>

  <div class="result" id="result">
    <div class="result-header">
      <span class="result-label">Transkription</span>
      <button class="copy-btn" id="copyBtn">Kopieren</button>
    </div>
    <textarea id="transcript" readonly></textarea>
  </div>
</div>

<script>
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const fileInfo = document.getElementById('fileInfo');
  const startBtn = document.getElementById('startBtn');
  const status = document.getElementById('status');
  const statusText = document.getElementById('statusText');
  const statusDetail = document.getElementById('statusDetail');
  const progBar = document.getElementById('progBar');
  const progFill = document.getElementById('progFill');
  const result = document.getElementById('result');
  const transcript = document.getElementById('transcript');
  const copyBtn = document.getElementById('copyBtn');
  const modelSelect = document.getElementById('model');
  const speakerNameInput = document.getElementById('speakerName');
  const outputFolderInput = document.getElementById('outputFolder');
  const modelHints = {
    tiny: 'Schnellste Option — für kurze Nachrichten gut geeignet.',
    base: 'Gute Balance aus Geschwindigkeit und Qualität.',
    small: 'Bessere Genauigkeit, dauert etwas länger.',
    medium: 'Sehr hohe Genauigkeit — empfohlen für Dialekt/Umgangssprache.'
  };

  modelSelect.addEventListener('change', () => {
    document.getElementById('modelHint').textContent =
      'Beim ersten Mal wird das Modell heruntergeladen. ' + modelHints[modelSelect.value];
  });

  let selectedFile = null;

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
    fileInfo.textContent = `${file.name} (${mb} MB)`;
    startBtn.disabled = false;
    result.classList.remove('visible');
    status.classList.remove('visible');
    // file.path is available in some local/Electron environments
    if (file.path) {
      const sep = file.path.includes('/') ? '/' : '\\\\';
      outputFolderInput.value = file.path.substring(0, file.path.lastIndexOf(sep));
    }
  }

  startBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    startBtn.disabled = true;
    status.classList.add('visible');
    statusText.innerHTML = '<span class="spinner"></span> Datei wird übertragen...';
    statusDetail.textContent = '';
    progFill.style.width = '0%';
    progBar.style.display = 'none';
    result.classList.remove('visible');

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('model', modelSelect.value);
    formData.append('language', document.getElementById('language').value);
    formData.append('speaker_name', speakerNameInput.value.trim());
    formData.append('output_folder', outputFolderInput.value.trim());

    try {
      const response = await fetch('/transcribe', { method: 'POST', body: formData });
      const data = await response.json();

      if (data.error) {
        statusText.innerHTML = '❌ Fehler';
        statusDetail.textContent = data.error;
        startBtn.disabled = false;
        return;
      }

      statusText.innerHTML = '<span class="spinner"></span> Modell wird geladen & Transkription läuft...';
      statusDetail.textContent = 'Das kann beim ersten Mal 1–2 Minuten dauern (Modell-Download).';
      progBar.style.display = 'block';

      const es = new EventSource(`/progress?job=${data.job_id}`);

      es.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'progress') {
          progFill.style.width = msg.value + '%';
          if (msg.value > 0) statusDetail.textContent = `Fortschritt: ${msg.value}%`;
        } else if (msg.type === 'done') {
          es.close();
          progFill.style.width = '100%';
          statusText.innerHTML = '✅ Fertig';
          statusDetail.textContent = `Sprache erkannt: ${msg.language} · Dauer: ${msg.duration}s · Gespeichert als: ${msg.saved_as}`;
          transcript.value = msg.text;
          result.classList.add('visible');
          startBtn.disabled = false;
        } else if (msg.type === 'error') {
          es.close();
          statusText.innerHTML = '❌ Fehler';
          statusDetail.textContent = msg.message;
          progBar.style.display = 'none';
          startBtn.disabled = false;
        }
      };

      es.onerror = () => {
        es.close();
        statusText.innerHTML = '❌ Verbindungsfehler';
        statusDetail.textContent = 'Verbindung zum Server unterbrochen.';
        progBar.style.display = 'none';
        startBtn.disabled = false;
      };

    } catch (err) {
      statusText.innerHTML = '❌ Verbindungsfehler';
      statusDetail.textContent = err.message;
      progBar.style.display = 'none';
      startBtn.disabled = false;
    }
  });

  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(transcript.value);
    copyBtn.textContent = 'Kopiert!';
    setTimeout(() => copyBtn.textContent = 'Kopieren', 2000);
  });
</script>
</body>
</html>"""


def _run_transcription(job_id, model_name, tmp_path, language, speaker_name, output_folder, file_name):
    _tqdm_local.job_id = job_id
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        print(f"  → Lade Modell '{model_name}'...")
        model = whisper.load_model(model_name, device=device)

        print(f"  → Transkribiere '{file_name}'...")
        kwargs = {"verbose": False}
        if language != "auto":
            kwargs["language"] = language

        result = model.transcribe(tmp_path, fp16=(device != "cpu"), **kwargs)
        text = result["text"].strip()
        lang = result.get("language", "?")

        import subprocess
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
                capture_output=True, text=True
            )
            duration = round(float(r.stdout.strip()))
        except Exception:
            duration = "?"

        if output_folder and Path(output_folder).is_dir():
            save_dir = Path(output_folder)
        else:
            save_dir = Path(__file__).parent / "transcriptions"
            save_dir.mkdir(exist_ok=True)

        import re
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
        txt_name = Path(file_name).stem + ".txt"
        txt_path = save_dir / txt_name
        txt_path.write_text(formatted_text, encoding="utf-8")
        print(f"  ✓ Fertig! Gespeichert als: {txt_path}")

        with _jobs_lock:
            _jobs[job_id]["progress"] = 100
            _jobs[job_id]["done"] = True
            _jobs[job_id]["result"] = {
                "text": formatted_text,
                "language": lang,
                "duration": duration,
                "saved_as": str(txt_path),
            }
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]["done"] = True
            _jobs[job_id]["error"] = str(e)
    finally:
        os.unlink(tmp_path)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Stille Logs

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/progress":
            job_id = parse_qs(parsed.query).get("job", [None])[0]
            if not job_id:
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    with _jobs_lock:
                        job = _jobs.get(job_id, {}).copy()
                    if not job:
                        break
                    if job.get("done"):
                        if job.get("error"):
                            payload = json.dumps({"type": "error", "message": job["error"]})
                        else:
                            payload = json.dumps({"type": "done", **job["result"]})
                        self.wfile.write(f"data: {payload}\n\n".encode())
                        self.wfile.flush()
                        with _jobs_lock:
                            _jobs.pop(job_id, None)
                        break
                    else:
                        payload = json.dumps({"type": "progress", "value": job.get("progress", 0)})
                        self.wfile.write(f"data: {payload}\n\n".encode())
                        self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        if self.path != "/transcribe":
            self.send_response(404)
            self.end_headers()
            return

        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Parse multipart
        boundary = content_type.split("boundary=")[-1].encode()
        parts = body.split(b"--" + boundary)

        file_data = None
        file_name = "audio.ogg"
        model_name = "base"
        language = "de"
        speaker_name = ""
        output_folder = ""

        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header, _, content = part.partition(b"\r\n\r\n")
            content = content.rstrip(b"\r\n")
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

        suffix = Path(file_name).suffix or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {"progress": 0, "done": False, "result": None, "error": None}

        threading.Thread(
            target=_run_transcription,
            args=(job_id, model_name, tmp_path, language, speaker_name, output_folder, file_name),
            daemon=True,
        ).start()

        self._json_response({"job_id": job_id})

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def main():
    print("=" * 50)
    print("  Whisper Transkriptions-Tool")
    print("=" * 50)
    print(f"  Server läuft auf http://localhost:{PORT}")
    print("  Browser öffnet sich automatisch...")
    stop_key = "Strg+C" if sys.platform == "win32" else "Ctrl+C"
    print(f"  Zum Beenden: {stop_key}")
    print("=" * 50)

    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server gestoppt.")


if __name__ == "__main__":
    main()
