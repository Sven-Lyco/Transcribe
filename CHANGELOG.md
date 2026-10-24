# Changelog

Changes to Transcribe, newest first. Each version matches a release tag `vX.Y.Z`; the release workflow copies the section of the tagged version into the GitHub release notes.

## [1.2.0] – 2026-10-24

### New
- Transcribe is available in English and German. It follows the system language; you can switch it in the settings (⚙︎) under **App language**. Messages in the terminal and in the log file follow the system language too.

### Changed
- App data folders and files have English names: `Transkripte` is now `Transcripts`, and the history index `.verlauf.json` is now `.history.json`. Existing data is moved automatically on the first start.
- The Mac app includes the license texts of all bundled components (`Transcribe.app/Contents/Resources/licenses`), and each release also provides the source code of the bundled FFmpeg.
- Files larger than 2 GB are rejected instead of being read into memory.
- Clearer interface: larger settings button and playback controls, settings grouped into *Transcription* and *App*, the speaker field is labeled *Who is speaking?*, and Copy and Delete sit apart on each card.
- An audio file dropped anywhere in the window is picked up; before, the window opened the file itself and the app disappeared.
- Keyboard: Escape closes the settings, and the arrow keys move the playback position.

### Fixed
- Long folder paths no longer make the page wider than the window.

## [1.1.0] – 2026-10-23

### New
- Play back the original voice message from the history. The sentence being spoken is highlighted while it plays; click a sentence or the progress bar to jump there.

### Notes
- The original audio file is now kept next to its transcription (WhatsApp voice messages typically take about 100–250 KB per minute) and deleted together with it.
- Transcriptions made with earlier versions have no playback, because their audio was not kept.
- Transcription now also computes word timings so the highlighting matches the audio closely (usually within 0.2 seconds). This makes it take about twice as long.

## [1.0.2] – 2026-10-23

### Changed
- mlx-whisper now uses the `medium` model by default, which gave the best results for voice messages. If the app remembered `large-v3-turbo`, switch to `medium` once in the settings (⚙︎).

## [1.0.1] – 2026-10-23

### New
- An ✕ next to the selected file removes it before starting.
- Settings (⚙︎): `Ordner öffnen` shows the transcriptions in Finder; `Alle App-Daten löschen …` removes transcriptions, history, and downloaded models before uninstalling.

### Changed
- All app data now lives in `~/Library/Application Support/Transcribe` instead of `~/Documents/Transkripte`.
- The history shows the saved `.txt` files. Deleting an entry deletes its file, and files deleted in Finder disappear from the history within a few seconds. History export and import were removed.

### Fixed
- A notice appears when the app's background server cannot be reached, and failed deletions show an error instead of doing nothing.
- The app now quits completely when its window is closed.

## [1.0.0] – 2026-10-23

First release of the Mac app for Apple Silicon (macOS 14 or later):

- Native window; transcription with mlx-whisper on the GPU, no Python, Terminal, or ffmpeg needed.
- History of transcriptions with copy and delete, cancel button for running transcriptions.
- Everything stays on your Mac.
