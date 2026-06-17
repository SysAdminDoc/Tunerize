"""Tests for the SF2 binary writer."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from app.core.sf2_writer import (
    SF2Bank,
    SF2Preset,
    SF2Sample,
    SF2WriteError,
    SF2Zone,
    _sustain_cb,
    _timecents,
    write_sf2,
)
from app.core.soundfonts import get_info, validate_sf2


@pytest.fixture
def tmp_sf2(tmp_path: Path) -> Path:
    return tmp_path / "test.sf2"


def _sine_sample(pitch: int = 60, duration_s: float = 0.5, sr: int = 44100) -> np.ndarray:
    freq = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
    t = np.arange(int(duration_s * sr), dtype=np.float32) / sr
    return (np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)


class TestSF2WriterBasic:
    def test_single_sample_roundtrip(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="TestBank")
        idx = bank.add_sample(SF2Sample(name="Tone", data=_sine_sample()))
        bank.add_preset(SF2Preset(name="TestPreset", zones=[SF2Zone(sample_index=idx)]))
        result = write_sf2(bank, tmp_sf2)

        assert result.exists()
        assert result.stat().st_size > 100
        valid, err = validate_sf2(result)
        assert valid, f"Invalid SF2: {err}"

    def test_riff_header(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="HeaderTest")
        idx = bank.add_sample(SF2Sample(name="S", data=_sine_sample()))
        bank.add_preset(SF2Preset(name="P", zones=[SF2Zone(sample_index=idx)]))
        write_sf2(bank, tmp_sf2)

        with open(tmp_sf2, "rb") as f:
            riff = f.read(4)
            size = struct.unpack("<I", f.read(4))[0]
            form = f.read(4)
        assert riff == b"RIFF"
        assert form == b"sfbk"
        assert size == tmp_sf2.stat().st_size - 8

    def test_preset_info_readable(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="ReadBack")
        idx = bank.add_sample(SF2Sample(name="MySample", data=_sine_sample()))
        bank.add_preset(SF2Preset(
            name="MyPreset", preset_number=42, bank=1,
            zones=[SF2Zone(sample_index=idx)],
        ))
        write_sf2(bank, tmp_sf2)

        info = get_info(tmp_sf2)
        assert info.is_valid
        assert info.preset_count == 1
        assert info.sample_count == 1
        assert info.presets[0].name == "MyPreset"
        assert info.presets[0].preset == 42
        assert info.presets[0].bank == 1

    def test_multi_sample_multi_preset(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="Multi")
        s1 = bank.add_sample(SF2Sample(name="Low", data=_sine_sample(36)))
        s2 = bank.add_sample(SF2Sample(name="Mid", data=_sine_sample(60)))
        s3 = bank.add_sample(SF2Sample(name="High", data=_sine_sample(84)))

        bank.add_preset(SF2Preset(name="Piano", preset_number=0, zones=[
            SF2Zone(sample_index=s1, key_lo=0, key_hi=47),
            SF2Zone(sample_index=s2, key_lo=48, key_hi=71),
            SF2Zone(sample_index=s3, key_lo=72, key_hi=127),
        ]))
        bank.add_preset(SF2Preset(name="Strings", preset_number=1, zones=[
            SF2Zone(sample_index=s2),
        ]))
        write_sf2(bank, tmp_sf2)

        info = get_info(tmp_sf2)
        assert info.preset_count == 2
        assert info.sample_count == 3

    def test_loop_points(self, tmp_sf2: Path) -> None:
        data = _sine_sample(60, duration_s=1.0)
        bank = SF2Bank(name="LoopTest")
        idx = bank.add_sample(SF2Sample(
            name="Looped", data=data,
            loop_start=1000, loop_end=40000, loop_enabled=True,
        ))
        bank.add_preset(SF2Preset(name="P", zones=[
            SF2Zone(sample_index=idx, loop_mode=1),
        ]))
        result = write_sf2(bank, tmp_sf2)
        assert validate_sf2(result)[0]

    def test_adsr_generators(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="ADSR")
        idx = bank.add_sample(SF2Sample(name="S", data=_sine_sample()))
        bank.add_preset(SF2Preset(name="P", zones=[SF2Zone(
            sample_index=idx,
            attack_ms=50.0,
            decay_ms=200.0,
            sustain_pct=30.0,
            release_ms=500.0,
        )]))
        result = write_sf2(bank, tmp_sf2)
        assert validate_sf2(result)[0]
        assert result.stat().st_size > 100


class TestSF2WriterEdgeCases:
    def test_no_samples_raises(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="Empty")
        bank.add_preset(SF2Preset(name="P", zones=[]))
        with pytest.raises(SF2WriteError, match="no samples"):
            write_sf2(bank, tmp_sf2)

    def test_no_presets_raises(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="NoPreset")
        bank.add_sample(SF2Sample(name="S", data=_sine_sample()))
        with pytest.raises(SF2WriteError, match="no presets"):
            write_sf2(bank, tmp_sf2)

    def test_float_data_converted_to_int16(self, tmp_sf2: Path) -> None:
        data = np.sin(np.linspace(0, 2 * np.pi * 440, 22050)).astype(np.float32)
        bank = SF2Bank(name="Float")
        idx = bank.add_sample(SF2Sample(name="FloatSample", data=data))
        assert bank.samples[idx].data.dtype == np.int16
        bank.add_preset(SF2Preset(name="P", zones=[SF2Zone(sample_index=idx)]))
        result = write_sf2(bank, tmp_sf2)
        assert validate_sf2(result)[0]

    def test_long_name_truncated(self, tmp_sf2: Path) -> None:
        bank = SF2Bank(name="A" * 300)
        idx = bank.add_sample(SF2Sample(name="X" * 30, data=_sine_sample()))
        bank.add_preset(SF2Preset(name="Y" * 30, zones=[SF2Zone(sample_index=idx)]))
        result = write_sf2(bank, tmp_sf2)
        assert validate_sf2(result)[0]

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "test.sf2"
        bank = SF2Bank(name="Deep")
        idx = bank.add_sample(SF2Sample(name="S", data=_sine_sample()))
        bank.add_preset(SF2Preset(name="P", zones=[SF2Zone(sample_index=idx)]))
        result = write_sf2(bank, deep)
        assert result.exists()


class TestTimecentsAndSustain:
    def test_timecents_instant(self) -> None:
        assert _timecents(0) == -32768

    def test_timecents_1_second(self) -> None:
        assert _timecents(1000) == 0

    def test_timecents_positive(self) -> None:
        tc = _timecents(2000)
        assert tc > 0

    def test_sustain_full(self) -> None:
        assert _sustain_cb(0.0) == 0

    def test_sustain_silent(self) -> None:
        assert _sustain_cb(100.0) == 1000

    def test_sustain_clamped(self) -> None:
        assert _sustain_cb(200.0) == 1440
