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

## v0.2.0 — Online SoundFont browser (shipped 2026-04-25)
- [x] **Online SoundFont browser** — search & install from public libraries inside the app
- [x] musical-artifacts.com provider (REST/JSON, license-aware, cached)
- [x] Provider abstraction so Reddit / GitHub / Polyphone can plug in
- [x] Streaming download with cancel + progress + post-download SF2 validation
- [x] Auto-switch to SF2 mode after install

## v0.3.0 — Self-contained install + more retro engines + more browser sources (shipped 2026-05-09)
- [ ] Bundle `fluidsynth.exe` (no `winget` requirement)
- [ ] PyInstaller one-file Windows binary
- [x] Auto-download FluidR3 GM on first run (uses the v0.2 browser plumbing)
  - Completed 2026-05-09: "Get FluidR3 GM…" button appears when no SoundFonts are installed, opening the browser pre-filled with "FluidR3 GM". BrowserDialog now accepts `initial_query` kwarg.
- [x] Per-preset dropdown with 5-second preview button
  - Completed 2026-04-25: SoundFont mode now parses `phdr` preset headers, exposes bank/program names in Advanced settings, and renders a five-second FluidSynth audition phrase for the selected preset.
- [x] Recent-soundfont MRU list in dropdown
  - Completed 2026-04-25: persists the last five used or installed `.sf2` / `.sf3` files and shows available matches first.
- [x] Drag-and-drop audio onto window
  - Completed 2026-04-25: accepts supported audio files anywhere on the main window and blocks drops during conversion.
- [x] **Game Boy DMG engine** — 4-voice variant (2 pulse, custom waveform, noise)
  - Completed 2026-04-25: Chiptune mode now offers a Game Boy DMG engine with two pulse channels, a 4-bit wave channel, noise, and the same mixer controls.
- [x] **SNES SPC700-style engine** — 8-voice with sample playback
  - Completed 2026-05-09: Multi-harmonic BRR waveforms (lead/harmony/bass), SNES-tuned ADSR envelopes, 4-tap Gaussian FIR warmth filter, vectorized multi-tap echo (delay/feedback/mix). 8-slot internal voice allocator merged into 4 mixer groups. Engine label "SNES SPC700" in the dropdown.
- [x] **Sega Genesis FM engine** — YM2612 6-channel FM synthesis
  - Completed 2026-05-09: 2-operator FM waveforms (feedback lead, 2:1 harmony, sub-modulator bass), YM2612-tuned ADSR envelopes, soft-saturation DAC clip model, 6-slot internal allocator (3 lead/2 harmony/1 bass) merged into 4 mixer groups. Engine label "Sega Genesis FM" in dropdown; voice labels update to FM Ch1-3/CH4-5/CH6/Rhythm.
- [x] Chiptune voice mixer in Advanced (per-voice volume, mute, solo)
  - Completed 2026-04-25: Advanced settings now control pulse 1, pulse 2, triangle, and noise voice volume/mute/solo before rendering.
- [x] **Reddit r/soundfonts** browser provider (trending community packs)
  - Completed 2026-04-26: Browser source selector now searches Reddit r/soundfonts top/search listings, surfaces score/comment context, installs direct SoundFont/archive URLs when present, and leaves discussion-only posts as open-in-browser leads.
- [x] **GitHub topic:soundfont** browser provider
  - Completed 2026-04-25: Browser source selector now searches GitHub repositories tagged `topic:soundfont`, shows license/star metadata, and downloads repositories as ZIP bundles.

## v0.4.0 — SoundFont editor (bundled)
- [ ] **Bundle Polyphone in installer** (GPL, ~25MB) — full SF2 editor, no external download
- [ ] *Edit SoundFont…* button — launches bundled Polyphone with current SF2 loaded
- [x] SoundFont metadata viewer (presets, banks, sample count) inside Tunerize
  - Completed 2026-04-25: `SoundFontInfo` now carries `sample_count` (from `shdr` chunk) and computed `bank_count`. A compact `sfMeta` label below the SF selector shows "N presets · N banks · N,NNN samples · X MB" on SF selection; hidden in chiptune mode. Single-pass `pdta` traversal reads both `phdr` and `shdr` in one file open.
- [x] Preset preview pane (play 5-sec arpeggio of selected preset)
  - Completed 2026-04-25: SoundFont mode parses `phdr` preset headers and renders a five-second FluidSynth audition phrase for the selected preset.

## v0.5.0 — Native SF2 creation
- [ ] Sample import (WAV → SF2 sample) — no external editor needed
- [ ] Multi-sample preset builder (key range mapping)
- [ ] Loop point editor
- [ ] ADSR envelope per preset
- [ ] SF2 export
- [ ] **"Convert chiptune voices to SF2"** — extract Tunerize's pulse/triangle/noise into a redistributable SF2

## v0.6.0 — Power-user features
- [x] Batch mode (folder of audio → folder of WAVs)
  - Completed 2026-05-09: `batch` CLI subcommand (`tunerize batch /dir --recursive --ext .wav,.flac --continue-on-error`) plus UI "Batch…" button. Shares all conversion args with `convert`. `_BatchWorker(QThread)` drives sequential processing with per-file progress signals. CLI respects `--ext` glob filter and `--continue-on-error`; exit code 1 if any file fails.
- [x] MP3 / OGG / FLAC output options
  - Completed 2026-05-09: format combo (WAV/FLAC/OGG/MP3) added to output row. Pipeline transcodes from intermediate WAV using soundfile (FLAC/OGG) or bundled ffmpeg via imageio-ffmpeg (MP3). `output_format` field on `PipelineConfig`; validated in `__post_init__`. `SUPPORTED_OUTPUT_FORMATS` constant in `audio_io.py`. `transcode_wav()` helper.
- [ ] Genre presets (chiptune, lo-fi, orchestral, etc.) — bundles SF2 + cleanup settings
- [x] CLI mode (`tunerize convert input.mp3 --sf2 nes.sf2 -o out.wav`)
  - Completed 2026-05-09: `app/core/cli.py` with `run_cli(argv)` entry point; `_is_cli_invocation()` in `main.py` dispatches to CLI when first positional arg is `convert` or `batch`. Full argparse interface: `--sf2`, `--engine`, `--format`, `--transpose`, `--quantize`, `--stem-separate`, `--no-midi`, `--min-note-ms`, `--sample-rate`, `--preset`, `--bank`, `--force-preset`. Progress bar to stdout; structured exit codes (0/1/130).
- [ ] Per-track multi-channel output (one SF2 per stem)

## Backlog (no version yet)
- VST3 plugin host integration
- Real-time monitoring / preview during render
- macOS / Linux first-class builds (CI artifacts)
- ONNX-only optimization pass for ~50% smaller bundle
