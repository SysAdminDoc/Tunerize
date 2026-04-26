"""Focused UI tests for the online SoundFont browser dialog."""
from __future__ import annotations

from app.core.soundfont_browser import SoundFontResult
from app.ui.browser_dialog import BrowserDialog


def test_browser_dialog_exposes_multiple_sources(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(BrowserDialog, "_do_search", lambda self, query: None)

    dialog = BrowserDialog(tmp_path / "soundfonts")
    qtbot.addWidget(dialog)

    sources = [dialog.source_combo.itemText(i) for i in range(dialog.source_combo.count())]
    assert sources == ["musical-artifacts.com", "github.com topic:soundfont", "reddit r/soundfonts"]

    dialog.source_combo.setCurrentText("github.com topic:soundfont")

    assert dialog.source_combo.currentText() == "github.com topic:soundfont"


def test_browser_dialog_disables_install_for_discovery_only_results(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(BrowserDialog, "_do_search", lambda self, query: None)
    dialog = BrowserDialog(tmp_path / "soundfonts")
    qtbot.addWidget(dialog)
    dialog.model.set_results([
        SoundFontResult(
            source="reddit r/soundfonts",
            name="Community lead",
            author="redditor",
            description="No direct download.",
            license="Community post - verify before use",
            file_url="",
            file_size_bytes=None,
            tags=("soundfont", "reddit", "discussion"),
            download_count=4,
            detail_url="https://www.reddit.com/r/soundfonts/comments/abc123/",
        )
    ])

    dialog.table.selectRow(0)

    assert not dialog.install_btn.isEnabled()
    assert dialog.open_web_btn.isEnabled()
