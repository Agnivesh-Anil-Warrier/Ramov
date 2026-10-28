"""
main.py - Application Entry Point for Ramov PDF Studio

Configures the PySide6 application, High-DPI attributes, styling,
and launches the MainWindow. Accepts an optional PDF file path via CLI.
"""

from __future__ import annotations
import sys
import os
from pathlib import Path

# Prevent PyMuPDF from loading unused heavy ONNX/layout machine-learning packages
for _mod in ("pymupdf.layout", "pymupdf_layout", "pymupdf4llm", "onnxruntime"):
    sys.modules.setdefault(_mod, None)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt
from main_window import MainWindow


def setup_exception_hook():
    """Ensure unhandled exceptions log cleanly without silent aborts."""
    orig_hook = sys.excepthook

    def custom_hook(exctype, value, traceback):
        sys.stderr.write(f"Unhandled Exception: {exctype.__name__}: {value}\n")
        orig_hook(exctype, value, traceback)

    sys.excepthook = custom_hook


def main():
    setup_exception_hook()

    # Enable High DPI pixmaps
    app = QApplication(sys.argv)
    app.setApplicationName("Ramov PDF Studio")
    app.setOrganizationName("Ramov")

    # Set application & taskbar icon
    icon_path = Path(__file__).resolve().parent / "app_icon.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Clean default application font
    font = app.font()
    font.setFamily("Segoe UI" if os.name == "nt" else "Sans-Serif")
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    # If an argument is provided, attempt to load that PDF file
    if len(sys.argv) > 1:
        initial_file = sys.argv[1]
        if Path(initial_file).is_file():
            window.load_pdf(initial_file)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
