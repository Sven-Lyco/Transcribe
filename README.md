# Transcribe

A local audio transcription tool with a small web UI, powered by [OpenAI Whisper](https://github.com/openai/whisper). Audio is transcribed on your own machine: no API key, no account, no upload.

It can also run on your own server (for example with [Coolify](https://coolify.io)) as a web app for your phone. Together with an iOS Shortcut you can transcribe WhatsApp voice messages straight from the share sheet. See [Hosting on your own server](#hosting-on-your-own-server).

> **Note:** The web UI and the console messages are in German. The steps below name the German labels you will see.

## Features

- Drag & drop audio files (OGG, MP3, WAV, M4A, OPUS, WebM)
- Real-time progress bar during transcription
- Language selection (German, English, auto-detect)
- Optional speaker name prefix in output
- Timestamp extracted automatically from filename (WhatsApp format supported)
- History of past transcriptions in the browser, with copy, delete, export, and import
- Saves each transcription as a `.txt` file in `transcriptions/` or in a folder of your choice
- Works on macOS, Windows, and Linux
- GPU acceleration when available (CUDA / Apple Silicon MPS), CPU fallback otherwise
- Optional hosted mode with token protection and an iOS Shortcut for WhatsApp voice messages

## Privacy

Local mode:

- Audio files and transcriptions never leave your machine.
- The web UI is served on `127.0.0.1` only, so other devices on your network cannot reach it. Requests coming from other websites are rejected.
- The page loads no external resources: no fonts, scripts, or analytics.
- An internet connection is needed only to install the dependencies on the first run and to download each Whisper model the first time you select it.

Hosted mode:

- Audio is uploaded to your own server, transcribed there, and deleted right away.
- The server never writes transcriptions to disk. A result stays in memory only until the web app has fetched it, and for at most one hour if it is never fetched.
- Transcriptions are stored only in the `localStorage` of the browser that fetched them.
- Uploads require a secret token.

## Requirements

- Python 3.10 or newer
- [ffmpeg](https://ffmpeg.org/) for audio decoding:

  | System  | Command                       |
  |---------|-------------------------------|
  | macOS   | `brew install ffmpeg`         |
  | Windows | `winget install Gyan.FFmpeg`  |
  | Linux   | `sudo apt install ffmpeg`     |

## Setup & Usage

Clone the repository first:

```bash
git clone https://github.com/Sven-Lyco/Transcribe.git
cd Transcribe
```

### macOS / Linux

```bash
./transcribe.sh
```

### Windows

Double-click `transcribe.bat` or run:

```bat
transcribe.bat
```

On the first run the script creates a virtual environment in `.venv` and installs Whisper together with PyTorch. This is a large download and can take several minutes.

The script then starts a local server and opens the web UI at `http://127.0.0.1:8765`. Press `Ctrl+C` in the terminal to stop it.

### Transcribing a file

1. Drop an audio file onto the page, or click the drop area to choose one.
2. Optional: open the settings (⚙︎ or `ändern`) to pick a model (`Modell`), the spoken language (`Sprache`), and an output folder (`Ausgabeordner`). The page remembers these settings.
3. Optional: enter a speaker name (`Name`).
4. Click `Starten`.

The result appears in the history (`Verlauf`) on the page and is saved as a `.txt` file named after the audio file. By default it goes to the `transcriptions/` folder inside the project directory. To save it elsewhere, enter the full path of an existing folder in `Ausgabeordner` (`~` is supported). An existing `.txt` with the same name is overwritten.

### Custom port

The web UI uses port `8765` by default. Pass `--port` (or `-p`) to use a different one:

```bash
./transcribe.sh --port 9000      # macOS / Linux
transcribe.bat --port 9000       # Windows
```

If the port is already in use, the tool lists the next free ports at startup. Pick one by its number, type a port of your own, or press Enter to take the first suggestion.

### Manual

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install openai-whisper
python transcribe.py
```

## Whisper Models

| Model  | Download | Quality        |
|--------|----------|----------------|
| tiny   | ~75 MB   | Fast, basic    |
| base   | ~140 MB  | Good           |
| small  | ~460 MB  | Better         |
| medium | ~1.4 GB  | Best (default) |

A model is downloaded automatically the first time you use it and cached in `~/.cache/whisper`.

## Output Format

The transcription can be prefixed with a timestamp and a speaker name. The timestamp is taken from the filename if it contains the pattern `YYYY-MM-DD at HH.MM.SS`, as WhatsApp audio files do.

| Speaker name | Timestamp in filename | Output                                        |
|--------------|-----------------------|-----------------------------------------------|
| yes          | yes                   | `2026-08-12 - 09.49.50 - Speaker Name: Text…` |
| yes          | no                    | `Speaker Name: Text…`                         |
| no           | yes                   | `2026-08-12 - 09.49.50: Text…`                |
| no           | no                    | `Text…`                                       |

**Example input:**

```text
WhatsApp Audio 2026-08-12 at 09.49.50.ogg
```

**Output (`WhatsApp Audio 2026-08-12 at 09.49.50.txt`):**

```text
2026-08-12 - 09.49.50 - Speaker Name: Transcribed text appears here.
```

## Hosting on your own server

The same app can run on a server as a web app for your phone. In hosted mode it uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on the CPU, protects uploads with a token, and stores nothing on the server. Transcriptions are kept in the browser only.

### Deploying with Coolify

1. Create a new resource from this Git repository and choose the **Dockerfile** build pack.
2. Set the port to `8765` and assign a domain with HTTPS. The web app needs HTTPS.
3. Add the environment variable `TRANSCRIBE_TOKEN` with a long random value, for example from `openssl rand -hex 32`.
4. Add a persistent volume mounted at `/models`. Otherwise every deployment downloads the model again.
5. Deploy. On first start the server downloads the default model (about 1.6 GB) and logs `Modell 'large-v3-turbo' bereit`.

Optional environment variables:

| Variable           | Default          | Meaning                                                       |
|--------------------|------------------|---------------------------------------------------------------|
| `TRANSCRIBE_TOKEN` | –                | Required. Secret for uploads.                                 |
| `TRANSCRIBE_MODEL` | `large-v3-turbo` | Default model: `small`, `medium`, or `large-v3-turbo`.        |

The server needs at least 4 GB of RAM for `large-v3-turbo`. On a CPU with 4 cores, a voice message takes roughly as long to transcribe as it is to listen to. If that is too slow, set `TRANSCRIBE_MODEL=medium` or `small`.

Without Coolify:

```bash
docker build -t transcribe .
docker run -d -p 8765:8765 -e TRANSCRIBE_TOKEN=<secret> -v transcribe-models:/models transcribe
```

Put a reverse proxy with HTTPS in front of it.

### Using the web app on iPhone

1. Open your domain in **Safari**.
2. Tap ⚙︎, enter the token, and pick the model.
3. Add the page as a Safari bookmark or to your favorites.

Use the page in Safari rather than adding it to the Home Screen. The Shortcut below always opens Safari, and a Home Screen web app keeps its own separate history. iOS does not let websites appear in the share sheet, so the Shortcut is what brings WhatsApp voice messages into the web app.

### iOS Shortcut for WhatsApp voice messages

The Shortcut uploads the voice message and opens the web app, which shows the progress and then the text.

Create a new shortcut in the Shortcuts app (German labels in parentheses):

1. Open the shortcut details (ⓘ) and turn on **Show in Share Sheet** (*Im Share-Sheet anzeigen*). Set the accepted input to **Files** (*Dateien*) and **Media** (*Medien*).
2. Add **Get Contents of URL** (*Inhalte von URL abrufen*):
   - URL: `https://<your-domain>/transcribe`
   - Method: `POST`
   - Headers: `Authorization` = `Bearer <your-token>`
   - Request Body: **Form** (*Formular*) with these fields:
     - `file` (type **File**) = **Shortcut Input** (*Kurzbefehleingabe*)
     - `language` (type **Text**) = `de`
     - `model` (type **Text**) = `large-v3-turbo` (optional; without it the server default is used)
3. Add **Get Dictionary Value** (*Wörterbuchwert abrufen*): key `job_id` from **Contents of URL**.
4. Add **URL**: `https://<your-domain>/?job=` followed by the **Dictionary Value** variable.
5. Add **Open URLs** (*URLs öffnen*).

To transcribe a voice message, long-press it in WhatsApp, tap **Forward** (*Weiterleiten*), then the share button, and pick the shortcut. Safari opens the web app and the text appears in the history. You can leave Safari in the meantime; the web app picks the job up again when you come back.

### Running hosted mode without Docker

```bash
pip install -r requirements-server.txt
TRANSCRIBE_HOSTED=1 TRANSCRIBE_TOKEN=<secret> python transcribe.py
```

The server listens on all interfaces. ffmpeg is not needed in hosted mode; audio is decoded with PyAV.

## Troubleshooting

**`Warnung: ffmpeg wurde nicht gefunden` at startup**
ffmpeg is missing or not on your `PATH`, and transcriptions will fail. Install it with the command from [Requirements](#requirements) and start the tool again.

**`Port 8765 ist nicht verfügbar`**
Another program is using the port. Choose one of the suggested ports, or start with `--port` as described under [Custom port](#custom-port).

**The first transcription with a model takes much longer**
The model is being downloaded. Later runs use the cached copy.

**`Ungültiges oder fehlendes Token` (hosted mode)**
The token in the web app settings or in the Shortcut does not match `TRANSCRIBE_TOKEN` on the server.

**`Job nicht gefunden` (hosted mode)**
The result was not fetched within one hour, or the server was restarted in the meantime. Share the voice message again.

**The history is gone (iPhone)**
Safari deletes website data after 7 days of Safari use without visiting the site. Export the history from time to time (⚙︎ → `Verlauf exportieren`). A Home Screen web app keeps a separate history from the Safari tab; see [Using the web app on iPhone](#using-the-web-app-on-iphone).

## License

[MIT](LICENSE)
