# Tunerize

[![Version](https://img.shields.io/badge/version-0.1.0-blue?style=flat-square)](https://github.com/SysAdminDoc/Tunerize/releases)
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

- **Built-in chiptune engine** — NES-style 4-voice synth (2 pulse + triangle + noise) ships in the app. Zero install, instant retro.
- **Bring-your-own SoundFonts** — Drop `.sf2` / `.sf3` into `soundfonts/`; Tunerize scans, validates, and lists them.
- **One-click conversion** — Open audio, pick mode, hit Convert. WAV out.
- **Stem separation (optional)** — Pre-split mixed tracks with Demucs for cleaner transcription on full songs.
- **MIDI export** — Keep the intermediate `.mid` for use elsewhere.
- **MIDI cleanup** — Quantize, remove tiny artifacts, normalize velocity, transpose. All defaults sane; tweak in Advanced.
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

Tunerize ships *no* SoundFonts (licensing varies). Drop your own into `soundfonts/`:

- **GeneralUser GS** (CC BY-SA, full GM bank, ~30MB) — [s-christian-griffiths.bandcamp.com](https://schristiangriffiths.bandcamp.com/album/generaluser-gs) or any mirror
- **FluidR3 GM** (MIT, the FluidSynth default, ~140MB)
- **8-bit / NES SF2 packs** — search "NES soundfont" / "chiptune sf2"
- **SC-55 / SC-88** soundfonts — Roland synth recreations

Restart Tunerize after adding files; it'll scan and list them.

---

## Usage

1. **Open Audio** — pick an MP3 or WAV.
2. **Choose render mode**:
   - **Chiptune Mode** — uses the built-in NES-style synth. No SoundFont required.
   - **SoundFont Mode** — pick a `.sf2` from the dropdown or click *Add SoundFont…*.
3. *(Optional)* Toggle **Stem separation** if your input is a mixed song.
4. *(Optional)* Open **Advanced** for transpose, quantize grid, force-preset mode, output folder.
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

- v0.2: Bundled FluidSynth (no separate install), per-preset selector with previews, Game Boy & SNES chiptune engines
- v0.3: Polyphone integration (bundled SF2 editor — GPL, ships in installer)
- v0.4: Built-in SF2 creator (sample → SF2, native, no external tool)
- v0.5: MP3/OGG/FLAC export, batch mode, genre presets

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
