"""Real-time audio monitoring — plays render output through speakers as it streams.

Uses QAudioSink (Qt6 multimedia) when available. Falls back gracefully to
no-op if Qt multimedia is not present.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

MonitorCallback = Callable[[np.ndarray, int], None]

_HAS_AUDIO_SINK = False
try:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
    _HAS_AUDIO_SINK = True
except ImportError:
    pass


def is_monitoring_available() -> bool:
    if not _HAS_AUDIO_SINK:
        return False
    try:
        devices = QMediaDevices.audioOutputs()
        return len(devices) > 0
    except Exception:
        return False


class AudioMonitor:
    """Streams int16 stereo PCM chunks to the default audio output device."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self._sample_rate = sample_rate
        self._sink = None
        self._io_device = None
        self._active = False

    def start(self) -> bool:
        if not _HAS_AUDIO_SINK:
            return False
        try:
            fmt = QAudioFormat()
            fmt.setSampleRate(self._sample_rate)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                return False

            self._sink = QAudioSink(device, fmt)
            self._sink.setBufferSize(self._sample_rate * 4)
            self._io_device = self._sink.start()
            self._active = self._io_device is not None
            return self._active
        except Exception:
            self._active = False
            return False

    def write_chunk(self, stereo_int16: np.ndarray) -> None:
        if not self._active or self._io_device is None:
            return
        try:
            data = stereo_int16.tobytes()
            self._io_device.write(data)
        except Exception:
            pass

    def stop(self) -> None:
        self._active = False
        if self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                pass
            self._sink = None
            self._io_device = None

    @property
    def active(self) -> bool:
        return self._active


def noop_monitor_callback(chunk: np.ndarray, sample_rate: int) -> None:
    pass
