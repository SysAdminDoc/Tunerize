"""Tests for app.core.midi_cleanup."""
from __future__ import annotations

import pretty_midi
import pytest

from app.core.midi_cleanup import EmptyMidiError, clean, note_count


def test_clean_returns_midi_with_notes(synthetic_midi):
    result = clean(synthetic_midi)
    assert note_count(result) > 0


def test_clean_raises_on_empty(empty_midi):
    with pytest.raises(EmptyMidiError):
        clean(empty_midi)


def test_clean_culls_below_min_notes_threshold():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=60, pitch=60, start=0, end=0.2))
    midi.instruments.append(inst)
    with pytest.raises(EmptyMidiError):
        clean(midi, min_notes=4)


def test_transpose_shifts_pitches(synthetic_midi):
    original = [n.pitch for inst in synthetic_midi.instruments for n in inst.notes if not inst.is_drum]
    cleaned = clean(synthetic_midi, transpose=12)
    shifted = [n.pitch for inst in cleaned.instruments for n in inst.notes if not inst.is_drum]
    assert all(s == o + 12 for o, s in zip(original, shifted))


def test_min_velocity_culls_quiet_notes():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    inst = pretty_midi.Instrument(program=0)
    for i in range(10):
        inst.notes.append(pretty_midi.Note(
            velocity=5 if i < 4 else 80,
            pitch=60 + i, start=i * 0.2, end=i * 0.2 + 0.1,
        ))
    midi.instruments.append(inst)
    cleaned = clean(midi, min_velocity=12, min_notes=1)
    assert note_count(cleaned) == 6


def test_quantize_snaps_starts_to_grid(synthetic_midi):
    cleaned = clean(synthetic_midi, quantize=True, quantize_grid="1/16")
    bpm = 120.0
    grid = (1 / 16) * 4 * (60.0 / bpm)
    for inst in cleaned.instruments:
        for n in inst.notes:
            remainder = (n.start / grid) - round(n.start / grid)
            assert abs(remainder) < 1e-6, f"note start {n.start} not snapped to grid {grid}"


def test_velocity_normalize_bounds(synthetic_midi):
    cleaned = clean(synthetic_midi, normalize_velocity=True)
    for inst in cleaned.instruments:
        for n in inst.notes:
            assert 1 <= n.velocity <= 127


def test_note_count_helper(synthetic_midi):
    n = note_count(synthetic_midi)
    assert n == 16  # 8 piano + 8 drum
