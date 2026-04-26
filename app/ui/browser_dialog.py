"""Online SoundFont browser dialog — modal search/install UI."""
from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
)

from app.core.soundfont_browser import (
    BrowserError,
    GitHubTopicProvider,
    MusicalArtifactsProvider,
    Provider,
    RedditSoundFontsProvider,
    SoundFontResult,
    download_to_library,
)


class _SearchWorker(QThread):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, provider, query: str):
        super().__init__()
        self._provider = provider
        self._query = query

    def run(self) -> None:
        try:
            results = self._provider.search(self._query)
            self.done.emit(results)
        except BrowserError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")


class _DownloadWorker(QThread):
    progress = Signal(int, int)        # downloaded_bytes, total_bytes (0 if unknown)
    done = Signal(object)               # Path
    failed = Signal(str)

    def __init__(self, result: SoundFontResult, library_dir: Path):
        super().__init__()
        self._result = result
        self._library_dir = library_dir
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            path = download_to_library(
                self._result,
                self._library_dir,
                progress=lambda d, t: self.progress.emit(d, t or 0),
                cancel_check=lambda: self._cancelled,
            )
            self.done.emit(path)
        except BrowserError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")


class _ResultsModel(QAbstractTableModel):
    HEADERS = ("Name", "Author", "Size", "License", "Downloads / Stars / Score")

    def __init__(self):
        super().__init__()
        self._results: list[SoundFontResult] = []

    def set_results(self, results: list[SoundFontResult]) -> None:
        self.beginResetModel()
        self._results = list(results)
        self.endResetModel()

    def rowCount(self, parent=None) -> int:
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self._results)

    def columnCount(self, parent=None) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        r = self._results[index.row()]
        col = index.column()
        if col == 0:
            return r.name
        if col == 1:
            return r.author or "—"
        if col == 2:
            return _format_size(r.file_size_bytes)
        if col == 3:
            return r.license
        if col == 4:
            return f"{r.download_count:,}" if r.download_count else "—"
        return None

    def get_row(self, row: int) -> SoundFontResult | None:
        if 0 <= row < len(self._results):
            return self._results[row]
        return None


class BrowserDialog(QDialog):
    """Modal dialog: search public SoundFont libraries and install into `library_dir`."""

    sf_installed = Signal(object)  # Path

    def __init__(self, library_dir: Path, *, initial_query: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse Online SoundFonts")
        self.resize(960, 660)
        self._library_dir = library_dir
        self._search_worker: _SearchWorker | None = None
        self._dl_worker: _DownloadWorker | None = None
        cache_dir = Path.home() / ".tunerize" / "browser-cache"
        self._providers: dict[str, Provider] = {
            "musical-artifacts.com": MusicalArtifactsProvider(cache_dir=cache_dir),
            "github.com topic:soundfont": GitHubTopicProvider(cache_dir=cache_dir),
            "reddit r/soundfonts": RedditSoundFontsProvider(cache_dir=cache_dir),
        }
        self._provider = self._providers["musical-artifacts.com"]
        self._initial_query = initial_query

        self._build_ui()
        if initial_query:
            self.search_edit.setText(initial_query)
        self._do_search(initial_query)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        header = QLabel("Browse and install SoundFonts from public libraries.")
        header.setObjectName("browserHeader")
        root.addWidget(header)

        srow = QHBoxLayout()
        self.source_combo = QComboBox()
        for source_name in self._providers:
            self.source_combo.addItem(source_name)
        self.source_combo.setToolTip("Choose a public SoundFont source.")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search (e.g. 'piano', 'NES', 'orchestral')…")
        self.search_edit.returnPressed.connect(self._on_search_clicked)
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._on_search_clicked)

        srow.addWidget(QLabel("Source:"))
        srow.addWidget(self.source_combo)
        srow.addWidget(self.search_edit, 1)
        srow.addWidget(search_btn)
        root.addLayout(srow)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.model = _ResultsModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        sel = self.table.selectionModel()
        if sel is not None:
            sel.selectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        self.detail_panel = QTextBrowser()
        self.detail_panel.setReadOnly(True)
        self.detail_panel.setPlaceholderText(
            "Select a SoundFont to see its description, tags, and license."
        )
        self.detail_panel.setOpenExternalLinks(True)
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.status_label = QLabel("Loading…")
        self.status_label.setObjectName("browserStatus")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.status_label)
        root.addWidget(self.progress_bar)

        arow = QHBoxLayout()
        self.open_web_btn = QPushButton("Open in browser")
        self.open_web_btn.setEnabled(False)
        self.open_web_btn.clicked.connect(self._on_open_web)

        self.cancel_btn = QPushButton("Cancel download")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_download)

        self.install_btn = QPushButton("Download && Install")
        self.install_btn.setObjectName("convertBtn")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._on_install)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        arow.addWidget(self.open_web_btn)
        arow.addStretch(1)
        arow.addWidget(self.cancel_btn)
        arow.addWidget(self.install_btn)
        arow.addWidget(close_btn)
        root.addLayout(arow)

    # ---------- search ----------

    def _do_search(self, query: str) -> None:
        if self._search_worker is not None and self._search_worker.isRunning():
            return
        self._provider = self._providers[self.source_combo.currentText()]
        self.status_label.setText("Searching…")
        self.install_btn.setEnabled(False)
        self.open_web_btn.setEnabled(False)
        self.detail_panel.clear()
        self._search_worker = _SearchWorker(self._provider, query)
        self._search_worker.done.connect(self._on_search_done)
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_worker.start()

    def _on_search_clicked(self) -> None:
        self._do_search(self.search_edit.text().strip())

    def _on_source_changed(self) -> None:
        self._do_search(self.search_edit.text().strip())

    @Slot(list)
    def _on_search_done(self, results: list) -> None:
        self.model.set_results(results)
        if results:
            self.status_label.setText(f"{len(results)} result(s) from {self._provider.name}")
            self.table.selectRow(0)
        else:
            self.status_label.setText("No results.")

    @Slot(str)
    def _on_search_failed(self, err: str) -> None:
        self.status_label.setText("Search failed.")
        QMessageBox.warning(self, "Search failed", err)

    # ---------- selection / detail ----------

    def _on_selection_changed(self, *_) -> None:
        idx = self.table.currentIndex()
        row = self.model.get_row(idx.row())
        if row is None:
            self.install_btn.setEnabled(False)
            self.open_web_btn.setEnabled(False)
            return
        self._show_detail(row)
        self.install_btn.setEnabled(bool(row.file_url))
        self.install_btn.setToolTip("" if row.file_url else "Open the Reddit post to review its download links.")
        self.open_web_btn.setEnabled(bool(row.detail_url))

    def _show_detail(self, r: SoundFontResult) -> None:
        tags_html = " ".join(f"<code>{escape(t)}</code>" for t in r.tags) or "—"
        size = _format_size(r.file_size_bytes)
        desc = escape(r.description).replace("\n", "<br>") if r.description else "<i>No description.</i>"
        source_note = (
            "Direct download detected."
            if r.file_url
            else "No direct download detected. Open the source page to review links."
        )
        html = (
            f"<h3 style='margin-bottom:4px'>{escape(r.name)}</h3>"
            f"<p style='color:#a6adc8;margin:0'>"
            f"<b>Author:</b> {escape(r.author or '—')} &nbsp;·&nbsp; "
            f"<b>License:</b> {escape(r.license)} &nbsp;·&nbsp; "
            f"<b>Size:</b> {size}</p>"
            f"<p><b>Tags:</b> {tags_html}</p>"
            f"<p>{desc}</p>"
            f"<p style='color:#6c7086'>"
            f"<b>Source:</b> {escape(r.source)} &nbsp;·&nbsp; "
            f"{escape(source_note)} &nbsp;·&nbsp; "
            f"<a href='{escape(r.detail_url, quote=True)}'>web page</a></p>"
        )
        self.detail_panel.setHtml(html)

    def _on_open_web(self) -> None:
        idx = self.table.currentIndex()
        row = self.model.get_row(idx.row())
        if row and row.detail_url:
            QDesktopServices.openUrl(QUrl(row.detail_url))

    # ---------- download / install ----------

    def _on_install(self) -> None:
        idx = self.table.currentIndex()
        row = self.model.get_row(idx.row())
        if row is None:
            return
        if not row.file_url:
            QMessageBox.warning(self, "No file", "This entry has no downloadable file.")
            return

        self.install_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Downloading {row.name} from {row.source}…")

        self._dl_worker = _DownloadWorker(row, self._library_dir)
        self._dl_worker.progress.connect(self._on_download_progress)
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.failed.connect(self._on_download_failed)
        self._dl_worker.start()

    def _on_cancel_download(self) -> None:
        if self._dl_worker is not None:
            self._dl_worker.cancel()
            self.status_label.setText("Cancelling download…")

    @Slot(int, int)
    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(100 * downloaded / total))
            self.status_label.setText(
                f"Downloading: {_format_size(downloaded)} / {_format_size(total)}"
            )
        else:
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(f"Downloading: {_format_size(downloaded)}")

    @Slot(object)
    def _on_download_done(self, path) -> None:
        self.install_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Installed: {path.name}")
        if Path(path).suffix.lower() in (".sf2", ".sf3"):
            self.sf_installed.emit(path)
            QMessageBox.information(
                self,
                "Installed",
                f"{path.name} was added to your soundfonts folder.\n\n"
                "It's now available in the main SoundFont dropdown.",
            )
        else:
            QMessageBox.information(
                self,
                "Bundle downloaded",
                f"{path.name} was saved to your soundfonts folder.\n\n"
                "Unpack it, then import any .sf2 or .sf3 files inside.",
            )

    @Slot(str)
    def _on_download_failed(self, err: str) -> None:
        self.install_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Download failed.")
        QMessageBox.warning(self, "Download failed", err)


def _format_size(n: int | None) -> str:
    if not n:
        return "—"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
