"""Audio file I/O — load, validate, save, transcode."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SUPPORTED_INPUT_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}
SUPPORTED_OUTPUT_FORMATS = ("wav", "flac", "ogg", "mp3")


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


def transcode_wav(wav_path: Path, out_path: Path, fmt: str) -> Path:
    """Convert an existing WAV file to *fmt* (wav/flac/ogg/mp3). Returns *out_path*."""
    fmt = fmt.lower()
    if fmt == "wav":
        if wav_path != out_path:
            shutil.copy2(wav_path, out_path)
        return out_path
    if fmt in ("flac", "ogg"):
        samples, sr = sf.read(str(wav_path), always_2d=False)
        sf.write(str(out_path), samples, sr, format=fmt.upper())
        return out_path
    if fmt == "mp3":
        try:
            import imageio_ffmpeg  # already in requirements; bundles ffmpeg binary
        except ImportError as exc:
            raise AudioError(
                "imageio-ffmpeg is required for MP3 export. Run: pip install imageio-ffmpeg"
            ) from exc
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg_exe, "-y", "-i", str(wav_path), "-q:a", "2", str(out_path)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise AudioError(
                f"ffmpeg MP3 encoding failed: {result.stderr.decode(errors='replace')[:500]}"
            )
        return out_path
    raise AudioError(f"Unknown output format: {fmt!r}. Supported: {SUPPORTED_OUTPUT_FORMATS}")


def get_duration_seconds(path: Path) -> float:
    info = sf.info(str(path))
    return float(info.duration)
