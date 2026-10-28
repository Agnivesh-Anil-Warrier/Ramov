"""
test_mode_restrictions.py - Verification of Viewing vs. Editing Mode enforcement
"""

import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox
from main_window import MainWindow


def test_mode_restrictions_in_viewing_mode(qapp, sample_pdf_path):
    win = MainWindow()
    loaded = win.load_pdf(str(sample_pdf_path))
    assert loaded

    # Window starts in Viewing Mode
    assert not win.is_edit_mode
    assert win.sidebar.list_widget.dragDropMode() == win.sidebar.list_widget.DragDropMode.NoDragDrop

    # Attempting modifying operations in viewing mode must be blocked
    with patch.object(QMessageBox, "warning") as mock_warn:
        win.delete_selected_pages()
        mock_warn.assert_called_once()
        assert win.model.page_count() == 5  # Unchanged!

    with patch.object(QMessageBox, "warning") as mock_warn:
        win.rotate_selected_pages(90)
        mock_warn.assert_called_once()
        assert win.model.get_page(0).rotation == 0  # Unchanged!

    with patch.object(QMessageBox, "warning") as mock_warn:
        win.duplicate_selected_pages()
        mock_warn.assert_called_once()
        assert win.model.page_count() == 5  # Unchanged!

    with patch.object(QMessageBox, "warning") as mock_warn:
        win.save_document()
        mock_warn.assert_called_once()


def test_switching_to_editing_mode_unlocks_operations(qapp, sample_pdf_path):
    win = MainWindow()
    win.load_pdf(str(sample_pdf_path))

    # Switch to Editing Mode
    win._mode_toggle_btn.setChecked(True)
    assert win.is_edit_mode
    assert win.sidebar.list_widget.dragDropMode() == win.sidebar.list_widget.DragDropMode.InternalMove

    # Deletion is now permitted in Editing Mode
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        win.model.set_selected_indices([1])
        win.delete_selected_pages()
        assert win.model.page_count() == 4
        assert win.model.is_modified


def test_mode_switch_prompt_on_unsaved_changes(qapp, sample_pdf_path):
    win = MainWindow()
    win.load_pdf(str(sample_pdf_path))

    # Switch to Editing Mode
    win._mode_toggle_btn.setChecked(True)
    assert win.is_edit_mode

    # Make a change
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        win.model.set_selected_indices([0])
        win.delete_selected_pages()
    assert win.model.is_modified

    # Attempt to switch back to Viewing Mode, choose Cancel
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Cancel):
        win._mode_toggle_btn.setChecked(False)
        # Should stay in Editing Mode because user chose Cancel
        assert win.is_edit_mode


def test_delete_dialog_default_button_is_yes(qapp, sample_pdf_path):
    win = MainWindow()
    win.load_pdf(str(sample_pdf_path))
    win._mode_toggle_btn.setChecked(True)

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as mock_q:
        win.sidebar.select_single_page(0)
        win.delete_selected_pages()
        mock_q.assert_called_once()
        args = mock_q.call_args[0]
        # args[4] is the defaultButton parameter passed to QMessageBox.question
        default_btn = args[4]
        assert default_btn == QMessageBox.StandardButton.Yes
