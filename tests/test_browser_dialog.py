"""Focused UI tests for the online SoundFont browser dialog."""
from __future__ import annotations

from app.ui.browser_dialog import BrowserDialog


def test_browser_dialog_exposes_multiple_sources(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(BrowserDialog, "_do_search", lambda self, query: None)

    dialog = BrowserDialog(tmp_path / "soundfonts")
    qtbot.addWidget(dialog)

    sources = [dialog.source_combo.itemText(i) for i in range(dialog.source_combo.count())]
    assert sources == ["musical-artifacts.com", "github.com topic:soundfont"]

    dialog.source_combo.setCurrentText("github.com topic:soundfont")

    assert dialog.source_combo.currentText() == "github.com topic:soundfont"
