# Transcribe

A local audio transcription tool with a small web UI, powered by [OpenAI Whisper](https://github.com/openai/whisper). Audio is transcribed on your own machine: no API key, no account, no upload.

> **Note:** The web UI and the console messages are in German. The steps below name the German labels you will see.

## Features

- Drag & drop audio files (OGG, MP3, WAV, M4A, OPUS, WebM)
- Real-time progress bar during transcription
- Language selection (German, English, auto-detect)
- Optional speaker name prefix in output
- Timestamp extracted automatically from filename (WhatsApp format supported)
- Saves each transcription as a `.txt` file in `transcriptions/` or in a folder of your choice
- Works on macOS, Windows, and Linux
- GPU acceleration when available (CUDA / Apple Silicon MPS), CPU fallback otherwise

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

On the first run the script creates a virtual environment in `.venv` and installs Whisper together with PyTorch. This is a large download and can take several minutes.

The script then starts a local server and opens the web UI at `http://127.0.0.1:8765`. Press `Ctrl+C` in the terminal to stop it.

### Transcribing a file

1. Drop an audio file onto the page, or click the drop area to choose one.
2. Pick a model (`Modell`) and the spoken language (`Sprache`).
3. Optional: enter a speaker name (`Name`) and an output folder (`Ausgabeordner`).
4. Click `Starten`.

The result appears on the page and is saved as a `.txt` file named after the audio file. By default it goes to the `transcriptions/` folder inside the project directory. To save it elsewhere, enter the full path of an existing folder in `Ausgabeordner` (`~` is supported). An existing `.txt` with the same name is overwritten.

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

## Troubleshooting

**`Warnung: ffmpeg wurde nicht gefunden` at startup**
ffmpeg is missing or not on your `PATH`, and transcriptions will fail. Install it with the command from [Requirements](#requirements) and start the tool again.

**`Port 8765 ist nicht verfügbar`**
Another program is using the port. Choose one of the suggested ports, or start with `--port` as described under [Custom port](#custom-port).

**The first transcription with a model takes much longer**
The model is being downloaded. Later runs use the cached copy.

## License

[MIT](LICENSE)
