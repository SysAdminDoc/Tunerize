"""Tests for app.core.soundfonts."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from app.core.soundfonts import SoundFontLibrary, get_info, read_presets, validate_sf2


def test_validate_sf2_accepts_valid_header(fake_sf2):
    is_valid, err = validate_sf2(fake_sf2)
    assert is_valid is True
    assert err is None


def test_validate_sf2_rejects_garbage(fake_invalid_sf2):
    is_valid, err = validate_sf2(fake_invalid_sf2)
    assert is_valid is False
    assert err is not None


def test_validate_sf2_rejects_too_small(tmp_path):
    p = tmp_path / "tiny.sf2"
    p.write_bytes(b"RI")
    is_valid, err = validate_sf2(p)
    assert is_valid is False
    assert "too small" in err.lower()


def test_get_info_reports_size_mb(fake_sf2):
    info = get_info(fake_sf2)
    assert info.is_valid
    assert info.name == "test"
    assert info.size_mb >= 0


def test_get_info_handles_missing_file(tmp_path):
    info = get_info(tmp_path / "does-not-exist.sf2")
    assert not info.is_valid
    assert "does not exist" in (info.error or "").lower()


def test_library_scan_empty(tmp_path):
    lib = SoundFontLibrary(tmp_path)
    assert lib.scan() == []


def test_library_scan_finds_sf2(tmp_path, fake_sf2):
    target = tmp_path / "lib"
    lib = SoundFontLibrary(target)
    # Copy via library import
    info = lib.import_file(fake_sf2)
    found = lib.scan()
    assert len(found) == 1
    assert found[0].path == info.path


def test_library_import_rejects_invalid(tmp_path, fake_invalid_sf2):
    lib = SoundFontLibrary(tmp_path / "lib")
    with pytest.raises(ValueError):
        lib.import_file(fake_invalid_sf2)


def test_library_import_handles_name_collision(tmp_path, fake_sf2):
    lib = SoundFontLibrary(tmp_path / "lib")
    a = lib.import_file(fake_sf2)
    b = lib.import_file(fake_sf2)
    assert a.path != b.path
    assert b.path.stem.endswith("__1") or "__" in b.path.stem


def test_read_presets_parses_phdr_records(tmp_path):
    sf2 = _write_sf2_with_presets(tmp_path / "presets.sf2")

    presets = read_presets(sf2)

    assert [p.label for p in presets] == [
        "0:0 - Piano",
        "1:5 - Warm Pad",
        "128:0 - Drum Kit",
    ]


def test_get_info_reports_preset_count(tmp_path):
    sf2 = _write_sf2_with_presets(tmp_path / "presets.sf2")

    info = get_info(sf2)

    assert info.preset_count == 3


def _write_sf2_with_presets(path: Path) -> Path:
    records = b"".join(
        [
            _phdr_record("Warm Pad", preset=5, bank=1, bag_index=1),
            _phdr_record("Piano", preset=0, bank=0, bag_index=0),
            _phdr_record("Drum Kit", preset=0, bank=128, bag_index=2),
            _phdr_record("EOP", preset=0, bank=0, bag_index=3),
        ]
    )
    phdr = b"phdr" + struct.pack("<I", len(records)) + records
    pdta_payload = b"pdta" + phdr
    list_chunk = b"LIST" + struct.pack("<I", len(pdta_payload)) + pdta_payload
    riff_payload = b"sfbk" + list_chunk
    path.write_bytes(b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload)
    return path


def _phdr_record(name: str, *, preset: int, bank: int, bag_index: int) -> bytes:
    raw_name = name.encode("latin-1")[:20].ljust(20, b"\x00")
    return struct.pack("<20sHHHIII", raw_name, preset, bank, bag_index, 0, 0, 0)
