"""Catppuccin Mocha-inspired dark theme for Tunerize."""
from __future__ import annotations

QSS = """
* { font-family: Segoe UI, Arial, sans-serif; }

QMainWindow, QWidget { background: #1e1e2e; color: #cdd6f4; }

QLabel { background: transparent; color: #cdd6f4; }
QLabel#title { font-size: 22pt; font-weight: 700; color: #cba6f7; }
QLabel#subtitle { font-size: 10pt; color: #a6adc8; padding-bottom: 8px; }
QLabel#stage { font-size: 10pt; color: #89b4fa; padding-top: 6px; }
QLabel#logLabel {
    font-size: 9pt; color: #6c7086; padding-top: 8px;
    text-transform: uppercase; letter-spacing: 1px;
}

QFrame#modeFrame, QFrame#sfFrame {
    background: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    padding: 6px 10px; selection-background-color: #585b70;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #89b4fa; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #6c7086; }

QPlainTextEdit#logPanel {
    font-family: 'Cascadia Mono', 'Consolas', 'Menlo', monospace;
    font-size: 9pt; padding: 10px;
}

QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #181825; color: #cdd6f4;
    border: 1px solid #313244; selection-background-color: #45475a;
    outline: none;
}

QRadioButton { color: #cdd6f4; spacing: 8px; }
QRadioButton::indicator {
    width: 15px; height: 15px; border-radius: 8px;
    border: 1px solid #585b70; background: #11111b;
}
QRadioButton::indicator:hover { border-color: #89b4fa; }
QRadioButton::indicator:checked {
    background: #89b4fa;
    border: 4px solid #11111b;
}

QPushButton {
    background: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 7px 14px; font-weight: 500;
}
QPushButton:hover { background: #45475a; border-color: #585b70; }
QPushButton:pressed { background: #585b70; }
QPushButton:disabled { background: #181825; color: #6c7086; border-color: #313244; }

QPushButton#convertBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #cba6f7, stop:1 #89b4fa);
    color: #1e1e2e; font-size: 11pt; font-weight: 700; border: none;
}
QPushButton#convertBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d6b8ff, stop:1 #9bc2ff);
}
QPushButton#convertBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b794eb, stop:1 #7aa6f0);
}
QPushButton#convertBtn:disabled {
    background: #313244; color: #6c7086;
}

QToolButton {
    background: transparent; color: #a6adc8; border: none;
    padding: 6px 4px; text-align: left; font-weight: 500;
}
QToolButton:hover { color: #cdd6f4; }
QToolButton:checked { color: #cba6f7; }

QCheckBox { color: #cdd6f4; spacing: 8px; padding: 4px 0; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 3px;
    border: 1px solid #585b70; background: #181825;
}
QCheckBox::indicator:hover { border-color: #89b4fa; }
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }

QProgressBar {
    background: #181825; border: 1px solid #313244; border-radius: 4px;
    height: 10px; text-align: center; color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #cba6f7, stop:1 #89b4fa);
    border-radius: 3px;
}

QTableView, QTextEdit {
    background: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    gridline-color: #313244; selection-background-color: #45475a;
    selection-color: #f5e0dc;
}
QTableView::item { padding: 6px; }
QHeaderView::section {
    background: #313244; color: #bac2de;
    border: none; border-right: 1px solid #45475a;
    padding: 7px 8px; font-weight: 600;
}
QSplitter::handle { background: #313244; height: 2px; }

QGroupBox {
    color: #a6adc8; border: 1px solid #313244; border-radius: 6px;
    padding-top: 18px; margin-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }

QScrollBar:vertical { background: #181825; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; background: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QMessageBox { background: #1e1e2e; }
QMessageBox QLabel { color: #cdd6f4; }
"""


def apply_dark_theme(app) -> None:
    """Apply the dark stylesheet to the QApplication."""
    app.setStyleSheet(QSS)
