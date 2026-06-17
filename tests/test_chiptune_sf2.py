"""Tests for chiptune-to-SF2 export."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES, ENGINE_SEGA, ENGINE_SNES
from app.core.chiptune_sf2 import export_chiptune_sf2
from app.core.soundfonts import get_info, validate_sf2


@pytest.fixture
def tmp_sf2(tmp_path: Path) -> Path:
    return tmp_path / "chip.sf2"


@pytest.mark.parametrize("engine", [ENGINE_NES, ENGINE_GAME_BOY, ENGINE_SNES, ENGINE_SEGA])
class TestChiptuneSF2Export:
    def test_produces_valid_sf2(self, engine: str, tmp_sf2: Path) -> None:
        result = export_chiptune_sf2(engine, tmp_sf2)
        assert result.exists()
        valid, err = validate_sf2(result)
        assert valid, f"Invalid SF2 for {engine}: {err}"

    def test_has_four_presets(self, engine: str, tmp_sf2: Path) -> None:
        export_chiptune_sf2(engine, tmp_sf2)
        info = get_info(tmp_sf2)
        assert info.preset_count == 4

    def test_has_multi_samples(self, engine: str, tmp_sf2: Path) -> None:
        export_chiptune_sf2(engine, tmp_sf2)
        info = get_info(tmp_sf2)
        assert info.sample_count >= 4

    def test_reasonable_file_size(self, engine: str, tmp_sf2: Path) -> None:
        export_chiptune_sf2(engine, tmp_sf2)
        size_kb = tmp_sf2.stat().st_size / 1024
        assert 500 < size_kb < 10000


class TestChiptuneSF2EdgeCases:
    def test_unknown_engine_raises(self, tmp_sf2: Path) -> None:
        with pytest.raises(ValueError, match="Unknown engine"):
            export_chiptune_sf2("commodore64", tmp_sf2)

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "chip.sf2"
        result = export_chiptune_sf2(ENGINE_NES, deep)
        assert result.exists()

    def test_preset_names_match_engine(self, tmp_sf2: Path) -> None:
        export_chiptune_sf2(ENGINE_NES, tmp_sf2)
        info = get_info(tmp_sf2)
        names = {p.name for p in info.presets}
        assert "NES Pulse 50%" in names
        assert "NES Triangle" in names

    def test_sega_preset_names(self, tmp_sf2: Path) -> None:
        export_chiptune_sf2(ENGINE_SEGA, tmp_sf2)
        info = get_info(tmp_sf2)
        names = {p.name for p in info.presets}
        assert "Sega FM Lead" in names
