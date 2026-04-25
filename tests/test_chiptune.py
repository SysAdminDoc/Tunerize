"""Tests for app.core.chiptune (built-in NES-style synth)."""
from __future__ import annotations

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from app.core.chiptune import ENGINE_GAME_BOY, ChiptuneError, _assign_voices, _voice_mixer_gains, render


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


def test_render_gameboy_engine_produces_nonsilent_wav(tmp_path, synthetic_midi):
    out = tmp_path / "gameboy.wav"
    render(synthetic_midi, out, engine=ENGINE_GAME_BOY)

    audio, sr = sf.read(str(out))
    assert sr == 44100
    assert audio.shape[1] == 2
    assert np.max(np.abs(audio)) > 0.01


def test_render_rejects_unknown_engine(tmp_path, synthetic_midi):
    with pytest.raises(ChiptuneError, match="Unsupported chiptune engine"):
        render(synthetic_midi, tmp_path / "bad.wav", engine="sid")


def test_render_respects_cancel(tmp_path, synthetic_midi):
    cancelled = {"flag": False}

    def cancel_check() -> bool:
        cancelled["flag"] = True
        return True

    with pytest.raises(ChiptuneError):
        render(synthetic_midi, tmp_path / "out.wav", cancel_check=cancel_check)
    assert cancelled["flag"]


def test_voice_mixer_solo_overrides_mute():
    gains = _voice_mixer_gains(
        voice_mutes=(True, False, False, False),
        voice_solos=(True, False, False, False),
    )
    assert gains == (1.0, 0.0, 0.0, 0.0)


def test_voice_mixer_rejects_all_muted(tmp_path, synthetic_midi):
    with pytest.raises(ChiptuneError, match="muted every voice"):
        render(
            synthetic_midi,
            tmp_path / "muted.wav",
            voice_mutes=(True, True, True, True),
        )


def test_render_voice_mute_changes_mix(tmp_path, synthetic_midi):
    default_out = tmp_path / "default.wav"
    muted_out = tmp_path / "muted.wav"

    render(synthetic_midi, default_out)
    render(synthetic_midi, muted_out, voice_mutes=(True, False, False, False))

    default_audio, _ = sf.read(str(default_out))
    muted_audio, _ = sf.read(str(muted_out))
    assert not np.allclose(default_audio, muted_audio)
