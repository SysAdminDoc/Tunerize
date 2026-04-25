"""Built-in chiptune renderers.

Synthesizes pulse (square with selectable duty cycle), triangle, and noise
waveforms directly from a MIDI sequence — no SoundFont required. The default
engine approximates the Nintendo NES APU: 2 pulse channels + 1 triangle + 1
noise. The Game Boy DMG variant uses the same voice allocator with 2 pulse
channels + 1 4-bit custom wavetable + 1 noise channel.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

SAMPLE_RATE = 44100
ENGINE_NES = "nes"
ENGINE_GAME_BOY = "gameboy"
SUPPORTED_ENGINES = (ENGINE_NES, ENGINE_GAME_BOY)

V_PULSE_LEAD = 0
V_PULSE_HARM = 1
V_TRIANGLE = 2
V_NOISE = 3
VOICE_COUNT = 4
DEFAULT_VOICE_VOLUMES = (1.0, 1.0, 1.0, 1.0)
DEFAULT_VOICE_MUTES = (False, False, False, False)
DEFAULT_VOICE_SOLOS = (False, False, False, False)
BASE_VOICE_GAINS = (0.28, 0.22, 0.32, 0.22)
GAME_BOY_WAVETABLE_4BIT = np.array(
    [8, 10, 12, 14, 15, 14, 12, 10, 8, 6, 4, 2, 1, 2, 4, 6,
     8, 11, 14, 15, 14, 11, 8, 5, 2, 1, 2, 5, 8, 7, 8, 9],
    dtype=np.float32,
)


class ChiptuneError(Exception):
    pass


@dataclass(frozen=True)
class _ChipNote:
    pitch: int
    start: float
    end: float
    velocity: int

    @property
    def freq_hz(self) -> float:
        return 440.0 * (2.0 ** ((self.pitch - 69) / 12.0))


# ---------- waveform generators ----------

def _square(t: np.ndarray, freq: float, duty: float) -> np.ndarray:
    phase = (t * freq) % 1.0
    return np.where(phase < duty, 1.0, -1.0).astype(np.float32)


def _triangle(t: np.ndarray, freq: float) -> np.ndarray:
    phase = (t * freq) % 1.0
    return (2.0 * np.abs(2.0 * phase - 1.0) - 1.0).astype(np.float32)


def _noise(n_samples: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, n_samples).astype(np.float32)


def _quantize_4bit(samples: np.ndarray) -> np.ndarray:
    levels = np.round((np.clip(samples, -1.0, 1.0) + 1.0) * 7.5)
    return ((levels / 7.5) - 1.0).astype(np.float32)


def _wave_pulse_lead(t: np.ndarray, freq: float) -> np.ndarray:
    return _square(t, freq, 0.5)


def _wave_pulse_harm(t: np.ndarray, freq: float) -> np.ndarray:
    return _square(t, freq, 0.25)


def _wave_triangle(t: np.ndarray, freq: float) -> np.ndarray:
    return _triangle(t, freq)


def _wave_gameboy_pulse_1(t: np.ndarray, freq: float) -> np.ndarray:
    return _quantize_4bit(_square(t, freq, 0.125))


def _wave_gameboy_pulse_2(t: np.ndarray, freq: float) -> np.ndarray:
    return _quantize_4bit(_square(t, freq, 0.5))


def _wave_gameboy_custom(t: np.ndarray, freq: float) -> np.ndarray:
    phase = (t * freq) % 1.0
    indices = np.floor(phase * len(GAME_BOY_WAVETABLE_4BIT)).astype(np.int32)
    values = GAME_BOY_WAVETABLE_4BIT[indices]
    return ((values - 7.5) / 7.5).astype(np.float32)


# ---------- envelopes ----------

def _adsr(
    n_samples: int, sample_rate: int,
    attack_ms: float, decay_ms: float, sustain: float, release_ms: float,
) -> np.ndarray:
    a = max(1, int(attack_ms * sample_rate / 1000))
    d = max(1, int(decay_ms * sample_rate / 1000))
    r = max(1, int(release_ms * sample_rate / 1000))
    if a + d + r > n_samples:
        scale = max(0.05, n_samples / (a + d + r))
        a = max(1, int(a * scale))
        d = max(1, int(d * scale))
        r = max(1, int(r * scale))
    s_len = max(0, n_samples - a - d - r)
    env = np.empty(n_samples, dtype=np.float32)
    env[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    env[a:a + d] = np.linspace(1.0, sustain, d, dtype=np.float32)
    env[a + d:a + d + s_len] = sustain
    tail = n_samples - a - d - s_len
    if tail > 0:
        env[a + d + s_len:] = np.linspace(sustain, 0.0, tail, dtype=np.float32)
    return env


def _env_pulse(n: int, sr: int) -> np.ndarray:
    return _adsr(n, sr, attack_ms=2.0, decay_ms=20.0, sustain=0.75, release_ms=40.0)


def _env_triangle(n: int, sr: int) -> np.ndarray:
    return _adsr(n, sr, attack_ms=4.0, decay_ms=10.0, sustain=0.85, release_ms=80.0)


def _env_gameboy_wave(n: int, sr: int) -> np.ndarray:
    return _adsr(n, sr, attack_ms=1.0, decay_ms=18.0, sustain=0.65, release_ms=34.0)


def _env_drum(n: int, sr: int) -> np.ndarray:
    decay_samples = min(n, max(1, int(0.18 * sr)))
    env = np.zeros(n, dtype=np.float32)
    env[:decay_samples] = np.exp(-np.linspace(0.0, 6.0, decay_samples, dtype=np.float32))
    return env


# ---------- voice allocation ----------

def _voice_label(idx: int, engine: str = ENGINE_NES) -> str:
    if engine == ENGINE_GAME_BOY:
        return (
            "Pulse 1 (lead, 12.5% duty)",
            "Pulse 2 (harmony, 50% duty)",
            "Wave channel (custom 4-bit)",
            "Noise (drums)",
        )[idx]
    return (
        "Pulse 1 (lead, 50% duty)",
        "Pulse 2 (harmony, 25% duty)",
        "Triangle (bass)",
        "Noise (drums)",
    )[idx]


def _voice_mixer_gains(
    voice_volumes: Sequence[float] | None = None,
    voice_mutes: Sequence[bool] | None = None,
    voice_solos: Sequence[bool] | None = None,
) -> tuple[float, float, float, float]:
    volumes = _coerce_voice_values(voice_volumes, DEFAULT_VOICE_VOLUMES, "voice_volumes")
    mutes = _coerce_voice_values(voice_mutes, DEFAULT_VOICE_MUTES, "voice_mutes")
    solos = _coerce_voice_values(voice_solos, DEFAULT_VOICE_SOLOS, "voice_solos")

    solo_mode = any(solos)
    gains: list[float] = []
    for volume, muted, soloed in zip(volumes, mutes, solos, strict=True):
        clamped_volume = min(1.5, max(0.0, float(volume)))
        if solo_mode:
            gains.append(clamped_volume if soloed else 0.0)
        else:
            gains.append(0.0 if muted else clamped_volume)

    if all(gain <= 0.0 for gain in gains):
        raise ChiptuneError("Chiptune mixer muted every voice.")
    return gains[0], gains[1], gains[2], gains[3]


def _coerce_voice_values(values, default, name: str):
    if values is None:
        return default
    coerced = tuple(values)
    if len(coerced) != VOICE_COUNT:
        raise ChiptuneError(f"{name} must contain {VOICE_COUNT} values.")
    return coerced


def _assign_voices(midi: pretty_midi.PrettyMIDI) -> list[list[_ChipNote]]:
    """Distribute MIDI notes across pulse-lead / pulse-harm / triangle / noise.

    - Drum-channel notes (`instrument.is_drum`) always go to the noise voice.
    - Melodic notes are routed by pitch:
        * pitch < 50  -> triangle preferred (bass)
        * pitch >= 72 -> pulse-lead preferred (lead)
        * otherwise   -> pulse-harm preferred (harmony)
      If the preferred voice is busy, fall back to the next free voice.
      If all 3 melodic voices are busy, steal the one freeing soonest.
    """
    drum: list[_ChipNote] = []
    melodic: list[_ChipNote] = []
    for inst in midi.instruments:
        for n in inst.notes:
            cn = _ChipNote(pitch=int(n.pitch), start=float(n.start),
                           end=float(n.end), velocity=int(n.velocity))
            (drum if inst.is_drum else melodic).append(cn)

    melodic.sort(key=lambda n: (n.start, n.pitch))

    pulse_lead: list[_ChipNote] = []
    pulse_harm: list[_ChipNote] = []
    triangle: list[_ChipNote] = []
    free_at = [0.0, 0.0, 0.0]  # earliest-free time for voices 0/1/2

    for n in melodic:
        if n.pitch < 50:
            order = (V_TRIANGLE, V_PULSE_HARM, V_PULSE_LEAD)
        elif n.pitch >= 72:
            order = (V_PULSE_LEAD, V_PULSE_HARM, V_TRIANGLE)
        else:
            order = (V_PULSE_HARM, V_PULSE_LEAD, V_TRIANGLE)

        chosen: int | None = None
        for v in order:
            if n.start >= free_at[v]:
                chosen = v
                break
        if chosen is None:
            chosen = min((V_PULSE_LEAD, V_PULSE_HARM, V_TRIANGLE), key=lambda i: free_at[i])

        if chosen == V_PULSE_LEAD:
            pulse_lead.append(n)
        elif chosen == V_PULSE_HARM:
            pulse_harm.append(n)
        else:
            triangle.append(n)
        free_at[chosen] = max(free_at[chosen], n.end)

    return [pulse_lead, pulse_harm, triangle, drum]


# ---------- per-voice render ----------

def _render_voice(
    voice_idx: int,
    notes: list[_ChipNote],
    total_samples: int,
    sample_rate: int,
    *,
    engine: str = ENGINE_NES,
    gain_multiplier: float = 1.0,
) -> np.ndarray:
    buf = np.zeros(total_samples, dtype=np.float32)
    if not notes or gain_multiplier <= 0.0:
        return buf

    wave_fn, env_fn, gain = _voice_patch(engine, voice_idx)

    for note in notes:
        start = int(note.start * sample_rate)
        end = int(note.end * sample_rate)
        n = end - start
        if n <= 0 or start >= total_samples:
            continue
        n = min(n, total_samples - start)
        vel_gain = (note.velocity / 127.0) * gain * gain_multiplier

        if voice_idx == V_NOISE:
            seed = (note.pitch * 1009 + start) & 0xFFFFFFFF
            samples = _noise(n, seed=seed)
            if engine == ENGINE_GAME_BOY:
                samples = _quantize_4bit(samples)
        else:
            t = np.arange(n, dtype=np.float32) / sample_rate
            samples = wave_fn(t, note.freq_hz)

        env = env_fn(n, sample_rate)
        buf[start:start + n] += samples * env * vel_gain

    return buf


def _voice_patch(engine: str, voice_idx: int):
    if engine == ENGINE_GAME_BOY:
        if voice_idx == V_PULSE_LEAD:
            return _wave_gameboy_pulse_1, _env_pulse, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_PULSE_HARM:
            return _wave_gameboy_pulse_2, _env_pulse, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_TRIANGLE:
            return _wave_gameboy_custom, _env_gameboy_wave, BASE_VOICE_GAINS[voice_idx]
        return None, _env_drum, BASE_VOICE_GAINS[voice_idx]

    if voice_idx == V_PULSE_LEAD:
        return _wave_pulse_lead, _env_pulse, BASE_VOICE_GAINS[voice_idx]
    if voice_idx == V_PULSE_HARM:
        return _wave_pulse_harm, _env_pulse, BASE_VOICE_GAINS[voice_idx]
    if voice_idx == V_TRIANGLE:
        return _wave_triangle, _env_triangle, BASE_VOICE_GAINS[voice_idx]
    return None, _env_drum, BASE_VOICE_GAINS[voice_idx]


# ---------- public render ----------

def render(
    midi: pretty_midi.PrettyMIDI | Path | str,
    output_wav_path: Path,
    *,
    sample_rate: int = SAMPLE_RATE,
    engine: str = ENGINE_NES,
    voice_volumes: Sequence[float] | None = None,
    voice_mutes: Sequence[bool] | None = None,
    voice_solos: Sequence[bool] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
) -> Path:
    """Render a MIDI through the chiptune engine to a 16-bit stereo WAV.

    `midi` may be a `pretty_midi.PrettyMIDI` instance or a path to an SMF.
    Output is normalized to -3 dB to prevent clipping.
    """
    log = log or (lambda _m: None)
    if engine not in SUPPORTED_ENGINES:
        raise ChiptuneError(f"Unsupported chiptune engine: {engine}")
    if isinstance(midi, (str, Path)):
        midi = pretty_midi.PrettyMIDI(str(midi))

    note_count = sum(len(inst.notes) for inst in midi.instruments)
    if note_count == 0:
        raise ChiptuneError("MIDI contains no notes to render.")

    voices = _assign_voices(midi)
    voice_gains = _voice_mixer_gains(voice_volumes, voice_mutes, voice_solos)
    end_times = [n.end for vlist in voices for n in vlist]
    total_seconds = (max(end_times) if end_times else 0.0) + 1.0
    total_samples = int(total_seconds * sample_rate)
    engine_label = "Game Boy DMG" if engine == ENGINE_GAME_BOY else "NES"
    log(f"  -> {note_count} notes across 4 voices, {engine_label}, {total_seconds:.1f}s")

    mix = np.zeros(total_samples, dtype=np.float32)
    for v_idx, notes in enumerate(voices):
        if cancel_check is not None and cancel_check():
            raise ChiptuneError("Render cancelled by user.")
        voice_status = "muted" if voice_gains[v_idx] <= 0.0 else f"{voice_gains[v_idx] * 100:.0f}%"
        log(f"  -> {_voice_label(v_idx, engine)}: {len(notes)} notes, {voice_status}")
        mix += _render_voice(
            v_idx,
            notes,
            total_samples,
            sample_rate,
            engine=engine,
            gain_multiplier=voice_gains[v_idx],
        )

    peak = float(np.max(np.abs(mix)))
    if peak <= 0.0:
        raise ChiptuneError("Chiptune render produced silence.")
    mix = mix / peak * 0.85

    stereo = np.column_stack([mix, mix])
    out_int16 = (stereo * 32767.0).astype(np.int16)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav_path), out_int16, sample_rate, subtype="PCM_16")
    return output_wav_path
