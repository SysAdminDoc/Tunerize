"""Render MIDI through a SoundFont using FluidSynth."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import mido
import numpy as np
import soundfile as sf


class RenderError(Exception):
    pass


TAIL_SECONDS = 2.0


def render(
    midi_path: Path,
    sf2_path: Path,
    output_wav_path: Path,
    *,
    sample_rate: int = 44100,
    bank: int = 0,
    preset: int = 0,
    force_preset: bool = False,
    forced_preset: int = 0,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    """Render midi_path through sf2_path to output_wav_path (16-bit stereo WAV)."""
    try:
        import fluidsynth
    except ImportError as e:
        raise RenderError(
            "pyFluidSynth is not installed.\n"
            "Run: pip install pyFluidSynth\n"
            "Also install the FluidSynth runtime — Windows: `winget install FluidSynth.FluidSynth`"
        ) from e

    try:
        fs = fluidsynth.Synth(samplerate=float(sample_rate))
    except Exception as e:
        raise RenderError(
            f"Could not start FluidSynth: {e}\n"
            "Ensure the FluidSynth runtime DLL/library is on PATH."
        ) from e

    try:
        sfid = fs.sfload(str(sf2_path))
        if sfid == -1:
            raise RenderError(f"FluidSynth could not load SoundFont: {sf2_path}")

        target_preset = forced_preset if force_preset else preset
        fs.program_select(0, sfid, bank, target_preset)
        active_channels: set[int] = {0}

        midi = mido.MidiFile(str(midi_path))
        chunks: list[np.ndarray] = []

        for msg in midi:
            if cancel_check is not None and cancel_check():
                raise RenderError("Render cancelled by user.")

            if msg.time > 0:
                n_samples = int(msg.time * sample_rate)
                if n_samples > 0:
                    chunks.append(np.frombuffer(fs.get_samples(n_samples), dtype=np.int16))

            if msg.is_meta:
                continue

            channel = 0 if force_preset else getattr(msg, "channel", 0)

            if msg.type == "note_on" and msg.velocity > 0:
                if not force_preset and channel not in active_channels:
                    fs.program_select(channel, sfid, bank, preset)
                    active_channels.add(channel)
                fs.noteon(channel, msg.note, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                fs.noteoff(channel, msg.note)
            elif not force_preset and msg.type == "control_change":
                fs.cc(channel, msg.control, msg.value)
            elif not force_preset and msg.type == "program_change":
                fs.program_change(channel, msg.program)
                active_channels.add(channel)
            elif not force_preset and msg.type == "pitchwheel":
                fs.pitch_bend(channel, msg.pitch)

        # Tail to capture release
        tail = int(TAIL_SECONDS * sample_rate)
        chunks.append(np.frombuffer(fs.get_samples(tail), dtype=np.int16))

    finally:
        try:
            fs.delete()
        except Exception:
            pass

    if not chunks:
        raise RenderError("FluidSynth produced no audio samples.")

    audio = np.concatenate(chunks)
    if audio.size % 2 != 0:
        audio = audio[:-1]
    audio = audio.reshape(-1, 2)

    if int(np.max(np.abs(audio.astype(np.int32)))) == 0:
        raise RenderError(
            "Render produced silent output. The selected SoundFont preset may have "
            "no samples mapped to the transcribed pitch range — try a different preset "
            "or enable Force Preset in advanced settings."
        )

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav_path), audio, sample_rate, subtype="PCM_16")
    return output_wav_path
