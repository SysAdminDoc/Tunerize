# Tunerize

[![Version](https://img.shields.io/badge/version-0.2.0-blue?style=flat-square)](https://github.com/SysAdminDoc/Tunerize/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows)](https://www.microsoft.com/windows)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Built with PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)

**Re-render any audio as chiptune — or through any SoundFont you choose.** Drop in an MP3 or WAV, pick **Chiptune Mode** (built-in NES-style synth, zero setup) or any `.sf2` (piano, brass, SC-55, anything), and get back a WAV in that style.

Tunerize does the full pipeline locally: audio → MIDI (via Spotify Basic Pitch) → cleaned MIDI → render. Two render paths:
- **Chiptune engine** (built-in) — 2 pulse channels + triangle + noise, NES APU-style. No SoundFont needed.
- **SoundFont engine** (FluidSynth) — anything `.sf2` you can find.

One window, one button, no cloud.

![Tunerize banner](assets/banner.png)

---

## Features

- **Built-in chiptune engines** — NES-style (2 pulse + triangle + noise) and Game Boy DMG-style (2 pulse + custom wave + noise) synths ship in the app. Zero install, instant retro.
- **Online SoundFont browser** — search and install SF2s from public libraries (musical-artifacts.com plus GitHub `topic:soundfont`) without leaving the app. License + author shown for every result.
- **Bring-your-own SoundFonts** — Drop `.sf2` / `.sf3` into `soundfonts/`; Tunerize scans, validates, lists them, and keeps your recent picks at the top.
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
- **FluidSynth** — *only required for SoundFont mode*; Chiptune Mode works without it.
  - Windows: `winget install FluidSynth.FluidSynth` *or* download from [fluidsynth.org](https://www.fluidsynth.org/) and put `fluidsynth.exe` on PATH
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

1. **Use the built-in browser** *(easiest)* — Open Tunerize, switch to SoundFont mode, click **Browse Online…**. Searches musical-artifacts.com and GitHub `topic:soundfont`, shows license per result, and downloads in one click. GitHub repositories are saved as ZIP bundles; unpack them and import any `.sf2` / `.sf3` files inside.
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
3. *(Optional)* Toggle **Stem separation** if your input is a mixed song.
4. *(Optional)* Open **Advanced** for transpose, quantize grid, chip engine, chiptune voice mix, force-preset mode, output folder.
5. **Convert.** Watch the progress bar and log panel.
6. Output lands at `<input_dir>/<song>__chiptune.wav` (or `__<soundfont>.wav`), plus `.mid` if you opted in.

---

## Limitations (read this before complaining)

- **Basic Pitch is best on monophonic / lightly polyphonic audio.** Single instruments, melodies, vocals: great. Full mixed songs: messy without stem separation.
- **Stem separation adds 1–3 minutes per song** (Demucs is heavy). It's opt-in for that reason.
- **Chiptune Mode is 4-voice polyphonic** (NES-style). Dense polyphonic input gets thinned via voice-stealing. That's the retro authenticity, not a bug.
- **General MIDI assumption (SoundFont mode):** Tunerize maps Basic Pitch's single output channel to preset 0 of the SoundFont's bank 0. For GM-compatible SoundFonts this is "Acoustic Grand Piano." Use *Force preset* to point at a specific instrument.
- **No realtime preview yet** — output is rendered offline to WAV.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md). Highlights:

- v0.2 (this release): Online SoundFont browser
- v0.3: Bundled FluidSynth, Game Boy / SNES / Genesis chiptune engines, more browser providers (Reddit, GitHub)
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

Build a Windows binary (after PyInstaller is installed):

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
