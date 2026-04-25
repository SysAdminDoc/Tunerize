# Tunerize Roadmap

## v0.1.0 — MVP (shipped 2026-04-25)
- [x] PySide6 UI with dark theme
- [x] Basic Pitch audio → MIDI transcription
- [x] FluidSynth MIDI + SF2 → WAV rendering
- [x] **Built-in chiptune engine (NES-style: 2 pulse + triangle + noise)**
- [x] Render mode toggle (Chiptune vs SoundFont)
- [x] SoundFont library scan + validation
- [x] Background worker (no UI freeze)
- [x] Progress reporting + log panel
- [x] Demucs stem separation toggle
- [x] MIDI export
- [x] Force-preset mode
- [x] Unit tests for cleanup / soundfonts / chiptune / pipeline

## v0.2.0 — Self-contained install + more retro engines
- [ ] Bundle `fluidsynth.exe` (no `winget` requirement)
- [ ] PyInstaller one-file Windows binary
- [ ] Auto-download a default SoundFont (FluidR3 GM) on first run
- [ ] Per-preset dropdown with 5-second preview button
- [ ] Recent-soundfont MRU list in dropdown
- [ ] Drag-and-drop audio onto window
- [ ] **Game Boy DMG engine** — 4-voice variant (2 pulse, custom waveform, noise)
- [ ] **SNES SPC700-style engine** — 8-voice with sample playback
- [ ] **Sega Genesis FM engine** — YM2612 6-channel FM synthesis
- [ ] Chiptune voice mixer in Advanced (per-voice volume, mute, solo)

## v0.3.0 — SoundFont editor (bundled)
- [ ] **Bundle Polyphone in installer** (GPL, ~25MB) — full SF2 editor, no external download
- [ ] *Edit SoundFont…* button — launches bundled Polyphone with current SF2 loaded
- [ ] SoundFont metadata viewer (presets, banks, sample count) inside Tunerize
- [ ] Preset preview pane (play 5-sec arpeggio of selected preset)

## v0.4.0 — Native SF2 creation
- [ ] Sample import (WAV → SF2 sample) — no external editor needed
- [ ] Multi-sample preset builder (key range mapping)
- [ ] Loop point editor
- [ ] ADSR envelope per preset
- [ ] SF2 export
- [ ] **"Convert chiptune voices to SF2"** — extract Tunerize's pulse/triangle/noise into a redistributable SF2

## v0.5.0 — Power-user features
- [ ] Batch mode (folder of audio → folder of WAVs)
- [ ] MP3 / OGG / FLAC output options
- [ ] Genre presets (chiptune, lo-fi, orchestral, etc.) — bundles SF2 + cleanup settings
- [ ] CLI mode (`tunerize convert input.mp3 --sf2 nes.sf2 -o out.wav`)
- [ ] Per-track multi-channel output (one SF2 per stem)

## Backlog (no version yet)
- VST3 plugin host integration
- Real-time monitoring / preview during render
- macOS / Linux first-class builds (CI artifacts)
- ONNX-only optimization pass for ~50% smaller bundle
