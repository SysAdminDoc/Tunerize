# Changelog

All notable changes to Tunerize are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Added
- Drag-and-drop audio selection on the main window for all supported input formats.
- Recent SoundFont persistence: the last five used or installed `.sf2` / `.sf3` files appear first in the SoundFont dropdown when still present in the local library.
- Chiptune voice mixer in Advanced settings with per-voice volume, mute, and solo controls for pulse 1, pulse 2, triangle, and noise.
- Game Boy DMG chiptune engine option with two pulse voices, a 4-bit custom wave channel, and noise.

### Changed
- Conversion now locks input/settings controls while work is running and treats user cancellation as a normal stopped state instead of a critical failure dialog.
- Main-window and browser table styling tightened for clearer grouping, focus, and selected states.

## v0.2.0 — 2026-04-25

Online SoundFont discovery — search public libraries from inside the app.

### Added
- **Online SoundFont browser** — modal dialog (`Browse Online…` button next to the SoundFont dropdown) that searches public libraries and installs straight into `soundfonts/`.
  - First provider: **musical-artifacts.com** (REST/JSON API, per-artifact license metadata, direct file URLs, 60 req/min cached).
  - Provider abstraction in [app/core/soundfont_browser.py](app/core/soundfont_browser.py) — Reddit r/soundfonts trending and a GitHub `topic:soundfont` provider can drop in next without UI changes.
- Per-result detail pane: name, author, license, size, tags, description, link to source web page.
- Streaming download with cancel + progress (bytes / total or indeterminate).
- Post-download SF2 validation (RIFF/sfbk header check) — corrupt downloads are rejected before they enter the library.
- Local response cache (`~/.tunerize/browser-cache/`) — searches stay snappy and keep us under the rate limit.
- Auto-switches main UI to SoundFont mode when a freshly-installed SF2 is selected.
- Bumped HTTP requirement: `requests>=2.31`.

### Changed
- README, ROADMAP, repo CLAUDE.md updated to reflect browser as the v0.2.0 headline.

## v0.1.0 — 2026-04-25

Initial release. End-to-end MVP: audio in, retro-style audio out.

### Added
- **Built-in chiptune engine** — NES APU-style synth (2 pulse + triangle + noise) with pitch-aware voice allocation and note stealing. Zero external dependencies; works without any SoundFont installed.
- **Render mode toggle** — Chiptune Mode vs SoundFont Mode in the main UI.
- PySide6 desktop UI with dark Catppuccin Mocha theme.
- Audio file picker (MP3, WAV, FLAC, OGG via `soundfile` + `imageio-ffmpeg`).
- SoundFont library scan from `soundfonts/` folder; runtime *Add SoundFont…* import.
- SF2 validation (RIFF header check) and basic metadata read.
- Spotify Basic Pitch transcription (audio → MIDI), ONNX backend.
- MIDI cleanup pass: tiny-note removal, velocity normalization, optional transpose, optional quantize.
- FluidSynth rendering (MIDI + SF2 → WAV) with sample-accurate event scheduling.
- Optional Demucs stem separation pre-pass for mixed audio.
- Background `QThread` worker — UI stays responsive during long conversions.
- Progress states: Loading → Stem-split (optional) → Transcribing → Cleaning → Rendering → Writing.
- Configurable output folder; default = same directory as input.
- Output naming: `<song>__chiptune.wav` (chiptune mode) or `<song>__<soundfont>.wav` (SF2 mode).
- Force-preset mode for non-GM SoundFonts.
- Advanced settings panel (collapsible).
- Comprehensive error handling with toast + log-panel feedback.
- Unit tests for `midi_cleanup`, `soundfonts`, `chiptune`, and `pipeline` orchestration.
