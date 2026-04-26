"""SoundFont library: scan folder, validate (RIFF/sfbk), import files, inspect presets."""
from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

SF2_RIFF_MAGIC = b"RIFF"
SF2_FORM_MAGIC = b"sfbk"
SF2_EXTS = (".sf2", ".sf3")
PHDR_RECORD_SIZE = 38


@dataclass(frozen=True)
class SoundFontPreset:
    bank: int
    preset: int
    name: str

    @property
    def label(self) -> str:
        return f"{self.bank}:{self.preset} - {self.name}"


@dataclass(frozen=True)
class SoundFontInfo:
    path: Path
    name: str
    size_mb: float
    is_valid: bool
    error: str | None = None
    presets: tuple[SoundFontPreset, ...] = ()

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def preset_count(self) -> int:
        return len(self.presets)


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
    presets = read_presets(path) if is_valid else ()
    return SoundFontInfo(
        path=path,
        name=path.stem,
        size_mb=size_mb,
        is_valid=is_valid,
        error=err,
        presets=presets,
    )


def read_presets(path: Path) -> tuple[SoundFontPreset, ...]:
    """Read bank/preset headers from a SoundFont's `pdta/phdr` chunk."""
    try:
        with open(path, "rb") as f:
            header = f.read(12)
            if len(header) < 12:
                return ()
            riff, riff_size, form = struct.unpack("<4sI4s", header)
            if riff != SF2_RIFF_MAGIC or form != SF2_FORM_MAGIC:
                return ()

            riff_end = min(path.stat().st_size, riff_size + 8)
            while f.tell() + 8 <= riff_end:
                chunk_id, chunk_size = _read_chunk_header(f)
                chunk_start = f.tell()
                chunk_end = min(chunk_start + chunk_size, riff_end)
                if chunk_id == b"LIST" and chunk_size >= 4:
                    list_type = f.read(4)
                    if list_type == b"pdta":
                        return _read_pdta_presets(f, chunk_end)
                f.seek(chunk_end + (chunk_size % 2))
    except (OSError, struct.error):
        return ()
    return ()


def _read_pdta_presets(f, pdta_end: int) -> tuple[SoundFontPreset, ...]:
    while f.tell() + 8 <= pdta_end:
        chunk_id, chunk_size = _read_chunk_header(f)
        chunk_start = f.tell()
        chunk_end = min(chunk_start + chunk_size, pdta_end)
        if chunk_id == b"phdr":
            data = f.read(chunk_end - chunk_start)
            return _parse_phdr(data)
        f.seek(chunk_end + (chunk_size % 2))
    return ()


def _read_chunk_header(f) -> tuple[bytes, int]:
    raw = f.read(8)
    if len(raw) < 8:
        raise struct.error("Incomplete chunk header")
    return struct.unpack("<4sI", raw)


def _parse_phdr(data: bytes) -> tuple[SoundFontPreset, ...]:
    if len(data) < PHDR_RECORD_SIZE * 2 or len(data) % PHDR_RECORD_SIZE != 0:
        return ()

    presets: list[SoundFontPreset] = []
    record_count = len(data) // PHDR_RECORD_SIZE
    for idx in range(record_count - 1):  # final record is the required EOP terminator
        record = data[idx * PHDR_RECORD_SIZE:(idx + 1) * PHDR_RECORD_SIZE]
        raw_name, preset, bank, _bag_idx, _library, _genre, _morphology = struct.unpack("<20sHHHIII", record)
        name = raw_name.split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()
        if not name or name.upper() == "EOP":
            continue
        presets.append(SoundFontPreset(bank=bank, preset=preset, name=name))

    return tuple(sorted(presets, key=lambda p: (p.bank, p.preset, p.name.lower())))


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
