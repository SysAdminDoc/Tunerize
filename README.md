# Tunerize

[![Version](https://img.shields.io/badge/version-0.4.1-blue?style=flat-square)](https://github.com/SysAdminDoc/Tunerize/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows)](https://www.microsoft.com/windows)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Built with PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)

**Re-render any audio as chiptune — or through any SoundFont you choose.** Drop in an MP3 or WAV, pick **Chiptune Mode** (built-in retro synths, zero setup) or any `.sf2` (piano, brass, SC-55, anything), and get back a WAV in that style.

Tunerize does the full pipeline locally: audio → MIDI (via Spotify Basic Pitch) → cleaned MIDI → render. Two render paths:
- **Chiptune engine** (built-in) — three chip models: **NES APU-style** (2 pulse + triangle + noise), **Game Boy DMG** (2 pulse + 4-bit wave + noise), and **SNES SPC700-style** (8 voices with multi-harmonic waveforms, Gaussian warmth filter, and echo). No SoundFont needed.
- **SoundFont engine** (FluidSynth) — anything `.sf2` you can find.

One window, one button, no cloud.

![Tunerize banner](assets/banner.png)

---

## Features

- **Built-in chiptune engines** — NES-style (2 pulse + triangle + noise) and Game Boy DMG-style (2 pulse + custom wave + noise) synths ship in the app. Zero install, instant retro.
- **Online SoundFont browser** — search and install SF2s from public libraries (musical-artifacts.com, GitHub `topic:soundfont`, and Reddit r/soundfonts leads) without leaving the app. License + author shown for every result.
- **Bring-your-own SoundFonts** — Drop `.sf2` / `.sf3` into `soundfonts/`; Tunerize scans, validates, lists them, and keeps your recent picks at the top.
- **Preset-aware SoundFont workflow** — Tunerize reads bank/program names from `.sf2` / `.sf3` files, lets you choose a preset, and can render a short preview before conversion.
- **Drag-and-drop input** — Drop supported audio files directly on the window, or use the file picker.
- **One-click conversion** — Open audio, pick mode, hit Convert. WAV out.
- **Stem separation (optional)** — Pre-split mixed tracks with Demucs for cleaner transcription on full songs.
- **MIDI export** — Keep the intermediate `.mid` for use elsewhere.
- **MIDI cleanup** — Quantize, remove tiny artifacts, normalize velocity, transpose. All defaults sane; tweak in Advanced.
- **Chiptune voice mixer** — Pick the chip engine, then adjust, mute, or solo the built-in pulse, triangle/wave, and noise voices before rendering.
- **Force-preset mode** — For non-GM SoundFonts, force every note through one preset.
- **Background worker** — UI never freezes during long conversions.
- **Dark by default** — Catppuccin Mocha theme.

---

## Install (from source)

### Prerequisites

- **Python 3.11 or 3.12** (3.13 may work but is not yet validated against `basic-pitch` ONNX)
- **FluidSynth** — *only required for SoundFont mode when running from source*; Chiptune Mode works without it, and the Windows packaged EXE bundles the FluidSynth runtime.
  - Windows source/dev: `winget install FluidSynth.FluidSynth` *or* download from [fluidsynth.org](https://www.fluidsynth.org/) and put `fluidsynth.exe` on PATH
  - macOS: `brew install fluid-synth`
  - Linux: `sudo apt install fluidsynth` (or distro equivalent)
- **FFmpeg** (MP3 decoding) — bundled via `imageio-ffmpeg`; no separate install needed

### Setup

```bash
git clone https://github.com/SysAdminDoc/Tunerize.git
cd Tunerize
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
python -m app.main
```

### Get some SoundFonts

Three options:

1. **Use the built-in browser** *(easiest)* — Open Tunerize, switch to SoundFont mode, click **Browse Online…**. Searches musical-artifacts.com, GitHub `topic:soundfont`, and Reddit r/soundfonts leads. Direct `.sf2` / `.sf3` / archive links download in one click; GitHub repositories are saved as ZIP bundles; Reddit discussion-only results open in your browser for review.
2. **Drop your own** into `soundfonts/` (`.sf2` / `.sf3`). Restart or hit ↻ to re-scan.
3. **Recommended grabs**:
   - **FluidR3 GM** (MIT, the FluidSynth default, ~140MB) — search the browser for "FluidR3"
   - **GeneralUser GS** (CC BY-SA, full GM bank, ~30MB) — search "GeneralUser"
   - **8-bit / NES** — search "NES" or "chiptune"
   - **SC-55 / SC-88** — Roland synth recreations

---

## Usage

1. **Open Audio** — pick or drop an MP3, WAV, FLAC, OGG, M4A, AIFF, or AIF.
2. **Choose render mode**:
   - **Chiptune Mode** — uses the built-in NES-style synth. No SoundFont required.
   - **SoundFont Mode** — pick a `.sf2` from the dropdown, click *Add…* to import one from disk, or click **Browse Online…** to grab one from a public library. Recently installed or used SoundFonts appear first.
3. *(Optional)* In **Advanced**, choose a SoundFont preset and click **Preview** to audition a five-second phrase. Enable **Force all notes to selected preset** for non-GM banks.
4. *(Optional)* Toggle **Stem separation** if your input is a mixed song.
5. *(Optional)* Open **Advanced** for transpose, quantize grid, chip engine, chiptune voice mix, force-preset mode, output folder.
6. **Convert.** Watch the progress bar and log panel.
7. Output lands at `<input_dir>/<song>__chiptune.wav` (or `__<soundfont>.wav`), plus `.mid` if you opted in.

---

## Limitations

- **Basic Pitch is best on monophonic / lightly polyphonic audio.** Single instruments, melodies, vocals: great. Full mixed songs: messy without stem separation.
- **Stem separation adds 1–3 minutes per song** (Demucs is heavy). It's opt-in for that reason.
- **Chiptune Mode is 4-voice polyphonic** (NES-style). Dense polyphonic input gets thinned via voice-stealing. That's the retro authenticity, not a bug.
- **General MIDI assumption (SoundFont mode):** Tunerize starts from the selected SoundFont preset. For GM-compatible SoundFonts this is usually bank 0, preset 0: "Acoustic Grand Piano." Use *Force all notes to selected preset* for non-GM banks.
- **No realtime monitoring yet** — preset preview and conversion are rendered offline to WAV.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md). Highlights:

- v0.2 (this release): Online SoundFont browser
- v0.3: Bundled FluidSynth, Windows binary, FluidR3 onboarding, SNES / Genesis chiptune engines
- v0.4: Polyphone integration (bundled SF2 editor — GPL, ships in installer)
- v0.5: Built-in SF2 creator (sample → SF2, native, no external tool)
- v0.6: MP3/OGG/FLAC export, batch mode, genre presets, CLI mode

---

## Development

```bash
pip install -r requirements-dev.txt
pytest                       # run tests
python -m app.main           # run the app
ruff check .                 # lint
```

Build a one-file Windows binary (after dev requirements are installed). The build script bundles FluidSynth from PATH, or from `TUNERIZE_FLUIDSYNTH_DIR` when set to the FluidSynth `bin` folder:

```bash
python build/build_windows.py
```

---

## License

[MIT](LICENSE). Built on:

- [Spotify Basic Pitch](https://github.com/spotify/basic-pitch) — Apache 2.0
- [FluidSynth](https://www.fluidsynth.org/) / [pyfluidsynth](https://github.com/nwhitehead/pyfluidsynth) — LGPL 2.1 / Public Domain bindings
- [PySide6](https://doc.qt.io/qtforpython/) — LGPL 3.0
- [Demucs](https://github.com/facebookresearch/demucs) — MIT
- [pretty_midi](https://github.com/craffel/pretty-midi), [mido](https://github.com/mido/mido), [librosa](https://librosa.org/), [soundfile](https://github.com/bastibe/python-soundfile)
