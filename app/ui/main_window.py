"""Tunerize main window — single-window converter UI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
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
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.pipeline import ConversionPipeline, PipelineConfig
from app.core.soundfonts import SoundFontLibrary


class _Worker(QThread):
    progress = Signal(str, int)
    log = Signal(str)
    finished_ok = Signal(object, object)   # (midi_path | None, wav_path)
    finished_err = Signal(str)

    def __init__(self, config: PipelineConfig):
        super().__init__()
        self._config = config
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            pipeline = ConversionPipeline(
                self._config,
                progress=lambda s, p: self.progress.emit(s, p),
                log=lambda m: self.log.emit(m),
                cancel_check=lambda: self._cancelled,
            )
            midi_out, wav_out = pipeline.run()
            self.finished_ok.emit(midi_out, wav_out)
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
    def __init__(self, soundfonts_dir: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"Tunerize  v{__version__}")
        self.setMinimumSize(760, 620)
        self.resize(960, 760)

        self.library = SoundFontLibrary(soundfonts_dir or Path.cwd() / "soundfonts")
        self._worker: _Worker | None = None

        self._build_ui()
        self._refresh_soundfonts()
        self._update_mode_visibility()

    # ---------- UI construction ----------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(12)

        title = QLabel("Tunerize")
        title.setObjectName("title")
        subtitle = QLabel("Re-render audio as chiptune — or through any SoundFont.")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._mode_section())
        root.addLayout(self._input_row())
        root.addWidget(self._soundfont_frame())
        root.addLayout(self._output_row())

        self.demucs_check = QCheckBox(
            "Stem-separate first (Demucs) — slower, much better on full songs"
        )
        root.addWidget(self.demucs_check)

        root.addWidget(self._advanced_section())
        root.addLayout(self._action_row())
        root.addLayout(self._progress_section())
        root.addWidget(self._log_section(), 1)

        self.setCentralWidget(central)

    def _mode_section(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("modeFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
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
        self.input_edit.setPlaceholderText("Pick an audio file (.mp3 / .wav / .flac / .ogg / .m4a)")
        self.input_edit.setReadOnly(True)
        btn = QPushButton("Open Audio…")
        btn.clicked.connect(self._pick_audio)

        row = QHBoxLayout()
        row.addWidget(QLabel("Audio:"))
        row.addWidget(self.input_edit, 1)
        row.addWidget(btn)
        return row

    def _soundfont_frame(self) -> QWidget:
        self.sf_frame = QFrame()
        self.sf_frame.setObjectName("sfFrame")
        layout = QHBoxLayout(self.sf_frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sf_combo = QComboBox()
        add_btn = QPushButton("Add SoundFont…")
        add_btn.clicked.connect(self._add_soundfont)
        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("Re-scan soundfonts/ folder")
        refresh_btn.setFixedWidth(36)
        refresh_btn.clicked.connect(self._refresh_soundfonts)

        layout.addWidget(QLabel("SoundFont:"))
        layout.addWidget(self.sf_combo, 1)
        layout.addWidget(refresh_btn)
        layout.addWidget(add_btn)
        return self.sf_frame

    def _output_row(self) -> QHBoxLayout:
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Default: same folder as input")
        btn = QPushButton("Choose…")
        btn.clicked.connect(self._pick_output)

        row = QHBoxLayout()
        row.addWidget(QLabel("Output:"))
        row.addWidget(self.out_edit, 1)
        row.addWidget(btn)
        return row

    def _advanced_section(self) -> QWidget:
        adv = _CollapsibleBox("Advanced settings")
        layout = QGridLayout()
        layout.setContentsMargins(20, 6, 0, 6)

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
        self.quantize_check.toggled.connect(self.quantize_combo.setEnabled)
        layout.addWidget(self.quantize_check, 1, 0)
        layout.addWidget(self.quantize_combo, 1, 1)

        self.force_preset_check = QCheckBox("Force all notes to preset (SF2 mode)")
        self.preset_spin = QSpinBox()
        self.preset_spin.setRange(0, 127)
        self.preset_spin.setEnabled(False)
        self.force_preset_check.toggled.connect(self.preset_spin.setEnabled)
        layout.addWidget(self.force_preset_check, 2, 0)
        layout.addWidget(self.preset_spin, 2, 1)

        self.export_midi_check = QCheckBox("Also export intermediate .mid file")
        self.export_midi_check.setChecked(True)
        layout.addWidget(self.export_midi_check, 3, 0, 1, 2)

        self.min_note_spin = QSpinBox()
        self.min_note_spin.setRange(20, 500)
        self.min_note_spin.setValue(58)
        self.min_note_spin.setSuffix(" ms")
        layout.addWidget(QLabel("Min note length:"), 4, 0)
        layout.addWidget(self.min_note_spin, 4, 1)

        adv.setContentLayout(layout)
        return adv

    def _action_row(self) -> QHBoxLayout:
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setObjectName("convertBtn")
        self.convert_btn.setMinimumHeight(46)
        self.convert_btn.clicked.connect(self._on_convert)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(46)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)

        row = QHBoxLayout()
        row.addWidget(self.convert_btn, 1)
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
            self.input_edit.setText(path)

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
            self._refresh_soundfonts()
            idx = self.sf_combo.findData(str(new_sf.path))
            if idx >= 0:
                self.sf_combo.setCurrentIndex(idx)
            self._log(f"Imported SoundFont: {new_sf.name}")
        except Exception as exc:
            self._log(f"Import failed: {exc}")
            QMessageBox.warning(self, "Import failed", str(exc))

    def _refresh_soundfonts(self) -> None:
        self.sf_combo.clear()
        sounds = self.library.scan()
        if not sounds:
            self.sf_combo.addItem(
                "(no soundfonts found — drop .sf2 files into ./soundfonts/)", None
            )
            self.sf_combo.setEnabled(False)
        else:
            self.sf_combo.setEnabled(True)
            for sf in sounds:
                label = f"{sf.name} ({sf.size_mb:.1f} MB)"
                if not sf.is_valid:
                    label += "  — INVALID"
                self.sf_combo.addItem(label, str(sf.path))

    def _update_mode_visibility(self) -> None:
        chiptune = self.mode_chiptune.isChecked()
        self.sf_frame.setVisible(not chiptune)

    def _log(self, msg: str) -> None:
        self.log_panel.appendPlainText(msg)

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

        out_dir_text = self.out_edit.text().strip()
        out_dir = Path(out_dir_text) if out_dir_text else Path(audio).parent

        try:
            config = PipelineConfig(
                audio_path=Path(audio),
                output_dir=out_dir,
                sf2_path=sf2_path,
                use_chiptune_engine=chiptune_mode,
                transpose=self.transpose_spin.value(),
                quantize=self.quantize_check.isChecked(),
                quantize_grid=self.quantize_combo.currentText(),
                force_preset=self.force_preset_check.isChecked(),
                forced_preset=self.preset_spin.value(),
                min_note_ms=self.min_note_spin.value(),
                stem_separate=self.demucs_check.isChecked(),
                export_midi=self.export_midi_check.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Configuration error", str(exc))
            return

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_panel.clear()
        self._log(
            f"Starting conversion in "
            f"{'Chiptune' if chiptune_mode else 'SoundFont'} mode..."
        )

        self._worker = _Worker(config)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log)
        self._worker.finished_ok.connect(self._on_done_ok)
        self._worker.finished_err.connect(self._on_done_err)
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._log("Cancellation requested...")

    @Slot(str, int)
    def _on_progress(self, stage: str, pct: int) -> None:
        self.stage_label.setText(stage)
        self.progress_bar.setValue(pct)

    @Slot(object, object)
    def _on_done_ok(self, midi_path, wav_path) -> None:
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.stage_label.setText("Done.")
        self.progress_bar.setValue(100)
        self._log(f"WAV written: {wav_path}")
        if midi_path is not None:
            self._log(f"MIDI written: {midi_path}")

    @Slot(str)
    def _on_done_err(self, err_msg: str) -> None:
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.stage_label.setText("Failed.")
        self._log(f"ERROR: {err_msg}")
        QMessageBox.critical(self, "Conversion failed", err_msg)
