"""Tests for app.core.cli — argument parsing and exit codes."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.cli import _build_parser, _engine_key, run_cli

# ── parser ────────────────────────────────────────────────────────────────────

def test_parser_requires_subcommand():
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.command is None


def test_parser_convert_defaults():
    parser = _build_parser()
    args = parser.parse_args(["convert", "song.mp3"])
    assert args.input == "song.mp3"
    assert args.sf2 is None
    assert args.engine == "nes"
    assert args.format == "wav"
    assert args.transpose == 0
    assert args.quantize is False
    assert args.stem_separate is False
    assert args.no_midi is False
    assert args.min_note_ms == 58
    assert args.sample_rate == 44100
    assert args.preset == 0
    assert args.bank == 0
    assert args.force_preset is False


def test_parser_convert_with_sf2():
    parser = _build_parser()
    args = parser.parse_args(["convert", "song.mp3", "--sf2", "fluid.sf2", "--format", "flac"])
    assert args.sf2 == "fluid.sf2"
    assert args.format == "flac"


def test_parser_convert_all_flags():
    parser = _build_parser()
    args = parser.parse_args([
        "convert", "song.mp3",
        "--engine", "sega",
        "--format", "mp3",
        "--transpose", "-3",
        "--quantize",
        "--quantize-grid", "1/8",
        "--stem-separate",
        "--no-midi",
        "--min-note-ms", "100",
        "--sample-rate", "22050",
    ])
    assert args.engine == "sega"
    assert args.format == "mp3"
    assert args.transpose == -3
    assert args.quantize is True
    assert args.quantize_grid == "1/8"
    assert args.stem_separate is True
    assert args.no_midi is True
    assert args.min_note_ms == 100
    assert args.sample_rate == 22050


def test_parser_rejects_unknown_engine():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["convert", "song.mp3", "--engine", "sid"])


def test_parser_rejects_unknown_format():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["convert", "song.mp3", "--format", "aiff"])


# ── engine key mapping ────────────────────────────────────────────────────────

def test_engine_key_nes():
    from app.core.chiptune import ENGINE_NES
    assert _engine_key("nes") == ENGINE_NES


def test_engine_key_sega():
    from app.core.chiptune import ENGINE_SEGA
    assert _engine_key("sega") == ENGINE_SEGA


# ── run_cli exit codes ────────────────────────────────────────────────────────

def test_run_cli_no_args_returns_zero():
    assert run_cli([]) == 0


def test_run_cli_missing_input_returns_one():
    assert run_cli(["convert", "/nonexistent/file.mp3"]) == 1


def test_run_cli_missing_sf2_returns_one(tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"RIFF")
    result = run_cli(["convert", str(audio), "--sf2", "/no/such.sf2"])
    assert result == 1


def test_run_cli_pipeline_error_returns_one(tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"not real audio")

    from app.core.pipeline import PipelineError

    with patch("app.core.pipeline.ConversionPipeline.run", side_effect=PipelineError("boom")):
        result = run_cli(["convert", str(audio)])
    assert result == 1


def test_run_cli_success_returns_zero(tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"RIFF")
    midi_out = tmp_path / "out.mid"
    wav_out = tmp_path / "out.wav"

    with patch("app.core.pipeline.ConversionPipeline.run", return_value=(midi_out, wav_out)):
        result = run_cli(["convert", str(audio)])
    assert result == 0
