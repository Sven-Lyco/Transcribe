# Changelog

Changes to Transcribe, newest first. Each version matches a release tag `vX.Y.Z`; the release workflow copies the section of the tagged version into the GitHub release notes.

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
