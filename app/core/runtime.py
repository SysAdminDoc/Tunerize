"""Runtime path helpers for bundled native tools."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLES: list[object] = []
POLYPHONE_EXE_ENV = "TUNERIZE_POLYPHONE_EXE"
POLYPHONE_DIR_ENV = "TUNERIZE_POLYPHONE_DIR"


def app_base_dir() -> Path:
    """Return the unpacked app base for frozen builds, or the repo root in source runs."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def ensure_bundled_runtime_paths() -> tuple[Path, ...]:
    """Expose bundled native runtime folders, such as FluidSynth, to subprocess imports."""
    candidates = (
        app_base_dir() / "vendor" / "fluidsynth",
    )
    found: list[Path] = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        _prepend_to_path(candidate)
        _add_dll_directory(candidate)
        found.append(candidate)
    return tuple(found)


def find_polyphone_executable() -> Path | None:
    """Return the bundled or developer-provided Polyphone executable."""
    exe_name = "polyphone.exe" if sys.platform == "win32" else "polyphone"

    env_exe = os.environ.get(POLYPHONE_EXE_ENV)
    if env_exe:
        candidate = Path(env_exe).expanduser()
        if candidate.is_file():
            return candidate

    env_dir = os.environ.get(POLYPHONE_DIR_ENV)
    if env_dir:
        found = _find_executable_in_dir(Path(env_dir).expanduser(), exe_name)
        if found is not None:
            return found

    return _find_executable_in_dir(app_base_dir() / "vendor" / "polyphone", exe_name)


def _prepend_to_path(path: Path) -> None:
    text = str(path)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if text not in parts:
        os.environ["PATH"] = text + os.pathsep + os.environ.get("PATH", "")


def _add_dll_directory(path: Path) -> None:
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return
    try:
        _DLL_DIRECTORY_HANDLES.append(add_dll_directory(str(path)))
    except OSError:
        return


def _find_executable_in_dir(root: Path, exe_name: str) -> Path | None:
    if not root.is_dir():
        return None
    direct = root / exe_name
    if direct.is_file():
        return direct
    try:
        matches = sorted(root.rglob(exe_name), key=lambda path: len(path.parts))
    except OSError:
        return None
    for match in matches:
        if match.is_file():
            return match
    return None
