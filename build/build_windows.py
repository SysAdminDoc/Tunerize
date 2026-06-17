"""Build a one-file Windows executable with bundled FluidSynth runtime files."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ENTRY = ROOT / "app" / "main.py"
APP_NAME = "Tunerize"
FLUIDSYNTH_ENV = "TUNERIZE_FLUIDSYNTH_DIR"
FLUIDSYNTH_DEST = "vendor/fluidsynth"
POLYPHONE_ENV = "TUNERIZE_POLYPHONE_DIR"
POLYPHONE_EXE = "polyphone.exe"
POLYPHONE_DEST = "vendor/polyphone"
BINARY_SUFFIXES = {".exe", ".dll", ".pyd"}


def main() -> int:
    if sys.platform != "win32":
        print("Windows packaging must be run on Windows.", file=sys.stderr)
        return 1

    try:
        from PyInstaller.__main__ import run as run_pyinstaller
    except ImportError:
        print("PyInstaller is not installed. Run: pip install -r requirements-dev.txt", file=sys.stderr)
        return 1

    fluidsynth_files = discover_fluidsynth_runtime()
    if not fluidsynth_files:
        print(
            "FluidSynth runtime not found. Install FluidSynth or set "
            f"{FLUIDSYNTH_ENV}=C:\\path\\to\\fluidsynth\\bin.",
            file=sys.stderr,
        )
        return 1

    polyphone_runtime = discover_polyphone_runtime()
    if polyphone_runtime is None:
        print(
            "Polyphone runtime not found. Install Polyphone or set "
            f"{POLYPHONE_ENV}=C:\\path\\to\\Polyphone.",
            file=sys.stderr,
        )
        return 1

    args = pyinstaller_args(fluidsynth_files, polyphone_runtime)
    run_pyinstaller(args)
    print(f"Built {ROOT / 'dist' / (APP_NAME + '.exe')}")
    return 0


def pyinstaller_args(
    fluidsynth_files: list[Path],
    polyphone_runtime: tuple[Path, list[Path]] | None = None,
) -> list[str]:
    args = [
        "--name",
        APP_NAME,
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
        "--collect-all",
        "basic_pitch",
        "--collect-all",
        "imageio_ffmpeg",
        "--collect-submodules",
        "app",
    ]

    icon_path = ROOT / "assets" / "icon.ico"
    if icon_path.is_file():
        args.extend(["--icon", str(icon_path)])

    if (ROOT / "assets").is_dir():
        args.extend(["--add-data", _bundle_arg(ROOT / "assets", "assets")])
    if (ROOT / "soundfonts" / "README.md").is_file():
        args.extend(["--add-data", _bundle_arg(ROOT / "soundfonts" / "README.md", "soundfonts")])
    for runtime_file in fluidsynth_files:
        args.extend(["--add-binary", _bundle_arg(runtime_file, FLUIDSYNTH_DEST)])
    if polyphone_runtime is not None:
        polyphone_root, polyphone_files = polyphone_runtime
        args.extend(_runtime_tree_args(polyphone_root, polyphone_files, POLYPHONE_DEST))

    args.append(str(APP_ENTRY))
    return args


def discover_fluidsynth_runtime() -> list[Path]:
    roots: list[Path] = []
    env_dir = os.environ.get(FLUIDSYNTH_ENV)
    if env_dir:
        roots.append(Path(env_dir))

    fluidsynth_exe = shutil.which("fluidsynth.exe") or shutil.which("fluidsynth")
    if fluidsynth_exe:
        roots.append(Path(fluidsynth_exe).parent)

    for base_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(base_var)
        if not base:
            continue
        roots.extend(
            candidate
            for candidate in (
                Path(base) / "FluidSynth" / "bin",
                Path(base) / "Programs" / "FluidSynth" / "bin",
                Path(base) / "Microsoft" / "WinGet" / "Packages",
            )
            if candidate.exists()
        )

    for root in _dedupe_existing_dirs(roots):
        files = _collect_runtime_files(root)
        if files:
            return files
    return []


def discover_polyphone_runtime() -> tuple[Path, list[Path]] | None:
    roots: list[Path] = []
    env_dir = os.environ.get(POLYPHONE_ENV)
    if env_dir:
        roots.append(Path(env_dir))

    polyphone_exe = shutil.which(POLYPHONE_EXE) or shutil.which("polyphone")
    if polyphone_exe:
        roots.append(Path(polyphone_exe).parent)

    for base_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(base_var)
        if not base:
            continue
        roots.extend(
            candidate
            for candidate in (
                Path(base) / "Polyphone",
                Path(base) / "Programs" / "Polyphone",
            )
            if candidate.exists()
        )

    for root in _dedupe_existing_dirs(roots):
        runtime = _collect_polyphone_runtime(root)
        if runtime is not None:
            return runtime
    return None


def _collect_runtime_files(root: Path) -> list[Path]:
    search_roots = [root]
    if root.name.lower() == "packages":
        search_roots = [path for path in root.glob("*FluidSynth*") if path.is_dir()]

    files: list[Path] = []
    for search_root in search_roots:
        for pattern in ("fluidsynth.exe", "libfluidsynth*.dll", "fluidsynth*.dll", "*.dll"):
            files.extend(search_root.rglob(pattern))

    return sorted(
        {path.resolve() for path in files if path.is_file()},
        key=lambda path: (path.suffix.lower() != ".exe", path.name.lower()),
    )


def _collect_polyphone_runtime(root: Path) -> tuple[Path, list[Path]] | None:
    if (root / POLYPHONE_EXE).is_file():
        install_root = root
    else:
        try:
            exe_matches = sorted(root.rglob(POLYPHONE_EXE), key=lambda path: len(path.parts))
        except OSError:
            return None
        if not exe_matches:
            return None
        install_root = root

    files = sorted(
        {path.resolve() for path in install_root.rglob("*") if path.is_file()},
        key=lambda path: path.relative_to(install_root).as_posix().lower(),
    )
    if not any(path.name.lower() == POLYPHONE_EXE for path in files):
        return None
    return install_root, files


def _dedupe_existing_dirs(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if not resolved.is_dir() or resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _bundle_arg(src: Path, dest: str) -> str:
    return f"{src}{os.pathsep}{dest}"


def _runtime_tree_args(root: Path, files: list[Path], dest_root: str) -> list[str]:
    args: list[str] = []
    for runtime_file in files:
        rel_parent = runtime_file.parent.relative_to(root).as_posix()
        dest = dest_root if rel_parent == "." else f"{dest_root}/{rel_parent}"
        flag = "--add-binary" if runtime_file.suffix.lower() in BINARY_SUFFIXES else "--add-data"
        args.extend([flag, _bundle_arg(runtime_file, dest)])
    return args


if __name__ == "__main__":
    raise SystemExit(main())
