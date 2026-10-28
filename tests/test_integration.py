"""
test_integration.py - Full End-to-End Workflow Integration Test
"""

import pytest
import pymupdf
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox
from main_window import MainWindow


def test_full_pdf_editor_workflow(qapp, sample_pdf_path, tmp_path):
    win = MainWindow()

    # 1. Open initial 5-page PDF: ALPHA (0), BETA (1), GAMMA (2), DELTA (3), EPSILON (4)
    opened = win.load_pdf(str(sample_pdf_path))
    assert opened
    assert win.model.page_count() == 5
    assert not win.is_edit_mode

    # 2. Switch to Edit Mode
    win._mode_toggle_btn.setChecked(True)
    assert win.is_edit_mode

    # 3. Reorder pages: move EPSILON (4) to the beginning -> [EPSILON, ALPHA, BETA, GAMMA, DELTA]
    orig_pages = win.model.get_pages()
    new_order = [orig_pages[4].page_id, orig_pages[0].page_id, orig_pages[1].page_id, orig_pages[2].page_id, orig_pages[3].page_id]
    win.reorder_pages_by_ids(new_order)
    assert win.model.page_count() == 5
    assert win.model.is_modified

    # 4. Delete page 2 (which is BETA) -> [EPSILON, ALPHA, GAMMA, DELTA]
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        win.sidebar.select_single_page(2)
        win.delete_selected_pages()
    assert win.model.page_count() == 4

    # 5. Rotate page 0 (EPSILON) by 90 degrees
    win.sidebar.select_single_page(0)
    win.rotate_selected_pages(90)
    assert win.model.get_page(0).rotation == 90

    # 6. Duplicate page 0 -> [EPSILON (rot 90), EPSILON copy (rot 90), ALPHA, GAMMA, DELTA]
    win.sidebar.select_single_page(0)
    win.duplicate_selected_pages()
    assert win.model.page_count() == 5

    # 7. Undo the duplicate -> back to 4 pages
    win.undo_action()
    assert win.model.page_count() == 4
    assert win.model.get_page(0).rotation == 90

    # 8. Save As to a new file
    output_pdf = tmp_path / "final_workflow_result.pdf"
    with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(output_pdf), "PDF")):
        with patch.object(QMessageBox, "information"):
            saved = win.save_document_as()
            assert saved

    assert output_pdf.is_file()
    assert not win.model.is_modified

    # 9. Verify the saved file on disk with PyMuPDF independently
    saved_doc = pymupdf.open(str(output_pdf))
    assert len(saved_doc) == 4
    # Page 0: EPSILON, rotated 90
    assert "EPSILON" in saved_doc[0].get_text()
    assert saved_doc[0].rotation == 90
    # Page 1: ALPHA
    assert "ALPHA" in saved_doc[1].get_text()
    # Page 2: GAMMA
    assert "GAMMA" in saved_doc[2].get_text()
    # Page 3: DELTA
    assert "DELTA" in saved_doc[3].get_text()
    saved_doc.close()

    # 10. Reopen the saved document in the UI
    reopened = win.load_pdf(str(output_pdf))
    assert reopened
    assert win.model.page_count() == 4
    assert win.model.get_page(0).rotation == 90
    assert not win.is_edit_mode
