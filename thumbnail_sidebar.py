"""
thumbnail_sidebar.py - Page Thumbnail Sidebar with Drag-and-Drop and Context Menu

Displays rich miniature previews of PDF pages, supports single/multi selection,
drag-and-drop reordering in edit mode, page deletion, rotation, duplication,
and sidebar collapsing/resizing.
"""

from __future__ import annotations
from typing import Optional, List, Dict
from PySide6.QtCore import (
    Qt,
    Signal,
    QSize,
    QPoint,
    QRect,
    QThreadPool,
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QPixmap,
    QImage,
    QAction,
    QIcon,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyle,
    QLabel,
    QToolButton,
    QMenu,
    QAbstractItemView,
)
from page_model import DocumentModel, PageItem
from workers import ThumbnailWorker, ThumbnailCache


class ThumbnailDelegate(QStyledItemDelegate):
    """Custom delegate that draws a polished card with page thumbnail and number."""

    def __init__(self, cache: ThumbnailCache, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cache = cache

    def sizeHint(self, option, index) -> QSize:
        return QSize(150, 195)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Card container dimensions
        card_rect = rect.adjusted(8, 6, -8, -6)

        # Draw card background
        if is_selected:
            bg_color = QColor("#eff6ff")  # Blue-50
            border_color = QColor("#2563eb")  # Blue-600
            border_width = 2
        elif is_hovered:
            bg_color = QColor("#f8fafc")
            border_color = QColor("#94a3b8")
            border_width = 1.5
        else:
            bg_color = QColor("#ffffff")
            border_color = QColor("#e2e8f0")
            border_width = 1

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(card_rect, 6, 6)

        # Retrieve thumbnail
        page_id = index.data(Qt.ItemDataRole.UserRole)
        rotation = index.data(Qt.ItemDataRole.UserRole + 1) or 0
        pixmap = self.cache.get(page_id, rotation)

        thumb_area = QRect(card_rect.left() + 6, card_rect.top() + 6, card_rect.width() - 12, 142)

        if pixmap and not pixmap.isNull():
            # Scale thumbnail preserving aspect ratio
            scaled_pix = pixmap.scaled(
                thumb_area.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Center thumbnail inside thumb_area
            x_offset = thumb_area.left() + (thumb_area.width() - scaled_pix.width()) // 2
            y_offset = thumb_area.top() + (thumb_area.height() - scaled_pix.height()) // 2
            dest_rect = QRect(x_offset, y_offset, scaled_pix.width(), scaled_pix.height())

            # Subtle paper drop shadow/border
            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            painter.drawRect(dest_rect.adjusted(-1, -1, 1, 1))
            painter.drawPixmap(dest_rect, scaled_pix)
        else:
            # Placeholder loading card
            painter.setPen(QPen(QColor("#cbd5e1"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor("#f1f5f9")))
            painter.drawRoundedRect(thumb_area.adjusted(4, 4, -4, -4), 4, 4)
            painter.setPen(QColor("#94a3b8"))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(thumb_area, Qt.AlignmentFlag.AlignCenter, "Loading...")

        # Draw page number badge at the bottom
        badge_rect = QRect(card_rect.left(), card_rect.bottom() - 26, card_rect.width(), 22)
        page_num = str(index.row() + 1)

        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        if is_selected:
            painter.setPen(QColor("#1d4ed8"))
        else:
            painter.setPen(QColor("#475569"))

        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, f"Page {page_num}")

        painter.restore()


class ThumbnailListWidget(QListWidget):
    """
    Subclassed QListWidget supporting internal move drag-and-drop in edit mode,
    multi-selection, and custom drop event handling.
    """

    order_changed = Signal(list)  # list[str] of page_ids in new order
    page_activated = Signal(int)  # single page jump
    context_menu_requested = Signal(QPoint, list)  # pos, selected_indices

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSpacing(4)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self._is_edit_mode: bool = False
        self.set_edit_mode(False)

        self.setStyleSheet("""
            QListWidget {
                background: #f8fafc;
                border: none;
                outline: 0;
            }
            QListWidget::item {
                border: none;
                margin: 0;
                padding: 0;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def set_edit_mode(self, enabled: bool) -> None:
        self._is_edit_mode = enabled
        if enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
            self.setDragEnabled(False)
            self.setAcceptDrops(False)

    def dropEvent(self, event) -> None:
        if not self._is_edit_mode:
            event.ignore()
            return

        super().dropEvent(event)
        # Extract new order of page_ids
        new_order = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        self.order_changed.emit(new_order)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is not None and not item.isSelected():
            # If clicked item was not part of current selection, select it
            self.setCurrentItem(item)

        selected_indices = [idx.row() for idx in self.selectedIndexes()]
        self.context_menu_requested.emit(event.globalPos(), selected_indices)


class ThumbnailSidebar(QWidget):
    """
    Left sidebar containing the page thumbnail list, header, collapse toggle,
    and asynchronous thumbnail generation pipeline.
    """

    page_selected = Signal(int)  # Page index clicked for navigation
    delete_requested = Signal()
    rotate_cw_requested = Signal()
    rotate_ccw_requested = Signal()
    rotate_180_requested = Signal()
    duplicate_requested = Signal()
    extract_requested = Signal()
    reorder_requested = Signal(list)  # new list of page_ids

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ThumbnailSidebar")

        self.cache = ThumbnailCache()
        self._thread_pool = QThreadPool.globalInstance()
        self._raw_pdf_bytes: Optional[bytes] = None
        self._model: Optional[DocumentModel] = None
        self._is_edit_mode: bool = False
        self._is_collapsed: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setMinimumWidth(170)
        self.setMaximumWidth(280)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar
        self.header = QWidget()
        self.header.setStyleSheet("background: #f1f5f9; border-bottom: 1px solid #cbd5e1;")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 6, 8, 6)

        self.title_label = QLabel("Pages")
        self.title_label.setStyleSheet("font-weight: bold; color: #334155; font-size: 13px;")
        header_layout.addWidget(self.title_label)

        self.count_badge = QLabel("0")
        self.count_badge.setStyleSheet("""
            background: #e2e8f0;
            color: #475569;
            font-size: 11px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 8px;
        """)
        header_layout.addWidget(self.count_badge)
        header_layout.addStretch()

        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("◀")
        self.collapse_btn.setToolTip("Collapse Sidebar")
        self.collapse_btn.setStyleSheet("border: none; color: #64748b; font-size: 12px; padding: 2px 4px;")
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        header_layout.addWidget(self.collapse_btn)

        main_layout.addWidget(self.header)

        # Thumbnail List
        self.list_widget = ThumbnailListWidget(self)
        self.delegate = ThumbnailDelegate(self.cache, self.list_widget)
        self.list_widget.setItemDelegate(self.delegate)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.order_changed.connect(self.reorder_requested)
        self.list_widget.context_menu_requested.connect(self._show_context_menu)

        main_layout.addWidget(self.list_widget)

    def set_edit_mode(self, enabled: bool) -> None:
        self._is_edit_mode = enabled
        self.list_widget.set_edit_mode(enabled)

    def toggle_collapse(self) -> None:
        self._is_collapsed = not self._is_collapsed
        if self._is_collapsed:
            self.list_widget.hide()
            self.title_label.hide()
            self.count_badge.hide()
            self.collapse_btn.setText("▶")
            self.collapse_btn.setToolTip("Expand Sidebar")
            self.setFixedWidth(36)
        else:
            self.list_widget.show()
            self.title_label.show()
            self.count_badge.show()
            self.collapse_btn.setText("◀")
            self.collapse_btn.setToolTip("Collapse Sidebar")
            self.setMinimumWidth(170)
            self.setMaximumWidth(280)

    def clear(self) -> None:
        self.list_widget.clear()
        self.cache.clear()
        self._raw_pdf_bytes = None
        self._model = None
        self.count_badge.setText("0")

    def sync_with_model(self, model: DocumentModel, raw_pdf_bytes: bytes) -> None:
        """
        Synchronizes the sidebar items with the DocumentModel.
        Triggers background thumbnail rendering for any un-cached pages.
        """
        self._model = model
        self._raw_pdf_bytes = raw_pdf_bytes

        # Preserve current selection
        selected_ids = set(model.get_selected_ids())
        active_idx = model.get_active_index()

        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        pages = model.get_pages()
        self.count_badge.setText(str(len(pages)))

        for idx, page in enumerate(pages):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, page.page_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, page.rotation)
            item.setData(Qt.ItemDataRole.UserRole + 2, idx + 1)
            self.list_widget.addItem(item)

            if page.page_id in selected_ids:
                item.setSelected(True)

            # Trigger background rendering if not in cache
            if self.cache.get(page.page_id, page.rotation) is None:
                self._render_thumbnail_async(page.page_id, page.source_page_index, page.rotation)

        if 0 <= active_idx < self.list_widget.count():
            self.list_widget.setCurrentRow(active_idx)

        self.list_widget.blockSignals(False)

    def set_active_page(self, page_index: int) -> None:
        """Scroll to and select the active page from the viewer."""
        if 0 <= page_index < self.list_widget.count():
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(page_index)
            item = self.list_widget.item(page_index)
            if item:
                self.list_widget.scrollToItem(item)
            self.list_widget.blockSignals(False)

    def select_single_page(self, page_index: int) -> None:
        """Selects a single page and deselects all others."""
        self.list_widget.clearSelection()
        if 0 <= page_index < self.list_widget.count():
            item = self.list_widget.item(page_index)
            if item:
                item.setSelected(True)
            self.list_widget.setCurrentRow(page_index)
        self._on_selection_changed()

    def get_selected_indices(self) -> List[int]:
        return sorted([idx.row() for idx in self.list_widget.selectedIndexes()])

    def _render_thumbnail_async(self, page_id: str, source_page_index: int, rotation: int) -> None:
        if not self._raw_pdf_bytes:
            return

        worker = ThumbnailWorker(
            raw_pdf_bytes=self._raw_pdf_bytes,
            source_page_index=source_page_index,
            rotation=rotation,
            page_id=page_id,
            target_max_dim=180,
        )
        worker.signals.thumbnail_ready.connect(self._on_thumbnail_rendered)
        self._thread_pool.start(worker)

    def _on_thumbnail_rendered(self, page_id: str, rotation: int, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        self.cache.put(page_id, rotation, pixmap)

        # Trigger redraw of matching item
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                self.list_widget.update(self.list_widget.indexFromItem(item))
                break

    def refresh_page_rotation(self, page_id: str, new_rotation: int) -> None:
        """Called when a page is rotated to update item data and re-render."""
        self.cache.invalidate(page_id)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                item.setData(Qt.ItemDataRole.UserRole + 1, new_rotation)
                if self._model:
                    page = self._model.get_page(i)
                    if page:
                        self._render_thumbnail_async(page_id, page.source_page_index, new_rotation)
                break

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        row = self.list_widget.row(item)
        self.page_selected.emit(row)

    def _on_selection_changed(self) -> None:
        if not self._model:
            return
        selected_indices = [idx.row() for idx in self.list_widget.selectedIndexes()]
        self._model.set_selected_indices(selected_indices)

    def _show_context_menu(self, global_pos: QPoint, selected_indices: List[int]) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px 6px 10px;
                border-radius: 4px;
                color: #1e293b;
            }
            QMenu::item:selected {
                background: #eff6ff;
                color: #2563eb;
            }
            QMenu::item:disabled {
                color: #94a3b8;
            }
            QMenu::separator {
                height: 1px;
                background: #e2e8f0;
                margin: 4px 0;
            }
        """)

        num_pages = len(selected_indices)
        page_str = f"({num_pages} pages)" if num_pages > 1 else ""

        # Rotate actions
        rot_cw_act = menu.addAction(f"Rotate Clockwise 90° {page_str}")
        rot_cw_act.setShortcut("Ctrl+R")
        rot_cw_act.triggered.connect(self.rotate_cw_requested)

        rot_ccw_act = menu.addAction(f"Rotate Counterclockwise 90° {page_str}")
        rot_ccw_act.setShortcut("Ctrl+Shift+R")
        rot_ccw_act.triggered.connect(self.rotate_ccw_requested)

        rot_180_act = menu.addAction(f"Rotate 180° {page_str}")
        rot_180_act.triggered.connect(self.rotate_180_requested)

        menu.addSeparator()

        dup_act = menu.addAction(f"Duplicate Page(s) {page_str}")
        dup_act.setShortcut("Ctrl+D")
        dup_act.triggered.connect(self.duplicate_requested)

        del_act = menu.addAction(f"Delete Page(s) {page_str}")
        del_act.setShortcut("Del")
        del_act.triggered.connect(self.delete_requested)

        menu.addSeparator()

        ext_act = menu.addAction(f"Extract Page(s)... {page_str}")
        ext_act.setShortcut("Ctrl+E")
        ext_act.triggered.connect(self.extract_requested)

        # Enforce edit mode restrictions
        if not self._is_edit_mode:
            rot_cw_act.setEnabled(False)
            rot_ccw_act.setEnabled(False)
            rot_180_act.setEnabled(False)
            dup_act.setEnabled(False)
            del_act.setEnabled(False)
            ext_act.setEnabled(False)

        menu.exec(global_pos)
