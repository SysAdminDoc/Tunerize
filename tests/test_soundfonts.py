"""Tests for app.core.soundfonts."""
from __future__ import annotations

import pytest

from app.core.soundfonts import SoundFontLibrary, get_info, validate_sf2


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
