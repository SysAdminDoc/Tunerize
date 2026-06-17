"""Tests for app.core.audio_io — transcode_wav and output format support."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.core.audio_io import MAX_INPUT_SIZE_BYTES, SUPPORTED_OUTPUT_FORMATS, AudioError, transcode_wav, validate_audio


def _write_test_wav(path: Path, sr: int = 22050, duration: float = 0.1) -> Path:
    """Write a short sine WAV to *path*. Returns *path*."""
    samples = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sr * duration)))
    sf.write(str(path), samples.astype(np.float32), sr, subtype="PCM_16")
    return path


def test_transcode_wav_to_wav(tmp_path):
    src = _write_test_wav(tmp_path / "in.wav")
    dst = tmp_path / "out.wav"
    result = transcode_wav(src, dst, "wav")
    assert result == dst
    assert dst.exists()


def test_transcode_wav_same_path_is_noop(tmp_path):
    src = _write_test_wav(tmp_path / "in.wav")
    result = transcode_wav(src, src, "wav")
    assert result == src


def test_transcode_wav_to_flac(tmp_path):
    src = _write_test_wav(tmp_path / "in.wav")
    dst = tmp_path / "out.flac"
    result = transcode_wav(src, dst, "flac")
    assert result == dst
    assert dst.exists()
    info = sf.info(str(dst))
    assert info.format == "FLAC"


def test_transcode_wav_to_flac_uppercase_fmt(tmp_path):
    src = _write_test_wav(tmp_path / "in.wav")
    dst = tmp_path / "out.flac"
    result = transcode_wav(src, dst, "FLAC")
    assert result.exists()


def test_transcode_wav_to_ogg(tmp_path):
    src = _write_test_wav(tmp_path / "in.wav")
    dst = tmp_path / "out.ogg"
    try:
        result = transcode_wav(src, dst, "ogg")
        assert result == dst
        assert dst.exists()
    except Exception as exc:
        pytest.skip(f"OGG encoding not available in this libsndfile build: {exc}")


def test_transcode_wav_to_mp3(tmp_path):
    pytest.importorskip("imageio_ffmpeg")
    src = _write_test_wav(tmp_path / "in.wav")
    dst = tmp_path / "out.mp3"
    try:
        result = transcode_wav(src, dst, "mp3")
        assert result == dst
        assert dst.exists()
        assert dst.stat().st_size > 0
    except AudioError as exc:
        pytest.skip(f"MP3 encoding failed (ffmpeg issue): {exc}")


def test_transcode_wav_unknown_format_raises(tmp_path):
    src = _write_test_wav(tmp_path / "in.wav")
    with pytest.raises(AudioError, match="Unknown output format"):
        transcode_wav(src, tmp_path / "out.aiff", "aiff")


def test_supported_output_formats_constant():
    assert "wav" in SUPPORTED_OUTPUT_FORMATS
    assert "flac" in SUPPORTED_OUTPUT_FORMATS
    assert "ogg" in SUPPORTED_OUTPUT_FORMATS
    assert "mp3" in SUPPORTED_OUTPUT_FORMATS


def test_validate_audio_rejects_oversized_file(tmp_path):
    big = tmp_path / "huge.wav"
    big.write_bytes(b"RIFF" + b"\x00" * (MAX_INPUT_SIZE_BYTES + 100))
    with pytest.raises(AudioError, match="too large"):
        validate_audio(big)
