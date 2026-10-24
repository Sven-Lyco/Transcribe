## Download

**Transcribe for macOS** – requires a Mac with Apple Silicon (M1 or newer) and macOS 14 Sonoma or later.

1. Download the `.dmg` file below and open it.
2. Drag **Transcribe** into **Applications**.
3. Open Transcribe. Because the app is not notarized by Apple, macOS blocks it the first time ("Apple could not verify …"). Click **Done**, then go to **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to Transcribe. This is needed only once.
4. Drop an audio file (for example a saved WhatsApp voice message) into the window.

The first transcription downloads the Whisper model (about 1.5 GB). All transcriptions appear in the history in the window and are saved as `.txt` files in `~/Library/Application Support/Transcribe/Transcripts` (⚙︎ → **Open folder**). Everything runs on your Mac; no audio is uploaded anywhere. The app is in English or German, following your system language.

**Uninstalling:** macOS keeps app data when you trash an app. Before deleting Transcribe, click ⚙︎ → **Delete all app data …** to remove transcriptions, history, and the downloaded model.

`ffmpeg-*.tar.xz` is the source code of the FFmpeg included in the app, provided as required by its license (LGPL).
