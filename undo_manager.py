"""
undo_manager.py - Undo and Redo Operation History

Provides command objects and an undo/redo stack for all PDF page operations:
- Page Reordering
- Page Deletion
- Page Rotation
- Page Duplication
"""

from __future__ import annotations
from typing import List, Tuple, Optional
from PySide6.QtCore import QObject, Signal
from page_model import DocumentModel, PageItem


class Command:
    """Base interface for undoable document commands."""

    def __init__(self, description: str = ""):
        self.description: str = description

    def redo(self) -> None:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError


class ReorderPagesCommand(Command):
    """Command for reordering pages via drag-and-drop or explicit move."""

    def __init__(
        self,
        model: DocumentModel,
        before_ids: List[str],
        after_ids: List[str],
        description: str = "Reorder Pages",
    ):
        super().__init__(description)
        self.model = model
        self.before_ids = list(before_ids)
        self.after_ids = list(after_ids)

    def redo(self) -> None:
        self.model.reorder_by_ids(self.after_ids)

    def undo(self) -> None:
        self.model.reorder_by_ids(self.before_ids)


class DeletePagesCommand(Command):
    """Command for deleting one or multiple pages."""

    def __init__(
        self,
        model: DocumentModel,
        indices: List[int],
        description: str = "Delete Page(s)",
    ):
        super().__init__(description)
        self.model = model
        self.target_indices = sorted(indices)
        self.deleted_items: List[Tuple[int, PageItem]] = []

    def redo(self) -> None:
        # Perform deletion and capture items if not yet captured
        self.deleted_items = self.model.delete_pages(self.target_indices)

    def undo(self) -> None:
        if self.deleted_items:
            self.model.restore_pages(self.deleted_items)


class RotatePagesCommand(Command):
    """Command for rotating one or multiple pages."""

    def __init__(
        self,
        model: DocumentModel,
        page_ids: List[str],
        angle_delta: int,
        description: str = "Rotate Page(s)",
    ):
        super().__init__(description)
        self.model = model
        self.page_ids = list(page_ids)
        self.angle_delta = angle_delta

    def redo(self) -> None:
        indices = self.model.get_indices_by_ids(self.page_ids)
        if indices:
            self.model.rotate_pages(indices, self.angle_delta)

    def undo(self) -> None:
        indices = self.model.get_indices_by_ids(self.page_ids)
        if indices:
            self.model.rotate_pages(indices, -self.angle_delta)


class DuplicatePagesCommand(Command):
    """Command for duplicating one or multiple pages."""

    def __init__(
        self,
        model: DocumentModel,
        indices: List[int],
        description: str = "Duplicate Page(s)",
    ):
        super().__init__(description)
        self.model = model
        self.target_indices = sorted(indices)
        self.inserted_items: List[Tuple[int, PageItem]] = []

    def redo(self) -> None:
        if not self.inserted_items:
            # First execution
            self.inserted_items = self.model.duplicate_pages(self.target_indices)
        else:
            # Re-execute by restoring items
            self.model.restore_pages(self.inserted_items)

    def undo(self) -> None:
        if self.inserted_items:
            self.model.remove_duplicated_pages(self.inserted_items)


class UndoManager(QObject):
    """
    Manages the undo and redo history stacks and emits signals for UI action states.
    """

    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    history_changed = Signal()

    def __init__(self, parent: Optional[QObject] = None, max_depth: int = 50):
        super().__init__(parent)
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_depth = max_depth

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_state()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def push(self, cmd: Command, execute_now: bool = True) -> None:
        """Push a command onto the undo stack and clear redo history."""
        if execute_now:
            cmd.redo()
        self._undo_stack.append(cmd)
        if len(self._undo_stack) > self._max_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._notify_state()

    def undo(self) -> Optional[Command]:
        """Undo the most recent command."""
        if not self.can_undo():
            return None
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        self._notify_state()
        return cmd

    def redo(self) -> Optional[Command]:
        """Redo the most recently undone command."""
        if not self.can_redo():
            return None
        cmd = self._redo_stack.pop()
        cmd.redo()
        self._undo_stack.append(cmd)
        self._notify_state()
        return cmd

    def undo_text(self) -> str:
        if self._undo_stack:
            return f"Undo {self._undo_stack[-1].description}"
        return "Undo"

    def redo_text(self) -> str:
        if self._redo_stack:
            return f"Redo {self._redo_stack[-1].description}"
        return "Redo"

    def _notify_state(self) -> None:
        self.can_undo_changed.emit(self.can_undo())
        self.can_redo_changed.emit(self.can_redo())
        self.history_changed.emit()
