"""Tunerize command-line interface.

Usage:
    tunerize convert <input> [options]
    tunerize batch <input_dir> [options]

Examples:
    tunerize convert song.mp3 --chiptune --engine sega
    tunerize convert song.wav --sf2 nes.sf2 --format mp3 -o ./out
    tunerize batch ./songs --sf2 fluid.sf2 --format flac -o ./out --recursive
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_conversion_args(parser: argparse.ArgumentParser) -> None:
    """Add shared conversion flags to *parser* (used by both convert and batch)."""
    parser.add_argument(
        "--sf2",
        metavar="FILE",
        help="SoundFont to render through. Omit to use the built-in chiptune engine.",
    )
    parser.add_argument(
        "--engine",
        choices=["nes", "gameboy", "snes", "sega"],
        default="nes",
        metavar="ENGINE",
        help="Chiptune engine: nes (default), gameboy, snes, sega. Ignored when --sf2 is given.",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        help="Output directory (default: same folder as input / input folder).",
    )
    parser.add_argument(
        "--format",
        choices=["wav", "flac", "ogg", "mp3"],
        default="wav",
        metavar="FMT",
        help="Output audio format: wav (default), flac, ogg, mp3.",
    )
    parser.add_argument(
        "--transpose",
        type=int,
        default=0,
        metavar="N",
        help="Transpose by N semitones (-24 … +24, default: 0).",
    )
    parser.add_argument("--quantize", action="store_true", help="Quantize MIDI notes to a rhythmic grid.")
    parser.add_argument(
        "--quantize-grid",
        default="1/16",
        choices=["1/4", "1/8", "1/16", "1/32"],
        metavar="GRID",
        help="Quantize grid (default: 1/16). Requires --quantize.",
    )
    parser.add_argument("--stem-separate", action="store_true", help="Run Demucs stem separation before transcription.")
    parser.add_argument("--no-midi", action="store_true", help="Delete the intermediate .mid file after rendering.")
    parser.add_argument(
        "--onset-threshold",
        type=float,
        default=0.5,
        metavar="T",
        help="Basic Pitch onset detection threshold 0.0–1.0 (default: 0.5). Lower = more sensitive.",
    )
    parser.add_argument(
        "--frame-threshold",
        type=float,
        default=0.3,
        metavar="T",
        help="Basic Pitch frame activation threshold 0.0–1.0 (default: 0.3). Lower = more notes detected.",
    )
    parser.add_argument(
        "--min-note-ms",
        type=int,
        default=58,
        metavar="MS",
        help="Discard MIDI notes shorter than this many milliseconds (default: 58).",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=44100,
        metavar="HZ",
        help="Output sample rate in Hz (default: 44100).",
    )
    parser.add_argument(
        "--preset",
        type=int,
        default=0,
        metavar="N",
        help="SF2 preset number (default: 0). Requires --sf2.",
    )
    parser.add_argument(
        "--bank",
        type=int,
        default=0,
        metavar="N",
        help="SF2 bank number (default: 0). Requires --sf2.",
    )
    parser.add_argument(
        "--force-preset",
        action="store_true",
        help="Force all MIDI channels to use --bank/--preset. Requires --sf2.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tunerize",
        description="Re-render audio as chiptune or through any SoundFont.",
    )
    sub = parser.add_subparsers(dest="command")

    conv = sub.add_parser(
        "convert",
        help="Convert a single audio file to chiptune or SoundFont-rendered audio.",
    )
    conv.add_argument("input", metavar="INPUT", help="Audio file to convert (.mp3 .wav .flac .ogg .m4a)")
    _add_conversion_args(conv)

    batch = sub.add_parser(
        "batch",
        help="Convert all audio files in a folder using shared settings.",
    )
    batch.add_argument(
        "input_dir",
        metavar="DIR",
        help="Folder containing audio files to convert.",
    )
    batch.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories.",
    )
    batch.add_argument(
        "--ext",
        metavar="EXTS",
        default=None,
        help="Comma-separated extensions to process (e.g. .mp3,.wav). Default: all supported.",
    )
    batch.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep processing remaining files after individual failures.",
    )
    _add_conversion_args(batch)

    return parser


def _engine_key(name: str) -> str:
    from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES, ENGINE_SEGA, ENGINE_SNES

    return {
        "nes": ENGINE_NES,
        "gameboy": ENGINE_GAME_BOY,
        "snes": ENGINE_SNES,
        "sega": ENGINE_SEGA,
    }[name]


def _make_config(args, audio_path: Path, out_dir: Path, sf2_path: Path | None):
    """Construct a PipelineConfig from parsed *args* and resolved paths."""
    from app.core.pipeline import PipelineConfig

    return PipelineConfig(
        audio_path=audio_path,
        output_dir=out_dir,
        sf2_path=sf2_path,
        use_chiptune_engine=sf2_path is None,
        transpose=args.transpose,
        quantize=args.quantize,
        quantize_grid=args.quantize_grid,
        sf2_bank=args.bank,
        sf2_preset=args.preset,
        force_preset=args.force_preset,
        forced_bank=args.bank,
        forced_preset=args.preset,
        min_note_ms=args.min_note_ms,
        stem_separate=args.stem_separate,
        export_midi=not args.no_midi,
        sample_rate=args.sample_rate,
        chiptune_engine=_engine_key(args.engine),
        output_format=args.format,
        onset_threshold=args.onset_threshold,
        frame_threshold=args.frame_threshold,
    )


def run_cli(argv: list[str] | None = None) -> int:
    """Parse *argv* and execute the requested CLI command. Returns an exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    from app.core.pipeline import CancelledError, ConversionPipeline, PipelineError

    sf2_path = Path(args.sf2) if args.sf2 else None
    if sf2_path is not None and not sf2_path.exists():
        print(f"error: SoundFont not found: {sf2_path}", file=sys.stderr)
        return 1

    def _progress(stage: str, pct: int) -> None:
        bar_width = 30
        filled = int(bar_width * pct / 100)
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\r[{bar}] {pct:3d}%  {stage:<55}", end="", flush=True)

    def _log(msg: str) -> None:
        print(f"\n  {msg}", end="", flush=True)

    # ── convert ──────────────────────────────────────────────────────────────
    if args.command == "convert":
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"error: input file not found: {input_path}", file=sys.stderr)
            return 1

        out_dir = Path(args.output) if args.output else input_path.parent
        try:
            config = _make_config(args, input_path, out_dir, sf2_path)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        pipeline = ConversionPipeline(config, progress=_progress, log=_log)
        try:
            midi_out, audio_out = pipeline.run()
            print()
            print(f"Done: {audio_out}")
            if midi_out:
                print(f"MIDI: {midi_out}")
            return 0
        except CancelledError:
            print("\nCancelled.", file=sys.stderr)
            return 130
        except PipelineError as exc:
            print(f"\nerror: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"\nunexpected error: {exc}", file=sys.stderr)
            return 1

    # ── batch ─────────────────────────────────────────────────────────────────
    if args.command == "batch":
        from app.core.audio_io import SUPPORTED_INPUT_EXTS

        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            print(f"error: not a directory: {input_dir}", file=sys.stderr)
            return 1

        allowed_exts: set[str]
        if args.ext:
            allowed_exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
        else:
            allowed_exts = SUPPORTED_INPUT_EXTS

        pattern = "**/*" if args.recursive else "*"
        audio_files = sorted(
            p for p in input_dir.glob(pattern)
            if p.is_file() and p.suffix.lower() in allowed_exts
        )

        if not audio_files:
            print(f"No audio files found in {input_dir}", file=sys.stderr)
            return 1

        out_base = Path(args.output) if args.output else input_dir
        out_base.mkdir(parents=True, exist_ok=True)

        ok: list[Path] = []
        failed: list[tuple[str, str]] = []

        print(f"Batch: {len(audio_files)} file(s) in {input_dir}")

        for idx, audio_path in enumerate(audio_files, 1):
            rel = audio_path.relative_to(input_dir)
            out_dir = out_base / rel.parent if args.recursive else out_base

            print(f"\n[{idx}/{len(audio_files)}] {rel}")
            try:
                config = _make_config(args, audio_path, out_dir, sf2_path)
            except ValueError as exc:
                msg = f"config error: {exc}"
                print(f"  SKIP — {msg}", file=sys.stderr)
                failed.append((str(rel), msg))
                if not args.continue_on_error:
                    break
                continue

            pipeline = ConversionPipeline(config, progress=_progress, log=_log)
            try:
                _, audio_out = pipeline.run()
                print(f"\n  -> {audio_out.name}")
                ok.append(audio_out)
            except CancelledError:
                print("\nCancelled.", file=sys.stderr)
                return 130
            except (PipelineError, Exception) as exc:
                msg = str(exc)
                print(f"\n  FAILED — {msg}", file=sys.stderr)
                failed.append((str(rel), msg))
                if not args.continue_on_error:
                    break

        print(f"\n\nBatch complete: {len(ok)} succeeded, {len(failed)} failed.")
        if failed:
            for name, reason in failed:
                print(f"  FAILED: {name}: {reason}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 0
