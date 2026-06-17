"""SF2 Creator dialog — build SoundFonts from WAV samples or chiptune voices."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf_lib

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen

try:
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:
    QSoundEffect = None
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.chiptune import ENGINE_GAME_BOY, ENGINE_NES, ENGINE_SEGA, ENGINE_SID, ENGINE_SNES
from app.core.chiptune_sf2 import export_chiptune_sf2
from app.core.sf2_writer import SF2Bank, SF2Preset, SF2Sample, SF2Zone, write_sf2


class _SampleWaveform(QWidget):
    """Inline waveform display for a sample's int16 data."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(50)
        self.setMaximumHeight(70)
        self._peaks: np.ndarray | None = None
        self._loop_start_pct = 0.0
        self._loop_end_pct = 1.0
        self._loop_enabled = False

    def set_sample(self, data: np.ndarray, loop_start: int, loop_end: int, loop_enabled: bool) -> None:
        n = len(data)
        self._loop_enabled = loop_enabled
        self._loop_start_pct = loop_start / max(n, 1)
        self._loop_end_pct = loop_end / max(n, 1) if loop_end > 0 else 1.0
        w = max(self.width(), 1)
        chunk = max(1, n // w)
        if n == 0:
            self._peaks = None
        else:
            trimmed = np.abs(data[:chunk * w].astype(np.float32)).reshape(-1, chunk)
            self._peaks = np.max(trimmed, axis=1)
        self.update()

    def clear(self) -> None:
        self._peaks = None
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._peaks is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2
        peak_max = float(np.max(self._peaks)) or 1.0
        pen = QPen(QColor("#89b4fa"), 1)
        painter.setPen(pen)
        for x in range(min(len(self._peaks), w)):
            amp = self._peaks[x] / peak_max
            bar = max(1, int(amp * mid))
            painter.drawLine(x, mid - bar, x, mid + bar)
        if self._loop_enabled:
            loop_pen = QPen(QColor("#a6e3a1"), 1)
            painter.setPen(loop_pen)
            ls = int(self._loop_start_pct * w)
            le = int(self._loop_end_pct * w)
            painter.drawLine(ls, 0, ls, h)
            painter.drawLine(le, 0, le, h)
        painter.end()


class _SampleEntry:
    """Internal state for one imported sample."""

    def __init__(self, path: Path, data: np.ndarray, sample_rate: int) -> None:
        self.path = path
        self.name = path.stem[:20]
        self.data = data
        self.sample_rate = sample_rate
        self.original_pitch = 60
        self.key_lo = 0
        self.key_hi = 127
        self.loop_start = 0
        self.loop_end = 0
        self.loop_enabled = False
        self.attack_ms = 2.0
        self.decay_ms = 20.0
        self.sustain_pct = 25.0
        self.release_ms = 40.0


class SF2CreatorDialog(QDialog):
    sf2_created = Signal(str)

    def __init__(
        self,
        library_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create SoundFont")
        self.setMinimumSize(780, 580)
        self.resize(880, 640)
        self._library_dir = library_dir
        self._samples: list[_SampleEntry] = []
        self._updating = False
        self._player = QSoundEffect(self) if QSoundEffect is not None else None
        if self._player is not None:
            self._player.setVolume(0.7)
        self._preview_dir = Path(tempfile.gettempdir()) / "tunerize-sf2-preview"
        self._build_ui()
        self._sync_controls()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- top: SF2 name + preset number ---
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("SoundFont name:"))
        self._name_edit = QLineEdit("My SoundFont")
        self._name_edit.setMaxLength(255)
        self._name_edit.setAccessibleName("SoundFont name")
        top_row.addWidget(self._name_edit, 1)

        top_row.addWidget(QLabel("Preset:"))
        self._preset_num_spin = QSpinBox()
        self._preset_num_spin.setRange(0, 127)
        self._preset_num_spin.setAccessibleName("Preset number")
        top_row.addWidget(self._preset_num_spin)

        top_row.addWidget(QLabel("Bank:"))
        self._bank_spin = QSpinBox()
        self._bank_spin.setRange(0, 128)
        self._bank_spin.setAccessibleName("Bank number")
        top_row.addWidget(self._bank_spin)
        root.addLayout(top_row)

        # --- main: splitter with sample list + properties ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # left: sample list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Samples"))
        self._sample_list = QListWidget()
        self._sample_list.setAccessibleName("Imported samples")
        self._sample_list.currentRowChanged.connect(self._on_sample_selected)
        left_layout.addWidget(self._sample_list, 1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add WAV…")
        self._add_btn.clicked.connect(self._add_samples)
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.clicked.connect(self._remove_sample)
        self._play_btn = QPushButton("Play")
        self._play_btn.setToolTip("Audition the selected sample")
        self._play_btn.clicked.connect(self._play_sample)
        self._play_btn.setEnabled(QSoundEffect is not None)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addWidget(self._play_btn)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        # right: properties
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # sample name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._sample_name_edit = QLineEdit()
        self._sample_name_edit.setMaxLength(20)
        self._sample_name_edit.setAccessibleName("Sample name")
        self._sample_name_edit.textChanged.connect(self._on_prop_changed)
        name_row.addWidget(self._sample_name_edit, 1)
        right_layout.addLayout(name_row)

        # key mapping
        key_group = QGroupBox("Key mapping")
        key_layout = QHBoxLayout(key_group)
        key_layout.addWidget(QLabel("Root key:"))
        self._root_spin = QSpinBox()
        self._root_spin.setRange(0, 127)
        self._root_spin.setValue(60)
        self._root_spin.setAccessibleName("Root key MIDI note")
        self._root_spin.valueChanged.connect(self._on_prop_changed)
        key_layout.addWidget(self._root_spin)

        key_layout.addWidget(QLabel("Range:"))
        self._key_lo_spin = QSpinBox()
        self._key_lo_spin.setRange(0, 127)
        self._key_lo_spin.setAccessibleName("Key range low")
        self._key_lo_spin.valueChanged.connect(self._on_prop_changed)
        key_layout.addWidget(self._key_lo_spin)
        key_layout.addWidget(QLabel("–"))
        self._key_hi_spin = QSpinBox()
        self._key_hi_spin.setRange(0, 127)
        self._key_hi_spin.setValue(127)
        self._key_hi_spin.setAccessibleName("Key range high")
        self._key_hi_spin.valueChanged.connect(self._on_prop_changed)
        key_layout.addWidget(self._key_hi_spin)
        right_layout.addWidget(key_group)

        # loop points
        loop_group = QGroupBox("Loop")
        loop_layout = QHBoxLayout(loop_group)
        self._loop_check = QCheckBox("Enable loop")
        self._loop_check.toggled.connect(self._on_prop_changed)
        loop_layout.addWidget(self._loop_check)

        loop_layout.addWidget(QLabel("Start:"))
        self._loop_start_spin = QSpinBox()
        self._loop_start_spin.setRange(0, 999999999)
        self._loop_start_spin.setAccessibleName("Loop start sample")
        self._loop_start_spin.valueChanged.connect(self._on_prop_changed)
        loop_layout.addWidget(self._loop_start_spin)

        loop_layout.addWidget(QLabel("End:"))
        self._loop_end_spin = QSpinBox()
        self._loop_end_spin.setRange(0, 999999999)
        self._loop_end_spin.setAccessibleName("Loop end sample")
        self._loop_end_spin.valueChanged.connect(self._on_prop_changed)
        loop_layout.addWidget(self._loop_end_spin)

        self._sample_len_label = QLabel()
        loop_layout.addWidget(self._sample_len_label)
        right_layout.addWidget(loop_group)

        # ADSR envelope
        adsr_group = QGroupBox("Volume envelope (ADSR)")
        adsr_layout = QHBoxLayout(adsr_group)

        adsr_layout.addWidget(QLabel("A:"))
        self._attack_spin = QDoubleSpinBox()
        self._attack_spin.setRange(0, 10000)
        self._attack_spin.setValue(2.0)
        self._attack_spin.setSuffix(" ms")
        self._attack_spin.setAccessibleName("Attack time")
        self._attack_spin.valueChanged.connect(self._on_prop_changed)
        adsr_layout.addWidget(self._attack_spin)

        adsr_layout.addWidget(QLabel("D:"))
        self._decay_spin = QDoubleSpinBox()
        self._decay_spin.setRange(0, 10000)
        self._decay_spin.setValue(20.0)
        self._decay_spin.setSuffix(" ms")
        self._decay_spin.setAccessibleName("Decay time")
        self._decay_spin.valueChanged.connect(self._on_prop_changed)
        adsr_layout.addWidget(self._decay_spin)

        adsr_layout.addWidget(QLabel("S:"))
        self._sustain_spin = QDoubleSpinBox()
        self._sustain_spin.setRange(0, 100)
        self._sustain_spin.setValue(25.0)
        self._sustain_spin.setSuffix(" %")
        self._sustain_spin.setAccessibleName("Sustain level")
        self._sustain_spin.setToolTip("Sustain attenuation: 0% = full volume, 100% = silent")
        self._sustain_spin.valueChanged.connect(self._on_prop_changed)
        adsr_layout.addWidget(self._sustain_spin)

        adsr_layout.addWidget(QLabel("R:"))
        self._release_spin = QDoubleSpinBox()
        self._release_spin.setRange(0, 10000)
        self._release_spin.setValue(40.0)
        self._release_spin.setSuffix(" ms")
        self._release_spin.setAccessibleName("Release time")
        self._release_spin.valueChanged.connect(self._on_prop_changed)
        adsr_layout.addWidget(self._release_spin)

        right_layout.addWidget(adsr_group)

        self._sample_waveform = _SampleWaveform()
        right_layout.addWidget(self._sample_waveform)
        right_layout.addStretch(1)

        splitter.addWidget(right)
        splitter.setSizes([280, 500])
        root.addWidget(splitter, 1)

        # --- chiptune export ---
        chip_row = QHBoxLayout()
        chip_row.addWidget(QLabel("Quick export:"))
        self._chip_combo = QComboBox()
        self._chip_combo.addItem("NES APU voices", ENGINE_NES)
        self._chip_combo.addItem("Game Boy DMG voices", ENGINE_GAME_BOY)
        self._chip_combo.addItem("SNES SPC700 voices", ENGINE_SNES)
        self._chip_combo.addItem("Sega Genesis FM voices", ENGINE_SEGA)
        self._chip_combo.addItem("C64 SID voices", ENGINE_SID)
        chip_row.addWidget(self._chip_combo)
        self._chip_export_btn = QPushButton("Export Chiptune as SF2…")
        self._chip_export_btn.clicked.connect(self._export_chiptune)
        chip_row.addWidget(self._chip_export_btn)
        chip_row.addStretch(1)
        root.addLayout(chip_row)

        # --- bottom: export ---
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self._export_btn = QPushButton("Export SF2…")
        self._export_btn.setMinimumHeight(40)
        self._export_btn.clicked.connect(self._export_sf2)
        bottom.addWidget(self._export_btn)
        self._close_btn = QPushButton("Close")
        self._close_btn.setMinimumHeight(40)
        self._close_btn.clicked.connect(self.close)
        bottom.addWidget(self._close_btn)
        root.addLayout(bottom)

    def _add_samples(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import WAV samples",
            str(Path.home()),
            "Audio (*.wav *.flac *.aiff *.aif);;All files (*)",
        )
        for path_str in paths:
            path = Path(path_str)
            try:
                data, sr = sf_lib.read(str(path), dtype="int16", always_2d=False)
                if data.ndim == 2:
                    data = data.mean(axis=1).astype(np.int16)
                entry = _SampleEntry(path, data, sr)
                self._samples.append(entry)
                item = QListWidgetItem(entry.name)
                self._sample_list.addItem(item)
            except Exception as exc:
                QMessageBox.warning(self, "Import failed", f"{path.name}: {exc}")

        if self._samples and self._sample_list.currentRow() < 0:
            self._sample_list.setCurrentRow(0)

        self._auto_distribute_keys()
        self._sync_controls()

    def _remove_sample(self) -> None:
        row = self._sample_list.currentRow()
        if row < 0:
            return
        self._samples.pop(row)
        self._sample_list.takeItem(row)
        self._auto_distribute_keys()
        self._sync_controls()

    def _auto_distribute_keys(self) -> None:
        n = len(self._samples)
        if n == 0:
            return
        if n == 1:
            self._samples[0].key_lo = 0
            self._samples[0].key_hi = 127
            return

        sorted_indices = sorted(range(n), key=lambda i: self._samples[i].original_pitch)
        span = 128 // n
        for rank, idx in enumerate(sorted_indices):
            self._samples[idx].key_lo = rank * span
            self._samples[idx].key_hi = (rank + 1) * span - 1 if rank < n - 1 else 127

        row = self._sample_list.currentRow()
        if 0 <= row < n:
            self._load_sample_props(row)

    def _on_sample_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._samples):
            return
        self._load_sample_props(row)
        self._sync_controls()

    def _load_sample_props(self, row: int) -> None:
        self._updating = True
        s = self._samples[row]
        self._sample_name_edit.setText(s.name)
        self._root_spin.setValue(s.original_pitch)
        self._key_lo_spin.setValue(s.key_lo)
        self._key_hi_spin.setValue(s.key_hi)
        self._loop_check.setChecked(s.loop_enabled)
        self._loop_start_spin.setValue(s.loop_start)
        self._loop_end_spin.setMaximum(len(s.data) - 1)
        self._loop_end_spin.setValue(s.loop_end if s.loop_end > 0 else len(s.data) - 1)
        self._loop_start_spin.setMaximum(len(s.data) - 1)
        self._sample_len_label.setText(f"({len(s.data):,} samples)")
        self._attack_spin.setValue(s.attack_ms)
        self._decay_spin.setValue(s.decay_ms)
        self._sustain_spin.setValue(s.sustain_pct)
        self._release_spin.setValue(s.release_ms)
        self._sample_waveform.set_sample(s.data, s.loop_start, s.loop_end, s.loop_enabled)
        self._updating = False

    def _on_prop_changed(self) -> None:
        if self._updating:
            return
        row = self._sample_list.currentRow()
        if row < 0 or row >= len(self._samples):
            return
        s = self._samples[row]
        s.name = self._sample_name_edit.text()[:20]
        s.original_pitch = self._root_spin.value()
        s.key_lo = self._key_lo_spin.value()
        s.key_hi = self._key_hi_spin.value()
        s.loop_enabled = self._loop_check.isChecked()
        s.loop_start = self._loop_start_spin.value()
        s.loop_end = self._loop_end_spin.value()
        s.attack_ms = self._attack_spin.value()
        s.decay_ms = self._decay_spin.value()
        s.sustain_pct = self._sustain_spin.value()
        s.release_ms = self._release_spin.value()
        self._check_key_overlaps()
        self._sample_waveform.set_sample(s.data, s.loop_start, s.loop_end, s.loop_enabled)

        item = self._sample_list.item(row)
        if item is not None:
            item.setText(s.name)

    def _check_key_overlaps(self) -> None:
        """Mark list items with a warning icon if their key ranges overlap."""
        n = len(self._samples)
        for i in range(n):
            has_overlap = False
            si = self._samples[i]
            for j in range(n):
                if i == j:
                    continue
                sj = self._samples[j]
                if si.key_lo <= sj.key_hi and sj.key_lo <= si.key_hi:
                    has_overlap = True
                    break
            item = self._sample_list.item(i)
            if item is not None:
                prefix = "⚠ " if has_overlap else ""
                name = self._samples[i].name
                if has_overlap:
                    item.setToolTip("Key range overlaps with another sample")
                else:
                    item.setToolTip("")
                item.setText(f"{prefix}{name}")

    def _play_sample(self) -> None:
        if self._player is None:
            return
        row = self._sample_list.currentRow()
        if row < 0 or row >= len(self._samples):
            return
        entry = self._samples[row]
        self._preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = self._preview_dir / "preview.wav"
        sf_lib.write(str(preview_path), entry.data, entry.sample_rate, subtype="PCM_16")
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(preview_path)))
        self._player.play()

    def _sync_controls(self) -> None:
        has_samples = len(self._samples) > 0
        selected = self._sample_list.currentRow() >= 0

        self._remove_btn.setEnabled(selected)
        self._play_btn.setEnabled(selected and self._player is not None)
        self._export_btn.setEnabled(has_samples)

        for widget in (
            self._sample_name_edit,
            self._root_spin,
            self._key_lo_spin,
            self._key_hi_spin,
            self._loop_check,
            self._loop_start_spin,
            self._loop_end_spin,
            self._attack_spin,
            self._decay_spin,
            self._sustain_spin,
            self._release_spin,
        ):
            widget.setEnabled(selected)

        loop_on = selected and self._loop_check.isChecked()
        self._loop_start_spin.setEnabled(loop_on)
        self._loop_end_spin.setEnabled(loop_on)

    def _export_sf2(self) -> None:
        if not self._samples:
            QMessageBox.warning(self, "No samples", "Add at least one WAV sample first.")
            return

        sf2_name = self._name_edit.text().strip() or "My SoundFont"
        default_path = self._library_dir / f"{sf2_name}.sf2"
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save SoundFont",
            str(default_path),
            "SoundFont (*.sf2);;Compressed SoundFont (*.sf3);;All files (*)",
        )
        if not path:
            return

        compressed = Path(path).suffix.lower() == ".sf3" or "sf3" in selected_filter.lower()

        try:
            sf2_bank = SF2Bank(name=sf2_name)
            zones: list[SF2Zone] = []

            for entry in self._samples:
                idx = sf2_bank.add_sample(SF2Sample(
                    name=entry.name,
                    data=entry.data.copy(),
                    sample_rate=entry.sample_rate,
                    original_pitch=entry.original_pitch,
                    loop_start=entry.loop_start,
                    loop_end=entry.loop_end,
                    loop_enabled=entry.loop_enabled,
                ))
                zones.append(SF2Zone(
                    sample_index=idx,
                    key_lo=entry.key_lo,
                    key_hi=entry.key_hi,
                    root_key=entry.original_pitch,
                    attack_ms=entry.attack_ms,
                    decay_ms=entry.decay_ms,
                    sustain_pct=entry.sustain_pct,
                    release_ms=entry.release_ms,
                ))

            sf2_bank.add_preset(SF2Preset(
                name=sf2_name[:20],
                preset_number=self._preset_num_spin.value(),
                bank=self._bank_spin.value(),
                zones=zones,
            ))

            result = write_sf2(sf2_bank, Path(path), compressed=compressed)
            self.sf2_created.emit(str(result))
            QMessageBox.information(
                self,
                "SoundFont exported",
                f"Saved {result.name}\n{len(self._samples)} sample(s), {result.stat().st_size / 1024:.0f} KB",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_chiptune(self) -> None:
        engine = self._chip_combo.currentData()
        engine_name = self._chip_combo.currentText().split(" voices")[0]
        default_name = f"Tunerize {engine_name}.sf2"
        default_path = self._library_dir / default_name

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chiptune SoundFont",
            str(default_path),
            "SoundFont (*.sf2);;All files (*)",
        )
        if not path:
            return

        try:
            result = export_chiptune_sf2(engine, Path(path))
            self.sf2_created.emit(str(result))
            QMessageBox.information(
                self,
                "Chiptune SF2 exported",
                f"Saved {result.name}\n{engine_name} voices ({result.stat().st_size / 1024:.0f} KB)",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
