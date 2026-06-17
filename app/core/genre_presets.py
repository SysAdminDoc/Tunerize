"""Genre presets — named bundles of conversion settings.

Each preset configures render mode, chiptune engine, quantization,
transpose, and note-length so users can dial in a sound in one click.
SF2-based presets carry a ``sf2_search_hint`` that the UI can use to
pre-fill the online SoundFont browser.
"""
from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class GenrePreset:
    name: str
    description: str
    chiptune_mode: bool
    engine: str | None = None     # chiptune engine key; None means keep current
    quantize: bool = False
    quantize_grid: str = "1/16"
    transpose: int = 0
    min_note_ms: int = 58
    sf2_search_hint: str = ""     # non-empty → suggest opening the browser


def _make_presets() -> list[GenrePreset]:
    # Import here to avoid a circular import at module load time.
    from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES, ENGINE_SEGA, ENGINE_SNES  # noqa: PLC0415

    return [
        GenrePreset(
            name="NES Chiptune",
            description="Classic 8-bit NES sound — tight quantization, punchy pulse waves.",
            chiptune_mode=True,
            engine=ENGINE_NES,
            quantize=True,
            quantize_grid="1/8",
            transpose=0,
            min_note_ms=80,
        ),
        GenrePreset(
            name="Game Boy",
            description="Handheld DMG-001 tone — softer pulse waves with wave channel warmth.",
            chiptune_mode=True,
            engine=ENGINE_GAME_BOY,
            quantize=True,
            quantize_grid="1/8",
            transpose=0,
            min_note_ms=100,
        ),
        GenrePreset(
            name="SNES RPG",
            description="16-bit SNES orchestral sound — warm BRR samples, subtle echo.",
            chiptune_mode=True,
            engine=ENGINE_SNES,
            quantize=False,
            quantize_grid="1/16",
            transpose=0,
            min_note_ms=60,
        ),
        GenrePreset(
            name="Sega Genesis FM",
            description="YM2612 FM synthesis — metallic leads, FM bass punch.",
            chiptune_mode=True,
            engine=ENGINE_SEGA,
            quantize=False,
            quantize_grid="1/16",
            transpose=0,
            min_note_ms=58,
        ),
        GenrePreset(
            name="General MIDI",
            description="Faithful GM rendering via SoundFont — natural instrument timbre.",
            chiptune_mode=False,
            quantize=False,
            min_note_ms=50,
            sf2_search_hint="FluidR3 GM",
        ),
        GenrePreset(
            name="Orchestral",
            description="Full-orchestra SoundFont rendering — best with a large GM bank.",
            chiptune_mode=False,
            quantize=False,
            min_note_ms=50,
            sf2_search_hint="symphony orchestra",
        ),
        GenrePreset(
            name="Lo-Fi Piano",
            description="Warm, detuned piano feel — intimate character via transpose.",
            chiptune_mode=False,
            quantize=False,
            transpose=-2,
            min_note_ms=80,
            sf2_search_hint="piano",
        ),
        GenrePreset(
            name="Jazz Ensemble",
            description="Swing-feel jazz via SoundFont — minimal quantization for human feel.",
            chiptune_mode=False,
            quantize=False,
            transpose=0,
            min_note_ms=55,
            sf2_search_hint="jazz",
        ),
    ]


# Module-level list populated lazily to avoid import-time side effects.
_PRESETS: list[GenrePreset] | None = None


def get_genre_presets() -> list[GenrePreset]:
    """Return the list of built-in genre presets (created once)."""
    global _PRESETS  # noqa: PLW0603
    if _PRESETS is None:
        _PRESETS = _make_presets()
    return _PRESETS


USER_PRESETS_DIR = Path.home() / ".tunerize" / "presets"


def save_user_preset(preset: GenrePreset) -> Path:
    """Save a user-created preset to disk. Returns the file path."""
    USER_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in preset.name if c.isalnum() or c in "-_ ").strip() or "preset"
    path = USER_PRESETS_DIR / f"{safe_name}.json"
    data = asdict(preset)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_user_presets() -> list[GenrePreset]:
    """Load all user-created presets from disk."""
    if not USER_PRESETS_DIR.is_dir():
        return []
    presets: list[GenrePreset] = []
    for p in sorted(USER_PRESETS_DIR.glob("*.json")):
        with suppress(OSError, ValueError, KeyError, TypeError):
            data = json.loads(p.read_text(encoding="utf-8"))
            presets.append(GenrePreset(
                name=data["name"],
                description=data.get("description", ""),
                chiptune_mode=data["chiptune_mode"],
                engine=data.get("engine"),
                quantize=data.get("quantize", False),
                quantize_grid=data.get("quantize_grid", "1/16"),
                transpose=data.get("transpose", 0),
                min_note_ms=data.get("min_note_ms", 58),
                sf2_search_hint=data.get("sf2_search_hint", ""),
            ))
    return presets


def delete_user_preset(name: str) -> bool:
    """Delete a user preset by name. Returns True if deleted."""
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
    path = USER_PRESETS_DIR / f"{safe_name}.json"
    if path.exists():
        path.unlink()
        return True
    return False
