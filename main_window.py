"""
main_window.py - Main Application Window and Controller

Coordinates PDF viewing and editing modes, toolbars, sidebar, central viewer,
undo/redo stack, status updates, and action-level mode enforcement.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, List
from PySide6.QtCore import Qt, QSize, QPoint, Signal
from PySide6.QtGui import (
    QAction,
    QIcon,
    QKeySequence,
    QFont,
    QColor,
    QPixmap,
    QPainter,
    QPen,
    QPolygon,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QSpinBox,
    QLabel,
    QMessageBox,
    QFileDialog,
    QStatusBar,
    QPushButton,
    QFrame,
)
from page_model import DocumentModel, PageItem
from pdf_document import (
    PDFDocumentHandler,
    PDFDocumentError,
    PDFPasswordProtectedError,
    PDFInvalidError,
    PDFSaveError,
)
from undo_manager import (
    UndoManager,
    ReorderPagesCommand,
    DeletePagesCommand,
    RotatePagesCommand,
    DuplicatePagesCommand,
)
from pdf_viewer import PDFViewer
from thumbnail_sidebar import ThumbnailSidebar


def _create_empty_state_icon() -> QPixmap:
    """Renders a clean, high-DPI document vector graphic without font fallback overhead."""
    pix = QPixmap(72, 84)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Document body
    p.setBrush(QColor("#f8fafc"))
    p.setPen(QPen(QColor("#cbd5e1"), 2))
    p.drawRoundedRect(4, 4, 64, 76, 6, 6)

    # Folded corner
    p.setBrush(QColor("#e2e8f0"))
    fold = QPolygon([
        QPoint(52, 4),
        QPoint(68, 20),
        QPoint(52, 20),
    ])
    p.drawPolygon(fold)

    # Red PDF badge
    p.setBrush(QColor("#ef4444"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(12, 28, 30, 15, 3, 3)

    p.setPen(QColor("white"))
    font = QFont("Segoe UI", 8, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(12, 28, 30, 15, int(Qt.AlignmentFlag.AlignCenter), "PDF")

    # Content preview lines
    p.setPen(QPen(QColor("#cbd5e1"), 2))
    p.drawLine(14, 52, 58, 52)
    p.drawLine(14, 60, 46, 60)
    p.end()
    return pix


class EmptyStateWidget(QWidget):
    """Clean, modern welcome / empty state shown when no document is open."""

    open_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon_label = QLabel()
        icon_label.setPixmap(_create_empty_state_icon())
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel("No PDF Document Open")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1e293b;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Open a PDF file to comfortably read, reorder, rotate, duplicate, or delete pages.")
        subtitle.setStyleSheet("font-size: 14px; color: #64748b; max-width: 450px;")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        open_btn = QPushButton("Open PDF File")
        open_btn.setStyleSheet("""
            QPushButton {
                background: #2563eb;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 24px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            QPushButton:pressed {
                background: #1e40af;
            }
        """)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self.open_requested)
        layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Shortcut: Ctrl+O")
        hint.setStyleSheet("font-size: 12px; color: #94a3b8;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)


class MainWindow(QMainWindow):
    """
    Main application window implementing:
    - Mode toggle (Viewing vs Editing) with action-level enforcement
    - PyMuPDF page operations (Delete, Reorder, Rotate, Duplicate, Extract)
    - Safe atomic saving
    - Undo/Redo stack integration
    - Central high-fidelity PDF viewer and synchronized thumbnail sidebar
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ramov PDF Studio")
        self.resize(1200, 800)

        # Set window icon directly on the window for Windows taskbar & titlebar
        app_inst = QApplication.instance()
        if app_inst and not app_inst.windowIcon().isNull():
            self.setWindowIcon(app_inst.windowIcon())

        # Core logic models
        self.doc_handler = PDFDocumentHandler()
        self.model = DocumentModel(self)
        self.undo_manager = UndoManager(self)
        self.is_edit_mode: bool = False

        # Build UI
        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self) -> None:
        # Central layout with Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background: #cbd5e1;
            }
            QSplitter::handle:hover {
                background: #3b82f6;
            }
        """)

        # Left Sidebar
        self.sidebar = ThumbnailSidebar(self.splitter)
        self.splitter.addWidget(self.sidebar)

        # Center Stacked Widget
        self.stack = QStackedWidget(self.splitter)
        self.empty_state = EmptyStateWidget(self.stack)
        self.viewer = PDFViewer(self.stack)

        self.stack.addWidget(self.empty_state)  # Index 0
        self.stack.addWidget(self.viewer)       # Index 1
        self.stack.setCurrentIndex(0)

        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self.splitter)

        # Status Bar
        self._setup_status_bar()

        # Toolbars & Menus
        self._setup_actions()
        self._setup_menus()
        self._setup_toolbars()

    def _setup_status_bar(self) -> None:
        self.status_bar = QStatusBar(self)
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background: #f8fafc;
                border-top: 1px solid #cbd5e1;
                color: #475569;
                font-size: 12px;
            }
            QStatusBar::item {
                border: none;
            }
        """)
        self.setStatusBar(self.status_bar)

        self.status_msg = QLabel("Ready")
        self.status_bar.addWidget(self.status_msg, 1)

        self.status_modified = QLabel("")
        self.status_bar.addPermanentWidget(self.status_modified)

        self.status_page = QLabel("Page: 0 / 0")
        self.status_bar.addPermanentWidget(self.status_page)

        self.status_zoom = QLabel("Zoom: 100%")
        self.status_bar.addPermanentWidget(self.status_zoom)

        self.status_mode_badge = QLabel(" ● VIEWING MODE ")
        self.status_mode_badge.setStyleSheet("""
            background: #dbeafe;
            color: #1e40af;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 4px;
        """)
        self.status_bar.addPermanentWidget(self.status_mode_badge)

    def _setup_actions(self) -> None:
        # File Actions
        self.act_open = QAction("Open PDF...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.setToolTip("Open a PDF file (Ctrl+O)")
        self.act_open.triggered.connect(self.open_file_dialog)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.setToolTip("Save modifications (Ctrl+S) [Edit Mode]")
        self.act_save.triggered.connect(self.save_document)

        self.act_save_as = QAction("Save As...", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.setToolTip("Save copy to new file (Ctrl+Shift+S) [Edit Mode]")
        self.act_save_as.triggered.connect(self.save_document_as)

        self.act_close = QAction("Close PDF", self)
        self.act_close.setShortcut(QKeySequence("Ctrl+W"))
        self.act_close.triggered.connect(self.close_document)

        self.act_exit = QAction("Exit", self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)

        # Edit Actions
        self.act_undo = QAction("Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.setToolTip("Undo last edit (Ctrl+Z)")
        self.act_undo.triggered.connect(self.undo_action)

        self.act_redo = QAction("Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.setToolTip("Redo last edit (Ctrl+Y)")
        self.act_redo.triggered.connect(self.redo_action)

        self.act_delete = QAction("Delete Page(s)", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.setToolTip("Delete selected page(s) (Del) [Edit Mode]")
        self.act_delete.triggered.connect(self.delete_selected_pages)

        self.act_rotate_cw = QAction("Rotate Clockwise 90°", self)
        self.act_rotate_cw.setShortcut(QKeySequence("Ctrl+R"))
        self.act_rotate_cw.setToolTip("Rotate selected page(s) 90° clockwise (Ctrl+R)")
        self.act_rotate_cw.triggered.connect(lambda: self.rotate_selected_pages(90))

        self.act_rotate_ccw = QAction("Rotate Counterclockwise 90°", self)
        self.act_rotate_ccw.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self.act_rotate_ccw.setToolTip("Rotate selected page(s) 90° counterclockwise (Ctrl+Shift+R)")
        self.act_rotate_ccw.triggered.connect(lambda: self.rotate_selected_pages(-90))

        self.act_rotate_180 = QAction("Rotate 180°", self)
        self.act_rotate_180.setToolTip("Rotate selected page(s) 180°")
        self.act_rotate_180.triggered.connect(lambda: self.rotate_selected_pages(180))

        self.act_duplicate = QAction("Duplicate Page(s)", self)
        self.act_duplicate.setShortcut(QKeySequence("Ctrl+D"))
        self.act_duplicate.setToolTip("Duplicate selected page(s) (Ctrl+D) [Edit Mode]")
        self.act_duplicate.triggered.connect(self.duplicate_selected_pages)

        self.act_extract = QAction("Extract Page(s)...", self)
        self.act_extract.setShortcut(QKeySequence("Ctrl+E"))
        self.act_extract.setToolTip("Extract selected page(s) to new PDF (Ctrl+E) [Edit Mode]")
        self.act_extract.triggered.connect(self.extract_selected_pages)

        # View Actions
        self.act_zoom_in = QAction("Zoom In", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.setToolTip("Zoom in (Ctrl++)")
        self.act_zoom_in.triggered.connect(self.viewer.zoom_in)

        self.act_zoom_out = QAction("Zoom Out", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.setToolTip("Zoom out (Ctrl+-)")
        self.act_zoom_out.triggered.connect(self.viewer.zoom_out)

        self.act_fit_page = QAction("Fit Page", self)
        self.act_fit_page.setShortcut(QKeySequence("Ctrl+0"))
        self.act_fit_page.setToolTip("Fit entire page in view (Ctrl+0)")
        self.act_fit_page.triggered.connect(self.viewer.fit_page)

        self.act_fit_width = QAction("Fit Width", self)
        self.act_fit_width.setShortcut(QKeySequence("Ctrl+9"))
        self.act_fit_width.setToolTip("Fit page to window width (Ctrl+9)")
        self.act_fit_width.triggered.connect(self.viewer.fit_width)

        self.act_prev_page = QAction("Previous Page", self)
        self.act_prev_page.setShortcut(QKeySequence("Left"))
        self.act_prev_page.setToolTip("Previous page (Left Arrow)")
        self.act_prev_page.triggered.connect(self.viewer.previous_page)

        self.act_next_page = QAction("Next Page", self)
        self.act_next_page.setShortcut(QKeySequence("Right"))
        self.act_next_page.setToolTip("Next page (Right Arrow)")
        self.act_next_page.triggered.connect(self.viewer.next_page)

        self.act_search = QAction("Find in Document", self)
        self.act_search.setShortcut(QKeySequence.StandardKey.Find)
        self.act_search.setToolTip("Search text (Ctrl+F)")
        self.act_search.triggered.connect(self.viewer.toggle_search)

    def _setup_menus(self) -> None:
        mb = self.menuBar()
        mb.setStyleSheet("""
            QMenuBar {
                background: #f8fafc;
                border-bottom: 1px solid #cbd5e1;
            }
            QMenuBar::item:selected {
                background: #e2e8f0;
            }
        """)

        # File Menu
        file_menu = mb.addMenu("&File")
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_close)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        # Edit Menu
        edit_menu = mb.addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_delete)
        edit_menu.addAction(self.act_duplicate)
        edit_menu.addAction(self.act_rotate_cw)
        edit_menu.addAction(self.act_rotate_ccw)
        edit_menu.addAction(self.act_rotate_180)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_extract)

        # View Menu
        view_menu = mb.addMenu("&View")
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_fit_page)
        view_menu.addAction(self.act_fit_width)
        view_menu.addSeparator()
        view_menu.addAction(self.act_prev_page)
        view_menu.addAction(self.act_next_page)
        view_menu.addSeparator()
        view_menu.addAction(self.act_search)

        # Help Menu
        help_menu = mb.addMenu("&Help")
        act_about = help_menu.addAction("About Ramov PDF Studio")
        act_about.triggered.connect(self._show_about)

    def _setup_toolbars(self) -> None:
        tb = QToolBar("Main Toolbar", self)
        tb.setObjectName("MainToolBar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setStyleSheet("""
            QToolBar {
                background: #ffffff;
                border-bottom: 1px solid #e2e8f0;
                spacing: 6px;
                padding: 4px 8px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 500;
                color: #334155;
            }
            QToolButton:hover {
                background: #f1f5f9;
                border-color: #cbd5e1;
            }
            QToolButton:pressed {
                background: #e2e8f0;
            }
            QToolButton:disabled {
                color: #94a3b8;
            }
        """)
        self.addToolBar(tb)

        # Open, Save, Save As
        tb.addAction(self.act_open)
        tb.addAction(self.act_save)
        tb.addAction(self.act_save_as)
        tb.addSeparator()

        # Undo, Redo
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()

        # Prominent Mode Toggle Widget
        self._mode_toggle_btn = QToolButton(self)
        self._mode_toggle_btn.setCheckable(True)
        self._mode_toggle_btn.setChecked(False)
        self._mode_toggle_btn.setText("Viewing Mode")
        self._mode_toggle_btn.setToolTip("Toggle between Viewing Mode and Editing Mode (Ctrl+M)")
        self._mode_toggle_btn.setShortcut(QKeySequence("Ctrl+M"))
        self._mode_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_mode_toggle_style()
        self._mode_toggle_btn.toggled.connect(self._on_mode_toggled)
        tb.addWidget(self._mode_toggle_btn)

        tb.addSeparator()

        # Zoom Controls
        tb.addAction(self.act_zoom_out)
        tb.addAction(self.act_zoom_in)
        tb.addAction(self.act_fit_page)
        tb.addAction(self.act_fit_width)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: #475569; font-size: 12px; min-width: 45px;")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(self.zoom_label)

        tb.addSeparator()

        # Page Navigation
        tb.addAction(self.act_prev_page)

        page_nav_widget = QWidget()
        p_layout = QHBoxLayout(page_nav_widget)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(4)

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setValue(1)
        self.page_spin.setFixedWidth(55)
        self.page_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        p_layout.addWidget(self.page_spin)

        self.page_total_label = QLabel("/ 0")
        self.page_total_label.setStyleSheet("color: #64748b; font-size: 12px; padding-right: 4px;")
        p_layout.addWidget(self.page_total_label)

        tb.addWidget(page_nav_widget)
        tb.addAction(self.act_next_page)

        tb.addSeparator()

        # Search Action
        tb.addAction(self.act_search)

    def _update_mode_toggle_style(self) -> None:
        if self.is_edit_mode:
            self._mode_toggle_btn.setText("Editing Mode (Active)")
            self._mode_toggle_btn.setStyleSheet("""
                QToolButton {
                    background: #f59e0b;
                    color: white;
                    border: 1px solid #d97706;
                    border-radius: 6px;
                    padding: 5px 12px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background: #d97706;
                }
            """)
            self.status_mode_badge.setText(" ● EDITING MODE (Pages Unlocked) ")
            self.status_mode_badge.setStyleSheet("""
                background: #fef3c7;
                color: #b45309;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 4px;
            """)
        else:
            self._mode_toggle_btn.setText("Viewing Mode (Active)")
            self._mode_toggle_btn.setStyleSheet("""
                QToolButton {
                    background: #3b82f6;
                    color: white;
                    border: 1px solid #2563eb;
                    border-radius: 6px;
                    padding: 5px 12px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background: #2563eb;
                }
            """)
            self.status_mode_badge.setText(" ● VIEWING MODE (Read-only) ")
            self.status_mode_badge.setStyleSheet("""
                background: #dbeafe;
                color: #1e40af;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 4px;
            """)

    def _connect_signals(self) -> None:
        # Empty state open button
        self.empty_state.open_requested.connect(self.open_file_dialog)

        # Viewer signals
        self.viewer.page_changed.connect(self._on_viewer_page_changed)
        self.viewer.zoom_changed.connect(self._on_viewer_zoom_changed)
        self.viewer._search_bar.find_next.connect(self._on_search_requested)
        self.viewer._search_bar.find_prev.connect(self._on_search_requested)

        # Sidebar signals
        self.sidebar.page_selected.connect(self._on_sidebar_page_selected)
        self.sidebar.reorder_requested.connect(self.reorder_pages_by_ids)
        self.sidebar.delete_requested.connect(self.delete_selected_pages)
        self.sidebar.rotate_cw_requested.connect(lambda: self.rotate_selected_pages(90))
        self.sidebar.rotate_ccw_requested.connect(lambda: self.rotate_selected_pages(-90))
        self.sidebar.rotate_180_requested.connect(lambda: self.rotate_selected_pages(180))
        self.sidebar.duplicate_requested.connect(self.duplicate_selected_pages)
        self.sidebar.extract_requested.connect(self.extract_selected_pages)

        # Document model signals
        self.model.modified_changed.connect(self._on_model_modified_changed)
        self.model.page_rotated.connect(self.sidebar.refresh_page_rotation)

        # Undo stack signals
        self.undo_manager.can_undo_changed.connect(self._on_undo_state_changed)
        self.undo_manager.can_redo_changed.connect(self._on_redo_state_changed)

    def _on_mode_toggled(self, checked: bool) -> None:
        """
        Handle switching between Viewing Mode and Editing Mode.
        If switching to Viewing Mode while unsaved changes exist,
        prompt the user with Save, Discard, and Cancel options.
        """
        target_edit_mode = checked

        if not target_edit_mode and self.is_edit_mode:
            # Switching from Editing Mode -> Viewing Mode
            if self.model.is_modified:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Unsaved Changes")
                msg_box.setText("You have unsaved changes in Editing Mode.")
                msg_box.setInformativeText("Do you want to save your modifications before switching to Viewing Mode?")
                msg_box.setStandardButtons(
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel
                )
                msg_box.setDefaultButton(QMessageBox.StandardButton.Save)

                reply = msg_box.exec()
                if reply == QMessageBox.StandardButton.Save:
                    saved = self.save_document()
                    if not saved:
                        # Save was cancelled or failed; keep in editing mode
                        self._mode_toggle_btn.blockSignals(True)
                        self._mode_toggle_btn.setChecked(True)
                        self._mode_toggle_btn.blockSignals(False)
                        return
                elif reply == QMessageBox.StandardButton.Discard:
                    self.discard_changes()
                else:  # Cancel
                    self._mode_toggle_btn.blockSignals(True)
                    self._mode_toggle_btn.setChecked(True)
                    self._mode_toggle_btn.blockSignals(False)
                    return

        self.is_edit_mode = target_edit_mode
        self._update_mode_toggle_style()
        self.sidebar.set_edit_mode(self.is_edit_mode)
        self._update_ui_state()

    def _update_ui_state(self) -> None:
        has_doc = self.doc_handler.is_open() and self.model.page_count() > 0

        # Enable view navigation and zoom actions when doc is open
        self.act_close.setEnabled(has_doc)
        self.act_zoom_in.setEnabled(has_doc)
        self.act_zoom_out.setEnabled(has_doc)
        self.act_fit_page.setEnabled(has_doc)
        self.act_fit_width.setEnabled(has_doc)
        self.act_prev_page.setEnabled(has_doc)
        self.act_next_page.setEnabled(has_doc)
        self.act_search.setEnabled(has_doc)
        self.page_spin.setEnabled(has_doc)
        self._mode_toggle_btn.setEnabled(has_doc)

        # Modifying actions depend strictly on Edit Mode
        can_edit = has_doc and self.is_edit_mode
        self.act_save.setEnabled(can_edit and self.model.is_modified)
        self.act_save_as.setEnabled(can_edit)
        self.act_delete.setEnabled(can_edit)
        self.act_duplicate.setEnabled(can_edit)
        self.act_rotate_cw.setEnabled(can_edit)
        self.act_rotate_ccw.setEnabled(can_edit)
        self.act_rotate_180.setEnabled(can_edit)
        self.act_extract.setEnabled(can_edit)

        # Undo/Redo only available in edit mode
        self.act_undo.setEnabled(can_edit and self.undo_manager.can_undo())
        self.act_redo.setEnabled(can_edit and self.undo_manager.can_redo())
        self.act_undo.setText(self.undo_manager.undo_text() if can_edit else "Undo")
        self.act_redo.setText(self.undo_manager.redo_text() if can_edit else "Redo")

        # Window title
        if has_doc:
            fname = self.doc_handler.file_name or "Untitled.pdf"
            mod_str = " *" if self.model.is_modified else ""
            mode_str = " [EDITING]" if self.is_edit_mode else " [VIEWING]"
            self.setWindowTitle(f"{fname}{mod_str}{mode_str} — Ramov PDF Studio")
        else:
            self.setWindowTitle("Ramov PDF Studio")

    # Document Loading & Closing
    def open_file_dialog(self) -> None:
        if self.model.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "The current document has unsaved modifications. Do you want to save before opening another file?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_document():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF Document",
            "",
            "PDF Files (*.pdf);;All Files (*.*)",
        )
        if path:
            self.load_pdf(path)

    def load_pdf(self, file_path: str) -> bool:
        try:
            count, warnings = self.doc_handler.load_from_file(file_path)
        except PDFPasswordProtectedError:
            QMessageBox.critical(
                self,
                "Password Protected PDF",
                "This document is password protected. Encrypted documents with passwords are not currently supported.",
            )
            return False
        except (PDFInvalidError, PDFDocumentError, Exception) as e:
            QMessageBox.critical(self, "Failed to Open PDF", f"Could not load PDF document:\n{e}")
            return False

        if warnings:
            QMessageBox.warning(
                self,
                "Document Warnings",
                "\n\n".join(warnings),
            )

        # Initialize model
        initial_rotations = self.doc_handler.get_initial_rotations()
        self.model.load_pages(count, initial_rotations)
        self.undo_manager.clear()

        # Update viewer
        raw_bytes = self.doc_handler.raw_bytes
        if raw_bytes:
            self.viewer.load_pdf_bytes(raw_bytes, 0)

        # Sync thumbnail sidebar
        if raw_bytes:
            self.sidebar.sync_with_model(self.model, raw_bytes)

        # Reset mode to Viewing mode on open
        self.is_edit_mode = False
        self._mode_toggle_btn.blockSignals(True)
        self._mode_toggle_btn.setChecked(False)
        self._mode_toggle_btn.blockSignals(False)
        self._update_mode_toggle_style()
        self.sidebar.set_edit_mode(False)

        # Show viewer in stack
        self.stack.setCurrentIndex(1)
        self.status_msg.setText(f"Opened: {self.doc_handler.file_name}")
        self._update_ui_state()
        return True

    def close_document(self) -> None:
        if self.model.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_document():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.doc_handler.close()
        self.model.clear()
        self.viewer.clear()
        self.sidebar.clear()
        self.undo_manager.clear()

        self.stack.setCurrentIndex(0)
        self.status_msg.setText("Ready. No document loaded.")
        self.status_page.setText("Page: 0 / 0")
        self.status_modified.setText("")
        self._update_ui_state()

    # Viewer & Thumbnail synchronization
    def _refresh_viewer_from_model(self, keep_current_page: bool = True) -> None:
        """
        Recompiles the in-memory PDF representation and updates the central viewer.
        Ensures the viewer displays the exact modified page order and rotations.
        """
        if not self.doc_handler.is_open() or self.model.page_count() == 0:
            return

        curr_page = self.viewer.current_page() if keep_current_page else 0
        try:
            pdf_bytes = self.doc_handler.compile_pdf_bytes(self.model)
            self.viewer.load_pdf_bytes(pdf_bytes, curr_page)
        except Exception as e:
            QMessageBox.critical(self, "Viewer Sync Error", f"Failed to refresh PDF viewer:\n{e}")

    def _on_viewer_page_changed(self, current_page: int, total_pages: int) -> None:
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, total_pages))
        self.page_spin.setValue(current_page + 1)
        self.page_spin.blockSignals(False)

        self.page_total_label.setText(f"/ {total_pages}")
        self.status_page.setText(f"Page: {current_page + 1} / {total_pages}" if total_pages > 0 else "Page: 0 / 0")
        self.sidebar.set_active_page(current_page)
        self.model.set_active_index(current_page)

    def _on_viewer_zoom_changed(self, factor: float) -> None:
        pct = int(round(factor * 100))
        self.zoom_label.setText(f"{pct}%")
        self.status_zoom.setText(f"Zoom: {pct}%")

    def _on_sidebar_page_selected(self, page_index: int) -> None:
        self.viewer.jump_to_page(page_index)

    def _on_page_spin_changed(self, value: int) -> None:
        self.viewer.jump_to_page(value - 1)

    def _on_model_modified_changed(self, modified: bool) -> None:
        if modified:
            self.status_modified.setText("● Modified")
            self.status_modified.setStyleSheet("color: #f59e0b; font-weight: bold;")
        else:
            self.status_modified.setText("✓ Saved")
            self.status_modified.setStyleSheet("color: #10b981; font-weight: bold;")
        self._update_ui_state()

    def _on_undo_state_changed(self, can_undo: bool) -> None:
        self._update_ui_state()

    def _on_redo_state_changed(self, can_redo: bool) -> None:
        self._update_ui_state()

    def _on_search_requested(self, query: str) -> None:
        self.viewer.perform_search(query, self.model, self.doc_handler.source_doc)

    # Editing Operations with Strict Mode Enforcement
    def _enforce_edit_mode(self, operation_name: str) -> bool:
        """Enforces that modifying operations only execute in Editing Mode."""
        if not self.is_edit_mode:
            QMessageBox.warning(
                self,
                "Editing Mode Required",
                f"Cannot {operation_name} in Viewing Mode.\n\n"
                "Please toggle to 'Editing Mode' in the toolbar to modify pages.",
            )
            return False
        return True

    def delete_selected_pages(self) -> None:
        if not self._enforce_edit_mode("delete pages"):
            return

        indices = self.sidebar.get_selected_indices()
        if not indices:
            curr = self.model.get_active_index()
            if 0 <= curr < self.model.page_count():
                indices = [curr]

        if not indices:
            return

        # Prevent deleting all pages
        if len(indices) >= self.model.page_count():
            QMessageBox.warning(
                self,
                "Cannot Delete All Pages",
                "A PDF document must contain at least one page. You cannot delete all pages.",
            )
            return

        # Confirmation Dialog
        num = len(indices)
        page_list_str = ", ".join(str(i + 1) for i in indices[:5])
        if num > 5:
            page_list_str += f"... (+{num - 5} more)"

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {num} page(s) (Page {page_list_str})?\n\nThis action can be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        cmd = DeletePagesCommand(self.model, indices, description=f"Delete {num} page(s)")
        self.undo_manager.push(cmd)

        self._refresh_viewer_from_model(keep_current_page=True)
        if self.doc_handler.raw_bytes:
            self.sidebar.sync_with_model(self.model, self.doc_handler.raw_bytes)

    def reorder_pages_by_ids(self, new_id_order: List[str]) -> None:
        if not self._enforce_edit_mode("reorder pages"):
            # Resync sidebar to revert invalid drag
            if self.doc_handler.raw_bytes:
                self.sidebar.sync_with_model(self.model, self.doc_handler.raw_bytes)
            return

        current_ids = [p.page_id for p in self.model.get_pages()]
        if current_ids == new_id_order:
            return

        cmd = ReorderPagesCommand(self.model, current_ids, new_id_order, description="Reorder Pages")
        self.undo_manager.push(cmd)

        self._refresh_viewer_from_model(keep_current_page=True)
        if self.doc_handler.raw_bytes:
            self.sidebar.sync_with_model(self.model, self.doc_handler.raw_bytes)

    def rotate_selected_pages(self, angle_delta: int) -> None:
        if not self._enforce_edit_mode("rotate pages"):
            return

        indices = self.sidebar.get_selected_indices()
        if not indices:
            curr = self.model.get_active_index()
            if 0 <= curr < self.model.page_count():
                indices = [curr]

        if not indices:
            return

        page_ids = [self.model.get_page(i).page_id for i in indices if self.model.get_page(i)]
        cmd = RotatePagesCommand(self.model, page_ids, angle_delta, description=f"Rotate {len(indices)} page(s)")
        self.undo_manager.push(cmd)

        self._refresh_viewer_from_model(keep_current_page=True)

    def duplicate_selected_pages(self) -> None:
        if not self._enforce_edit_mode("duplicate pages"):
            return

        indices = self.sidebar.get_selected_indices()
        if not indices:
            curr = self.model.get_active_index()
            if 0 <= curr < self.model.page_count():
                indices = [curr]

        if not indices:
            return

        cmd = DuplicatePagesCommand(self.model, indices, description=f"Duplicate {len(indices)} page(s)")
        self.undo_manager.push(cmd)

        self._refresh_viewer_from_model(keep_current_page=True)
        if self.doc_handler.raw_bytes:
            self.sidebar.sync_with_model(self.model, self.doc_handler.raw_bytes)

    def extract_selected_pages(self) -> None:
        if not self._enforce_edit_mode("extract pages"):
            return

        indices = self.sidebar.get_selected_indices()
        if not indices:
            curr = self.model.get_active_index()
            if 0 <= curr < self.model.page_count():
                indices = [curr]

        if not indices:
            return

        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Extract Pages to New PDF",
            "extracted_pages.pdf",
            "PDF Files (*.pdf)",
        )
        if not target_path:
            return

        try:
            self.doc_handler.extract_pages(self.model, indices, target_path)
            QMessageBox.information(
                self,
                "Extraction Complete",
                f"Successfully extracted {len(indices)} page(s) to:\n{target_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Extraction Failed", f"Failed to extract pages:\n{e}")

    # Undo & Redo Handlers
    def undo_action(self) -> None:
        if not self._enforce_edit_mode("undo"):
            return
        self.undo_manager.undo()
        self._refresh_viewer_from_model(keep_current_page=True)
        if self.doc_handler.raw_bytes:
            self.sidebar.sync_with_model(self.model, self.doc_handler.raw_bytes)

    def redo_action(self) -> None:
        if not self._enforce_edit_mode("redo"):
            return
        self.undo_manager.redo()
        self._refresh_viewer_from_model(keep_current_page=True)
        if self.doc_handler.raw_bytes:
            self.sidebar.sync_with_model(self.model, self.doc_handler.raw_bytes)

    # Safe Saving
    def save_document(self) -> bool:
        if not self._enforce_edit_mode("save modifications"):
            return False

        if not self.doc_handler.file_path:
            return self.save_document_as()

        return self._do_save(self.doc_handler.file_path)

    def save_document_as(self) -> bool:
        if not self._enforce_edit_mode("save modifications"):
            return False

        current_path = self.doc_handler.file_path or "modified_document.pdf"
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Document As",
            current_path,
            "PDF Files (*.pdf);;All Files (*.*)",
        )
        if not target_path:
            return False

        return self._do_save(target_path)

    def _do_save(self, path: str) -> bool:
        # Check signature warning
        if self.doc_handler.has_signatures:
            reply = QMessageBox.warning(
                self,
                "Digital Signature Invalidation Warning",
                "This PDF contains digital signatures. Saving your changes will invalidate all digital signatures.\n\n"
                "Do you still want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        try:
            saved_path = self.doc_handler.save(self.model, path)
            self.status_msg.setText(f"Saved: {Path(saved_path).name}")
            self._update_ui_state()
            QMessageBox.information(
                self,
                "Document Saved",
                f"Successfully saved PDF to:\n{saved_path}",
            )
            return True
        except PDFSaveError as e:
            QMessageBox.critical(self, "Save Failed", f"Failed to save document:\n{e}")
            return False
        except Exception as e:
            QMessageBox.critical(self, "Unexpected Save Error", f"An error occurred while saving:\n{e}")
            return False

    def discard_changes(self) -> None:
        """Discards pending edits and reverts the document to the last saved state on disk."""
        if self.doc_handler.file_path and Path(self.doc_handler.file_path).exists():
            self.load_pdf(self.doc_handler.file_path)
        else:
            self.model.set_modified(False)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Ramov PDF Studio",
            "<h3>Ramov PDF Studio</h3>"
            "<p>A complete native PDF viewer and page editor built with PySide6, QtPdf, and PyMuPDF.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Seamless High-Fidelity Viewing Mode</li>"
            "<li>Page Reordering via Drag-and-Drop</li>"
            "<li>Multi-page Deletion, Duplication, and Rotation</li>"
            "<li>Safe Atomic Saving with Disk Replacement</li>"
            "<li>Full Undo and Redo History</li>"
            "<li>Fast Document Text Search</li>"
            "</ul>",
        )

    def closeEvent(self, event) -> None:
        if self.model.is_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing the application?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if self.save_document():
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
