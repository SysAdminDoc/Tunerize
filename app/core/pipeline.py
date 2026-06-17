"""Conversion pipeline orchestration: audio -> (stem) -> MIDI -> cleaned MIDI -> WAV."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from app.core import audio_io, chiptune, midi_cleanup, renderer, transcriber

import numpy as np

ProgressCallback = Callable[[str, int], None]
LogCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]
MonitorCallback = Callable[[np.ndarray, int], None]


class PipelineError(Exception):
    pass


class CancelledError(PipelineError):
    pass


@dataclass
class PipelineConfig:
    audio_path: Path
    output_dir: Path
    sf2_path: Path | None = None             # required unless use_chiptune_engine=True
    use_chiptune_engine: bool = False        # when True, render via the built-in NES-style engine
    transpose: int = 0
    quantize: bool = False
    quantize_grid: str = "1/16"
    sf2_bank: int = 0
    sf2_preset: int = 0
    force_preset: bool = False
    forced_bank: int = 0
    forced_preset: int = 0
    min_note_ms: int = 58
    stem_separate: bool = False
    export_midi: bool = True
    sample_rate: int = 44100
    chiptune_engine: str = chiptune.ENGINE_NES
    chiptune_voice_volumes: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    chiptune_voice_mutes: tuple[bool, bool, bool, bool] = (False, False, False, False)
    chiptune_voice_solos: tuple[bool, bool, bool, bool] = (False, False, False, False)
    output_format: str = "wav"

    def __post_init__(self) -> None:
        if not self.use_chiptune_engine and self.sf2_path is None:
            raise ValueError("sf2_path is required unless use_chiptune_engine=True")
        if self.chiptune_engine not in chiptune.SUPPORTED_ENGINES:
            raise ValueError(f"Unsupported chiptune_engine: {self.chiptune_engine}")
        if self.output_format.lower() not in audio_io.SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(
                f"Unsupported output_format: {self.output_format!r}. "
                f"Supported: {audio_io.SUPPORTED_OUTPUT_FORMATS}"
            )
        for name in (
            "chiptune_voice_volumes",
            "chiptune_voice_mutes",
            "chiptune_voice_solos",
        ):
            if len(getattr(self, name)) != 4:
                raise ValueError(f"{name} must contain 4 values")


class ConversionPipeline:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancel_check: CancelCheck | None = None,
        monitor_callback: MonitorCallback | None = None,
    ):
        self.config = config
        self._progress = progress or (lambda _s, _p: None)
        self._log = log or (lambda _m: None)
        self._cancel_check = cancel_check or (lambda: False)
        self._monitor_callback = monitor_callback

    def _check_cancel(self) -> None:
        if self._cancel_check():
            raise CancelledError("Conversion cancelled by user.")

    def _stage(self, label: str, pct: int) -> None:
        self._progress(label, pct)
        self._log(label)
        self._check_cancel()

    def run(self) -> tuple[Path | None, Path]:
        cfg = self.config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        stem = cfg.audio_path.stem
        suffix = _chiptune_suffix(cfg.chiptune_engine) if cfg.use_chiptune_engine else cfg.sf2_path.stem  # type: ignore[union-attr]
        midi_out = cfg.output_dir / f"{stem}__{suffix}.mid"
        wav_out = cfg.output_dir / f"{stem}__{suffix}.wav"

        self._stage(f"Loading {cfg.audio_path.name}...", 5)
        audio_io.validate_audio(cfg.audio_path)

        audio_for_transcription = cfg.audio_path
        if cfg.stem_separate:
            self._stage("Separating stems (Demucs)...", 15)
            audio_for_transcription = self._stem_separate(cfg.audio_path)

        self._stage("Transcribing audio -> MIDI (Basic Pitch)...", 35)
        midi_data = transcriber.transcribe(
            audio_for_transcription,
            min_note_length_ms=cfg.min_note_ms,
        )
        self._log(f"  -> {midi_cleanup.note_count(midi_data)} raw notes")

        self._stage("Cleaning MIDI...", 60)
        midi_data = midi_cleanup.clean(
            midi_data,
            transpose=cfg.transpose,
            quantize=cfg.quantize,
            quantize_grid=cfg.quantize_grid,
        )
        self._log(f"  -> {midi_cleanup.note_count(midi_data)} cleaned notes")

        midi_data.write(str(midi_out))

        if cfg.use_chiptune_engine:
            engine_label = "Game Boy DMG" if cfg.chiptune_engine == chiptune.ENGINE_GAME_BOY else "NES-style"
            self._stage(f"Rendering chiptune ({engine_label} synth)...", 75)
            chiptune.render(
                midi=midi_data,
                output_wav_path=wav_out,
                sample_rate=cfg.sample_rate,
                engine=cfg.chiptune_engine,
                voice_volumes=cfg.chiptune_voice_volumes,
                voice_mutes=cfg.chiptune_voice_mutes,
                voice_solos=cfg.chiptune_voice_solos,
                cancel_check=self._cancel_check,
                log=self._log,
                monitor_callback=self._monitor_callback,
            )
        else:
            self._stage(f"Rendering through {cfg.sf2_path.name}...", 75)  # type: ignore[union-attr]
            renderer.render(
                midi_path=midi_out,
                sf2_path=cfg.sf2_path,  # type: ignore[arg-type]
                output_wav_path=wav_out,
                sample_rate=cfg.sample_rate,
                bank=cfg.sf2_bank,
                preset=cfg.sf2_preset,
                force_preset=cfg.force_preset,
                forced_bank=cfg.forced_bank,
                forced_preset=cfg.forced_preset,
                cancel_check=self._cancel_check,
                monitor_callback=self._monitor_callback,
            )

        final_out = wav_out
        fmt = cfg.output_format.lower()
        if fmt != "wav":
            ext = f".{fmt}"
            final_out = wav_out.with_suffix(ext)
            self._stage(f"Encoding to {fmt.upper()}...", 92)
            audio_io.transcode_wav(wav_out, final_out, fmt)
            with suppress(OSError):
                wav_out.unlink()

        self._stage(f"Wrote {final_out.name}", 100)

        midi_returned: Path | None = midi_out
        if not cfg.export_midi:
            with suppress(OSError):
                midi_out.unlink()
            midi_returned = None

        return midi_returned, final_out

    def _stem_separate(self, audio: Path) -> Path:
        try:
            import torch
            from demucs.apply import apply_model
            from demucs.audio import AudioFile, save_audio
            from demucs.pretrained import get_model
        except ImportError as e:
            raise PipelineError(
                "Demucs is not installed. Run `pip install demucs torch`, or disable "
                "stem separation in the UI."
            ) from e

        self._log("Loading htdemucs model (downloads on first use, ~85MB)...")
        model = get_model("htdemucs")
        model.eval()

        wav = AudioFile(str(audio)).read(
            streams=0,
            samplerate=model.samplerate,
            channels=model.audio_channels,
        )
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / max(float(ref.std()), 1e-8)

        with torch.no_grad():
            sources = apply_model(model, wav[None], device="cpu", progress=False)[0]
        sources = sources * float(ref.std()) + float(ref.mean())

        stem_names = list(model.sources)
        target_idx = stem_names.index("other") if "other" in stem_names else 0
        out_path = audio.parent / f"{audio.stem}__stem-{stem_names[target_idx]}.wav"
        save_audio(sources[target_idx], str(out_path), samplerate=model.samplerate)
        self._log(f"  -> stem '{stem_names[target_idx]}' saved to {out_path.name}")
        return out_path


class MultiChannelPipeline:
    """Run per-stem conversion: Demucs split -> transcribe each -> render each."""

    STEM_NAMES = ("vocals", "drums", "bass", "other")

    def __init__(
        self,
        config: PipelineConfig,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ):
        self.config = config
        self._progress = progress or (lambda _s, _p: None)
        self._log = log or (lambda _m: None)
        self._cancel_check = cancel_check or (lambda: False)

    def _check_cancel(self) -> None:
        if self._cancel_check():
            raise CancelledError("Conversion cancelled by user.")

    def _stage(self, label: str, pct: int) -> None:
        self._progress(label, pct)
        self._log(label)
        self._check_cancel()

    def run(self) -> tuple[list[Path | None], list[Path]]:
        """Returns (midi_paths, audio_paths) — one per stem."""
        cfg = self.config
        cfg.output_dir.mkdir(parents=True, exist_ok=True)

        self._stage(f"Loading {cfg.audio_path.name}...", 2)
        audio_io.validate_audio(cfg.audio_path)

        self._stage("Separating stems (Demucs)...", 5)
        stem_paths = self._separate_all_stems(cfg.audio_path)

        midi_outputs: list[Path | None] = []
        audio_outputs: list[Path] = []
        stem_count = len(stem_paths)

        for i, (stem_name, stem_audio) in enumerate(stem_paths):
            self._check_cancel()
            base_pct = 10 + int(80 * i / stem_count)
            end_pct = 10 + int(80 * (i + 1) / stem_count)

            base_stem = cfg.audio_path.stem
            suffix = _chiptune_suffix(cfg.chiptune_engine) if cfg.use_chiptune_engine else cfg.sf2_path.stem  # type: ignore[union-attr]
            midi_out = cfg.output_dir / f"{base_stem}__{stem_name}__{suffix}.mid"
            wav_out = cfg.output_dir / f"{base_stem}__{stem_name}__{suffix}.wav"

            self._stage(f"[{stem_name}] Transcribing...", base_pct)
            try:
                midi_data = transcriber.transcribe(
                    stem_audio,
                    min_note_length_ms=cfg.min_note_ms,
                )
            except Exception as exc:
                self._log(f"  [{stem_name}] Skipped: {exc}")
                continue

            note_ct = midi_cleanup.note_count(midi_data)
            self._log(f"  [{stem_name}] {note_ct} raw notes")

            mid_pct = base_pct + (end_pct - base_pct) // 3
            self._stage(f"[{stem_name}] Cleaning MIDI...", mid_pct)
            try:
                midi_data = midi_cleanup.clean(
                    midi_data,
                    transpose=cfg.transpose,
                    quantize=cfg.quantize,
                    quantize_grid=cfg.quantize_grid,
                )
            except Exception as exc:
                self._log(f"  [{stem_name}] Cleanup skipped: {exc}")
                continue

            midi_data.write(str(midi_out))

            render_pct = base_pct + 2 * (end_pct - base_pct) // 3
            if cfg.use_chiptune_engine:
                self._stage(f"[{stem_name}] Rendering chiptune...", render_pct)
                chiptune.render(
                    midi=midi_data,
                    output_wav_path=wav_out,
                    sample_rate=cfg.sample_rate,
                    engine=cfg.chiptune_engine,
                    voice_volumes=cfg.chiptune_voice_volumes,
                    voice_mutes=cfg.chiptune_voice_mutes,
                    voice_solos=cfg.chiptune_voice_solos,
                    cancel_check=self._cancel_check,
                    log=self._log,
                )
            else:
                self._stage(f"[{stem_name}] Rendering SF2...", render_pct)
                renderer.render(
                    midi_path=midi_out,
                    sf2_path=cfg.sf2_path,  # type: ignore[arg-type]
                    output_wav_path=wav_out,
                    sample_rate=cfg.sample_rate,
                    bank=cfg.sf2_bank,
                    preset=cfg.sf2_preset,
                    force_preset=cfg.force_preset,
                    forced_bank=cfg.forced_bank,
                    forced_preset=cfg.forced_preset,
                    cancel_check=self._cancel_check,
                )

            final_out = wav_out
            fmt = cfg.output_format.lower()
            if fmt != "wav":
                ext = f".{fmt}"
                final_out = wav_out.with_suffix(ext)
                audio_io.transcode_wav(wav_out, final_out, fmt)
                with suppress(OSError):
                    wav_out.unlink()

            audio_outputs.append(final_out)

            if cfg.export_midi:
                midi_outputs.append(midi_out)
            else:
                with suppress(OSError):
                    midi_out.unlink()
                midi_outputs.append(None)

        self._stage(f"Multi-channel done: {len(audio_outputs)} stems rendered.", 100)
        return midi_outputs, audio_outputs

    def _separate_all_stems(self, audio: Path) -> list[tuple[str, Path]]:
        try:
            import torch
            from demucs.apply import apply_model
            from demucs.audio import AudioFile, save_audio
            from demucs.pretrained import get_model
        except ImportError as exc:
            raise PipelineError(
                "Multi-channel output requires Demucs. Run: pip install demucs torch"
            ) from exc

        self._log("Loading htdemucs model (downloads on first use, ~85MB)...")
        model = get_model("htdemucs")
        model.eval()

        wav = AudioFile(str(audio)).read(
            streams=0,
            samplerate=model.samplerate,
            channels=model.audio_channels,
        )
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / max(float(ref.std()), 1e-8)

        with torch.no_grad():
            sources = apply_model(model, wav[None], device="cpu", progress=False)[0]
        sources = sources * float(ref.std()) + float(ref.mean())

        stem_names = list(model.sources)
        results: list[tuple[str, Path]] = []
        for idx, name in enumerate(stem_names):
            out_path = audio.parent / f"{audio.stem}__stem-{name}.wav"
            save_audio(sources[idx], str(out_path), samplerate=model.samplerate)
            results.append((name, out_path))
            self._log(f"  -> stem '{name}' saved to {out_path.name}")

        return results


def _chiptune_suffix(engine: str) -> str:
    if engine == chiptune.ENGINE_GAME_BOY:
        return "gameboy"
    if engine == chiptune.ENGINE_SNES:
        return "snes"
    if engine == chiptune.ENGINE_SEGA:
        return "sega"
    return "chiptune"
