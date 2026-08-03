"""Tests for native runtime path setup."""
from __future__ import annotations

import os
import sys

from app.core.runtime import (
    POLYPHONE_DIR_ENV,
    POLYPHONE_EXE_ENV,
    ensure_bundled_runtime_paths,
    find_polyphone_executable,
)


def test_ensure_bundled_runtime_paths_adds_frozen_vendor_dir(monkeypatch, tmp_path):
    vendor = tmp_path / "vendor" / "fluidsynth"
    vendor.mkdir(parents=True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("PATH", "")

    found = ensure_bundled_runtime_paths()

    assert found == (vendor,)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(vendor)


def test_find_polyphone_executable_prefers_env_exe(monkeypatch, tmp_path):
    polyphone = tmp_path / "custom-polyphone.exe"
    polyphone.write_bytes(b"exe")
    vendor = tmp_path / "vendor" / "polyphone"
    vendor.mkdir(parents=True)
    (vendor / "polyphone.exe").write_bytes(b"bundled")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv(POLYPHONE_EXE_ENV, str(polyphone))

    assert find_polyphone_executable() == polyphone


def test_find_polyphone_executable_finds_env_dir(monkeypatch, tmp_path):
    polyphone = tmp_path / "Polyphone" / "bin" / "polyphone.exe"
    polyphone.parent.mkdir(parents=True)
    polyphone.write_bytes(b"exe")

    monkeypatch.delenv(POLYPHONE_EXE_ENV, raising=False)
    monkeypatch.setenv(POLYPHONE_DIR_ENV, str(tmp_path / "Polyphone"))

    assert find_polyphone_executable() == polyphone
