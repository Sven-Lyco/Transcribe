# Transcribe

A local, privacy-first audio transcription tool powered by [OpenAI Whisper](https://github.com/openai/whisper). No API key, no internet connection required after setup — everything runs on your machine.

## Features

- Drag & drop audio files (OGG, MP3, WAV, M4A, OPUS, WebM)
- Real-time progress bar during transcription
- Language selection (German, English, auto-detect)
- Optional speaker name prefix in output
- Timestamp extracted automatically from filename (WhatsApp format supported)
- Saves transcription as `.txt` next to the audio file or in a custom folder
- Works on macOS, Windows, and Linux
- GPU acceleration when available (CUDA / Apple Silicon MPS), CPU fallback otherwise

## Requirements

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) (for audio decoding)

## Setup & Usage

### macOS / Linux

```bash
./transcribe.sh
```

The script creates a virtual environment, installs dependencies on first run, and opens the web UI at `http://localhost:8765`.

### Windows

Double-click `transcribe.bat` or run:

```bat
transcribe.bat
```

### Manual

```bash
pip install openai-whisper
python transcribe.py
```

## Whisper Models

| Model  | Size    | Quality        |
|--------|---------|----------------|
| tiny   | ~39 MB  | Fast, basic    |
| base   | ~74 MB  | Good           |
| small  | ~244 MB | Better         |
| medium | ~769 MB | Best (default) |

Models are downloaded automatically on first use.

## Output Format

Transcriptions are saved as `.txt` files. If a speaker name is entered and the filename contains a timestamp (WhatsApp audio format), the output is prefixed with date, time, and name:

**Input filename:**
```
WhatsApp Audio 2026-08-12 at 09.49.50.ogg
```

**Output (`WhatsApp Audio 2026-08-12 at 09.49.50.txt`):**
```
2026-08-12 - 09.49.50 - Speaker Name: Transcribed text appears here.
```
