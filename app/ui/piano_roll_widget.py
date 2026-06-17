"""Read-only piano-roll visualization for transcribed MIDI data."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

import pretty_midi


class PianoRollWidget(QWidget):
    """Renders a read-only piano roll from a PrettyMIDI or SMF file."""

    _BG = QColor("#181825")
    _GRID = QColor("#313244")
    _NOTE = QColor("#89b4fa")
    _DRUM = QColor("#f38ba8")
    _KEY_LABEL = QColor("#6c7086")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMaximumHeight(160)
        self._notes: list[tuple[float, float, int, bool]] = []
        self._duration = 0.0
        self._pitch_lo = 127
        self._pitch_hi = 0

    def set_midi(self, midi: pretty_midi.PrettyMIDI | Path | str | None) -> None:
        if midi is None:
            self._notes = []
            self._duration = 0.0
            self.update()
            return

        if isinstance(midi, (str, Path)):
            midi = pretty_midi.PrettyMIDI(str(midi))

        notes: list[tuple[float, float, int, bool]] = []
        for inst in midi.instruments:
            for n in inst.notes:
                notes.append((n.start, n.end, n.pitch, inst.is_drum))

        self._notes = notes
        if notes:
            self._pitch_lo = max(0, min(n[2] for n in notes) - 2)
            self._pitch_hi = min(127, max(n[2] for n in notes) + 2)
            self._duration = max(n[1] for n in notes)
        else:
            self._pitch_lo = 60
            self._pitch_hi = 72
            self._duration = 0.0
        self.update()

    def clear(self) -> None:
        self.set_midi(None)

    def paintEvent(self, event) -> None:
        if not self._notes or self._duration <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, self._BG)

        pitch_range = max(1, self._pitch_hi - self._pitch_lo)
        note_h = max(1, h / pitch_range)

        grid_pen = QPen(self._GRID, 1)
        painter.setPen(grid_pen)
        for p in range(self._pitch_lo, self._pitch_hi + 1):
            y = int(h - (p - self._pitch_lo) / pitch_range * h)
            painter.drawLine(0, y, w, y)

        for start, end, pitch, is_drum in self._notes:
            x1 = int(start / self._duration * w)
            x2 = max(x1 + 1, int(end / self._duration * w))
            y = int(h - (pitch - self._pitch_lo + 1) / pitch_range * h)
            nh = max(1, int(note_h))
            color = self._DRUM if is_drum else self._NOTE
            painter.fillRect(x1, y, x2 - x1, nh, color)

        painter.end()
