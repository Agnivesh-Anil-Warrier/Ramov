# Ramov PDF Studio

A native desktop PDF viewer and page editor built with **PySide6**, **QtPdf**, and **PyMuPDF (`pymupdf`)**.

---

## 🌟 Key Features

### 1. Dual Mode Architecture (Viewing vs. Editing)
- **Prominent Toolbar Toggle**: Instantly switch between **Viewing Mode** (read-only) and **Editing Mode** (pages unlocked).
- **Strict Handler-Level Enforcement**: Editing operations (delete, reorder, rotate, duplicate, extract, save) are strictly enforced in logic—not just disabled in the UI.
- **Safety Prompts**: Switching from Editing Mode back to Viewing Mode while unsaved changes exist prompts the user with **Save**, **Discard**, or **Cancel** options.
- **Visual Status**: Distinctive color badges and status bar indicators keep the current mode immediately obvious.

### 2. High-Performance PDF Viewing
- **Continuous Vertical Scrolling**: Powered by `QPdfView` (`MultiPage` mode) for reading.
- **Comprehensive Zoom Controls**:
  - Zoom In (`Ctrl++`) and Zoom Out (`Ctrl+-`)
  - Fit Page (`Ctrl+0`)
  - Fit Width (`Ctrl+9`)
  - Custom zoom factor scaling from 20% to 500% with real-time percentage readout.
- **Page Navigation**:
  - Jump to page via toolbar numeric spinbox
  - Next page (`Right Arrow`) and Previous page (`Left Arrow`)
  - Real-time synchronization with thumbnail selection.
- **Fast Text Search**:
  - Search bar (`Ctrl+F`) with match count indicator ("Match X of Y")
  - Next match (`Enter` / `▶`) and Previous match (`Shift+Enter` / `◀`) jumping.

### 3. Page Thumbnail Sidebar & Drag-and-Drop
- **Rich Miniature Previews**: Rendered asynchronously via background worker threads (`QThreadPool`) without freezing the user interface.
- **Selection Modes**:
  - Single click to navigate
  - `Ctrl+Click` to select multiple disjoint pages
  - `Shift+Click` to select a range of pages
- **Drag-and-Drop Reordering**: Rearrange pages visually in Editing Mode. Drag-and-drop is automatically locked in Viewing Mode.
- **Context Menu Operations**:
  - Rotate Clockwise 90° (`Ctrl+R`)
  - Rotate Counterclockwise 90° (`Ctrl+Shift+R`)
  - Rotate 180°
  - Duplicate Page(s) (`Ctrl+D`)
  - Delete Page(s) (`Del`) with confirmation dialog
  - Extract Page(s)... (`Ctrl+E`) to a new PDF file
- **Collapsible Sidebar**: Toggle button (`◀` / `▶`) and resizable splitter.

### 4. Robust Document Model & Safe Atomic Saving
- **Stable Page Identifiers**: Each logical page maintains a stable identifier (`page_id`), tracking source page indices and cumulative rotation.
- **Zero In-Place Corruption**: The original PDF file is never modified until explicitly committed. In-memory buffers ensure that Windows file-locking issues (`[WinError 32]` or `[WinError 5]`) never occur.
- **Atomic File Replacement**: Saves write to an isolated temporary file first, flush and fsync, then replace the target atomically (`os.replace`).
- **Signature & Form Warnings**: Automatically detects digital signatures or interactive form fields and warns the user before modifications invalidate them.

### 5. Complete Undo and Redo
- Full undo and redo history for:
  - Page reordering
  - Single and multi-page deletion
  - Clockwise and counterclockwise rotations
  - Page duplication
- Restoring a previous state restores both page order, rotations, and active selection.

---

## 📁 Project Structure

```text
Ramov/
├── main.py                 # Application entry point & high-DPI bootstrap
├── main_window.py          # Main window, menus, toolbars, dialogs & mode enforcement
├── pdf_document.py         # PyMuPDF loading, compiling, extraction & atomic saving
├── page_model.py           # DocumentModel, PageItem, stable IDs & state tracking
├── pdf_viewer.py           # QPdfView central viewer, continuous scroll & text search
├── thumbnail_sidebar.py    # Thumbnail sidebar, custom delegate, drag-and-drop & context menu
├── undo_manager.py         # Undo/Redo command stack
├── workers.py              # Asynchronous thumbnail rendering & in-memory cache
├── sample_document.pdf     # Included 6-page test document
├── requirements.txt        # Project dependencies
├── README.md               # Documentation & instructions
└── tests/                  # Automated pytest suite (24 tests)
    ├── conftest.py         # Fixtures & sample PDF generators
    ├── test_page_model.py  # Model state, reordering & deletion tests
    ├── test_pdf_document.py# Loading, atomic saving & extraction tests
    ├── test_undo_redo.py   # Undo/redo command tests
    ├── test_mode_restrictions.py # Mode security & restriction tests
    └── test_integration.py # Full end-to-end workflow integration test
```

---

## 🚀 Quickstart & Execution

Use the existing `.venv` Python virtual environment in the project directory:

### On Windows:
```powershell
# Activate the existing virtual environment
.venv\Scripts\activate

# Launch the application
python main.py

# Or launch directly with a PDF file:
python main.py sample_document.pdf
```

### On Linux / macOS:
```bash
# Activate the virtual environment
source .venv/bin/activate

# Launch the application
python main.py sample_document.pdf
```

---

## 🧪 Running Automated Tests

Run the complete test suite with `pytest`:

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

All 24 automated unit and integration tests will execute, verifying:
- Document loading and error handling
- Page reordering (including reordering after deletions)
- Multi-page deletion and safety constraints (preventing 0-page PDFs)
- Page rotation (90°, -90°, 180°)
- Page duplication and page extraction
- Safe atomic saving and reopening verified against PyMuPDF
- Viewing vs. Editing Mode restrictions and unsaved changes dialogs
- Undo/Redo stack across all operations
