"""MIDI cleanup: tiny-note removal, velocity normalize, transpose, quantize."""
from __future__ import annotations

import pretty_midi


class EmptyMidiError(Exception):
    pass


GRIDS = {
    "1/4": 0.25,
    "1/8": 0.125,
    "1/16": 0.0625,
    "1/32": 0.03125,
}


def clean(
    midi: pretty_midi.PrettyMIDI,
    *,
    transpose: int = 0,
    quantize: bool = False,
    quantize_grid: str = "1/16",
    min_velocity: int = 12,
    normalize_velocity: bool = True,
    min_notes: int = 4,
) -> pretty_midi.PrettyMIDI:
    """Clean up a transcribed MIDI in-place and return it.

    Raises EmptyMidiError if the result has fewer than `min_notes` notes —
    this catches the silent / noise / speech edge case where Basic Pitch
    returns a near-empty MIDI.
    """
    total_notes = sum(len(inst.notes) for inst in midi.instruments)
    if total_notes < min_notes:
        raise EmptyMidiError(
            f"MIDI has only {total_notes} notes — input may be silent, noise, or speech. "
            "Try a different audio source or lower the min-note threshold in advanced settings."
        )

    bpm = _get_tempo(midi)
    sec_per_beat = 60.0 / bpm
    grid_seconds = GRIDS.get(quantize_grid, 0.0625) * 4 * sec_per_beat

    for inst in midi.instruments:
        cleaned: list[pretty_midi.Note] = []
        for note in inst.notes:
            if note.velocity < min_velocity:
                continue
            if transpose:
                new_pitch = note.pitch + transpose
                if new_pitch < 0 or new_pitch > 127:
                    continue
                note.pitch = new_pitch
            if quantize and grid_seconds > 0:
                qstart = round(note.start / grid_seconds) * grid_seconds
                qend = round(note.end / grid_seconds) * grid_seconds
                if qend <= qstart:
                    qend = qstart + grid_seconds
                note.start = qstart
                note.end = qend
            cleaned.append(note)
        inst.notes = cleaned

    if normalize_velocity:
        all_v = [n.velocity for inst in midi.instruments for n in inst.notes]
        if all_v:
            v_min, v_max = min(all_v), max(all_v)
            if v_max > v_min:
                for inst in midi.instruments:
                    for n in inst.notes:
                        scaled = 50 + int((n.velocity - v_min) / (v_max - v_min) * 60)
                        n.velocity = max(1, min(127, scaled))

    remaining = sum(len(inst.notes) for inst in midi.instruments)
    if remaining < min_notes:
        raise EmptyMidiError(
            f"After cleanup only {remaining} notes remained — try lowering velocity/length thresholds."
        )

    return midi


def _get_tempo(midi: pretty_midi.PrettyMIDI) -> float:
    try:
        _, tempi = midi.get_tempo_changes()
        if len(tempi) > 0:
            return float(tempi[0])
    except Exception:
        pass
    return 120.0


def note_count(midi: pretty_midi.PrettyMIDI) -> int:
    return sum(len(inst.notes) for inst in midi.instruments)
