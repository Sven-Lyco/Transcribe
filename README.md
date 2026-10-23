# Transcribe

A local audio transcription tool with a small web UI, powered by [OpenAI Whisper](https://github.com/openai/whisper). Audio is transcribed on your own machine: no API key, no account, no upload.

On Macs with Apple Silicon it uses [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), which runs Whisper on the GPU and is much faster. Everywhere else it uses [openai-whisper](https://github.com/openai/whisper).

> **Note:** The web UI and the console messages are in German. The steps below name the German labels you will see.

## Download for macOS

Transcribe is available as a Mac app for **Apple Silicon (M1 or newer) with macOS 14 Sonoma or later**. No Python, Terminal, or ffmpeg needed.

1. Download `Transcribe-<version>-arm64.dmg` from the [latest release](https://github.com/Sven-Lyco/Transcribe/releases/latest) and open it.
2. Drag **Transcribe** into **Applications**.
3. Open Transcribe. The app is not signed by Apple, so macOS blocks it the first time ("Apple could not verify …"). Click **Done**, open **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to Transcribe. This is needed only once.
4. Drop an audio file into the window.

The first transcription downloads the Whisper model (about 1.6 GB). The history (`Verlauf`) in the window shows all transcriptions; each one is also saved as a `.txt` file. Settings (⚙︎) → `Ordner öffnen` shows these files in Finder.

All app data lives in one folder, `~/Library/Application Support/Transcribe`:

| Folder or file   | Content                                  |
|------------------|------------------------------------------|
| `Transkripte/`   | Transcriptions as `.txt`, plus the index of the history |
| `huggingface/`   | Downloaded Whisper models                |
| `cache/`         | Compiled code cache, if one is needed    |
| `transcribe.log` | Log file                                 |

On Intel Macs, Windows, and Linux, use the script version described under [Setup & Usage](#setup--usage).

### Uninstalling the app

macOS does not remove an app's data when you move the app to the Trash. To remove everything:

1. In Transcribe, open the settings (⚙︎) and click `Alle App-Daten löschen …`. This deletes all transcriptions, the history, and the downloaded model.
2. Quit Transcribe and move it from **Applications** to the Trash.

The window settings (engine, model, language) remain as a few hundred KB of WebKit data in `~/Library/WebKit/io.github.sven-lyco.transcribe` and `~/Library/Caches/io.github.sven-lyco.transcribe`; you can delete these folders too.

## Features

- Drag & drop audio files (OGG, MP3, WAV, M4A, OPUS, WebM)
- Two Whisper engines: mlx-whisper (Apple Silicon, default there) and openai-whisper
- Real-time progress bar during transcription, with a button to cancel
- Language selection (German, English, auto-detect)
- Optional speaker name prefix in output
- Timestamp extracted automatically from filename (WhatsApp format supported)
- History of past transcriptions with copy and delete, based on the saved `.txt` files
- Saves each transcription as a `.txt` file in `transcriptions/` or in a folder of your choice
- Works on macOS, Windows, and Linux
- GPU acceleration when available (Apple Silicon via MLX or MPS, CUDA), CPU fallback otherwise

## Privacy

- Audio files and transcriptions never leave your machine.
- The web UI is served on `127.0.0.1` only, so other devices on your network cannot reach it. Requests coming from other websites are rejected.
- The page loads no external resources: no fonts, scripts, or analytics.
- An internet connection is needed only to install the dependencies on the first run and to download each Whisper model the first time you select it.

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

On the first run the script creates a virtual environment in `.venv` and installs Whisper together with PyTorch, plus mlx-whisper on Apple Silicon. This is a large download and can take several minutes. An existing `.venv` that was created with Python older than 3.10 is replaced automatically.

The script then starts a local server and opens the web UI at `http://127.0.0.1:8765`. Press `Ctrl+C` in the terminal to stop it.

### Transcribing a file

1. Drop an audio file onto the page, or click the drop area to choose one.
2. Optional: open the settings (⚙︎ or `ändern`) to pick the engine (`Engine`), the model (`Modell`), the spoken language (`Sprache`), and an output folder (`Ausgabeordner`). The page remembers these settings, including the chosen model for each engine.
3. Optional: enter a speaker name (`Name`).
4. Click `Starten`.

To stop a transcription, click `Abbrechen` below its progress bar. Whisper works through the audio in sections of about 30 seconds, so a running transcription stops at the end of the current section.

The result appears in the history (`Verlauf`) on the page and is saved as a `.txt` file named after the audio file. By default it goes to the `transcriptions/` folder inside the project directory. To save it elsewhere, enter the full path of an existing folder in `Ausgabeordner` (`~` is supported). An existing `.txt` with the same name is overwritten.

The history lists the `.txt` files in the `transcriptions/` folder and those saved elsewhere through `Ausgabeordner`. Deleting an entry in the history also deletes its `.txt` file; a file deleted in Finder disappears from the history.

### Custom port

The web UI uses port `8765` by default. Pass `--port` (or `-p`) to use a different one:

```bash
./transcribe.sh --port 9000      # macOS / Linux
transcribe.bat --port 9000       # Windows
```

If the port is already in use, the tool lists the next free ports at startup. Pick one by its number, type a port of your own, or press Enter to take the first suggestion.

Pass `--no-browser` to start the server without opening the browser.

### Manual

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install openai-whisper
pip install mlx-whisper    # only on Apple Silicon
python transcribe.py
```

## Engines

| Engine         | Runs on                                | Default model    |
|----------------|----------------------------------------|------------------|
| mlx-whisper    | Macs with Apple Silicon (GPU)          | `large-v3-turbo` |
| openai-whisper | macOS, Windows, Linux (CUDA, MPS, CPU) | `medium`         |

Both engines use the same Whisper models from OpenAI, so their results are comparable. When both are installed, mlx-whisper is the default. You can switch engines in the settings.

## Whisper Models

| Model          | Download | Quality     |
|----------------|----------|-------------|
| tiny           | ~75 MB   | Fast, basic |
| base           | ~140 MB  | Good        |
| small          | ~460 MB  | Better      |
| medium         | ~1.4 GB  | Very good   |
| large-v3-turbo | ~1.6 GB  | Best        |

A model is downloaded automatically the first time you use it. openai-whisper caches its models in `~/.cache/whisper`, mlx-whisper in `~/.cache/huggingface`. The Mac app keeps its models in its own data folder.

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

## Building the macOS app

```bash
packaging/macos/build.sh
```

This creates `dist/Transcribe.app` and `dist/Transcribe-<version>-arm64.dmg`. It needs a Mac with Apple Silicon, Python 3.12 or newer, and the Xcode Command Line Tools. The script

- installs the app dependencies into `build/venv` (mlx-whisper without PyTorch, see `packaging/macos/requirements.txt`),
- builds a minimal FFmpeg for audio decoding from source (`packaging/macos/build_ffmpeg.sh`; LGPL only, no GPL parts),
- packs everything with PyInstaller (`packaging/macos/Transcribe.spec`) and signs the app ad hoc.

The app entry point is `macos_app.py`. It starts the same server as `transcribe.py` and shows the UI in a native window using [pywebview](https://pywebview.flowrl.com).

### Releasing

1. Raise `VERSION` in `transcribe.py` and commit.
2. Tag and push:

   ```bash
   git tag v1.2.3
   git push origin main v1.2.3
   ```

The workflow `.github/workflows/release.yml` builds the app on GitHub Actions and publishes a release with the DMG and its SHA-256 checksum. It fails if the tag does not match `VERSION`. To build a test DMG without publishing, start the workflow manually under **Actions → macOS App → Run workflow**; the DMG is then attached to the run as an artifact.

## Troubleshooting

**`Warnung: ffmpeg wurde nicht gefunden` at startup**
ffmpeg is missing or not on your `PATH`, and transcriptions will fail. Install it with the command from [Requirements](#requirements) and start the tool again.

**`Port 8765 ist nicht verfügbar`**
Another program is using the port. Choose one of the suggested ports, or start with `--port` as described under [Custom port](#custom-port).

**The first transcription with a model takes much longer**
The model is being downloaded. Later runs use the cached copy.

**The engine selection is missing in the settings**
Only one engine is installed. On Apple Silicon, run `pip install mlx-whisper` in the virtual environment, or start `./transcribe.sh`, which installs it automatically. The Mac app always uses mlx-whisper only.

**The Mac app says it "is damaged and can't be opened"**
The download was modified or incomplete. Download the DMG again and compare its checksum with `SHA256SUMS.txt` from the release (`shasum -a 256 Transcribe-*.dmg`).

## License

[MIT](LICENSE)
