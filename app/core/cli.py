"""Tunerize command-line interface.

Usage:
    tunerize convert <input> [options]

Examples:
    tunerize convert song.mp3 --chiptune --engine sega
    tunerize convert song.wav --sf2 nes.sf2 --format mp3 -o ./out
    tunerize convert song.flac --sf2 fluid.sf2 --format flac --transpose -2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tunerize",
        description="Re-render audio as chiptune or through any SoundFont.",
    )
    sub = parser.add_subparsers(dest="command")

    conv = sub.add_parser(
        "convert",
        help="Convert an audio file to chiptune or SoundFont-rendered WAV/FLAC/OGG/MP3.",
    )
    conv.add_argument("input", metavar="INPUT", help="Audio file to convert (.mp3 .wav .flac .ogg .m4a)")
    conv.add_argument(
        "--sf2",
        metavar="FILE",
        help="SoundFont to render through. Omit to use the built-in chiptune engine.",
    )
    conv.add_argument(
        "--engine",
        choices=["nes", "gameboy", "snes", "sega"],
        default="nes",
        metavar="ENGINE",
        help="Chiptune engine: nes (default), gameboy, snes, sega. Ignored when --sf2 is given.",
    )
    conv.add_argument(
        "-o", "--output",
        metavar="DIR",
        help="Output directory (default: same folder as input).",
    )
    conv.add_argument(
        "--format",
        choices=["wav", "flac", "ogg", "mp3"],
        default="wav",
        metavar="FMT",
        help="Output audio format: wav (default), flac, ogg, mp3.",
    )
    conv.add_argument(
        "--transpose",
        type=int,
        default=0,
        metavar="N",
        help="Transpose by N semitones (-24 … +24, default: 0).",
    )
    conv.add_argument("--quantize", action="store_true", help="Quantize MIDI notes to a rhythmic grid.")
    conv.add_argument(
        "--quantize-grid",
        default="1/16",
        choices=["1/4", "1/8", "1/16", "1/32"],
        metavar="GRID",
        help="Quantize grid (default: 1/16). Requires --quantize.",
    )
    conv.add_argument("--stem-separate", action="store_true", help="Run Demucs stem separation before transcription.")
    conv.add_argument("--no-midi", action="store_true", help="Delete the intermediate .mid file after rendering.")
    conv.add_argument(
        "--min-note-ms",
        type=int,
        default=58,
        metavar="MS",
        help="Discard MIDI notes shorter than this many milliseconds (default: 58).",
    )
    conv.add_argument(
        "--sample-rate",
        type=int,
        default=44100,
        metavar="HZ",
        help="Output sample rate in Hz (default: 44100).",
    )
    conv.add_argument(
        "--preset",
        type=int,
        default=0,
        metavar="N",
        help="SF2 preset number (default: 0). Requires --sf2.",
    )
    conv.add_argument(
        "--bank",
        type=int,
        default=0,
        metavar="N",
        help="SF2 bank number (default: 0). Requires --sf2.",
    )
    conv.add_argument(
        "--force-preset",
        action="store_true",
        help="Force all MIDI channels to use --bank/--preset. Requires --sf2.",
    )

    return parser


def _engine_key(name: str) -> str:
    from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES, ENGINE_SEGA, ENGINE_SNES

    return {
        "nes": ENGINE_NES,
        "gameboy": ENGINE_GAME_BOY,
        "snes": ENGINE_SNES,
        "sega": ENGINE_SEGA,
    }[name]


def run_cli(argv: list[str] | None = None) -> int:
    """Parse *argv* and execute the requested CLI command. Returns an exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # ── convert ──────────────────────────────────────────────────────────────
    from app.core.pipeline import CancelledError, ConversionPipeline, PipelineConfig, PipelineError

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"error: input file not found: {input_path}", file=sys.stderr)
        return 1

    sf2_path = Path(args.sf2) if args.sf2 else None
    use_chiptune = sf2_path is None

    if sf2_path is not None and not sf2_path.exists():
        print(f"error: SoundFont not found: {sf2_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.output) if args.output else input_path.parent

    def _progress(stage: str, pct: int) -> None:
        bar_width = 30
        filled = int(bar_width * pct / 100)
        bar = "#" * filled + "-" * (bar_width - filled)
        print(f"\r[{bar}] {pct:3d}%  {stage:<55}", end="", flush=True)

    def _log(msg: str) -> None:
        print(f"\n  {msg}", end="", flush=True)

    try:
        config = PipelineConfig(
            audio_path=input_path,
            output_dir=out_dir,
            sf2_path=sf2_path,
            use_chiptune_engine=use_chiptune,
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
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    pipeline = ConversionPipeline(config, progress=_progress, log=_log)
    try:
        midi_out, audio_out = pipeline.run()
        print()  # newline after progress bar
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
