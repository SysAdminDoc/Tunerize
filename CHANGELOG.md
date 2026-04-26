# Changelog

All notable changes to Tunerize are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow [Semantic Versioning](https://semver.org/).

## v0.4.0 — 2026-05-09

SoundFont metadata viewer with live preset/bank/sample stats.

### Added
- **SoundFont metadata label** — compact status line below the SoundFont selector showing preset count, bank count, sample count, and file size (e.g., "128 presets · 3 banks · 1,024 samples · 8.2 MB"). Reads the `shdr` chunk from the SF2 binary so sample count is always accurate. Hidden automatically when switching to chiptune mode.

### Changed
- `SoundFontInfo` now carries `sample_count` (parsed from the `shdr` chunk) and a computed `bank_count` property.
- SF2 parser refactored to traverse the `pdta` LIST sub-chunks in a single file-open pass, reading both `phdr` and `shdr` together instead of two separate reads.



More retro engines, smarter SoundFont onboarding, and a deeper chiptune voice model.

### Added
- **Sega Genesis YM2612 FM engine** — 6-channel FM synthesis model with 2-operator FM waveforms (self-modulating feedback lead, 2:1 ratio harmony, sub-modulator bass), per-engine ADSR envelopes tuned to Genesis brass/electric-piano/slap-bass patches, a soft-saturation post-filter modelling the YM2612 9-bit DAC distortion characteristic, and a 6-slot internal voice allocator (3 lead / 2 harmony / 1 bass) merged into 4 mixer groups. Selected via the new "Sega Genesis FM" entry in the engine dropdown; voice labels update to FM Ch1-3/CH4-5/CH6/Rhythm.
- **SNES SPC700-style chiptune engine** — 8-voice BRR-sample model with multi-harmonic sine waveforms (lead/harmony/bass voice layers), per-engine ADSR envelopes tuned to SNES instrument recordings, a 4-tap Gaussian FIR warmth filter matching the SPC700 DSP interpolation table, and a vectorized multi-tap echo approximating the SPC700 echo buffer with configurable delay, feedback, and mix level. Selected via the new "SNES SPC700" entry in the engine dropdown.
- **FluidR3 GM quick-download button** — a "Get FluidR3 GM…" button appears in the SoundFont row when no SoundFonts are installed, opening the online browser pre-filled with "FluidR3 GM" so new users can get a great default SoundFont in two clicks.
- Drag-and-drop audio selection on the main window for all supported input formats.
- Recent SoundFont persistence: the last five used or installed `.sf2` / `.sf3` files appear first in the SoundFont dropdown when still present in the local library.
- Chiptune voice mixer in Advanced settings with per-voice volume, mute, and solo controls for pulse 1, pulse 2, triangle, and noise.
- Game Boy DMG chiptune engine option with two pulse voices, a 4-bit custom wave channel, and noise.
- GitHub `topic:soundfont` browser source with license-aware repository results and ZIP bundle downloads.
- SoundFont preset dropdown parsed from `.sf2` / `.sf3` preset headers, plus a five-second FluidSynth preview button.
- Reddit r/soundfonts browser source for community leads, direct `.sf2` / archive links, and discussion-only results that open in the browser.

### Changed
- Conversion now locks input/settings controls while work is running and treats user cancellation as a normal stopped state instead of a critical failure dialog.
- Main-window and browser table styling tightened for clearer grouping, focus, and selected states.
- SoundFont rendering starts from the selected bank/program, and force-preset mode now uses that selected bank/program instead of a preset-number-only spinbox.
- Browser details now escape provider text before rendering HTML and disable install for discovery-only rows without a direct download URL.
- `BrowserDialog` now accepts an `initial_query` keyword argument to pre-fill the search bar and run an automatic first search on open.

## v0.2.0 — 2026-04-25

Online SoundFont discovery — search public libraries from inside the app.

### Added
- **Online SoundFont browser** — modal dialog (`Browse Online…` button next to the SoundFont dropdown) that searches public libraries and installs straight into `soundfonts/`.
  - First provider: **musical-artifacts.com** (REST/JSON API, per-artifact license metadata, direct file URLs, 60 req/min cached).
  - Provider abstraction in [app/core/soundfont_browser.py](app/core/soundfont_browser.py) — additional sources can drop in without UI rewrites.
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
