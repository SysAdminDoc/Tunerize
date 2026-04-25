"""Shared pytest fixtures."""
from __future__ import annotations

import struct
from pathlib import Path

import pretty_midi
import pytest


@pytest.fixture
def synthetic_midi() -> pretty_midi.PrettyMIDI:
    """A 4-second piano arpeggio + a drum hit on every quarter beat."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)

    piano = pretty_midi.Instrument(program=0, is_drum=False, name="Piano")
    pitches = [60, 64, 67, 72, 67, 64, 60, 64]  # C-E-G-C arpeggio
    t = 0.0
    for pitch in pitches:
        piano.notes.append(pretty_midi.Note(
            velocity=80, pitch=pitch, start=t, end=t + 0.45,
        ))
        t += 0.5
    midi.instruments.append(piano)

    drums = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    for i in range(8):
        drums.notes.append(pretty_midi.Note(
            velocity=100, pitch=36 if i % 2 == 0 else 38,  # kick / snare
            start=i * 0.5, end=i * 0.5 + 0.05,
        ))
    midi.instruments.append(drums)

    return midi


@pytest.fixture
def empty_midi() -> pretty_midi.PrettyMIDI:
    """A PrettyMIDI with no notes — simulates Basic Pitch on silence."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    midi.instruments.append(pretty_midi.Instrument(program=0))
    return midi


@pytest.fixture
def fake_sf2(tmp_path: Path) -> Path:
    """Create a file with a valid RIFF/sfbk header (enough to pass validation).

    Not a usable SoundFont — only used to exercise the validation/scanning code.
    """
    p = tmp_path / "test.sf2"
    payload = b"RIFF" + struct.pack("<I", 4) + b"sfbk" + b"\x00" * 32
    p.write_bytes(payload)
    return p


@pytest.fixture
def fake_invalid_sf2(tmp_path: Path) -> Path:
    p = tmp_path / "broken.sf2"
    p.write_bytes(b"NOT A SOUNDFONT FILE")
    return p
