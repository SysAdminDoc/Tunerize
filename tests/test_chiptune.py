"""Tests for app.core.chiptune (built-in NES-style synth)."""
from __future__ import annotations

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from app.core.chiptune import (
    ENGINE_GAME_BOY,
    ENGINE_SEGA,
    ENGINE_SNES,
    ChiptuneError,
    _apply_snes_echo,
    _apply_snes_gaussian,
    _assign_voices,
    _assign_voices_sega,
    _assign_voices_snes,
    _voice_mixer_gains,
    render,
)


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
        render(synthetic_midi, tmp_path / "bad.wav", engine="atari")


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


# ---------- SNES SPC700 engine tests ----------

def test_render_snes_engine_produces_nonsilent_wav(tmp_path, synthetic_midi):
    out = tmp_path / "snes.wav"
    render(synthetic_midi, out, engine=ENGINE_SNES)

    audio, sr = sf.read(str(out))
    assert sr == 44100
    assert audio.shape[1] == 2
    assert np.max(np.abs(audio)) > 0.01


def test_render_snes_differs_from_nes(tmp_path, synthetic_midi):
    nes_out = tmp_path / "nes.wav"
    snes_out = tmp_path / "snes.wav"
    render(synthetic_midi, nes_out)
    render(synthetic_midi, snes_out, engine=ENGINE_SNES)

    nes_audio, _ = sf.read(str(nes_out))
    snes_audio, _ = sf.read(str(snes_out))
    assert not np.allclose(nes_audio, snes_audio)


def test_assign_voices_snes_distributes_notes():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0, is_drum=False)
    # low bass, mid harmony, high lead — all at separated times
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=36, start=0.0, end=0.4))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.5, end=0.9))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=84, start=1.0, end=1.4))
    midi.instruments.append(inst)
    drum_inst = pretty_midi.Instrument(program=0, is_drum=True)
    drum_inst.notes.append(pretty_midi.Note(velocity=80, pitch=38, start=0.0, end=0.1))
    midi.instruments.append(drum_inst)

    lead, harm, bass, noise = _assign_voices_snes(midi)

    assert 84 in [n.pitch for n in lead]
    assert 60 in [n.pitch for n in harm]
    assert 36 in [n.pitch for n in bass]
    assert len(noise) == 1


def test_assign_voices_snes_total_notes_preserved():
    """All melodic notes must appear in exactly one voice group (no duplicates, no drops)."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0, is_drum=False)
    for i, pitch in enumerate([40, 50, 60, 70, 80, 90]):
        inst.notes.append(pretty_midi.Note(velocity=80, pitch=pitch, start=i * 0.5, end=i * 0.5 + 0.4))
    midi.instruments.append(inst)

    lead, harm, bass, noise = _assign_voices_snes(midi)
    all_melodic = lead + harm + bass
    assert len(all_melodic) == 6
    assert len(noise) == 0


def test_apply_snes_gaussian_preserves_length():
    signal = np.random.default_rng(0).uniform(-1, 1, 4096).astype(np.float32)
    filtered = _apply_snes_gaussian(signal)
    assert filtered.shape == signal.shape


def test_apply_snes_gaussian_attenuates_high_freq():
    """After Gaussian filter, the high-frequency component should be weaker."""
    sr = 44100
    t = np.arange(sr, dtype=np.float32) / sr
    high_freq = np.sin(2 * np.pi * 18000 * t)
    filtered = _apply_snes_gaussian(high_freq)
    assert np.max(np.abs(filtered)) < np.max(np.abs(high_freq))


def test_apply_snes_echo_produces_longer_signal():
    """Echo should introduce energy after the original impulse ends."""
    sr = 44100
    delay_ms = 100.0
    pulse = np.zeros(sr, dtype=np.float32)
    pulse[:100] = 1.0  # short impulse at start
    echoed = _apply_snes_echo(pulse, sr, delay_ms=delay_ms, feedback=0.3, mix_vol=0.4, taps=2)
    assert echoed.shape == pulse.shape
    # Echo tap 1 lands at delay_samples offset; energy should appear there
    delay_samples = int(delay_ms * sr / 1000)
    echo_window = echoed[delay_samples: delay_samples + 200]
    assert np.max(np.abs(echo_window)) > 0.01


# ---------- Sega Genesis YM2612 FM engine tests ----------

def test_render_sega_produces_nonsilent_wav(tmp_path, synthetic_midi):
    out = tmp_path / "sega.wav"
    render(synthetic_midi, out, engine=ENGINE_SEGA)
    assert out.exists()
    audio, sr = sf.read(str(out))
    assert sr == 44100
    assert audio.shape[1] == 2
    assert np.max(np.abs(audio)) > 0.01


def test_render_sega_differs_from_nes(tmp_path, synthetic_midi):
    out_nes = tmp_path / "nes.wav"
    out_sega = tmp_path / "sega.wav"
    render(synthetic_midi, out_nes)
    render(synthetic_midi, out_sega, engine=ENGINE_SEGA)
    nes_audio, _ = sf.read(str(out_nes))
    sega_audio, _ = sf.read(str(out_sega))
    min_len = min(len(nes_audio), len(sega_audio))
    diff = np.max(np.abs(nes_audio[:min_len] - sega_audio[:min_len]))
    assert diff > 0.01, "SEGA and NES renders should sound different"


def test_assign_voices_sega_distributes_notes(synthetic_midi):
    groups = _assign_voices_sega(synthetic_midi)
    assert len(groups) == 4  # lead, harmony, bass, drum
    total_notes = sum(len(g) for g in groups)
    all_notes = [n for inst in synthetic_midi.instruments for n in inst.notes]
    assert total_notes == len(all_notes)


def test_assign_voices_sega_pitch_routing(synthetic_midi):
    """High-pitch notes should land in the lead group; low-pitch in bass."""
    groups = _assign_voices_sega(synthetic_midi)
    lead_pitches = [n.pitch for n in groups[0]]
    bass_pitches = [n.pitch for n in groups[2]]
    # Any lead note should generally be above any bass note (not strict, but statistically true)
    if lead_pitches and bass_pitches:
        assert max(bass_pitches) < max(lead_pitches)


def test_render_sid_produces_nonsilent_wav(tmp_path, synthetic_midi):
    from app.core.chiptune import ENGINE_SID
    out = tmp_path / "sid.wav"
    render(synthetic_midi, out, engine=ENGINE_SID)
    assert out.exists()
    audio, sr = sf.read(str(out))
    assert sr == 44100
    assert audio.shape[1] == 2
    assert np.max(np.abs(audio)) > 0.01


def test_render_sid_differs_from_nes(tmp_path, synthetic_midi):
    from app.core.chiptune import ENGINE_SID
    out_nes = tmp_path / "nes.wav"
    out_sid = tmp_path / "sid.wav"
    render(synthetic_midi, out_nes)
    render(synthetic_midi, out_sid, engine=ENGINE_SID)
    nes_audio, _ = sf.read(str(out_nes))
    sid_audio, _ = sf.read(str(out_sid))
    min_len = min(len(nes_audio), len(sid_audio))
    diff = np.max(np.abs(nes_audio[:min_len] - sid_audio[:min_len]))
    assert diff > 0.01, "SID and NES renders should sound different"
