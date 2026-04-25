"""SoundFont library: scan folder, validate (RIFF/sfbk), import files."""
from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

SF2_RIFF_MAGIC = b"RIFF"
SF2_FORM_MAGIC = b"sfbk"
SF2_EXTS = (".sf2", ".sf3")


@dataclass(frozen=True)
class SoundFontInfo:
    path: Path
    name: str
    size_mb: float
    is_valid: bool
    error: str | None = None

    @property
    def stem(self) -> str:
        return self.path.stem


def validate_sf2(path: Path) -> tuple[bool, str | None]:
    """Check the file's RIFF header. Returns (is_valid, error_message)."""
    try:
        with open(path, "rb") as f:
            header = f.read(12)
    except OSError as e:
        return False, f"Read error: {e}"

    if len(header) < 12:
        return False, "File too small to be a SoundFont"

    try:
        riff, _size, form = struct.unpack("<4sI4s", header)
    except struct.error as e:
        return False, f"Header parse error: {e}"

    if riff != SF2_RIFF_MAGIC:
        return False, "Not a RIFF file"
    if form != SF2_FORM_MAGIC:
        return False, "RIFF is not a SoundFont (expected 'sfbk')"
    return True, None


def get_info(path: Path) -> SoundFontInfo:
    if not path.exists():
        return SoundFontInfo(path=path, name=path.stem, size_mb=0.0, is_valid=False, error="File does not exist")

    size_mb = path.stat().st_size / (1024 * 1024)
    is_valid, err = validate_sf2(path)
    return SoundFontInfo(
        path=path,
        name=path.stem,
        size_mb=size_mb,
        is_valid=is_valid,
        error=err,
    )


class SoundFontLibrary:
    """Manages a folder of .sf2/.sf3 SoundFont files."""

    def __init__(self, library_dir: Path):
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)

    def scan(self) -> list[SoundFontInfo]:
        seen: set[Path] = set()
        results: list[SoundFontInfo] = []
        for ext in SF2_EXTS:
            for pattern in (f"*{ext}", f"*{ext.upper()}"):
                for p in sorted(self.library_dir.glob(pattern)):
                    key = p.resolve()
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(get_info(p))
        results.sort(key=lambda s: s.name.lower())
        return results

    def import_file(self, source: Path) -> SoundFontInfo:
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"Source SoundFont not found: {source}")
        if source.suffix.lower() not in SF2_EXTS:
            raise ValueError(f"Not a SoundFont: {source.suffix}")
        is_valid, err = validate_sf2(source)
        if not is_valid:
            raise ValueError(f"Invalid SoundFont: {err}")

        dest = self.library_dir / source.name
        if dest.resolve() == source.resolve():
            return get_info(dest)

        if dest.exists():
            i = 1
            while True:
                alt = self.library_dir / f"{source.stem}__{i}{source.suffix}"
                if not alt.exists():
                    dest = alt
                    break
                i += 1

        shutil.copy2(source, dest)
        return get_info(dest)
