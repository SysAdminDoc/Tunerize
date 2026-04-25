"""Focused UI tests for main-window workflow helpers."""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

from app.core.recent_soundfonts import remember_soundfont
from app.ui.main_window import MainWindow


class _DropEventStub:
    def __init__(self, urls: list[QUrl]):
        self._mime = QMimeData()
        self._mime.setUrls(urls)

    def mimeData(self) -> QMimeData:
        return self._mime


def test_main_window_prioritizes_recent_soundfonts(qtbot, tmp_path):
    library = tmp_path / "soundfonts"
    library.mkdir()
    first = _write_fake_sf2(library / "first.sf2")
    recent = _write_fake_sf2(library / "recent.sf2")
    settings = tmp_path / "settings.json"
    remember_soundfont(first, settings)
    remember_soundfont(recent, settings)

    window = MainWindow(soundfonts_dir=library, settings_path=settings)
    qtbot.addWidget(window)
    window.mode_sf2.setChecked(True)

    assert window.sf_combo.itemText(0).startswith("Recent: recent")
    assert window.sf_combo.itemData(0) == str(recent)


def test_main_window_drop_helper_accepts_audio_and_blocks_while_busy(qtbot, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.touch()
    window = MainWindow(soundfonts_dir=tmp_path / "soundfonts", settings_path=tmp_path / "settings.json")
    qtbot.addWidget(window)
    event = _DropEventStub([QUrl.fromLocalFile(str(audio))])

    assert window._audio_path_from_drop(event) == audio

    window._set_busy(True)

    assert window._audio_path_from_drop(event) is None


def _write_fake_sf2(path: Path) -> Path:
    path.write_bytes(b"RIFF" + struct.pack("<I", 4) + b"sfbk" + b"\x00" * 32)
    return path
