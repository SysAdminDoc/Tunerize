"""Convert Tunerize's built-in chiptune voices into a redistributable SF2.

Generates one multi-sample SF2 per chip engine containing all voice types
(pulse, triangle/wave, noise, FM variants) mapped across the keyboard.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.core.chiptune import (
    ENGINE_GAME_BOY,
    ENGINE_NES,
    ENGINE_SEGA,
    ENGINE_SID,
    ENGINE_SNES,
    SAMPLE_RATE,
    _noise,
    _square,
    _triangle,
    _wave_gameboy_custom,
    _wave_gameboy_pulse_1,
    _wave_gameboy_pulse_2,
    _wave_sega_bass,
    _wave_sega_harm,
    _wave_sega_lead,
    _wave_sid_bass,
    _wave_sid_pulse,
    _wave_sid_saw,
    _wave_snes_bass,
    _wave_snes_harm,
    _wave_snes_lead,
)
from app.core.sf2_writer import SF2Bank, SF2Preset, SF2Sample, SF2Zone, write_sf2

_SAMPLE_DURATION = 2.0
_NOISE_DURATION = 1.0

_NOTE_PITCHES = [36, 48, 60, 72, 84, 96]

_ENGINE_VOICES: dict[str, list[tuple[str, object, bool]]] = {
    ENGINE_NES: [
        ("NES Pulse 50%", lambda t, f: _square(t, f, 0.5), False),
        ("NES Pulse 25%", lambda t, f: _square(t, f, 0.25), False),
        ("NES Triangle", lambda t, f: _triangle(t, f), False),
        ("NES Noise", None, True),
    ],
    ENGINE_GAME_BOY: [
        ("GB Pulse 12.5%", _wave_gameboy_pulse_1, False),
        ("GB Pulse 50%", _wave_gameboy_pulse_2, False),
        ("GB Wave", _wave_gameboy_custom, False),
        ("GB Noise", None, True),
    ],
    ENGINE_SNES: [
        ("SNES Lead", _wave_snes_lead, False),
        ("SNES Harmony", _wave_snes_harm, False),
        ("SNES Bass", _wave_snes_bass, False),
        ("SNES Noise", None, True),
    ],
    ENGINE_SEGA: [
        ("Sega FM Lead", _wave_sega_lead, False),
        ("Sega FM Harmony", _wave_sega_harm, False),
        ("Sega FM Bass", _wave_sega_bass, False),
        ("Sega Noise", None, True),
    ],
    ENGINE_SID: [
        ("SID Pulse", _wave_sid_pulse, False),
        ("SID Sawtooth", _wave_sid_saw, False),
        ("SID Tri+Ring", _wave_sid_bass, False),
        ("SID Noise", None, True),
    ],
}


def _midi_to_freq(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def _render_sample(wave_fn, pitch: int, duration: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    t = np.arange(n, dtype=np.float32) / sr
    raw = wave_fn(t, _midi_to_freq(pitch))
    peak = float(np.max(np.abs(raw))) or 1.0
    normalized = raw / peak * 0.9
    return (normalized * 32767).astype(np.int16)


def _render_noise_sample(pitch: int, duration: float, sr: int) -> np.ndarray:
    n = int(duration * sr)
    seed = (pitch * 1009 + 42) & 0xFFFFFFFF
    raw = _noise(n, seed=seed)
    return (raw * 0.9 * 32767).astype(np.int16)


def export_chiptune_sf2(engine: str, output_path: Path) -> Path:
    """Generate an SF2 containing all voices for the given chiptune engine."""
    voices = _ENGINE_VOICES.get(engine)
    if voices is None:
        raise ValueError(f"Unknown engine: {engine}")

    engine_labels = {
        ENGINE_NES: "Tunerize NES APU",
        ENGINE_GAME_BOY: "Tunerize Game Boy DMG",
        ENGINE_SNES: "Tunerize SNES SPC700",
        ENGINE_SEGA: "Tunerize Sega Genesis",
    }
    bank_name = engine_labels.get(engine, f"Tunerize {engine}")
    sf2_bank = SF2Bank(name=bank_name)

    for preset_num, (voice_name, wave_fn, is_noise) in enumerate(voices):
        zones: list[SF2Zone] = []

        if is_noise:
            data = _render_noise_sample(60, _NOISE_DURATION, SAMPLE_RATE)
            loop_len = SAMPLE_RATE // 4
            loop_start = len(data) // 4
            loop_end = loop_start + loop_len
            sample_idx = sf2_bank.add_sample(SF2Sample(
                name=voice_name[:20],
                data=data,
                sample_rate=SAMPLE_RATE,
                original_pitch=60,
                loop_start=loop_start,
                loop_end=loop_end,
                loop_enabled=True,
            ))
            zones.append(SF2Zone(
                sample_index=sample_idx,
                key_lo=0,
                key_hi=127,
                root_key=60,
                attack_ms=1.0,
                decay_ms=200.0,
                sustain_pct=0.0,
                release_ms=80.0,
                loop_mode=1,
            ))
        else:
            for i, pitch in enumerate(_NOTE_PITCHES):
                data = _render_sample(wave_fn, pitch, _SAMPLE_DURATION, SAMPLE_RATE)
                n = len(data)
                cycles = max(1, int(_midi_to_freq(pitch) * 0.01))
                samples_per_cycle = SAMPLE_RATE / _midi_to_freq(pitch)
                loop_len = int(cycles * samples_per_cycle)
                loop_start = n // 3
                loop_end = loop_start + loop_len

                sample_idx = sf2_bank.add_sample(SF2Sample(
                    name=f"{voice_name[:14]} {pitch}",
                    data=data,
                    sample_rate=SAMPLE_RATE,
                    original_pitch=pitch,
                    loop_start=loop_start,
                    loop_end=min(loop_end, n - 1),
                    loop_enabled=True,
                ))

                key_lo = 0 if i == 0 else (_NOTE_PITCHES[i - 1] + pitch) // 2
                key_hi = 127 if i == len(_NOTE_PITCHES) - 1 else (pitch + _NOTE_PITCHES[i + 1]) // 2 - 1

                zones.append(SF2Zone(
                    sample_index=sample_idx,
                    key_lo=key_lo,
                    key_hi=key_hi,
                    root_key=pitch,
                    attack_ms=2.0,
                    decay_ms=20.0,
                    sustain_pct=25.0,
                    release_ms=40.0,
                    loop_mode=1,
                ))

        sf2_bank.add_preset(SF2Preset(
            name=voice_name,
            preset_number=preset_num,
            bank=0,
            zones=zones,
        ))

    return write_sf2(sf2_bank, output_path)
