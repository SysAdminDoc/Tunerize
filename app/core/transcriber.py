"""Audio -> MIDI transcription via Spotify Basic Pitch (ONNX backend)."""
from __future__ import annotations

from pathlib import Path

import pretty_midi


class TranscriptionError(Exception):
    pass


def transcribe(
    audio_path: Path,
    *,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_length_ms: int = 58,
) -> pretty_midi.PrettyMIDI:
    """Run Basic Pitch on the audio file and return a PrettyMIDI object.

    Requires `basic-pitch` and `onnxruntime` installed. Will not pull in
    TensorFlow if it isn't already present — basic-pitch falls back to
    ONNX automatically.
    """
    try:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except ImportError as e:
        raise TranscriptionError(
            "basic-pitch is not installed. Run:\n"
            "    pip install basic-pitch onnxruntime"
        ) from e

    try:
        result = predict(
            str(audio_path),
            model_or_model_path=ICASSP_2022_MODEL_PATH,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_length_ms,
        )
    except Exception as e:
        raise TranscriptionError(f"Basic Pitch failed: {e}") from e

    if isinstance(result, tuple) and len(result) >= 2:
        midi_data = result[1]
    else:
        midi_data = result

    if midi_data is None:
        raise TranscriptionError("Basic Pitch returned no MIDI data.")

    return midi_data
