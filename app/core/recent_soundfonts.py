"""Persistence helpers for recently used SoundFonts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.soundfonts import SF2_EXTS

RECENT_SOUNDFONTS_LIMIT = 5
SETTINGS_PATH = Path.home() / ".tunerize" / "settings.json"
RECENT_SOUNDFONTS_KEY = "recent_soundfonts"


def normalize_path_key(path: Path | str) -> str:
    """Return a stable comparison key for a filesystem path."""
    try:
        return str(Path(path).expanduser().resolve(strict=False)).casefold()
    except OSError:
        return str(Path(path).expanduser()).casefold()


def load_recent_soundfonts(
    settings_path: Path | None = None,
    *,
    limit: int = RECENT_SOUNDFONTS_LIMIT,
    existing_only: bool = True,
) -> list[Path]:
    """Load recent SoundFont paths, filtering duplicates and stale entries."""
    data = _read_settings(settings_path)
    raw_entries = data.get(RECENT_SOUNDFONTS_KEY, [])
    if not isinstance(raw_entries, list):
        return []

    recent: list[Path] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, str):
            continue
        path = Path(raw).expanduser()
        key = normalize_path_key(path)
        if key in seen or path.suffix.lower() not in SF2_EXTS:
            continue
        if existing_only and not path.exists():
            continue
        seen.add(key)
        recent.append(path)
        if len(recent) >= limit:
            break
    return recent


def remember_soundfont(
    soundfont_path: Path | str,
    settings_path: Path | None = None,
    *,
    limit: int = RECENT_SOUNDFONTS_LIMIT,
) -> list[Path]:
    """Move a SoundFont to the front of the persisted recent list."""
    path = Path(soundfont_path).expanduser()
    if path.suffix.lower() not in SF2_EXTS:
        raise ValueError(f"Not a SoundFont path: {path}")

    data = _read_settings(settings_path)
    prior = load_recent_soundfonts(settings_path, limit=limit * 2, existing_only=False)
    current_key = normalize_path_key(path)

    updated: list[Path] = [path]
    seen: set[str] = {current_key}
    for item in prior:
        key = normalize_path_key(item)
        if key in seen:
            continue
        seen.add(key)
        updated.append(item)
        if len(updated) >= limit:
            break

    data[RECENT_SOUNDFONTS_KEY] = [str(item) for item in updated[:limit]]
    _write_settings(data, settings_path)
    return updated[:limit]


def _read_settings(settings_path: Path | None = None) -> dict[str, Any]:
    path = settings_path or SETTINGS_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_settings(data: dict[str, Any], settings_path: Path | None = None) -> None:
    path = settings_path or SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
