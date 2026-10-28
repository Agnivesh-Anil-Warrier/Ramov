"""
page_model.py - Document and Page State Model

Maintains stable page identities, logical ordering, rotation tracking,
selection state, and modification flags for PDF documents.
"""

from __future__ import annotations
import uuid
from typing import List, Optional, Set, Tuple, Dict, Any
from PySide6.QtCore import QObject, Signal


class PageItem:
    """Represents a single logical page with a stable identifier."""

    def __init__(
        self,
        source_page_index: int,
        source_doc_id: str = "main",
        rotation: int = 0,
        page_id: Optional[str] = None,
        display_label: str = "",
    ):
        self.page_id: str = page_id or f"page-{uuid.uuid4().hex[:10]}"
        self.source_doc_id: str = source_doc_id
        self.source_page_index: int = source_page_index
        self.rotation: int = rotation % 360
        self.display_label: str = display_label

    def clone(self) -> PageItem:
        """Create a duplicate of this page item with a brand new stable ID."""
        return PageItem(
            source_page_index=self.source_page_index,
            source_doc_id=self.source_doc_id,
            rotation=self.rotation,
            page_id=f"page-{uuid.uuid4().hex[:10]}",
            display_label=self.display_label,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_id": self.page_id,
            "source_doc_id": self.source_doc_id,
            "source_page_index": self.source_page_index,
            "rotation": self.rotation,
            "display_label": self.display_label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PageItem:
        return cls(
            source_page_index=data["source_page_index"],
            source_doc_id=data.get("source_doc_id", "main"),
            rotation=data.get("rotation", 0),
            page_id=data.get("page_id"),
            display_label=data.get("display_label", ""),
        )

    def __repr__(self) -> str:
        return f"<PageItem id={self.page_id} src={self.source_page_index} rot={self.rotation}>"


class DocumentModel(QObject):
    """
    In-memory document model tracking the current pages, order, selection,
    and modification state.
    """

    # Signals for UI synchronization
    pages_changed = Signal()  # Emitted when order, count, or pages change
    selection_changed = Signal(list)  # Emitted when selected indices change: list[int]
    active_page_changed = Signal(int)  # Emitted when current viewed page changes: int
    modified_changed = Signal(bool)  # Emitted when modified status flips: bool
    page_rotated = Signal(str, int)  # Emitted when page_id rotation updates: page_id, new_rotation

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._pages: List[PageItem] = []
        self._selected_ids: Set[str] = set()
        self._active_index: int = 0
        self._is_modified: bool = False

    @property
    def is_modified(self) -> bool:
        return self._is_modified

    def set_modified(self, modified: bool) -> None:
        if self._is_modified != modified:
            self._is_modified = modified
            self.modified_changed.emit(self._is_modified)

    def clear(self) -> None:
        """Clear all pages and reset state."""
        self._pages.clear()
        self._selected_ids.clear()
        self._active_index = 0
        self._is_modified = False
        self.pages_changed.emit()
        self.selection_changed.emit([])
        self.active_page_changed.emit(0)
        self.modified_changed.emit(False)

    def load_pages(self, count: int, initial_rotations: Optional[List[int]] = None) -> None:
        """Initialize document model with initial pages from a freshly opened document."""
        self._pages.clear()
        self._selected_ids.clear()
        self._active_index = 0

        for i in range(count):
            rot = initial_rotations[i] if initial_rotations and i < len(initial_rotations) else 0
            self._pages.append(PageItem(source_page_index=i, rotation=rot))

        if self._pages:
            self._selected_ids = {self._pages[0].page_id}

        self._is_modified = False
        self.pages_changed.emit()
        self.selection_changed.emit([0] if self._pages else [])
        self.active_page_changed.emit(0)
        self.modified_changed.emit(False)

    def page_count(self) -> int:
        return len(self._pages)

    def get_pages(self) -> List[PageItem]:
        return list(self._pages)

    def get_page(self, index: int) -> Optional[PageItem]:
        if 0 <= index < len(self._pages):
            return self._pages[index]
        return None

    def get_index_by_id(self, page_id: str) -> int:
        for idx, page in enumerate(self._pages):
            if page.page_id == page_id:
                return idx
        return -1

    def get_indices_by_ids(self, page_ids: List[str]) -> List[int]:
        id_set = set(page_ids)
        return [idx for idx, page in enumerate(self._pages) if page.page_id in id_set]

    def get_active_index(self) -> int:
        return self._active_index

    def set_active_index(self, index: int) -> None:
        if not self._pages:
            self._active_index = 0
            self.active_page_changed.emit(0)
            return

        clamped = max(0, min(index, len(self._pages) - 1))
        if self._active_index != clamped:
            self._active_index = clamped
            self.active_page_changed.emit(clamped)

    def get_selected_indices(self) -> List[int]:
        return [idx for idx, page in enumerate(self._pages) if page.page_id in self._selected_ids]

    def get_selected_ids(self) -> List[str]:
        return [page.page_id for page in self._pages if page.page_id in self._selected_ids]

    def set_selected_indices(self, indices: List[int]) -> None:
        valid_indices = [i for i in indices if 0 <= i < len(self._pages)]
        new_ids = {self._pages[i].page_id for i in valid_indices}
        if new_ids != self._selected_ids:
            self._selected_ids = new_ids
            self.selection_changed.emit(valid_indices)

    def set_selected_ids(self, page_ids: List[str]) -> None:
        new_ids = set(page_ids)
        if new_ids != self._selected_ids:
            self._selected_ids = new_ids
            self.selection_changed.emit(self.get_selected_indices())

    def reorder_by_ids(self, new_id_order: List[str]) -> bool:
        """
        Reorders the current pages according to a list of page_ids.
        Returns True if the order actually changed.
        """
        if len(new_id_order) != len(self._pages):
            return False

        id_to_page = {page.page_id: page for page in self._pages}
        if set(new_id_order) != set(id_to_page.keys()):
            return False

        current_order = [p.page_id for p in self._pages]
        if current_order == new_id_order:
            return False

        self._pages = [id_to_page[pid] for pid in new_id_order]
        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        return True

    def move_page(self, from_index: int, to_index: int) -> bool:
        """Move a single page from one index to another."""
        if not (0 <= from_index < len(self._pages)) or not (0 <= to_index < len(self._pages)):
            return False
        if from_index == to_index:
            return False

        item = self._pages.pop(from_index)
        self._pages.insert(to_index, item)
        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        return True

    def delete_pages(self, indices: List[int]) -> List[Tuple[int, PageItem]]:
        """
        Delete pages at specified indices.
        Returns list of (index, PageItem) tuples in ascending index order for undo.
        Guarantees at least 0 pages, but callers should prevent deleting all pages if needed.
        """
        unique_indices = sorted(set(i for i in indices if 0 <= i < len(self._pages)), reverse=True)
        if not unique_indices:
            return []

        deleted_items: List[Tuple[int, PageItem]] = []
        for idx in unique_indices:
            item = self._pages.pop(idx)
            self._selected_ids.discard(item.page_id)
            deleted_items.append((idx, item))

        # Deleted items in ascending index order
        deleted_items.reverse()

        # Update active and selected page
        if self._pages:
            new_active = min(self._active_index, len(self._pages) - 1)
            self._active_index = new_active
            if not self._selected_ids:
                self._selected_ids = {self._pages[new_active].page_id}
        else:
            self._active_index = 0
            self._selected_ids = set()

        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        self.active_page_changed.emit(self._active_index)
        return deleted_items

    def restore_pages(self, items: List[Tuple[int, PageItem]]) -> None:
        """
        Restore previously deleted pages at their original indices (for undo).
        items should be sorted by index ascending.
        """
        if not items:
            return

        restored_ids = []
        for idx, item in sorted(items, key=lambda x: x[0]):
            target_idx = min(idx, len(self._pages))
            self._pages.insert(target_idx, item)
            restored_ids.append(item.page_id)

        self._selected_ids = set(restored_ids)
        if self._pages:
            self._active_index = min(items[0][0], len(self._pages) - 1)

        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        self.active_page_changed.emit(self._active_index)

    def rotate_pages(self, indices: List[int], angle_delta: int) -> Dict[str, int]:
        """
        Rotates pages at given indices by angle_delta (e.g., 90, -90, 180).
        Returns mapping of page_id -> new_rotation.
        """
        valid_indices = [i for i in indices if 0 <= i < len(self._pages)]
        if not valid_indices or angle_delta % 360 == 0:
            return {}

        result = {}
        for idx in valid_indices:
            page = self._pages[idx]
            page.rotation = (page.rotation + angle_delta) % 360
            result[page.page_id] = page.rotation
            self.page_rotated.emit(page.page_id, page.rotation)

        self.set_modified(True)
        self.pages_changed.emit()
        return result

    def duplicate_pages(self, indices: List[int]) -> List[Tuple[int, PageItem]]:
        """
        Duplicate pages at given indices, inserting copies immediately after each original.
        Returns list of (inserted_index, new_PageItem) tuples for undo.
        """
        sorted_indices = sorted(set(i for i in indices if 0 <= i < len(self._pages)), reverse=True)
        if not sorted_indices:
            return []

        inserted: List[Tuple[int, PageItem]] = []
        for idx in sorted_indices:
            original = self._pages[idx]
            clone_item = original.clone()
            insert_pos = idx + 1
            self._pages.insert(insert_pos, clone_item)
            inserted.append((insert_pos, clone_item))

        # Re-sort inserted items by index ascending
        inserted.sort(key=lambda x: x[0])

        # Select the newly duplicated pages
        new_ids = {item.page_id for _, item in inserted}
        self._selected_ids = new_ids
        if inserted:
            self._active_index = inserted[0][0]

        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        self.active_page_changed.emit(self._active_index)
        return inserted

    def remove_duplicated_pages(self, items: List[Tuple[int, PageItem]]) -> None:
        """Remove previously duplicated pages by ID (for undo)."""
        ids_to_remove = {item.page_id for _, item in items}
        self._pages = [p for p in self._pages if p.page_id not in ids_to_remove]
        self._selected_ids = {pid for pid in self._selected_ids if pid not in ids_to_remove}

        if self._pages:
            self._active_index = min(self._active_index, len(self._pages) - 1)
            if not self._selected_ids:
                self._selected_ids = {self._pages[self._active_index].page_id}
        else:
            self._active_index = 0
            self._selected_ids = set()

        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        self.active_page_changed.emit(self._active_index)

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return a serializable snapshot of the current page list."""
        return [p.to_dict() for p in self._pages]

    def restore_snapshot(self, snapshot_data: List[Dict[str, Any]]) -> None:
        """Restore pages from a snapshot."""
        self._pages = [PageItem.from_dict(d) for d in snapshot_data]
        valid_ids = {p.page_id for p in self._pages}
        self._selected_ids = {pid for pid in self._selected_ids if pid in valid_ids}
        if self._pages:
            self._active_index = min(self._active_index, len(self._pages) - 1)
            if not self._selected_ids:
                self._selected_ids = {self._pages[self._active_index].page_id}
        else:
            self._active_index = 0
            self._selected_ids = set()

        self.set_modified(True)
        self.pages_changed.emit()
        self.selection_changed.emit(self.get_selected_indices())
        self.active_page_changed.emit(self._active_index)
