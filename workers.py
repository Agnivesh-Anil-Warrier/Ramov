"""
workers.py - Background Thumbnail Rendering and Caching

Generates thumbnails asynchronously using PyMuPDF and QThreadPool so the UI
never hangs even when loading large documents.
"""

from __future__ import annotations
from typing import Optional, Dict
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
import pymupdf


class WorkerSignals(QObject):
    """Signals for background workers."""
    thumbnail_ready = Signal(str, int, QImage)  # page_id, rotation, image
    error = Signal(str, str)  # page_id, error_message


class ThumbnailWorker(QRunnable):
    """
    Renders a single page thumbnail in a background thread and returns a QImage.
    """

    def __init__(
        self,
        raw_pdf_bytes: bytes,
        source_page_index: int,
        rotation: int,
        page_id: str,
        target_max_dim: int = 180,
    ):
        super().__init__()
        self.raw_pdf_bytes = raw_pdf_bytes
        self.source_page_index = source_page_index
        self.rotation = rotation
        self.page_id = page_id
        self.target_max_dim = target_max_dim
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            doc = pymupdf.open(stream=self.raw_pdf_bytes, filetype="pdf")
            if not (0 <= self.source_page_index < len(doc)):
                self.signals.error.emit(self.page_id, "Source page index out of range")
                doc.close()
                return

            page = doc[self.source_page_index]
            rect = page.rect

            # Calculate scale based on desired dimension
            current_dim = max(rect.width, rect.height)
            scale = max(0.1, min(2.0, self.target_max_dim / max(current_dim, 1.0)))

            mat = pymupdf.Matrix(scale, scale).prerotate(self.rotation % 360)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Copy byte buffer into QImage safely
            qimg = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            ).copy()

            doc.close()
            self.signals.thumbnail_ready.emit(self.page_id, self.rotation, qimg)
        except Exception as e:
            self.signals.error.emit(self.page_id, str(e))


class ThumbnailCache:
    """In-memory cache for rendered page thumbnails."""

    def __init__(self, max_entries: int = 500):
        self._cache: Dict[str, QPixmap] = {}
        self._max_entries = max_entries

    def _make_key(self, page_id: str, rotation: int) -> str:
        return f"{page_id}_{rotation % 360}"

    def get(self, page_id: str, rotation: int) -> Optional[QPixmap]:
        return self._cache.get(self._make_key(page_id, rotation))

    def put(self, page_id: str, rotation: int, pixmap: QPixmap) -> None:
        if len(self._cache) >= self._max_entries:
            # Drop oldest key
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[self._make_key(page_id, rotation)] = pixmap

    def invalidate(self, page_id: str) -> None:
        keys_to_remove = [k for k in self._cache if k.startswith(f"{page_id}_")]
        for k in keys_to_remove:
            del self._cache[k]

    def clear(self) -> None:
        self._cache.clear()
