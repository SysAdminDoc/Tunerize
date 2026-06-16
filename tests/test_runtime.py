"""Tests for native runtime path setup."""
from __future__ import annotations

import os
import sys

from app.core.runtime import ensure_bundled_runtime_paths


def test_ensure_bundled_runtime_paths_adds_frozen_vendor_dir(monkeypatch, tmp_path):
    vendor = tmp_path / "vendor" / "fluidsynth"
    vendor.mkdir(parents=True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("PATH", "")

    found = ensure_bundled_runtime_paths()

    assert found == (vendor,)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(vendor)
