"""Audio file I/O — load, validate, save."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SUPPORTED_INPUT_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}


class AudioError(Exception):
    pass


def validate_audio(path: Path) -> None:
    """Raise AudioError if the file isn't a usable input."""
    if not path.exists():
        raise AudioError(f"Audio file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_INPUT_EXTS:
        raise AudioError(
            f"Unsupported audio extension: {path.suffix} "
            f"(supported: {sorted(SUPPORTED_INPUT_EXTS)})"
        )
    if path.stat().st_size == 0:
        raise AudioError(f"Audio file is empty: {path}")


def load_audio(path: Path, sample_rate: int = 22050) -> tuple[np.ndarray, int]:
    """Load audio as mono float32 at the requested sample rate."""
    try:
        import librosa
    except ImportError as e:
        raise AudioError("librosa is not installed.") from e
    try:
        y, sr = librosa.load(str(path), sr=sample_rate, mono=True)
        return y.astype(np.float32), sr
    except Exception as e:
        raise AudioError(f"Failed to load {path.name}: {e}") from e


def save_wav(path: Path, samples: np.ndarray, sample_rate: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples, sample_rate, subtype="PCM_16")
    return path


def get_duration_seconds(path: Path) -> float:
    info = sf.info(str(path))
    return float(info.duration)
