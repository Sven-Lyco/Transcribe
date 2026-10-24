# Transcribe

Transcribe turns audio files, such as WhatsApp voice messages, into text on your own computer. It uses [OpenAI Whisper](https://github.com/openai/whisper) and has a small web interface. No API key, no account, no upload.

On Macs with Apple Silicon it uses [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), which runs Whisper on the GPU and is much faster. Everywhere else it uses [openai-whisper](https://github.com/openai/whisper).

There are two ways to use it:

- **Mac app** for Apple Silicon: download, drag into Applications, done.
- **Script** for macOS, Windows, and Linux: runs a local server and opens the interface in your browser.

## Features

- Drag and drop common audio formats: OGG/Opus (WhatsApp), MP3, M4A/AAC, WAV, FLAC, AIFF, WebM; several files at once are transcribed one after another
- Progress bar while transcribing and while the model downloads, with a button to cancel
- Spoken language German, English, or detected automatically
- Optional speaker name and a timestamp taken from the file name (WhatsApp format) at the start of the text
- History of all transcriptions with search, copy, edit, and delete; each one is saved as a `.txt` file
- Playback of the original recording with the sentence being spoken highlighted; click a sentence to jump there
- Interface in English and German, light or dark following your system
- Mac app: open audio files with **Open With** or by dropping them on the Dock icon, a notification when a transcription is done, and a hint when a new version is out
- GPU acceleration where available (Apple Silicon via MLX or MPS, NVIDIA via CUDA), otherwise the CPU

## Mac app

For **Apple Silicon (M1 or newer) with macOS 14 Sonoma or later**. No Python, Terminal, or ffmpeg needed.

1. Download `Transcribe-<version>-arm64.dmg` from the [latest release](https://github.com/Sven-Lyco/Transcribe/releases/latest) and open it.
2. Drag **Transcribe** into **Applications**.
3. Open Transcribe. The app is not notarized by Apple, so macOS blocks it the first time ("Apple could not verify …"). Click **Done**, open **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to Transcribe. This is needed only once.
4. Drop an audio file into the window and click **Start**.

The first transcription downloads the Whisper model (about 1.5 GB). On Intel Macs, use the [script](#script-macos-windows-linux).

You can also right-click an audio file in Finder and choose **Open With → Transcribe**, or drop it on Transcribe's Dock icon; the file is then selected in the window. Transcribe never makes itself the default app for audio files.

When a transcription finishes while Transcribe is in the background, it shows a notification. macOS asks for permission the first time; you can change it later in **System Settings → Notifications → Transcribe**.

### Uninstalling the app

macOS does not remove an app's data when you move the app to the Trash. To remove everything:

1. In Transcribe, open the settings (⚙︎) and click **Delete all app data …**. This deletes all transcriptions, the history, and the downloaded model.
2. Quit Transcribe and move it from **Applications** to the Trash.

macOS also keeps a few hundred KB of window data (the settings) in `~/Library/WebKit` and `~/Library/Caches`, each in a folder named after the app's bundle identifier, which ends in `.transcribe`. You can delete these two folders too.

## Script (macOS, Windows, Linux)

### Requirements

- Python 3.10 or newer
- [ffmpeg](https://ffmpeg.org/) for reading audio files:

  | System  | Command                       |
  |---------|-------------------------------|
  | macOS   | `brew install ffmpeg`         |
  | Windows | `winget install Gyan.FFmpeg`  |
  | Linux   | `sudo apt install ffmpeg`     |

### Starting

```bash
git clone https://github.com/Sven-Lyco/Transcribe.git
cd Transcribe
./transcribe.sh        # macOS / Linux
transcribe.bat         # Windows (or double-click the file)
```

On the first run, the script creates a virtual environment in `.venv` and installs Whisper together with PyTorch, plus mlx-whisper on Apple Silicon. This is a large download and can take several minutes. An existing `.venv` created with Python older than 3.10 is replaced automatically.

The script then starts a local server and opens `http://127.0.0.1:8765` in your browser. Press `Ctrl+C` in the terminal to stop it.

Options:

- `--port 9000` (or `-p 9000`) uses another port. If the port is taken, the script lists free ports to choose from.
- `--no-browser` starts the server without opening the browser.

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install openai-whisper
pip install mlx-whisper    # only on Apple Silicon
python transcribe.py
```

## Using Transcribe

1. Drop one or more audio files anywhere onto the window, or click the drop area to choose them. ✕ removes a file from the selection.
2. Optional: open the settings (⚙︎, or **change** below the start button) to pick the engine, the **Model**, the **Spoken language**, and, in the script, an **Output folder**. These settings are remembered, including the model for each engine.
3. Optional: enter a name under **Who is speaking?**. It is put in front of the text.
4. Click **Start**. Several files are transcribed one after another in the order shown; each waiting file shows how many are ahead of it.

To stop a transcription, click **Cancel** below its progress bar. Whisper works through the audio in sections of about 30 seconds, so a running transcription stops at the end of the current section.

The result appears in the **History** and is saved as a `.txt` file named after the audio file. An existing `.txt` with the same name is overwritten. Deleting an entry in the history also deletes its `.txt` file, and a file you delete in Finder or Explorer disappears from the history. The search field above the history filters by text and file name.

To correct a transcription, click **Edit** on its card, change the text, and click **Save** (or press Cmd/Ctrl+Enter; Esc cancels). The change is saved to the `.txt` file. Sentences you changed are no longer highlighted during playback; the others still are.

To listen to a transcription, click ▶ on its card. The sentence being spoken is highlighted; click any sentence or the progress bar to jump there. Transcriptions made before version 1.1.0 have no playback, because their audio was not kept.

**Language and appearance:** the interface, the terminal, and the log follow your system language: German on a German system, English otherwise. You can switch the interface under **App language** in the settings. Light or dark follows your system setting.

## Where your data is stored

Settings (⚙︎) → **Open folder** shows the transcriptions in Finder or Explorer.

**Mac app:** everything lives in `~/Library/Application Support/Transcribe`:

| Folder or file                | Content                                              |
|-------------------------------|------------------------------------------------------|
| `Transcripts/`                | The transcriptions as `.txt` files                   |
| `Transcripts/.history.json`   | History with date, duration, and sentence timing     |
| `Transcripts/.audio/`         | The original recordings for playback                 |
| `huggingface/`                | Downloaded Whisper models                            |
| `cache/`                      | Compiled code cache, if one is needed                |
| `transcribe.log`              | Log file                                             |

Versions up to 1.1.0 used German names (`Transkripte/`, `.verlauf.json`). They are renamed automatically the first time a newer version starts.

**Script:** transcriptions go to the `transcriptions/` folder in the project, with the same `.history.json` and `.audio/` inside. To save elsewhere, enter the full path of an existing folder under **Output folder** (`~` is supported); the history then also lists the files saved there. openai-whisper keeps its models in `~/.cache/whisper`, mlx-whisper in `~/.cache/huggingface`.

## Privacy

- Audio files and transcriptions never leave your computer. For playback, the original recording is kept next to its transcription and deleted together with it.
- The interface is served on `127.0.0.1` only, so other devices on your network cannot reach it. Requests coming from other websites are rejected. Like any local server without a login, it can be reached by other user accounts on the same computer.
- The page loads no external resources: no fonts, scripts, or analytics.
- An internet connection is needed only to install the dependencies (script) and to download each Whisper model the first time you use it.
- The Mac app asks GitHub once at startup whether a newer version exists (`api.github.com`). Nothing about your recordings is sent. Turn it off in the settings under **Check for updates at startup**.

## Engines and models

| Engine         | Runs on                                | Default model |
|----------------|----------------------------------------|---------------|
| mlx-whisper    | Macs with Apple Silicon (GPU)          | `medium`      |
| openai-whisper | macOS, Windows, Linux (CUDA, MPS, CPU) | `medium`      |

Both engines use the same Whisper models from OpenAI, so their results are comparable. When both are installed, mlx-whisper is the default; the settings show an engine selection. The Mac app always uses mlx-whisper.

| Model          | Download | Quality                     |
|----------------|----------|-----------------------------|
| tiny           | ~75 MB   | Fast, basic                 |
| base           | ~140 MB  | Good                        |
| small          | ~460 MB  | Better                      |
| medium         | ~1.5 GB  | Very good (default)         |
| large-v3-turbo | ~1.6 GB  | Very good, newer and faster |

A model is downloaded automatically the first time you use it.

## Output format

The text can start with a timestamp and a speaker name. The timestamp is taken from the file name if it contains `YYYY-MM-DD at HH.MM.SS`, as WhatsApp audio files do.

| Speaker name | Timestamp in file name | Output                                        |
|--------------|------------------------|-----------------------------------------------|
| yes          | yes                    | `2026-08-12 - 09.49.50 - Speaker Name: Text…` |
| yes          | no                     | `Speaker Name: Text…`                         |
| no           | yes                    | `2026-08-12 - 09.49.50: Text…`                |
| no           | no                     | `Text…`                                       |

For example, `WhatsApp Audio 2026-08-12 at 09.49.50.ogg` becomes `WhatsApp Audio 2026-08-12 at 09.49.50.txt`:

```text
2026-08-12 - 09.49.50 - Speaker Name: Transcribed text appears here.
```

## Troubleshooting

**`Warning: ffmpeg was not found`** (German: `Warnung: ffmpeg wurde nicht gefunden`)
ffmpeg is missing or not on your `PATH`, and transcriptions will fail. Install it as shown under [Requirements](#requirements) and start the script again.

**`Port 8765 is not available`** (German: `Port 8765 ist nicht verfügbar`)
Another program is using the port. Choose one of the suggested ports, or start with `--port`.

**The first transcription with a model takes much longer**
The model is being downloaded. Later runs use the downloaded copy.

**There is no engine selection in the settings**
Only one engine is installed. On Apple Silicon, start `./transcribe.sh`, which installs mlx-whisper, or run `pip install mlx-whisper` in the virtual environment.

**The Mac app says it "is damaged and can't be opened"**
The download was modified or incomplete. Download the DMG again and compare its checksum with `SHA256SUMS.txt` from the release (`shasum -a 256 Transcribe-*.dmg`).

## Development

### Running the tests

```bash
python3 -m unittest discover -s tests
```

Run this in the project folder. The tests need no extra packages, not even Whisper. GitHub Actions runs them on every push and pull request.

### Building the Mac app

```bash
packaging/macos/build.sh
```

This creates `dist/Transcribe.app` and `dist/Transcribe-<version>-arm64.dmg`. It needs a Mac with Apple Silicon, Python 3.12 or newer, and the Xcode Command Line Tools. The script

- installs the app's dependencies into `build/venv` (mlx-whisper without PyTorch, see `packaging/macos/requirements.txt`),
- builds a minimal FFmpeg for reading audio from source (`packaging/macos/build_ffmpeg.sh`; LGPL only, no GPL parts),
- collects the license texts of all bundled components (`packaging/macos/collect_licenses.py`),
- packs everything with PyInstaller (`packaging/macos/Transcribe.spec`) and signs the app ad hoc.

The app's entry point is `macos_app.py`. It starts the same server as `transcribe.py` and shows the interface in a native window using [pywebview](https://pywebview.flowrl.com).

### Releasing

1. Raise `VERSION` in `transcribe.py` and add a section for the new version to `CHANGELOG.md`; commit both.
2. Tag and push:

   ```bash
   git tag v1.2.3
   git push origin main v1.2.3
   ```

The workflow `.github/workflows/release.yml` builds the app on GitHub Actions and publishes a release with the DMG, the FFmpeg source code it was built from (required by the LGPL), and their SHA-256 checksums. The release notes start with the version's section from `CHANGELOG.md`, followed by the download instructions from `packaging/macos/release-notes.md`. The workflow fails if the tag does not match `VERSION` or the changelog has no section for it.

To build a test DMG without publishing, start the workflow manually under **Actions → macOS App → Run workflow**; the DMG is then attached to the run as an artifact.

## Security

Please report security problems privately, as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). The Mac app bundles third-party software under its own licenses, listed in [THIRD_PARTY_NOTICES.md](packaging/macos/THIRD_PARTY_NOTICES.md).
