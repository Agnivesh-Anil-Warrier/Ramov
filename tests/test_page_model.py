"""
test_page_model.py - Tests for DocumentModel and PageItem
"""

import pytest
from page_model import DocumentModel, PageItem


def test_page_item_creation_and_clone(qapp):
    item = PageItem(source_page_index=2, rotation=90)
    assert item.source_page_index == 2
    assert item.rotation == 90
    assert item.page_id.startswith("page-")

    clone = item.clone()
    assert clone.source_page_index == 2
    assert clone.rotation == 90
    assert clone.page_id != item.page_id  # Cloned item must have unique stable ID


def test_document_model_load(qapp):
    model = DocumentModel()
    model.load_pages(5, [0, 90, 180, 270, 0])

    assert model.page_count() == 5
    assert model.get_page(0).rotation == 0
    assert model.get_page(1).rotation == 90
    assert model.get_page(2).rotation == 180
    assert model.get_page(3).rotation == 270
    assert model.get_active_index() == 0
    assert model.get_selected_indices() == [0]
    assert not model.is_modified


def test_single_and_multi_page_deletion(qapp):
    model = DocumentModel()
    model.load_pages(5)

    # Delete single page (page 1)
    deleted = model.delete_pages([1])
    assert len(deleted) == 1
    assert deleted[0][0] == 1
    assert model.page_count() == 4
    assert model.is_modified

    # Delete multiple pages (0 and 2 of the remaining 4)
    deleted_multi = model.delete_pages([0, 2])
    assert len(deleted_multi) == 2
    assert model.page_count() == 2
    assert model.get_active_index() <= 1


def test_page_reordering(qapp):
    model = DocumentModel()
    model.load_pages(4)
    pages = model.get_pages()
    ids = [p.page_id for p in pages]

    # Reorder to reverse: 3, 2, 1, 0
    reversed_ids = list(reversed(ids))
    success = model.reorder_by_ids(reversed_ids)
    assert success
    assert [p.page_id for p in model.get_pages()] == reversed_ids
    assert model.is_modified


def test_reordering_after_deletion(qapp):
    model = DocumentModel()
    model.load_pages(5)

    # Delete page at index 2
    model.delete_pages([2])
    assert model.page_count() == 4

    # Now reorder the remaining pages
    current_ids = [p.page_id for p in model.get_pages()]
    new_order = [current_ids[3], current_ids[0], current_ids[1], current_ids[2]]
    success = model.reorder_by_ids(new_order)
    assert success
    assert [p.page_id for p in model.get_pages()] == new_order


def test_page_rotation(qapp):
    model = DocumentModel()
    model.load_pages(3)

    # Rotate page 0 by 90 degrees
    model.rotate_pages([0], 90)
    assert model.get_page(0).rotation == 90

    # Rotate again by 180 -> 270 degrees
    model.rotate_pages([0], 180)
    assert model.get_page(0).rotation == 270

    # Rotate by -90 (CCW) -> 180 degrees
    model.rotate_pages([0], -90)
    assert model.get_page(0).rotation == 180


def test_page_duplication(qapp):
    model = DocumentModel()
    model.load_pages(3)

    # Duplicate page 1
    inserted = model.duplicate_pages([1])
    assert len(inserted) == 1
    assert model.page_count() == 4

    # The duplicated page should be at index 2, with same source index
    dup_page = model.get_page(2)
    assert dup_page.source_page_index == 1
    assert dup_page.page_id != model.get_page(1).page_id
    assert model.get_selected_indices() == [2]


def test_selection_maintenance(qapp):
    model = DocumentModel()
    model.load_pages(5)

    model.set_selected_indices([1, 3])
    assert model.get_selected_indices() == [1, 3]

    # Delete index 3
    model.delete_pages([3])
    # Index 1 should still be selected
    assert model.get_selected_indices() == [1]
