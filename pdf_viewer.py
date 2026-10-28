"""
pdf_viewer.py - Central PDF Viewing Component

Provides high-fidelity rendering, continuous scrolling, zoom controls,
page navigation, and fast text search using QPdfView and QPdfDocument.
"""

from __future__ import annotations
from typing import Optional, List, Tuple
from PySide6.QtCore import QObject, Signal, QByteArray, QBuffer, QIODevice, QPointF, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QToolButton,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
import pymupdf
from page_model import DocumentModel


class SearchMatch:
    """Represents a search match result."""
    def __init__(self, page_index: int, rect: Optional[pymupdf.Rect] = None):
        self.page_index = page_index
        self.rect = rect


class SearchBar(QFrame):
    """Modern inline search bar that docks at the top or bottom of the viewer."""

    find_next = Signal(str)
    find_prev = Signal(str)
    search_closed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SearchBar")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self.search_label = QLabel("Find:")
        self.search_label.setStyleSheet("font-weight: bold; color: #4b5563;")
        layout.addWidget(self.search_label)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Search in document...")
        self.input_field.setClearButtonEnabled(True)
        self.input_field.setMinimumWidth(200)
        self.input_field.returnPressed.connect(self._on_find_next)
        layout.addWidget(self.input_field)

        self.prev_btn = QToolButton()
        self.prev_btn.setText("◀")
        self.prev_btn.setToolTip("Previous match (Shift+Enter)")
        self.prev_btn.clicked.connect(self._on_find_prev)
        layout.addWidget(self.prev_btn)

        self.next_btn = QToolButton()
        self.next_btn.setText("▶")
        self.next_btn.setToolTip("Next match (Enter)")
        self.next_btn.clicked.connect(self._on_find_next)
        layout.addWidget(self.next_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("Close search (Esc)")
        self.close_btn.clicked.connect(self._on_close)
        layout.addWidget(self.close_btn)

        self.setStyleSheet("""
            #SearchBar {
                background: #f8fafc;
                border-bottom: 1px solid #cbd5e1;
            }
            QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 8px;
                background: white;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            QToolButton {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background: white;
                padding: 4px 8px;
                font-weight: bold;
            }
            QToolButton:hover {
                background: #e2e8f0;
            }
        """)

    def _on_find_next(self):
        text = self.input_field.text().strip()
        if text:
            self.find_next.emit(text)

    def _on_find_prev(self):
        text = self.input_field.text().strip()
        if text:
            self.find_prev.emit(text)

    def _on_close(self):
        self.hide()
        self.search_closed.emit()

    def set_match_status(self, current: int, total: int):
        if total == 0:
            self.status_label.setText("No matches found")
            self.status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        else:
            self.status_label.setText(f"{current} of {total} matches")
            self.status_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: bold;")

    def clear_status(self):
        self.status_label.setText("")


class PDFViewer(QWidget):
    """
    Main central viewer widget embedding QPdfView with navigation,
    zooming, page tracking, and search synchronization.
    """

    # Signals
    page_changed = Signal(int, int)  # current_page (0-indexed), total_pages
    zoom_changed = Signal(float)  # zoom_factor (e.g. 1.0 = 100%)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._qdoc = QPdfDocument(self)
        self._qview = QPdfView(self)
        self._qview.setDocument(self._qdoc)

        # MultiPage mode enables seamless continuous vertical scrolling
        self._qview.setPageMode(QPdfView.PageMode.MultiPage)
        self._qview.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        # Hold strong references to QBuffer and QByteArray to prevent garbage collection
        self._byte_array: Optional[QByteArray] = None
        self._buffer: Optional[QBuffer] = None

        # Search state
        self._matches: List[SearchMatch] = []
        self._current_match_index: int = -1
        self._last_search_query: str = ""

        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Inline search bar
        self._search_bar = SearchBar(self)
        self._search_bar.hide()
        self._search_bar.find_next.connect(self.find_next)
        self._search_bar.find_prev.connect(self.find_prev)
        self._layout.addWidget(self._search_bar)

        self._layout.addWidget(self._qview)

        # Connect navigator signals
        nav = self._qview.pageNavigator()
        nav.currentPageChanged.connect(self._on_current_page_changed)
        self._qview.zoomFactorChanged.connect(self._on_zoom_factor_changed)

    def get_view(self) -> QPdfView:
        return self._qview

    def get_document(self) -> QPdfDocument:
        return self._qdoc

    def load_pdf_bytes(self, pdf_bytes: bytes, initial_page: int = 0) -> bool:
        """
        Loads PDF bytes into the viewer via an in-memory QBuffer.
        Keeps previous page position where possible.
        """
        if not pdf_bytes:
            self.clear()
            return False

        # Close existing buffer
        if self._buffer is not None:
            if self._buffer.isOpen():
                self._buffer.close()
            self._buffer = None

        self._byte_array = QByteArray(pdf_bytes)
        self._buffer = QBuffer()
        self._buffer.setData(self._byte_array)
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)

        status = self._qdoc.load(self._buffer)

        # Restore or clamp page
        total = self._qdoc.pageCount()
        if total > 0:
            target_page = max(0, min(initial_page, total - 1))
            self.jump_to_page(target_page)
            self.page_changed.emit(target_page, total)
        else:
            self.page_changed.emit(0, 0)

        self.zoom_changed.emit(self._qview.zoomFactor())
        return True

    def clear(self) -> None:
        """Clear viewer and close document."""
        if self._buffer is not None and self._buffer.isOpen():
            self._buffer.close()
        self._buffer = None
        self._byte_array = None
        self._qdoc.close()
        self._matches.clear()
        self._current_match_index = -1
        self._search_bar.hide()
        self.page_changed.emit(0, 0)

    def current_page(self) -> int:
        return self._qview.pageNavigator().currentPage()

    def page_count(self) -> int:
        return self._qdoc.pageCount()

    def jump_to_page(self, page_index: int) -> None:
        if 0 <= page_index < self._qdoc.pageCount():
            self._qview.pageNavigator().jump(page_index, QPointF(0, 0))

    def next_page(self) -> None:
        curr = self.current_page()
        if curr + 1 < self.page_count():
            self.jump_to_page(curr + 1)

    def previous_page(self) -> None:
        curr = self.current_page()
        if curr > 0:
            self.jump_to_page(curr - 1)

    # Zoom controls
    def zoom_in(self) -> None:
        self._qview.setZoomMode(QPdfView.ZoomMode.Custom)
        current = self._qview.zoomFactor()
        new_factor = min(5.0, current * 1.25)
        self._qview.setZoomFactor(new_factor)

    def zoom_out(self) -> None:
        self._qview.setZoomMode(QPdfView.ZoomMode.Custom)
        current = self._qview.zoomFactor()
        new_factor = max(0.2, current / 1.25)
        self._qview.setZoomFactor(new_factor)

    def fit_page(self) -> None:
        self._qview.setZoomMode(QPdfView.ZoomMode.FitInView)

    def fit_width(self) -> None:
        self._qview.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def set_zoom_factor(self, factor: float) -> None:
        self._qview.setZoomMode(QPdfView.ZoomMode.Custom)
        self._qview.setZoomFactor(max(0.1, min(5.0, factor)))

    def zoom_factor(self) -> float:
        return self._qview.zoomFactor()

    # Search functions
    def show_search(self) -> None:
        self._search_bar.show()
        self._search_bar.input_field.setFocus()
        self._search_bar.input_field.selectAll()

    def hide_search(self) -> None:
        self._search_bar.hide()
        self._matches.clear()
        self._current_match_index = -1

    def toggle_search(self) -> None:
        if self._search_bar.isVisible():
            self.hide_search()
        else:
            self.show_search()

    def perform_search(self, query: str, model: DocumentModel, source_doc: Optional[pymupdf.Document]) -> None:
        """Find occurrences of query across the document using PyMuPDF."""
        self._matches.clear()
        self._current_match_index = -1
        self._last_search_query = query

        if not query or not source_doc or source_doc.is_closed or model.page_count() == 0:
            self._search_bar.set_match_status(0, 0)
            return

        for idx, item in enumerate(model.get_pages()):
            if 0 <= item.source_page_index < len(source_doc):
                src_page = source_doc[item.source_page_index]
                rects = src_page.search_for(query)
                for r in rects:
                    self._matches.append(SearchMatch(page_index=idx, rect=r))

        total = len(self._matches)
        if total > 0:
            self._current_match_index = 0
            self._search_bar.set_match_status(1, total)
            self._navigate_to_match(0)
        else:
            self._search_bar.set_match_status(0, 0)

    def find_next(self, query: str) -> None:
        if query != self._last_search_query or not self._matches:
            # Re-run search if query changed or no matches yet (caller should supply doc/model)
            return

        if self._matches:
            self._current_match_index = (self._current_match_index + 1) % len(self._matches)
            self._search_bar.set_match_status(self._current_match_index + 1, len(self._matches))
            self._navigate_to_match(self._current_match_index)

    def find_prev(self, query: str) -> None:
        if query != self._last_search_query or not self._matches:
            return

        if self._matches:
            self._current_match_index = (self._current_match_index - 1) % len(self._matches)
            self._search_bar.set_match_status(self._current_match_index + 1, len(self._matches))
            self._navigate_to_match(self._current_match_index)

    def _navigate_to_match(self, match_idx: int) -> None:
        if 0 <= match_idx < len(self._matches):
            match = self._matches[match_idx]
            self.jump_to_page(match.page_index)

    def _on_current_page_changed(self, page: int) -> None:
        self.page_changed.emit(page, self.page_count())

    def _on_zoom_factor_changed(self, factor: float) -> None:
        self.zoom_changed.emit(factor)
