"""Tests for app.core.pipeline configuration and orchestration scaffolding."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES
from app.core.pipeline import PipelineConfig, _chiptune_suffix


def test_config_requires_sf2_path_when_not_chiptune(tmp_path):
    with pytest.raises(ValueError, match="sf2_path"):
        PipelineConfig(
            audio_path=tmp_path / "in.mp3",
            output_dir=tmp_path / "out",
            sf2_path=None,
            use_chiptune_engine=False,
        )


def test_config_allows_no_sf2_in_chiptune_mode(tmp_path):
    cfg = PipelineConfig(
        audio_path=tmp_path / "in.mp3",
        output_dir=tmp_path / "out",
        sf2_path=None,
        use_chiptune_engine=True,
    )
    assert cfg.use_chiptune_engine is True
    assert cfg.sf2_path is None


def test_config_accepts_sf2_in_sf_mode(tmp_path):
    sf2 = tmp_path / "fake.sf2"
    cfg = PipelineConfig(
        audio_path=tmp_path / "in.mp3",
        output_dir=tmp_path / "out",
        sf2_path=sf2,
        use_chiptune_engine=False,
    )
    assert cfg.sf2_path == sf2


def test_config_defaults():
    cfg = PipelineConfig(
        audio_path=Path("dummy.mp3"),
        output_dir=Path("out"),
        use_chiptune_engine=True,
    )
    assert cfg.transpose == 0
    assert cfg.quantize is False
    assert cfg.export_midi is True
    assert cfg.sample_rate == 44100
    assert cfg.stem_separate is False
    assert cfg.min_note_ms == 58
    assert cfg.sf2_bank == 0
    assert cfg.sf2_preset == 0
    assert cfg.forced_bank == 0
    assert cfg.chiptune_engine == ENGINE_NES
    assert cfg.chiptune_voice_volumes == (1.0, 1.0, 1.0, 1.0)
    assert cfg.chiptune_voice_mutes == (False, False, False, False)
    assert cfg.chiptune_voice_solos == (False, False, False, False)


def test_config_validates_chiptune_voice_control_lengths(tmp_path):
    with pytest.raises(ValueError, match="chiptune_voice_volumes"):
        PipelineConfig(
            audio_path=tmp_path / "in.mp3",
            output_dir=tmp_path / "out",
            use_chiptune_engine=True,
            chiptune_voice_volumes=(1.0, 1.0),  # type: ignore[arg-type]
        )


def test_config_accepts_gameboy_engine(tmp_path):
    cfg = PipelineConfig(
        audio_path=tmp_path / "in.mp3",
        output_dir=tmp_path / "out",
        use_chiptune_engine=True,
        chiptune_engine=ENGINE_GAME_BOY,
    )

    assert cfg.chiptune_engine == ENGINE_GAME_BOY
    assert _chiptune_suffix(cfg.chiptune_engine) == "gameboy"


def test_config_rejects_unknown_chiptune_engine(tmp_path):
    with pytest.raises(ValueError, match="Unsupported chiptune_engine"):
        PipelineConfig(
            audio_path=tmp_path / "in.mp3",
            output_dir=tmp_path / "out",
            use_chiptune_engine=True,
            chiptune_engine="sid",
        )


def test_config_default_output_format():
    cfg = PipelineConfig(
        audio_path=Path("dummy.mp3"),
        output_dir=Path("out"),
        use_chiptune_engine=True,
    )
    assert cfg.output_format == "wav"


def test_config_accepts_supported_output_formats(tmp_path):
    for fmt in ("wav", "flac", "ogg", "mp3"):
        cfg = PipelineConfig(
            audio_path=tmp_path / "in.mp3",
            output_dir=tmp_path / "out",
            use_chiptune_engine=True,
            output_format=fmt,
        )
        assert cfg.output_format == fmt


def test_config_rejects_unknown_output_format(tmp_path):
    with pytest.raises(ValueError, match="Unsupported output_format"):
        PipelineConfig(
            audio_path=tmp_path / "in.mp3",
            output_dir=tmp_path / "out",
            use_chiptune_engine=True,
            output_format="aiff",
        )
