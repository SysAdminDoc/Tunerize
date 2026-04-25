# Changelog

All notable changes to Tunerize are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [Semantic Versioning](https://semver.org/).

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
