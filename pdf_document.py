"""
pdf_document.py - PDF Document Operations and Safe Persistence

Handles loading, validating, manipulating, extracting, and safely saving PDF documents
using PyMuPDF. Ensures atomic file replacement and guards against file corruption.
"""

from __future__ import annotations
import os
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import pymupdf
from page_model import DocumentModel, PageItem


class PDFDocumentError(Exception):
    """Base exception for PDF operations."""
    pass


class PDFPasswordProtectedError(PDFDocumentError):
    """Raised when a document is encrypted and requires a password."""
    pass


class PDFInvalidError(PDFDocumentError):
    """Raised when file content is not a valid PDF."""
    pass


class PDFSaveError(PDFDocumentError):
    """Raised when saving the document fails."""
    pass


class PDFDocumentHandler:
    """
    Manages loading, compiling, and safely saving PDF documents using PyMuPDF.
    Maintains an in-memory representation so that original files are never
    modified until explicitly committed.
    """

    def __init__(self):
        self.file_path: Optional[str] = None
        self.file_name: str = ""
        self.raw_bytes: Optional[bytes] = None
        self.source_doc: Optional[pymupdf.Document] = None
        self.has_signatures: bool = False
        self.is_form: bool = False
        self.is_encrypted: bool = False

    def is_open(self) -> bool:
        return self.source_doc is not None and not self.source_doc.is_closed

    def close(self) -> None:
        if self.source_doc is not None and not self.source_doc.is_closed:
            self.source_doc.close()
        self.source_doc = None
        self.raw_bytes = None
        self.file_path = None
        self.file_name = ""
        self.has_signatures = False
        self.is_form = False
        self.is_encrypted = False

    def load_from_file(self, file_path: str, password: Optional[str] = None) -> Tuple[int, List[str]]:
        """
        Loads a PDF from the given file path into memory.
        Returns (page_count, warnings).
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            raw_bytes = path.read_bytes()
        except Exception as e:
            raise PDFDocumentError(f"Failed to read file: {e}") from e

        return self.load_from_bytes(raw_bytes, file_name=path.name, file_path=str(path.resolve()), password=password)

    def load_from_bytes(
        self,
        raw_bytes: bytes,
        file_name: str = "document.pdf",
        file_path: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Tuple[int, List[str]]:
        """
        Loads PDF bytes in memory without keeping open disk file locks.
        Returns (page_count, list_of_warning_messages).
        """
        if not raw_bytes or not raw_bytes.startswith(b"%PDF"):
            # Check if anywhere in first 1024 bytes
            if b"%PDF-" not in raw_bytes[:1024]:
                raise PDFInvalidError("Selected file does not appear to be a valid PDF document.")

        try:
            doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        except Exception as e:
            raise PDFInvalidError(f"PyMuPDF failed to open document: {e}") from e

        if doc.is_encrypted:
            self.is_encrypted = True
            if password is not None:
                if not doc.authenticate(password):
                    doc.close()
                    raise PDFPasswordProtectedError("Incorrect password for encrypted PDF.")
            else:
                doc.close()
                raise PDFPasswordProtectedError("This PDF document is password-protected.")

        warnings: List[str] = []

        # Check for signatures or special form features
        sigflags = getattr(doc, "get_sigflags", lambda: -1)()
        if sigflags > 0:
            self.has_signatures = True
            warnings.append(
                "This document contains digital signatures. Modifying, reordering, or deleting "
                "pages will invalidate existing digital signatures."
            )

        if getattr(doc, "is_form_pdf", False):
            self.is_form = True
            warnings.append(
                "This document contains interactive form fields. Page manipulation may alter form field mappings."
            )

        # Close any previous doc
        if self.source_doc is not None and not self.source_doc.is_closed:
            self.source_doc.close()

        self.source_doc = doc
        self.raw_bytes = raw_bytes
        self.file_path = file_path
        self.file_name = file_name

        page_count = len(doc)
        if page_count == 0:
            warnings.append("The document contains no pages.")

        return page_count, warnings

    def get_initial_rotations(self) -> List[int]:
        """Returns the initial rotation angles of all pages in the source document."""
        if not self.source_doc:
            return []
        return [page.rotation for page in self.source_doc]

    def compile_pdf_bytes(self, model: DocumentModel) -> bytes:
        """
        Assembles a complete in-memory PDF from the current DocumentModel state.
        Applies page selection order and rotation.
        """
        if not self.source_doc or self.source_doc.is_closed:
            raise PDFDocumentError("No source document loaded to compile.")

        if model.page_count() == 0:
            raise PDFDocumentError("Cannot compile an empty PDF document (must have at least 1 page).")

        new_doc = pymupdf.open()
        try:
            for item in model.get_pages():
                # Verify source page index is valid in source doc
                if not (0 <= item.source_page_index < len(self.source_doc)):
                    raise PDFDocumentError(
                        f"Page source index {item.source_page_index} out of range in source document."
                    )
                new_doc.insert_pdf(
                    self.source_doc,
                    from_page=item.source_page_index,
                    to_page=item.source_page_index,
                )
                page = new_doc[-1]
                page.set_rotation(item.rotation % 360)

            out_bytes = new_doc.tobytes(garbage=3, deflate=True)
            return out_bytes
        finally:
            new_doc.close()

    def extract_pages(self, model: DocumentModel, indices: List[int], target_path: str) -> None:
        """
        Extracts selected pages according to the model and writes them to target_path safely.
        """
        if not self.source_doc or self.source_doc.is_closed:
            raise PDFDocumentError("No source document loaded.")

        valid_indices = [i for i in indices if 0 <= i < model.page_count()]
        if not valid_indices:
            raise PDFDocumentError("No valid pages selected for extraction.")

        dest_doc = pymupdf.open()
        try:
            for idx in valid_indices:
                item = model.get_page(idx)
                if item is None:
                    continue
                dest_doc.insert_pdf(
                    self.source_doc,
                    from_page=item.source_page_index,
                    to_page=item.source_page_index,
                )
                page = dest_doc[-1]
                page.set_rotation(item.rotation % 360)

            out_bytes = dest_doc.tobytes(garbage=3, deflate=True)
        finally:
            dest_doc.close()

        self._atomic_write(target_path, out_bytes)

    def save(self, model: DocumentModel, target_path: Optional[str] = None) -> str:
        """
        Compiles the modified PDF and atomically writes it to target_path (or self.file_path).
        Reloads the in-memory source document to reflect the saved state and re-aligns model indices.
        Returns the saved file path.
        """
        save_path = target_path or self.file_path
        if not save_path:
            raise PDFSaveError("No file path specified for saving.")

        if model.page_count() == 0:
            raise PDFSaveError("Cannot save a PDF with 0 pages.")

        try:
            new_bytes = self.compile_pdf_bytes(model)
        except Exception as e:
            raise PDFSaveError(f"Failed to compile PDF: {e}") from e

        # Atomic file write to avoid corrupting the file if an error occurs
        try:
            self._atomic_write(save_path, new_bytes)
        except Exception as e:
            raise PDFSaveError(f"Failed to write PDF to '{save_path}': {e}") from e

        # Reload our source doc from the newly written bytes so subsequent edits branch from here
        try:
            new_source = pymupdf.open(stream=new_bytes, filetype="pdf")
            if self.source_doc and not self.source_doc.is_closed:
                self.source_doc.close()
            self.source_doc = new_source
            self.raw_bytes = new_bytes
            self.file_path = str(Path(save_path).resolve())
            self.file_name = Path(save_path).name

            # Reset page source indices to 0..N in the model so future changes match the new document
            current_pages = model.get_pages()
            for idx, p in enumerate(current_pages):
                p.source_page_index = idx
                p.rotation = self.source_doc[idx].rotation

            model.set_modified(False)
            return self.file_path
        except Exception as e:
            raise PDFSaveError(f"Document saved but failed to reload internal state: {e}") from e

    def _atomic_write(self, target_path: str, data: bytes) -> None:
        """
        Writes data to a temporary file in the same directory as target_path,
        flushes, syncs to disk, and uses os.replace for atomic replacement.
        """
        target = Path(target_path).resolve()
        parent_dir = target.parent
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise PDFSaveError(f"Cannot create directory '{parent_dir}': {e}") from e

        # Unique temp file in same filesystem/directory to ensure atomic os.replace
        temp_name = f".{target.name}.tmp-{uuid.uuid4().hex}"
        temp_path = parent_dir / temp_name

        try:
            with open(temp_path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            os.replace(temp_path, target)
        except Exception as e:
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise PDFSaveError(f"Atomic file write failed for '{target}': {e}") from e
