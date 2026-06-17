"""Tunerize main window — single-window converter UI."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on the local PySide6 build
    QSoundEffect = None
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.audio_io import SUPPORTED_INPUT_EXTS
from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES, ENGINE_SEGA, ENGINE_SNES
from app.core.genre_presets import GenrePreset, get_genre_presets
from app.core.monitor import AudioMonitor, is_monitoring_available
from app.core.pipeline import ConversionPipeline, MultiChannelPipeline, PipelineConfig
from app.core.recent_soundfonts import load_recent_soundfonts, normalize_path_key, remember_soundfont
from app.core.renderer import render_preview
from app.core.runtime import find_polyphone_executable
from app.core.soundfonts import SoundFontInfo, SoundFontLibrary
from app.ui.browser_dialog import BrowserDialog
from app.ui.sf2_creator_dialog import SF2CreatorDialog


class _Worker(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    monitor_chunk = Signal(object, int)  # (stereo_int16 ndarray, sample_rate)
    finished_ok = Signal(object, object)   # (midi_path | None, wav_path)
    finished_err = Signal(str)

    def __init__(self, config: PipelineConfig, *, monitor: bool = False):
        super().__init__()
        self._config = config
        self._cancelled = False
        self._monitor = monitor

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            monitor_cb = (lambda chunk, sr: self.monitor_chunk.emit(chunk, sr)) if self._monitor else None
            pipeline = ConversionPipeline(
                self._config,
                progress=lambda s, p: self.progress.emit(s, p),
                log=lambda m: self.log.emit(m),
                cancel_check=lambda: self._cancelled,
                monitor_callback=monitor_cb,
            )
            midi_out, wav_out = pipeline.run()
            self.finished_ok.emit(midi_out, wav_out)
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _BatchWorker(QThread):
    file_started = Signal(str, int, int)   # filename, current_idx (1-based), total
    progress = Signal(str, int)
    log = Signal(str)
    finished_all = Signal(list, list)      # ok_paths, failed [(name, reason)]

    def __init__(self, configs: list[PipelineConfig]):
        super().__init__()
        self._configs = configs
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        ok: list[Path] = []
        failed: list[tuple[str, str]] = []
        total = len(self._configs)

        for idx, cfg in enumerate(self._configs, 1):
            if self._cancelled:
                break
            self.file_started.emit(cfg.audio_path.name, idx, total)
            try:
                pipeline = ConversionPipeline(
                    cfg,
                    progress=lambda s, p: self.progress.emit(s, p),
                    log=lambda m: self.log.emit(m),
                    cancel_check=lambda: self._cancelled,
                )
                _, audio_out = pipeline.run()
                ok.append(audio_out)
            except Exception as exc:
                reason = str(exc)
                self.log.emit(f"FAILED: {cfg.audio_path.name}: {reason}")
                failed.append((cfg.audio_path.name, reason))

        self.finished_all.emit(ok, failed)


class _PreviewWorker(QThread):
    finished_ok = Signal(object)
    finished_err = Signal(str)

    def __init__(self, sf2_path: Path, output_path: Path, bank: int, preset: int):
        super().__init__()
        self._sf2_path = sf2_path
        self._output_path = output_path
        self._bank = bank
        self._preset = preset
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            path = render_preview(
                self._sf2_path,
                self._output_path,
                bank=self._bank,
                preset=self._preset,
                duration_seconds=5.0,
                cancel_check=lambda: self._cancelled,
            )
            self.finished_ok.emit(path)
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _MultiChannelWorker(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    finished_ok = Signal(list, list)   # (midi_paths, audio_paths)
    finished_err = Signal(str)

    def __init__(self, config: PipelineConfig):
        super().__init__()
        self._config = config
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            pipeline = MultiChannelPipeline(
                self._config,
                progress=lambda s, p: self.progress.emit(s, p),
                log=lambda m: self.log.emit(m),
                cancel_check=lambda: self._cancelled,
            )
            midi_outs, audio_outs = pipeline.run()
            self.finished_ok.emit(
                [str(p) if p else None for p in midi_outs],
                [str(p) for p in audio_outs],
            )
        except Exception as exc:
            self.finished_err.emit(str(exc))


class _CollapsibleBox(QWidget):
    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.toggle = QToolButton(text=title, checkable=True, checked=False)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.toggled.connect(self._on_toggle)

        self.content = QWidget()
        self.content.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

    def _on_toggle(self, checked: bool) -> None:
        self.content.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def setContentLayout(self, layout) -> None:
        self.content.setLayout(layout)


class MainWindow(QMainWindow):
    def __init__(self, soundfonts_dir: Path | None = None, settings_path: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"Tunerize  v{__version__}")
        self.setMinimumSize(760, 620)
        self.resize(960, 760)
        self.setAcceptDrops(True)

        self.library = SoundFontLibrary(soundfonts_dir or Path.cwd() / "soundfonts")
        self._settings_path = settings_path
        self._polyphone_exe = find_polyphone_executable()
        self._worker: _Worker | None = None
        self._preview_worker: _PreviewWorker | None = None
        self._preview_player = QSoundEffect(self) if QSoundEffect is not None else None
        if self._preview_player is not None:
            self._preview_player.setVolume(0.7)
        self._busy = False
        self._has_soundfonts = False
        self._soundfont_infos: dict[str, SoundFontInfo] = {}
        self._soundfont_preset_widgets: list[QWidget] = []
        self._batch_worker: _BatchWorker | None = None
        self._multi_worker: _MultiChannelWorker | None = None
        self._audio_monitor: AudioMonitor | None = None
        self.voice_name_labels: list[QLabel] = []
        self.voice_volume_sliders: list[QSlider] = []
        self.voice_value_labels: list[QLabel] = []
        self.voice_mute_checks: list[QCheckBox] = []
        self.voice_solo_checks: list[QCheckBox] = []
        self._chiptune_mixer_widgets: list[QWidget] = []

        self._build_ui()
        self._refresh_soundfonts()
        self._update_mode_visibility()

    # ---------- UI construction ----------

    def _build_ui(self) -> None:
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)

        title = QLabel("Tunerize")
        title.setObjectName("title")
        subtitle = QLabel("Re-render audio as chiptune — or through any SoundFont.")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addLayout(self._style_preset_row())
        root.addWidget(self._mode_section())
        root.addLayout(self._input_row())
        root.addWidget(self._soundfont_frame())
        self.sf_meta_label = QLabel()
        self.sf_meta_label.setObjectName("sfMeta")
        root.addWidget(self.sf_meta_label)
        root.addLayout(self._output_row())

        self.demucs_check = QCheckBox(
            "Stem-separate first (Demucs) — slower, much better on full songs"
        )
        root.addWidget(self.demucs_check)

        self.multi_channel_check = QCheckBox(
            "Multi-channel output — render each stem separately (requires Demucs)"
        )
        self.multi_channel_check.setToolTip(
            "Split into vocals/drums/bass/other and render each stem independently."
        )
        root.addWidget(self.multi_channel_check)

        self.monitor_check = QCheckBox("Monitor output — play audio through speakers during render")
        self.monitor_check.setToolTip(
            "Stream audio to your speakers in real time as the conversion runs."
        )
        self.monitor_check.setEnabled(is_monitoring_available())
        if not is_monitoring_available():
            self.monitor_check.setToolTip(
                "Requires PySide6 multimedia module and an audio output device."
            )
        root.addWidget(self.monitor_check)

        root.addWidget(self._advanced_section())
        root.addLayout(self._action_row())
        root.addLayout(self._progress_section())
        root.addWidget(self._log_section(), 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)

    def _style_preset_row(self) -> QHBoxLayout:
        self.style_combo = QComboBox()
        self.style_combo.setMinimumWidth(180)
        self.style_combo.addItem("Custom (current settings)", None)
        for preset in get_genre_presets():
            self.style_combo.addItem(preset.name, preset)
        self.style_combo.setToolTip("Apply a named style — sets mode, engine, and conversion options in one click.")

        self.style_hint_label = QLabel()
        self.style_hint_label.setObjectName("styleHint")
        self.style_hint_label.setWordWrap(True)
        self.style_hint_label.setVisible(False)

        self.style_combo.activated.connect(self._apply_genre_preset_by_idx)

        row = QHBoxLayout()
        row.addWidget(QLabel("Style:"))
        row.addWidget(self.style_combo)
        row.addWidget(self.style_hint_label, 1)
        row.addStretch(1)
        return row

    @Slot(int)
    def _apply_genre_preset_by_idx(self, idx: int) -> None:
        preset: GenrePreset | None = self.style_combo.itemData(idx)
        if preset is None:
            self.style_hint_label.setVisible(False)
            return
        self._apply_genre_preset(preset)

    def _apply_genre_preset(self, preset: GenrePreset) -> None:
        if preset.chiptune_mode:
            self.mode_chiptune.setChecked(True)
            if preset.engine is not None:
                for i in range(self.engine_combo.count()):
                    if self.engine_combo.itemData(i) == preset.engine:
                        self.engine_combo.setCurrentIndex(i)
                        break
        else:
            self.mode_sf2.setChecked(True)

        self.transpose_spin.setValue(preset.transpose)
        self.quantize_check.setChecked(preset.quantize)
        if preset.quantize_grid:
            idx = self.quantize_combo.findText(preset.quantize_grid)
            if idx >= 0:
                self.quantize_combo.setCurrentIndex(idx)
        self.min_note_spin.setValue(preset.min_note_ms)

        if preset.sf2_search_hint and not preset.chiptune_mode:
            self.style_hint_label.setText(
                f"Tip: search for \"{preset.sf2_search_hint}\" in Browse Online."
            )
            self.style_hint_label.setVisible(True)
        else:
            self.style_hint_label.setVisible(False)

        self._update_mode_visibility()
        self._sync_control_state()

    def _mode_section(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("modeFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(20)

        layout.addWidget(QLabel("Render mode:"))

        self.mode_chiptune = QRadioButton("Chiptune (built-in NES synth)")
        self.mode_chiptune.setChecked(True)
        self.mode_sf2 = QRadioButton("SoundFont (.sf2)")

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_chiptune)
        self.mode_group.addButton(self.mode_sf2)
        self.mode_chiptune.toggled.connect(self._update_mode_visibility)

        layout.addWidget(self.mode_chiptune)
        layout.addWidget(self.mode_sf2)
        layout.addStretch(1)
        return frame

    def _input_row(self) -> QHBoxLayout:
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Pick or drop an audio file (.mp3 / .wav / .flac / .ogg / .m4a)")
        self.input_edit.setAccessibleName("Selected audio file")
        self.input_edit.setToolTip("Audio file to transcribe and render")
        self.input_edit.setReadOnly(True)
        self.open_audio_btn = QPushButton("Open Audio…")
        self.open_audio_btn.clicked.connect(self._pick_audio)

        row = QHBoxLayout()
        row.addWidget(QLabel("Audio:"))
        row.addWidget(self.input_edit, 1)
        row.addWidget(self.open_audio_btn)
        return row

    def _soundfont_frame(self) -> QWidget:
        self.sf_frame = QFrame()
        self.sf_frame.setObjectName("sfFrame")
        layout = QHBoxLayout(self.sf_frame)
        layout.setContentsMargins(12, 10, 12, 10)

        self.sf_combo = QComboBox()
        self.sf_combo.setAccessibleName("SoundFont library")
        self.sf_combo.currentIndexChanged.connect(lambda _idx: self._on_soundfont_changed())
        self.sf_refresh_btn = QPushButton("↻")
        self.sf_refresh_btn.setToolTip("Re-scan soundfonts/ folder")
        self.sf_refresh_btn.setFixedWidth(36)
        self.sf_refresh_btn.clicked.connect(self._refresh_soundfonts)
        self.sf_add_btn = QPushButton("Add…")
        self.sf_add_btn.setToolTip("Import a .sf2 file from disk into your library")
        self.sf_add_btn.clicked.connect(self._add_soundfont)
        self.sf_edit_btn = QPushButton("Edit SoundFont…")
        self.sf_edit_btn.clicked.connect(self._edit_current_soundfont)
        self.sf_fluids_btn = QPushButton("Get FluidR3 GM…")
        self.sf_fluids_btn.setToolTip(
            "Search for the free FluidR3 GM SoundFont in the online browser"
        )
        self.sf_fluids_btn.clicked.connect(self._open_fluids_browser)
        self.sf_browse_btn = QPushButton("Browse Online…")
        self.sf_browse_btn.setToolTip("Search and install SoundFonts from public libraries")
        self.sf_browse_btn.clicked.connect(self._open_browser)
        self.sf_create_btn = QPushButton("Create SF2…")
        self.sf_create_btn.setToolTip("Build a new SoundFont from WAV samples or export chiptune voices")
        self.sf_create_btn.clicked.connect(self._open_sf2_creator)

        layout.addWidget(QLabel("SoundFont:"))
        layout.addWidget(self.sf_combo, 1)
        layout.addWidget(self.sf_refresh_btn)
        layout.addWidget(self.sf_add_btn)
        layout.addWidget(self.sf_edit_btn)
        layout.addWidget(self.sf_fluids_btn)
        layout.addWidget(self.sf_browse_btn)
        layout.addWidget(self.sf_create_btn)
        return self.sf_frame

    def _output_row(self) -> QHBoxLayout:
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Default: same folder as input")
        self.out_edit.setAccessibleName("Output folder")
        self.output_btn = QPushButton("Choose…")
        self.output_btn.clicked.connect(self._pick_output)

        self.format_combo = QComboBox()
        self.format_combo.setToolTip("Output audio format")
        self.format_combo.setAccessibleName("Output format")
        self.format_combo.addItem("WAV", "wav")
        self.format_combo.addItem("FLAC", "flac")
        self.format_combo.addItem("OGG", "ogg")
        self.format_combo.addItem("MP3", "mp3")
        self.format_combo.setFixedWidth(72)

        row = QHBoxLayout()
        row.addWidget(QLabel("Output:"))
        row.addWidget(self.out_edit, 1)
        row.addWidget(self.format_combo)
        row.addWidget(self.output_btn)
        return row

    def _advanced_section(self) -> QWidget:
        adv = _CollapsibleBox("Advanced settings")
        layout = QGridLayout()
        layout.setContentsMargins(20, 6, 0, 6)
        layout.setColumnStretch(1, 1)

        self.transpose_spin = QSpinBox()
        self.transpose_spin.setRange(-24, 24)
        self.transpose_spin.setValue(0)
        self.transpose_spin.setSuffix(" semitones")
        layout.addWidget(QLabel("Transpose:"), 0, 0)
        layout.addWidget(self.transpose_spin, 0, 1)

        self.quantize_check = QCheckBox("Quantize to grid")
        self.quantize_combo = QComboBox()
        self.quantize_combo.addItems(["1/4", "1/8", "1/16", "1/32"])
        self.quantize_combo.setCurrentText("1/16")
        self.quantize_combo.setEnabled(False)
        self.quantize_check.toggled.connect(lambda _checked: self._sync_control_state())
        layout.addWidget(self.quantize_check, 1, 0)
        layout.addWidget(self.quantize_combo, 1, 1)

        self.force_preset_check = QCheckBox("Force all notes to selected preset (SF2 mode)")
        self.preset_combo = QComboBox()
        self.preset_combo.setAccessibleName("SoundFont preset")
        self.preset_combo.setToolTip("Preset list parsed from the selected SoundFont.")
        self.preview_preset_btn = QPushButton("Preview")
        self.preview_preset_btn.setToolTip("Render and play a five-second preview of the selected preset.")
        self.preview_preset_btn.clicked.connect(self._preview_selected_preset)
        self.force_preset_check.toggled.connect(lambda _checked: self._sync_control_state())
        self._soundfont_preset_widgets.extend([
            self.force_preset_check,
            self.preset_combo,
            self.preview_preset_btn,
        ])

        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.preview_preset_btn)
        layout.addWidget(self.force_preset_check, 2, 0)
        layout.addLayout(preset_row, 2, 1)

        self.export_midi_check = QCheckBox("Also export intermediate .mid file")
        self.export_midi_check.setChecked(True)
        layout.addWidget(self.export_midi_check, 3, 0, 1, 2)

        self.min_note_spin = QSpinBox()
        self.min_note_spin.setRange(20, 500)
        self.min_note_spin.setValue(58)
        self.min_note_spin.setSuffix(" ms")
        layout.addWidget(QLabel("Min note length:"), 4, 0)
        layout.addWidget(self.min_note_spin, 4, 1)

        engine_label = QLabel("Chip engine:")
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("NES APU-style", ENGINE_NES)
        self.engine_combo.addItem("Game Boy DMG", ENGINE_GAME_BOY)
        self.engine_combo.addItem("SNES SPC700", ENGINE_SNES)
        self.engine_combo.addItem("Sega Genesis FM", ENGINE_SEGA)
        self.engine_combo.setToolTip("Choose the built-in chip model used by Chiptune mode.")
        self.engine_combo.currentIndexChanged.connect(lambda _idx: self._update_chiptune_engine_labels())
        layout.addWidget(engine_label, 5, 0)
        layout.addWidget(self.engine_combo, 5, 1)
        self._chiptune_mixer_widgets.extend([engine_label, self.engine_combo])

        mixer_label = QLabel("Chiptune voice mixer:")
        mixer_label.setToolTip("Applies only to the built-in chiptune renderer.")
        layout.addWidget(mixer_label, 6, 0, 1, 2)
        self._chiptune_mixer_widgets.append(mixer_label)

        mixer_widget = QWidget()
        mixer_layout = QGridLayout(mixer_widget)
        mixer_layout.setContentsMargins(0, 0, 0, 0)
        mixer_layout.setHorizontalSpacing(12)
        mixer_layout.setVerticalSpacing(6)
        mixer_layout.setColumnStretch(1, 1)

        voice_names = (
            "Pulse 1 lead",
            "Pulse 2 harmony",
            "Triangle bass",
            "Noise drums",
        )
        for row_offset, voice_name in enumerate(voice_names):
            name_label = QLabel(voice_name)
            volume = QSlider(Qt.Orientation.Horizontal)
            volume.setRange(0, 150)
            volume.setValue(100)
            volume.setSingleStep(5)
            volume.setPageStep(10)
            volume.setMinimumWidth(180)
            volume.setMaximumWidth(520)
            volume.setAccessibleName(f"{voice_name} volume")
            volume.setToolTip("Voice volume, 100% preserves the default mix.")
            value_label = QLabel("100%")
            value_label.setFixedWidth(42)
            volume.valueChanged.connect(lambda value, label=value_label: label.setText(f"{value}%"))

            mute = QCheckBox("Mute")
            mute.setAccessibleName(f"Mute {voice_name}")
            solo = QCheckBox("Solo")
            solo.setAccessibleName(f"Solo {voice_name}")

            mixer_layout.addWidget(name_label, row_offset, 0)
            mixer_layout.addWidget(volume, row_offset, 1)
            mixer_layout.addWidget(value_label, row_offset, 2)
            mixer_layout.addWidget(mute, row_offset, 3)
            mixer_layout.addWidget(solo, row_offset, 4)

            self.voice_volume_sliders.append(volume)
            self.voice_name_labels.append(name_label)
            self.voice_value_labels.append(value_label)
            self.voice_mute_checks.append(mute)
            self.voice_solo_checks.append(solo)
            self._chiptune_mixer_widgets.extend([name_label, volume, value_label, mute, solo])

        layout.addWidget(mixer_widget, 7, 0, 1, 2)
        self._chiptune_mixer_widgets.append(mixer_widget)
        self._update_chiptune_engine_labels()

        adv.setContentLayout(layout)
        return adv

    def _action_row(self) -> QHBoxLayout:
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setObjectName("convertBtn")
        self.convert_btn.setMinimumHeight(46)
        self.convert_btn.setDefault(True)
        self.convert_btn.clicked.connect(self._on_convert)

        self.batch_btn = QPushButton("Batch…")
        self.batch_btn.setMinimumHeight(46)
        self.batch_btn.setToolTip("Convert all audio files in a folder using the current settings.")
        self.batch_btn.clicked.connect(self._on_batch)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(46)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)

        row = QHBoxLayout()
        row.addWidget(self.convert_btn, 1)
        row.addWidget(self.batch_btn)
        row.addWidget(self.cancel_btn)
        return row

    def _progress_section(self) -> QVBoxLayout:
        self.stage_label = QLabel("Ready.")
        self.stage_label.setObjectName("stage")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout = QVBoxLayout()
        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress_bar)
        return layout

    def _log_section(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        log_label = QLabel("Log")
        log_label.setObjectName("logLabel")
        self.log_panel = QPlainTextEdit()
        self.log_panel.setObjectName("logPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumBlockCount(10000)
        layout.addWidget(log_label)
        layout.addWidget(self.log_panel, 1)
        return wrapper

    # ---------- handlers ----------

    def _pick_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open audio file",
            str(Path.home()),
            "Audio (*.mp3 *.wav *.flac *.ogg *.m4a *.aiff *.aif);;All files (*)",
        )
        if path:
            self._set_audio_path(Path(path), announce=True)

    def _pick_output(self) -> None:
        start = self.out_edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choose output folder", start)
        if path:
            self.out_edit.setText(path)

    def _add_soundfont(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import SoundFont",
            str(Path.home()),
            "SoundFont (*.sf2 *.sf3);;All files (*)",
        )
        if not path:
            return
        try:
            new_sf = self.library.import_file(Path(path))
            self._remember_soundfont(new_sf.path, select=True)
            self._log(f"Imported SoundFont: {new_sf.name}")
        except Exception as exc:
            self._log(f"Import failed: {exc}")
            QMessageBox.warning(self, "Import failed", str(exc))

    def _open_browser(self) -> None:
        dlg = BrowserDialog(self.library.library_dir, parent=self)
        dlg.sf_installed.connect(self._on_browser_installed)
        dlg.exec()

    def _open_fluids_browser(self) -> None:
        dlg = BrowserDialog(self.library.library_dir, initial_query="FluidR3 GM", parent=self)
        dlg.sf_installed.connect(self._on_browser_installed)
        dlg.exec()

    def _open_sf2_creator(self) -> None:
        dlg = SF2CreatorDialog(self.library.library_dir, parent=self)
        dlg.sf2_created.connect(self._on_sf2_created)
        dlg.exec()

    def _on_sf2_created(self, path: str) -> None:
        created = Path(path)
        if created.parent == self.library.library_dir:
            self._remember_soundfont(created, select=True)
            if self.mode_chiptune.isChecked():
                self.mode_sf2.setChecked(True)
            self._log(f"Created SoundFont: {created.name}")
        else:
            self._log(f"SF2 saved: {created}")

    def _edit_current_soundfont(self) -> None:
        sf_data = self.sf_combo.currentData()
        if not sf_data:
            QMessageBox.warning(self, "Missing SoundFont", "Pick a SoundFont before opening the editor.")
            return
        if self._polyphone_exe is None:
            QMessageBox.warning(
                self,
                "Polyphone unavailable",
                "Polyphone is not bundled. Source runs can set TUNERIZE_POLYPHONE_EXE or TUNERIZE_POLYPHONE_DIR.",
            )
            return

        sf_path = Path(sf_data)
        started = QProcess.startDetached(str(self._polyphone_exe), [str(sf_path)], str(sf_path.parent))
        ok = started[0] if isinstance(started, tuple) else started
        if not ok:
            QMessageBox.warning(self, "Editor failed", f"Could not launch Polyphone:\n{self._polyphone_exe}")
            return
        self._log(f"Opened in Polyphone: {sf_path.name}")

    def _on_browser_installed(self, path) -> None:
        installed = Path(path)
        self._remember_soundfont(installed, select=True)
        if self.mode_chiptune.isChecked():
            self.mode_sf2.setChecked(True)  # auto-switch to SF2 mode after install
        self._log(f"Installed from browser: {installed.name}")

    def _refresh_soundfonts(self, select_path: Path | None = None) -> None:
        current_data = self.sf_combo.currentData()
        current = str(select_path) if select_path is not None else (str(current_data) if current_data else "")
        self.sf_combo.clear()
        sounds = self.library.scan()
        self._soundfont_infos = {normalize_path_key(sf.path): sf for sf in sounds}
        self._has_soundfonts = bool(sounds)
        if not sounds:
            self.sf_combo.addItem(
                "(no soundfonts found — drop .sf2 files into ./soundfonts/)", None
            )
            self._refresh_preset_combo()
            self._sync_control_state()
            self._update_sf_meta_label()
            return

        recent_infos = []
        seen_recent: set[str] = set()
        for recent_path in load_recent_soundfonts(self._settings_path):
            key = normalize_path_key(recent_path)
            info = self._soundfont_infos.get(key)
            if info is None or key in seen_recent:
                continue
            seen_recent.add(key)
            recent_infos.append(info)

        def add_soundfont(info, *, recent: bool = False) -> None:
            prefix = "Recent: " if recent else ""
            label = f"{prefix}{info.name} ({info.size_mb:.1f} MB)"
            if info.preset_count:
                label += f" - {info.preset_count} presets"
            if not info.is_valid:
                label += "  — INVALID"
            self.sf_combo.addItem(label, str(info.path))

        for sf in recent_infos:
            add_soundfont(sf, recent=True)

        recent_keys = {normalize_path_key(sf.path) for sf in recent_infos}
        regular_infos = [sf for sf in sounds if normalize_path_key(sf.path) not in recent_keys]
        if recent_infos and regular_infos:
            self.sf_combo.insertSeparator(self.sf_combo.count())
        for sf in regular_infos:
            add_soundfont(sf)

        idx = self.sf_combo.findData(current)
        if idx >= 0:
            self.sf_combo.setCurrentIndex(idx)
        else:
            for i in range(self.sf_combo.count()):
                if self.sf_combo.itemData(i):
                    self.sf_combo.setCurrentIndex(i)
                    break

        self._refresh_preset_combo()
        self._sync_control_state()
        self._update_sf_meta_label()

    def _on_soundfont_changed(self) -> None:
        if hasattr(self, "preset_combo"):
            self._refresh_preset_combo()
            self._sync_control_state()
        self._update_sf_meta_label()

    def _update_sf_meta_label(self) -> None:
        if not hasattr(self, "sf_meta_label"):
            return
        sf_data = self.sf_combo.currentData()
        if not sf_data:
            self.sf_meta_label.setText("")
            return
        info = self._soundfont_infos.get(normalize_path_key(Path(sf_data)))
        if info is None or not info.is_valid:
            self.sf_meta_label.setText("")
            return
        parts: list[str] = []
        if info.preset_count:
            parts.append(f"{info.preset_count} presets")
        if info.bank_count > 1:
            parts.append(f"{info.bank_count} banks")
        if info.sample_count:
            parts.append(f"{info.sample_count:,} samples")
        parts.append(f"{info.size_mb:.1f}\u202fMB")
        self.sf_meta_label.setText(" \u00b7 ".join(parts))

    def _refresh_preset_combo(self) -> None:
        if not hasattr(self, "preset_combo"):
            return
        previous = self.preset_combo.currentData()
        self.preset_combo.clear()

        sf_data = self.sf_combo.currentData()
        if not sf_data:
            self.preset_combo.addItem("No SoundFont selected", None)
            return

        info = self._soundfont_infos.get(normalize_path_key(Path(sf_data)))
        if info is None:
            self.preset_combo.addItem("Preset 0:0 - default", (0, 0))
            return

        if not info.is_valid:
            self.preset_combo.addItem("Preset list unavailable", None)
            return

        if not info.presets:
            self.preset_combo.addItem("Preset 0:0 - default", (0, 0))
            return

        for preset in info.presets:
            self.preset_combo.addItem(preset.label, (preset.bank, preset.preset))

        preferred_idx = self._find_preset_data(previous)
        if preferred_idx < 0:
            preferred_idx = self._find_preset_data((0, 0))
        self.preset_combo.setCurrentIndex(max(preferred_idx, 0))

    def _selected_soundfont_preset(self) -> tuple[int, int]:
        data = self.preset_combo.currentData()
        if isinstance(data, tuple) and len(data) == 2:
            return int(data[0]), int(data[1])
        return 0, 0

    def _find_preset_data(self, target) -> int:
        for idx in range(self.preset_combo.count()):
            if self.preset_combo.itemData(idx) == target:
                return idx
        return -1

    def _preview_selected_preset(self) -> None:
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return
        sf_data = self.sf_combo.currentData()
        if not sf_data:
            QMessageBox.warning(self, "Missing SoundFont", "Pick a SoundFont before previewing a preset.")
            return

        bank, preset = self._selected_soundfont_preset()
        preview_dir = Path(tempfile.gettempdir()) / "tunerize-previews"
        preview_path = preview_dir / "preset-preview.wav"
        if self._preview_player is not None:
            self._preview_player.stop()
        self.preview_preset_btn.setText("Rendering...")
        self.preview_preset_btn.setEnabled(False)
        self.stage_label.setText("Rendering preset preview...")

        self._preview_worker = _PreviewWorker(Path(sf_data), preview_path, bank, preset)
        self._preview_worker.finished_ok.connect(self._on_preview_done)
        self._preview_worker.finished_err.connect(self._on_preview_failed)
        self._preview_worker.start()

    @Slot(object)
    def _on_preview_done(self, path) -> None:
        self.preview_preset_btn.setText("Preview")
        self._sync_control_state()
        self.stage_label.setText("Preset preview ready.")
        self._log(f"Preview rendered: {Path(path).name}")
        if self._preview_player is None:
            QMessageBox.information(
                self,
                "Preview rendered",
                "The preset preview was rendered, but this PySide6 build cannot play it.",
            )
            return
        self._preview_player.stop()
        self._preview_player.setSource(QUrl.fromLocalFile(str(path)))
        self._preview_player.play()

    @Slot(str)
    def _on_preview_failed(self, err_msg: str) -> None:
        self.preview_preset_btn.setText("Preview")
        self._sync_control_state()
        self.stage_label.setText("Preset preview failed.")
        self._log(f"Preview failed: {err_msg}")
        QMessageBox.warning(self, "Preview failed", err_msg)

    def _update_mode_visibility(self) -> None:
        chiptune = self.mode_chiptune.isChecked()
        self.sf_frame.setVisible(not chiptune)
        if hasattr(self, "sf_meta_label"):
            self.sf_meta_label.setVisible(not chiptune)
        self._sync_control_state()

    def _log(self, msg: str) -> None:
        self.log_panel.appendPlainText(msg)

    def _set_audio_path(self, path: Path, *, announce: bool = False) -> None:
        self.input_edit.setText(str(path))
        self.stage_label.setText(f"Ready: {path.name}")
        if announce:
            self._log(f"Audio selected: {path}")

    def _remember_soundfont(self, path: Path, *, select: bool = False) -> None:
        try:
            remember_soundfont(path, self._settings_path)
        except (OSError, ValueError) as exc:
            self._log(f"Could not update recent SoundFonts: {exc}")
        self._refresh_soundfonts(select_path=path if select else None)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_control_state()

    def _sync_control_state(self) -> None:
        enabled = not self._busy
        for widget in (
            self.open_audio_btn,
            self.input_edit,
            self.mode_chiptune,
            self.mode_sf2,
            self.out_edit,
            self.output_btn,
            self.format_combo,
            self.demucs_check,
            self.multi_channel_check,
            self.sf_refresh_btn,
            self.sf_add_btn,
            self.sf_edit_btn,
            self.sf_browse_btn,
            self.sf_create_btn,
            self.transpose_spin,
            self.quantize_check,
            self.export_midi_check,
            self.min_note_spin,
            self.style_combo,
        ):
            widget.setEnabled(enabled)

        sf2_mode = self.mode_sf2.isChecked()
        for widget in self._soundfont_preset_widgets:
            widget.setVisible(sf2_mode)
        self.sf_combo.setEnabled(enabled and self._has_soundfonts)
        sf_selected = self.sf_combo.currentData() is not None
        polyphone_available = self._polyphone_exe is not None
        self.sf_edit_btn.setEnabled(enabled and self._has_soundfonts and sf_selected and polyphone_available)
        self.sf_edit_btn.setToolTip(
            "Open the selected SoundFont in bundled Polyphone."
            if polyphone_available
            else "Polyphone is not bundled; set TUNERIZE_POLYPHONE_EXE or TUNERIZE_POLYPHONE_DIR for source runs."
        )
        self.quantize_combo.setEnabled(enabled and self.quantize_check.isChecked())
        self.force_preset_check.setEnabled(enabled and sf2_mode and self._has_soundfonts)
        preset_available = self.preset_combo.currentData() is not None
        self.preset_combo.setEnabled(enabled and sf2_mode and self._has_soundfonts and preset_available)
        preview_running = self._preview_worker is not None and self._preview_worker.isRunning()
        self.preview_preset_btn.setEnabled(
            enabled and sf2_mode and self._has_soundfonts and preset_available and not preview_running
        )
        self.convert_btn.setEnabled(enabled and not preview_running)
        self.batch_btn.setEnabled(enabled and not preview_running)
        self.cancel_btn.setEnabled(self._busy)
        self.setAcceptDrops(enabled)
        # Show the FluidR3 quick-download button only when no soundfonts are present
        self.sf_fluids_btn.setVisible(not self._has_soundfonts)

        multi_ch = self.multi_channel_check.isChecked()
        self.monitor_check.setEnabled(enabled and not multi_ch)
        if multi_ch:
            self.monitor_check.setToolTip("Monitoring is not available in multi-channel mode.")
        else:
            self.monitor_check.setToolTip("Stream audio to your speakers in real time as the conversion runs.")

        mixer_enabled = enabled and self.mode_chiptune.isChecked()
        for widget in self._chiptune_mixer_widgets:
            widget.setVisible(self.mode_chiptune.isChecked())
            widget.setEnabled(mixer_enabled)

    def _audio_path_from_drop(self, event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> Path | None:
        if self._busy:
            return None
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_INPUT_EXTS:
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._audio_path_from_drop(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._audio_path_from_drop(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._audio_path_from_drop(event)
        if path is None:
            event.ignore()
            return
        self._set_audio_path(path, announce=True)
        event.acceptProposedAction()

    def _on_convert(self) -> None:
        audio = self.input_edit.text().strip()
        if not audio or not Path(audio).exists():
            QMessageBox.warning(self, "Missing input", "Pick an audio file first.")
            return

        chiptune_mode = self.mode_chiptune.isChecked()
        sf2_path: Path | None = None
        if not chiptune_mode:
            sf2_data = self.sf_combo.currentData()
            if not sf2_data:
                QMessageBox.warning(
                    self,
                    "Missing SoundFont",
                    "Pick a SoundFont, or switch to Chiptune Mode.",
                )
                return
            sf2_path = Path(sf2_data)
        elif not self._chiptune_mixer_has_audible_voice():
            QMessageBox.warning(
                self,
                "Mixer muted",
                "Enable at least one chiptune voice or raise a soloed voice above 0%.",
            )
            return

        out_dir_text = self.out_edit.text().strip()
        out_dir = Path(out_dir_text) if out_dir_text else Path(audio).parent
        voice_volumes, voice_mutes, voice_solos = self._chiptune_voice_settings()
        sf2_bank, sf2_preset = self._selected_soundfont_preset()

        try:
            config = PipelineConfig(
                audio_path=Path(audio),
                output_dir=out_dir,
                sf2_path=sf2_path,
                use_chiptune_engine=chiptune_mode,
                transpose=self.transpose_spin.value(),
                quantize=self.quantize_check.isChecked(),
                quantize_grid=self.quantize_combo.currentText(),
                sf2_bank=sf2_bank,
                sf2_preset=sf2_preset,
                force_preset=self.force_preset_check.isChecked(),
                forced_bank=sf2_bank,
                forced_preset=sf2_preset,
                min_note_ms=self.min_note_spin.value(),
                stem_separate=self.demucs_check.isChecked(),
                export_midi=self.export_midi_check.isChecked(),
                output_format=self.format_combo.currentData(),
                chiptune_engine=self._selected_chiptune_engine(),
                chiptune_voice_volumes=voice_volumes,
                chiptune_voice_mutes=voice_mutes,
                chiptune_voice_solos=voice_solos,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Configuration error", str(exc))
            return

        if sf2_path is not None:
            self._remember_soundfont(sf2_path, select=True)

        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.log_panel.clear()

        multi_channel = self.multi_channel_check.isChecked()
        mode_label = "Chiptune" if chiptune_mode else "SoundFont"
        self._log(
            f"Starting {'multi-channel ' if multi_channel else ''}conversion in "
            f"{mode_label} mode..."
        )

        use_monitor = self.monitor_check.isChecked() and is_monitoring_available()
        if use_monitor:
            self._audio_monitor = AudioMonitor(sample_rate=config.sample_rate)
            if not self._audio_monitor.start():
                self._log("Audio monitor: could not open output device, continuing without.")
                self._audio_monitor = None

        if multi_channel:
            self._multi_worker = _MultiChannelWorker(config)
            self._multi_worker.progress.connect(self._on_progress)
            self._multi_worker.log.connect(self._log)
            self._multi_worker.finished_ok.connect(self._on_multi_done_ok)
            self._multi_worker.finished_err.connect(self._on_done_err)
            self._multi_worker.start()
        else:
            self._worker = _Worker(config, monitor=use_monitor)
            self._worker.progress.connect(self._on_progress)
            self._worker.log.connect(self._log)
            if use_monitor:
                self._worker.monitor_chunk.connect(self._on_monitor_chunk)
            self._worker.finished_ok.connect(self._on_done_ok)
            self._worker.finished_err.connect(self._on_done_err)
            self._worker.start()

    def _on_cancel(self) -> None:
        if self._multi_worker is not None and self._multi_worker.isRunning():
            self._multi_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.stage_label.setText("Cancelling multi-channel...")
            self._log("Multi-channel cancellation requested...")
        elif self._batch_worker is not None and self._batch_worker.isRunning():
            self._batch_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.stage_label.setText("Cancelling batch...")
            self._log("Batch cancellation requested...")
        elif self._worker is not None:
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.stage_label.setText("Cancelling...")
            self._log("Cancellation requested...")

    def _on_batch(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose folder to batch-convert", str(Path.home())
        )
        if not folder:
            return
        folder_path = Path(folder)

        chiptune_mode = self.mode_chiptune.isChecked()
        sf2_path: Path | None = None
        if not chiptune_mode:
            sf2_data = self.sf_combo.currentData()
            if not sf2_data:
                QMessageBox.warning(self, "Missing SoundFont", "Pick a SoundFont, or switch to Chiptune Mode.")
                return
            sf2_path = Path(sf2_data)
        elif not self._chiptune_mixer_has_audible_voice():
            QMessageBox.warning(self, "Mixer muted", "Enable at least one chiptune voice first.")
            return

        from app.core.audio_io import SUPPORTED_INPUT_EXTS

        audio_files = sorted(p for p in folder_path.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTS)
        if not audio_files:
            QMessageBox.information(self, "No audio files", f"No supported audio files found in:\n{folder_path}")
            return

        out_dir_text = self.out_edit.text().strip()
        out_dir = Path(out_dir_text) if out_dir_text else folder_path
        voice_volumes, voice_mutes, voice_solos = self._chiptune_voice_settings()
        sf2_bank, sf2_preset = self._selected_soundfont_preset()

        configs: list[PipelineConfig] = []
        for audio_path in audio_files:
            try:
                configs.append(PipelineConfig(
                    audio_path=audio_path,
                    output_dir=out_dir,
                    sf2_path=sf2_path,
                    use_chiptune_engine=chiptune_mode,
                    transpose=self.transpose_spin.value(),
                    quantize=self.quantize_check.isChecked(),
                    quantize_grid=self.quantize_combo.currentText(),
                    sf2_bank=sf2_bank,
                    sf2_preset=sf2_preset,
                    force_preset=self.force_preset_check.isChecked(),
                    forced_bank=sf2_bank,
                    forced_preset=sf2_preset,
                    min_note_ms=self.min_note_spin.value(),
                    stem_separate=self.demucs_check.isChecked(),
                    export_midi=self.export_midi_check.isChecked(),
                    output_format=self.format_combo.currentData(),
                    chiptune_engine=self._selected_chiptune_engine(),
                    chiptune_voice_volumes=voice_volumes,
                    chiptune_voice_mutes=voice_mutes,
                    chiptune_voice_solos=voice_solos,
                ))
            except ValueError as exc:
                self._log(f"Skipping {audio_path.name}: {exc}")

        if not configs:
            QMessageBox.warning(self, "No valid files", "All files were skipped due to configuration errors.")
            return

        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.log_panel.clear()
        self._log(f"Batch: {len(configs)} file(s) from {folder_path}")

        self._batch_worker = _BatchWorker(configs)
        self._batch_worker.file_started.connect(self._on_batch_file_started)
        self._batch_worker.progress.connect(self._on_progress)
        self._batch_worker.log.connect(self._log)
        self._batch_worker.finished_all.connect(self._on_batch_done)
        self._batch_worker.start()

    @Slot(str, int, int)
    def _on_batch_file_started(self, filename: str, current: int, total: int) -> None:
        self.stage_label.setText(f"[{current}/{total}] {filename}")
        self.progress_bar.setValue(int(100 * (current - 1) / total))
        self._log(f"\n[{current}/{total}] {filename}")

    @Slot(list, list)
    def _on_batch_done(self, ok_paths: list, failed: list) -> None:
        self._set_busy(False)
        self.progress_bar.setValue(100)
        summary = f"Batch complete: {len(ok_paths)} succeeded, {len(failed)} failed."
        self.stage_label.setText(summary)
        self._log(f"\n{summary}")
        for name, reason in failed:
            self._log(f"  FAILED: {name}: {reason}")

    @Slot(str, int)
    def _on_progress(self, stage: str, pct: int) -> None:
        self.stage_label.setText(stage)
        self.progress_bar.setValue(pct)

    @Slot(object, int)
    def _on_monitor_chunk(self, chunk, sample_rate: int) -> None:
        if self._audio_monitor is not None and self._audio_monitor.active:
            self._audio_monitor.write_chunk(chunk)

    def _stop_monitor(self) -> None:
        if self._audio_monitor is not None:
            self._audio_monitor.stop()
            self._audio_monitor = None

    @Slot(object, object)
    def _on_done_ok(self, midi_path, wav_path) -> None:
        self._stop_monitor()
        self._set_busy(False)
        self.stage_label.setText("Done.")
        self.progress_bar.setValue(100)
        self._log(f"WAV written: {wav_path}")
        if midi_path is not None:
            self._log(f"MIDI written: {midi_path}")

    @Slot(list, list)
    def _on_multi_done_ok(self, midi_paths: list, audio_paths: list) -> None:
        self._stop_monitor()
        self._set_busy(False)
        self.progress_bar.setValue(100)
        count = len(audio_paths)
        self.stage_label.setText(f"Done — {count} stem(s) rendered.")
        for path in audio_paths:
            self._log(f"Stem output: {path}")
        for path in midi_paths:
            if path is not None:
                self._log(f"Stem MIDI: {path}")

    @Slot(str)
    def _on_done_err(self, err_msg: str) -> None:
        self._stop_monitor()
        self._set_busy(False)
        if "cancelled" in err_msg.lower():
            self.stage_label.setText("Cancelled.")
            self._log("Conversion cancelled.")
            return

        self.stage_label.setText("Failed.")
        self._log(f"ERROR: {err_msg}")
        QMessageBox.critical(self, "Conversion failed", err_msg)

    def _chiptune_voice_settings(self) -> tuple[
        tuple[float, float, float, float],
        tuple[bool, bool, bool, bool],
        tuple[bool, bool, bool, bool],
    ]:
        volumes = tuple(slider.value() / 100.0 for slider in self.voice_volume_sliders)
        mutes = tuple(check.isChecked() for check in self.voice_mute_checks)
        solos = tuple(check.isChecked() for check in self.voice_solo_checks)
        return (
            (volumes[0], volumes[1], volumes[2], volumes[3]),
            (mutes[0], mutes[1], mutes[2], mutes[3]),
            (solos[0], solos[1], solos[2], solos[3]),
        )

    def _chiptune_mixer_has_audible_voice(self) -> bool:
        volumes, mutes, solos = self._chiptune_voice_settings()
        if any(solos):
            return any(volume > 0.0 and solo for volume, solo in zip(volumes, solos, strict=True))
        return any(
            volume > 0.0 and not muted
            for volume, muted in zip(volumes, mutes, strict=True)
        )

    def _selected_chiptune_engine(self) -> str:
        return self.engine_combo.currentData() or ENGINE_NES

    def _update_chiptune_engine_labels(self) -> None:
        engine = self._selected_chiptune_engine()
        if engine == ENGINE_GAME_BOY:
            names = ("Pulse 1 lead", "Pulse 2 harmony", "Wave channel", "Noise drums")
        elif engine == ENGINE_SNES:
            names = ("Lead (V1-2)", "Harmony (V3-4)", "Bass (V5-6)", "Noise (V7-8)")
        elif engine == ENGINE_SEGA:
            names = ("FM Lead (CH1-3)", "FM Harmony (CH4-5)", "FM Bass (CH6)", "Rhythm")
        else:
            names = ("Pulse 1 lead", "Pulse 2 harmony", "Triangle bass", "Noise drums")
        for label, name in zip(self.voice_name_labels, names, strict=True):
            label.setText(name)
