"""
conftest.py - Pytest Fixtures for Ramov PDF Studio Tests
"""

import sys

# Prevent PyMuPDF from loading unused heavy ONNX/layout machine-learning packages
for _mod in ("pymupdf.layout", "pymupdf_layout", "pymupdf4llm", "onnxruntime"):
    sys.modules.setdefault(_mod, None)

import pytest
import pymupdf
from pathlib import Path
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance exists for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def sample_pdf_path(tmp_path) -> Path:
    """
    Creates a 5-page test PDF with clearly distinguishable text and colors.
    Page 1: 'Page 1: ALPHA'
    Page 2: 'Page 2: BETA'
    Page 3: 'Page 3: GAMMA'
    Page 4: 'Page 4: DELTA'
    Page 5: 'Page 5: EPSILON'
    """
    doc = pymupdf.open()
    pages_data = [
        ("Page 1: ALPHA", (100, 100)),
        ("Page 2: BETA", (100, 100)),
        ("Page 3: GAMMA", (100, 100)),
        ("Page 4: DELTA", (100, 100)),
        ("Page 5: EPSILON", (100, 100)),
    ]
    for text, pos in pages_data:
        p = doc.new_page(width=400, height=500)
        p.insert_text(pos, text, fontsize=18)

    file_path = tmp_path / "test_sample.pdf"
    doc.save(str(file_path))
    doc.close()
    return file_path


@pytest.fixture
def sample_pdf_bytes(sample_pdf_path) -> bytes:
    return sample_pdf_path.read_bytes()
