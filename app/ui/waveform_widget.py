"""Lightweight waveform display widget for audio preview."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class _LoadWorker(QThread):
    loaded = Signal(object, int)  # (mono float32 array, sample_rate)

    def __init__(self, path: Path):
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            import librosa
            y, sr = librosa.load(str(self._path), sr=22050, mono=True, duration=600)
            self.loaded.emit(y.astype(np.float32), sr)
        except Exception:
            self.loaded.emit(None, 0)


class WaveformWidget(QWidget):
    """Draws a waveform strip from audio data. Loads async to avoid UI freeze."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setMaximumHeight(80)
        self._samples: np.ndarray | None = None
        self._peaks: np.ndarray | None = None
        self._duration_s = 0.0
        self._worker: _LoadWorker | None = None

        self._info_label = QLabel()
        self._info_label.setObjectName("sfMeta")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._info_label)

    def load_file(self, path: Path) -> None:
        self._samples = None
        self._peaks = None
        self._info_label.setText("Loading waveform…")
        self.update()

        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)

        self._worker = _LoadWorker(path)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.start()

    def clear(self) -> None:
        self._samples = None
        self._peaks = None
        self._duration_s = 0.0
        self._info_label.setText("")
        self.update()

    def _on_loaded(self, samples, sr: int) -> None:
        if samples is None or sr == 0:
            self._info_label.setText("Could not load waveform.")
            return
        self._samples = samples
        self._duration_s = len(samples) / sr
        self._info_label.setText(f"{self._duration_s:.1f}s")
        self._peaks = self._compute_peaks(samples, self.width())
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._samples is not None:
            self._peaks = self._compute_peaks(self._samples, self.width())

    @staticmethod
    def _compute_peaks(samples: np.ndarray, width: int) -> np.ndarray:
        width = max(width, 1)
        n = len(samples)
        if n == 0:
            return np.zeros(width, dtype=np.float32)
        chunk = max(1, n // width)
        trimmed = samples[: chunk * width]
        if len(trimmed) == 0:
            return np.zeros(width, dtype=np.float32)
        reshaped = trimmed.reshape(-1, chunk)
        return np.max(np.abs(reshaped), axis=1).astype(np.float32)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._peaks is None or len(self._peaks) == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height() - 16
        mid_y = 8 + h // 2

        pen = QPen(QColor("#89b4fa"), 1)
        painter.setPen(pen)

        peaks = self._peaks
        if len(peaks) != w:
            peaks = self._compute_peaks(self._samples, w) if self._samples is not None else peaks

        peak_max = float(np.max(peaks)) if len(peaks) > 0 else 1.0
        if peak_max < 1e-6:
            peak_max = 1.0

        for x in range(min(len(peaks), w)):
            amp = peaks[x] / peak_max
            bar_h = int(amp * (h // 2))
            if bar_h < 1:
                bar_h = 1
            painter.drawLine(x, mid_y - bar_h, x, mid_y + bar_h)

        painter.end()
