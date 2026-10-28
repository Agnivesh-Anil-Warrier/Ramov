"""
test_pdf_document.py - Tests for PDFDocumentHandler and PyMuPDF operations
"""

import pytest
import pymupdf
from pathlib import Path
from page_model import DocumentModel
from pdf_document import (
    PDFDocumentHandler,
    PDFInvalidError,
    PDFDocumentError,
    PDFSaveError,
)


def test_load_valid_pdf(sample_pdf_path):
    handler = PDFDocumentHandler()
    count, warnings = handler.load_from_file(str(sample_pdf_path))

    assert count == 5
    assert handler.is_open()
    assert handler.file_name == "test_sample.pdf"
    assert handler.file_path == str(sample_pdf_path.resolve())
    handler.close()
    assert not handler.is_open()


def test_load_invalid_pdf():
    handler = PDFDocumentHandler()
    with pytest.raises(PDFInvalidError):
        handler.load_from_bytes(b"NOT A REAL PDF FILE HEADER")


def test_compile_reordered_and_deleted_pdf(sample_pdf_path):
    handler = PDFDocumentHandler()
    count, _ = handler.load_from_file(str(sample_pdf_path))

    model = DocumentModel()
    model.load_pages(count)

    # Delete page 1 (BETA) and page 3 (DELTA) -> Remaining: ALPHA (0), GAMMA (2), EPSILON (4)
    model.delete_pages([1, 3])
    assert model.page_count() == 3

    # Reverse order: EPSILON, GAMMA, ALPHA
    current_ids = [p.page_id for p in model.get_pages()]
    model.reorder_by_ids(list(reversed(current_ids)))

    # Compile
    out_bytes = handler.compile_pdf_bytes(model)
    assert out_bytes.startswith(b"%PDF")

    # Verify actual content order using PyMuPDF
    res_doc = pymupdf.open(stream=out_bytes, filetype="pdf")
    assert len(res_doc) == 3
    assert "EPSILON" in res_doc[0].get_text()
    assert "GAMMA" in res_doc[1].get_text()
    assert "ALPHA" in res_doc[2].get_text()
    res_doc.close()
    handler.close()


def test_compile_with_rotation_and_duplication(sample_pdf_path):
    handler = PDFDocumentHandler()
    count, _ = handler.load_from_file(str(sample_pdf_path))

    model = DocumentModel()
    model.load_pages(count)

    # Rotate page 0 by 90
    model.rotate_pages([0], 90)

    # Duplicate page 0
    model.duplicate_pages([0])
    assert model.page_count() == 6

    out_bytes = handler.compile_pdf_bytes(model)
    res_doc = pymupdf.open(stream=out_bytes, filetype="pdf")
    assert len(res_doc) == 6
    # Both first two pages are ALPHA and rotated 90
    assert "ALPHA" in res_doc[0].get_text()
    assert res_doc[0].rotation == 90
    assert "ALPHA" in res_doc[1].get_text()
    assert res_doc[1].rotation == 90
    res_doc.close()
    handler.close()


def test_atomic_save_and_reopen(sample_pdf_path, tmp_path):
    handler = PDFDocumentHandler()
    count, _ = handler.load_from_file(str(sample_pdf_path))

    model = DocumentModel()
    model.load_pages(count)

    # Delete page 0 (ALPHA)
    model.delete_pages([0])
    assert model.page_count() == 4

    save_target = tmp_path / "saved_modified.pdf"
    saved_path = handler.save(model, str(save_target))

    assert Path(saved_path).is_file()
    assert not model.is_modified

    # Reopen saved file and verify content
    verify_doc = pymupdf.open(str(save_target))
    assert len(verify_doc) == 4
    # First page should now be BETA
    assert "BETA" in verify_doc[0].get_text()
    verify_doc.close()
    handler.close()


def test_extract_pages(sample_pdf_path, tmp_path):
    handler = PDFDocumentHandler()
    count, _ = handler.load_from_file(str(sample_pdf_path))

    model = DocumentModel()
    model.load_pages(count)

    extract_target = tmp_path / "extracted.pdf"
    # Extract BETA (1) and DELTA (3)
    handler.extract_pages(model, [1, 3], str(extract_target))

    assert extract_target.is_file()
    ext_doc = pymupdf.open(str(extract_target))
    assert len(ext_doc) == 2
    assert "BETA" in ext_doc[0].get_text()
    assert "DELTA" in ext_doc[1].get_text()
    ext_doc.close()
    handler.close()


def test_failed_save_on_invalid_path(sample_pdf_path):
    handler = PDFDocumentHandler()
    count, _ = handler.load_from_file(str(sample_pdf_path))

    model = DocumentModel()
    model.load_pages(count)

    # Invalid path on Windows (invalid drive or illegal filename character)
    invalid_path = "Z:\\nonexistent_dir_12345\\impossible_file.pdf"
    with pytest.raises(PDFSaveError):
        handler.save(model, invalid_path)

    handler.close()


def test_save_empty_pages_rejected(sample_pdf_path, tmp_path):
    handler = PDFDocumentHandler()
    count, _ = handler.load_from_file(str(sample_pdf_path))

    model = DocumentModel()
    model.load_pages(count)

    # Delete all pages
    model.delete_pages(list(range(count)))
    assert model.page_count() == 0

    with pytest.raises(PDFSaveError):
        handler.save(model, str(tmp_path / "empty.pdf"))

    handler.close()
