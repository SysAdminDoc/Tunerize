"""Focused tests for SoundFont rendering helpers."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np

from app.core.renderer import render_preview


def test_render_preview_uses_selected_bank_and_preset(monkeypatch, tmp_path):
    selected: dict[str, tuple[int, int, int]] = {}

    class FakeSynth:
        def __init__(self, *, samplerate: float):
            self.samplerate = samplerate

        def sfload(self, path: str) -> int:
            selected["path"] = (len(path), 0, 0)
            return 7

        def program_select(self, channel: int, sfid: int, bank: int, preset: int) -> None:
            selected["program"] = (channel, bank, preset)
            assert sfid == 7

        def noteon(self, channel: int, note: int, velocity: int) -> None:
            assert channel == 0
            assert note > 0
            assert velocity > 0

        def noteoff(self, channel: int, note: int) -> None:
            assert channel == 0
            assert note > 0

        def get_samples(self, n_samples: int) -> bytes:
            audio = np.full(n_samples * 2, 256, dtype=np.int16)
            return audio.tobytes()

        def delete(self) -> None:
            selected["deleted"] = (1, 0, 0)

    monkeypatch.setitem(sys.modules, "fluidsynth", SimpleNamespace(Synth=FakeSynth))

    sf2 = tmp_path / "fake.sf2"
    sf2.write_bytes(b"RIFF")
    out = render_preview(sf2, tmp_path / "preview.wav", bank=1, preset=5, duration_seconds=0.2)

    assert out.exists()
    assert selected["program"] == (0, 1, 5)
    assert selected["deleted"] == (1, 0, 0)
