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
ENGINE_SNES = "snes"
ENGINE_SEGA = "sega"
ENGINE_SID = "sid"
SUPPORTED_ENGINES = (ENGINE_NES, ENGINE_GAME_BOY, ENGINE_SNES, ENGINE_SEGA, ENGINE_SID)

V_PULSE_LEAD = 0
V_PULSE_HARM = 1
V_TRIANGLE = 2
V_NOISE = 3
VOICE_COUNT = 4
DEFAULT_VOICE_VOLUMES = (1.0, 1.0, 1.0, 1.0)
DEFAULT_VOICE_MUTES = (False, False, False, False)
DEFAULT_VOICE_SOLOS = (False, False, False, False)
BASE_VOICE_GAINS = (0.28, 0.22, 0.32, 0.22)

# SNES SPC700 constants
# 4-tap FIR that approximates the Gaussian interpolation filter in the SPC700 DSP
_SNES_GAUSS_KERNEL = np.array([0.0625, 0.4375, 0.4375, 0.0625], dtype=np.float32)
SNES_ECHO_DELAY_MS = 280.0   # comparable to SNES EDL register, step = 16ms
SNES_ECHO_FEEDBACK = 0.28    # EFB decay per tap
SNES_ECHO_MIX = 0.20         # EVOL (echo output level)
SNES_ECHO_TAPS = 4           # number of feedback taps to approximate recursive echo

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

# SNES SPC700: multi-harmonic sine blends modelling the BRR sample playback.
# Ratios match typical SNES instrument recordings (lead synth / pad / bass).

def _wave_snes_lead(t: np.ndarray, freq: float) -> np.ndarray:
    """SNES-style lead voice: warm sine with 2nd/3rd harmonics."""
    out = (
        0.55 * np.sin(2.0 * np.pi * freq * t)
        + 0.28 * np.sin(4.0 * np.pi * freq * t)
        + 0.12 * np.sin(6.0 * np.pi * freq * t)
        + 0.05 * np.sin(8.0 * np.pi * freq * t)
    ).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


def _wave_snes_harm(t: np.ndarray, freq: float) -> np.ndarray:
    """SNES-style harmony / pad voice: brighter harmonic stack."""
    out = (
        0.50 * np.sin(2.0 * np.pi * freq * t)
        + 0.30 * np.sin(4.0 * np.pi * freq * t)
        + 0.15 * np.sin(6.0 * np.pi * freq * t)
        + 0.05 * np.sin(8.0 * np.pi * freq * t)
    ).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


def _wave_snes_bass(t: np.ndarray, freq: float) -> np.ndarray:
    """SNES-style bass / wave voice: sine-dominant with soft 2nd harmonic."""
    out = (
        0.70 * np.sin(2.0 * np.pi * freq * t)
        + 0.22 * np.sin(4.0 * np.pi * freq * t)
        + 0.08 * np.sin(6.0 * np.pi * freq * t)
    ).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


# Sega Genesis YM2612: 2-operator FM synthesis.
# The YM2612 uses FM (frequency modulation) synthesis with 4 operators per
# channel and 8 algorithms; we use a 2-op model (op2 modulates op1 carrier)
# which captures the characteristic metallic/digital texture at low cost.
# Parameters are tuned to match classic Genesis instrument patches.

def _wave_sega_lead(t: np.ndarray, freq: float) -> np.ndarray:
    """YM2612-style lead: 1:1 self-modulating FM (feedback brass/synth lead).

    Algorithm: mod = sin(f·t + fb·mod_prev), out = sin(f·t + beta·mod)
    Approximated stateless as sin(f·t + beta·sin(f·t + fb·sin(f·t))).
    """
    phase = 2.0 * np.pi * freq * t
    inner_mod = np.sin(phase)
    mod = np.sin(phase + 0.35 * inner_mod)  # single feedback iteration
    out = np.sin(phase + 2.8 * mod).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


def _wave_sega_harm(t: np.ndarray, freq: float) -> np.ndarray:
    """YM2612-style harmony: 2:1 modulator ratio (electric piano / mallet).

    Modulator at 2x carrier freq gives the characteristic YM2612 bell/ep tone.
    """
    mod = np.sin(4.0 * np.pi * freq * t)         # modulator at 2× freq
    out = np.sin(2.0 * np.pi * freq * t + 1.4 * mod).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


def _wave_sega_bass(t: np.ndarray, freq: float) -> np.ndarray:
    """YM2612-style bass: 0.5:1 sub-modulator — punchy FM bass.

    Sub-ratio modulator (half the carrier freq) produces the YM2612's
    characteristic low-mid punch heard on Genesis bass patches.
    """
    mod = np.sin(np.pi * freq * t)               # modulator at 0.5× freq
    out = np.sin(2.0 * np.pi * freq * t + 3.8 * mod).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


# Commodore 64 SID: 3 voices with pulse, sawtooth, and noise.
# The 6581 SID chip uses analog filters with characteristic resonance.

def _sawtooth(t: np.ndarray, freq: float) -> np.ndarray:
    phase = (t * freq) % 1.0
    return (2.0 * phase - 1.0).astype(np.float32)


def _wave_sid_pulse(t: np.ndarray, freq: float) -> np.ndarray:
    """SID-style pulse wave with 40% duty cycle — the classic C64 lead sound."""
    phase = (t * freq) % 1.0
    return np.where(phase < 0.4, 1.0, -1.0).astype(np.float32)


def _wave_sid_saw(t: np.ndarray, freq: float) -> np.ndarray:
    """SID sawtooth — raw 12-bit DAC character with slight harmonic roll-off."""
    raw = _sawtooth(t, freq)
    return (raw * 0.92).astype(np.float32)


def _wave_sid_bass(t: np.ndarray, freq: float) -> np.ndarray:
    """SID triangle with ring-mod overtone — the warm C64 bass tone."""
    phase = (t * freq) % 1.0
    tri = (2.0 * np.abs(2.0 * phase - 1.0) - 1.0)
    ring = np.sin(4.0 * np.pi * freq * t) * 0.15
    out = (tri + ring).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    return out / peak


def _env_sid_lead(n: int, sr: int) -> np.ndarray:
    return _adsr(n, sr, attack_ms=2.0, decay_ms=40.0, sustain=0.55, release_ms=90.0)


def _env_sid_harm(n: int, sr: int) -> np.ndarray:
    return _adsr(n, sr, attack_ms=5.0, decay_ms=80.0, sustain=0.48, release_ms=120.0)


def _env_sid_bass(n: int, sr: int) -> np.ndarray:
    return _adsr(n, sr, attack_ms=1.0, decay_ms=20.0, sustain=0.72, release_ms=50.0)


def _apply_sid_filter(mix: np.ndarray, sample_rate: int) -> np.ndarray:
    """Approximate the SID 6581's resonant low-pass filter characteristic."""
    cutoff_hz = 4800
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)
    out = np.empty_like(mix)
    out[0] = mix[0] * alpha
    for i in range(1, len(mix)):
        out[i] = out[i - 1] + alpha * (mix[i] - out[i - 1])
    resonance = 0.25
    out += resonance * (mix - out)
    return out.astype(np.float32)


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


def _env_snes(n: int, sr: int) -> np.ndarray:
    """SNES SPC700 ADSR envelope: smooth attack, moderate decay, warm sustain."""
    return _adsr(n, sr, attack_ms=8.0, decay_ms=120.0, sustain=0.82, release_ms=280.0)


def _env_snes_bass(n: int, sr: int) -> np.ndarray:
    """SNES bass/wave voice envelope: quicker attack, longer sustain."""
    return _adsr(n, sr, attack_ms=4.0, decay_ms=80.0, sustain=0.88, release_ms=180.0)


def _env_sega_lead(n: int, sr: int) -> np.ndarray:
    """YM2612 lead envelope: punchy attack, medium decay, sustain typical of brass patches."""
    return _adsr(n, sr, attack_ms=3.0, decay_ms=60.0, sustain=0.62, release_ms=110.0)


def _env_sega_harm(n: int, sr: int) -> np.ndarray:
    """YM2612 harmony envelope: slightly slower attack for electric-piano / mallet feel."""
    return _adsr(n, sr, attack_ms=6.0, decay_ms=110.0, sustain=0.50, release_ms=170.0)


def _env_sega_bass(n: int, sr: int) -> np.ndarray:
    """YM2612 bass envelope: instant attack, fast decay, low sustain — classic FM slap bass."""
    return _adsr(n, sr, attack_ms=1.0, decay_ms=28.0, sustain=0.68, release_ms=55.0)


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
    if engine == ENGINE_SNES:
        return (
            "Voices 1-2 (lead)",
            "Voices 3-4 (harmony)",
            "Voices 5-6 (bass)",
            "Voices 7-8 (noise/drums)",
        )[idx]
    if engine == ENGINE_SEGA:
        return (
            "FM Ch1-3 (lead)",
            "FM Ch4-5 (harmony)",
            "FM Ch6 (bass)",
            "Noise (drums)",
        )[idx]
    if engine == ENGINE_SID:
        return (
            "SID Voice 1 (pulse lead)",
            "SID Voice 2 (saw harmony)",
            "SID Voice 3 (tri+ring bass)",
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


def _apply_snes_gaussian(mix: np.ndarray) -> np.ndarray:
    """Approximate the SPC700 Gaussian interpolation low-pass filter.

    A 4-tap symmetric FIR (coefficients derived from the original SPC700 ROM table)
    gives the characteristic warm/slightly-blurred texture of SNES audio.
    """
    return np.convolve(mix, _SNES_GAUSS_KERNEL, mode="same").astype(np.float32)


def _apply_snes_echo(
    mix: np.ndarray,
    sample_rate: int,
    *,
    delay_ms: float = SNES_ECHO_DELAY_MS,
    feedback: float = SNES_ECHO_FEEDBACK,
    mix_vol: float = SNES_ECHO_MIX,
    taps: int = SNES_ECHO_TAPS,
) -> np.ndarray:
    """Vectorized multi-tap echo approximating the SPC700 echo buffer.

    The SPC700 implements a recursive FIR echo; we approximate it with
    a fixed number of additive delay taps so the whole operation is
    a single numpy vectorized expression with no Python loop per sample.
    """
    delay_samples = max(1, int(delay_ms * sample_rate / 1000))
    out = mix.copy()
    total_len = len(mix)
    gain = mix_vol
    for tap in range(1, taps + 1):
        offset = tap * delay_samples
        if offset >= total_len:
            break
        echo = np.zeros(total_len, dtype=np.float32)
        echo[offset:] = mix[: total_len - offset] * gain
        out += echo
        gain *= feedback
    return out


def _apply_sega_clip(mix: np.ndarray, threshold: float = 0.72) -> np.ndarray:
    """Soft saturation approximating the YM2612 DAC's characteristic digital edge.

    The YM2612 used a 9-bit DAC that introduced a subtle but recognizable
    harmonic distortion at higher amplitudes. We model this with a piecewise
    cubic soft-clip: linear below threshold, curved above it, clamped at 1.0.
    This adds odd-order harmonics without hard digital square-wave distortion.
    """
    out = mix.copy()
    high = np.abs(out) > threshold
    sign = np.sign(out[high])
    excess = (np.abs(out[high]) - threshold) / (1.0 - threshold)  # 0-1 in overdrive zone
    curved = threshold + (1.0 - threshold) * (1.5 * excess - 0.5 * excess ** 3)
    out[high] = sign * np.clip(curved, 0.0, 1.0)
    return out.astype(np.float32)


def _assign_voices_snes(midi: pretty_midi.PrettyMIDI) -> list[list[_ChipNote]]:
    """8-voice SNES allocator, output merged into 4 mixer groups.

    Internal slots:
        0, 1  -> lead group     (high-pitch melodic / treble)
        2, 3  -> harmony group  (mid-pitch melodic / chords)
        4, 5  -> bass group     (low-pitch melodic / sub-bass)
        6, 7  -> noise group    (drums)

    Two slots per group allow simultaneous polyphony (chord hits) without
    stealing, matching how SNES games reserved pairs of voices per section.
    """
    drum: list[_ChipNote] = []
    melodic: list[_ChipNote] = []
    for inst in midi.instruments:
        for n in inst.notes:
            cn = _ChipNote(pitch=int(n.pitch), start=float(n.start),
                           end=float(n.end), velocity=int(n.velocity))
            (drum if inst.is_drum else melodic).append(cn)

    melodic.sort(key=lambda n: (n.start, n.pitch))

    # 8 internal slots; free_at[i] = earliest time slot i is available
    free_at = [0.0] * 8
    groups: list[list[_ChipNote]] = [[], [], [], [], [], [], [], []]

    for n in melodic:
        if n.pitch >= 68:
            candidates = [0, 1, 2, 3]     # prefer lead, fall back to harmony
        elif n.pitch >= 48:
            candidates = [2, 3, 0, 1]     # prefer harmony, fall back to lead
        else:
            candidates = [4, 5, 2, 3]     # prefer bass, fall back to harmony

        chosen = min(candidates, key=lambda i: free_at[i])
        groups[chosen].append(n)
        free_at[chosen] = max(free_at[chosen], n.end)

    # Merge slots into 4 mixer groups
    lead = sorted(groups[0] + groups[1], key=lambda n: n.start)
    harm = sorted(groups[2] + groups[3], key=lambda n: n.start)
    bass = sorted(groups[4] + groups[5], key=lambda n: n.start)
    return [lead, harm, bass, drum]


def _assign_voices_sega(midi: pretty_midi.PrettyMIDI) -> list[list[_ChipNote]]:
    """6-channel YM2612 allocator, output merged into 4 mixer groups.

    The YM2612 has 6 FM channels; channel 6 can switch to a DAC/noise rhythm
    mode. We model this as:
        Slots 0-2 -> lead group    (3 channels for high-pitch melody/brass)
        Slots 3-4 -> harmony group (2 channels for mid-range chords)
        Slot 5    -> bass group    (1 channel for low bass)

    Drums are always separated into the noise group (equivalent to YM2612
    channel-6 rhythm mode).

    More slots for lead reflects how Genesis composers dedicated more channels
    to the primary melody to compensate for FM's limited polyphony.
    """
    drum: list[_ChipNote] = []
    melodic: list[_ChipNote] = []
    for inst in midi.instruments:
        for n in inst.notes:
            cn = _ChipNote(pitch=int(n.pitch), start=float(n.start),
                           end=float(n.end), velocity=int(n.velocity))
            (drum if inst.is_drum else melodic).append(cn)

    melodic.sort(key=lambda n: (n.start, n.pitch))

    free_at = [0.0] * 6
    groups: list[list[_ChipNote]] = [[], [], [], [], [], []]

    for n in melodic:
        if n.pitch >= 65:
            candidates = [0, 1, 2, 3, 4]   # lead channels first, then harmony
        elif n.pitch >= 46:
            candidates = [3, 4, 0, 1, 2]   # harmony channels first, then lead
        else:
            candidates = [5, 3, 4]         # bass slot first, then harmony

        chosen = min(candidates, key=lambda i: free_at[i])
        groups[chosen].append(n)
        free_at[chosen] = max(free_at[chosen], n.end)

    # Merge into 4 mixer groups: lead=slots 0-2, harm=slots 3-4, bass=slot 5
    lead = sorted(groups[0] + groups[1] + groups[2], key=lambda n: n.start)
    harm = sorted(groups[3] + groups[4], key=lambda n: n.start)
    bass = groups[5]
    return [lead, harm, bass, drum]


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

    if engine == ENGINE_SNES:
        if voice_idx == V_PULSE_LEAD:
            return _wave_snes_lead, _env_snes, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_PULSE_HARM:
            return _wave_snes_harm, _env_snes, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_TRIANGLE:
            return _wave_snes_bass, _env_snes_bass, BASE_VOICE_GAINS[voice_idx]
        return None, _env_drum, BASE_VOICE_GAINS[voice_idx]

    if engine == ENGINE_SEGA:
        if voice_idx == V_PULSE_LEAD:
            return _wave_sega_lead, _env_sega_lead, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_PULSE_HARM:
            return _wave_sega_harm, _env_sega_harm, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_TRIANGLE:
            return _wave_sega_bass, _env_sega_bass, BASE_VOICE_GAINS[voice_idx]
        return None, _env_drum, BASE_VOICE_GAINS[voice_idx]

    if engine == ENGINE_SID:
        if voice_idx == V_PULSE_LEAD:
            return _wave_sid_pulse, _env_sid_lead, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_PULSE_HARM:
            return _wave_sid_saw, _env_sid_harm, BASE_VOICE_GAINS[voice_idx]
        if voice_idx == V_TRIANGLE:
            return _wave_sid_bass, _env_sid_bass, BASE_VOICE_GAINS[voice_idx]
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
    monitor_callback: Callable[[np.ndarray, int], None] | None = None,
) -> Path:
    """Render a MIDI through the chiptune engine to a 16-bit stereo WAV.

    `midi` may be a `pretty_midi.PrettyMIDI` instance or a path to an SMF.
    Output is normalized to -3 dB to prevent clipping.
    """
    log = log or (lambda _m: None)
    if engine not in SUPPORTED_ENGINES:
        raise ChiptuneError(f"Unsupported chiptune engine: {engine}")
    if isinstance(midi, str | Path):
        midi = pretty_midi.PrettyMIDI(str(midi))

    note_count = sum(len(inst.notes) for inst in midi.instruments)
    if note_count == 0:
        raise ChiptuneError("MIDI contains no notes to render.")

    if engine == ENGINE_SNES:
        voices = _assign_voices_snes(midi)
        engine_label = "SNES SPC700"
    elif engine == ENGINE_SEGA:
        voices = _assign_voices_sega(midi)
        engine_label = "Sega Genesis YM2612"
    elif engine == ENGINE_SID:
        voices = _assign_voices(midi)
        engine_label = "C64 SID"
    else:
        voices = _assign_voices(midi)
        engine_label = "Game Boy DMG" if engine == ENGINE_GAME_BOY else "NES"
    voice_gains = _voice_mixer_gains(voice_volumes, voice_mutes, voice_solos)
    end_times = [n.end for vlist in voices for n in vlist]
    total_seconds = (max(end_times) if end_times else 0.0) + 1.0
    total_samples = int(total_seconds * sample_rate)
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
        if monitor_callback is not None:
            _emit_monitor_chunk(mix, sample_rate, monitor_callback)

    if engine == ENGINE_SNES:
        mix = _apply_snes_gaussian(mix)
        mix = _apply_snes_echo(mix, sample_rate)
    elif engine == ENGINE_SEGA:
        mix = _apply_sega_clip(mix)
    elif engine == ENGINE_SID:
        mix = _apply_sid_filter(mix, sample_rate)

    peak = float(np.max(np.abs(mix)))
    if peak <= 0.0:
        raise ChiptuneError("Chiptune render produced silence.")
    mix = mix / peak * 0.85

    stereo = np.column_stack([mix, mix])
    out_int16 = (stereo * 32767.0).astype(np.int16)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav_path), out_int16, sample_rate, subtype="PCM_16")

    if monitor_callback is not None:
        _emit_monitor_chunk(mix, sample_rate, monitor_callback)

    return output_wav_path


def _emit_monitor_chunk(
    mix: np.ndarray,
    sample_rate: int,
    callback: Callable[[np.ndarray, int], None],
) -> None:
    """Send a normalized stereo int16 chunk to the monitor callback."""
    peak = float(np.max(np.abs(mix))) or 1.0
    normalized = mix / peak * 0.7
    chunk_size = min(len(normalized), sample_rate * 2)
    mono_chunk = normalized[:chunk_size]
    stereo_chunk = np.column_stack([mono_chunk, mono_chunk])
    callback((stereo_chunk * 32767).astype(np.int16), sample_rate)
