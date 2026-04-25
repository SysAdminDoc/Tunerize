"""Tests for app.core.chiptune (built-in NES-style synth)."""
from __future__ import annotations

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from app.core.chiptune import ChiptuneError, _assign_voices, render


def test_render_produces_nonsilent_wav(tmp_path, synthetic_midi):
    out = tmp_path / "out.wav"
    render(synthetic_midi, out)
    assert out.exists()
    assert out.stat().st_size > 0

    audio, sr = sf.read(str(out))
    assert sr == 44100
    assert audio.shape[1] == 2  # stereo
    assert np.max(np.abs(audio)) > 0.01  # actually has signal


def test_render_raises_on_empty_midi(tmp_path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    midi.instruments.append(pretty_midi.Instrument(program=0))
    with pytest.raises(ChiptuneError):
        render(midi, tmp_path / "empty.wav")


def test_voice_assignment_routes_drums_to_noise(synthetic_midi):
    voices = _assign_voices(synthetic_midi)
    pulse_lead, pulse_harm, triangle, noise = voices
    # All 8 drum notes should land in noise
    assert len(noise) == 8
    # All 8 melodic notes split across the 3 melodic voices
    assert len(pulse_lead) + len(pulse_harm) + len(triangle) == 8


def test_voice_assignment_low_pitch_prefers_triangle():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0, is_drum=False)
    # Distinct pitches: low (40), mid (60), high (80) at separated times
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=40, start=0.0, end=0.4))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.5, end=0.9))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=80, start=1.0, end=1.4))
    midi.instruments.append(inst)
    pulse_lead, pulse_harm, triangle, _ = _assign_voices(midi)

    triangle_pitches = [n.pitch for n in triangle]
    pulse_lead_pitches = [n.pitch for n in pulse_lead]
    pulse_harm_pitches = [n.pitch for n in pulse_harm]
    assert 40 in triangle_pitches
    assert 80 in pulse_lead_pitches
    assert 60 in pulse_harm_pitches


def test_render_accepts_path(tmp_path, synthetic_midi):
    midi_path = tmp_path / "in.mid"
    synthetic_midi.write(str(midi_path))
    out_path = tmp_path / "out.wav"
    render(midi_path, out_path)
    assert out_path.exists()


def test_render_respects_cancel(tmp_path, synthetic_midi):
    cancelled = {"flag": False}

    def cancel_check() -> bool:
        cancelled["flag"] = True
        return True

    with pytest.raises(ChiptuneError):
        render(synthetic_midi, tmp_path / "out.wav", cancel_check=cancel_check)
    assert cancelled["flag"]
