"""
test_undo_redo.py - Tests for Undo/Redo commands and UndoManager
"""

import pytest
from page_model import DocumentModel
from undo_manager import (
    UndoManager,
    ReorderPagesCommand,
    DeletePagesCommand,
    RotatePagesCommand,
    DuplicatePagesCommand,
)


def test_undo_redo_deletion(qapp):
    model = DocumentModel()
    model.load_pages(4)
    undo_mgr = UndoManager()

    cmd = DeletePagesCommand(model, [1, 2], "Delete 2 pages")
    undo_mgr.push(cmd)

    assert model.page_count() == 2
    assert undo_mgr.can_undo()
    assert not undo_mgr.can_redo()

    # Undo
    undo_mgr.undo()
    assert model.page_count() == 4
    assert not undo_mgr.can_undo()
    assert undo_mgr.can_redo()

    # Redo
    undo_mgr.redo()
    assert model.page_count() == 2
    assert undo_mgr.can_undo()
    assert not undo_mgr.can_redo()


def test_undo_redo_reorder(qapp):
    model = DocumentModel()
    model.load_pages(3)
    undo_mgr = UndoManager()

    init_ids = [p.page_id for p in model.get_pages()]
    new_ids = [init_ids[2], init_ids[0], init_ids[1]]

    cmd = ReorderPagesCommand(model, init_ids, new_ids, "Reorder")
    undo_mgr.push(cmd)

    assert [p.page_id for p in model.get_pages()] == new_ids

    # Undo
    undo_mgr.undo()
    assert [p.page_id for p in model.get_pages()] == init_ids

    # Redo
    undo_mgr.redo()
    assert [p.page_id for p in model.get_pages()] == new_ids


def test_undo_redo_rotation(qapp):
    model = DocumentModel()
    model.load_pages(2)
    undo_mgr = UndoManager()

    page_id = model.get_page(0).page_id
    cmd = RotatePagesCommand(model, [page_id], 90, "Rotate")
    undo_mgr.push(cmd)

    assert model.get_page(0).rotation == 90

    # Undo
    undo_mgr.undo()
    assert model.get_page(0).rotation == 0

    # Redo
    undo_mgr.redo()
    assert model.get_page(0).rotation == 90


def test_undo_redo_duplication(qapp):
    model = DocumentModel()
    model.load_pages(2)
    undo_mgr = UndoManager()

    cmd = DuplicatePagesCommand(model, [0], "Duplicate")
    undo_mgr.push(cmd)

    assert model.page_count() == 3

    # Undo
    undo_mgr.undo()
    assert model.page_count() == 2

    # Redo
    undo_mgr.redo()
    assert model.page_count() == 3
