"""Tests for recent SoundFont persistence."""
from __future__ import annotations

import json

import pytest

from app.core.recent_soundfonts import load_recent_soundfonts, remember_soundfont


def test_remember_soundfont_moves_latest_to_front(tmp_path):
    settings = tmp_path / "settings.json"
    first = tmp_path / "first.sf2"
    second = tmp_path / "second.sf2"
    first.touch()
    second.touch()

    remember_soundfont(first, settings)
    remember_soundfont(second, settings)
    remember_soundfont(first, settings)

    assert load_recent_soundfonts(settings) == [first, second]


def test_load_recent_soundfonts_filters_stale_duplicates_and_non_soundfonts(tmp_path):
    settings = tmp_path / "settings.json"
    valid = tmp_path / "valid.sf2"
    valid.touch()
    missing = tmp_path / "missing.sf2"
    wav = tmp_path / "not-a-soundfont.wav"
    wav.touch()
    settings.write_text(
        json.dumps(
            {
                "recent_soundfonts": [
                    str(valid),
                    str(valid),
                    str(missing),
                    str(wav),
                    42,
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_recent_soundfonts(settings) == [valid]


def test_remember_soundfont_preserves_unrelated_settings(tmp_path):
    settings = tmp_path / "settings.json"
    sf2 = tmp_path / "piano.sf2"
    sf2.touch()
    settings.write_text(json.dumps({"window": {"width": 960}}), encoding="utf-8")

    remember_soundfont(sf2, settings)

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["window"] == {"width": 960}
    assert data["recent_soundfonts"] == [str(sf2)]


def test_remember_soundfont_rejects_non_soundfont_path(tmp_path):
    with pytest.raises(ValueError, match="Not a SoundFont"):
        remember_soundfont(tmp_path / "song.wav", tmp_path / "settings.json")
