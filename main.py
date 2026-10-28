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


def setup_windows_app_id() -> None:
    """
    Explicitly assign a unique Application User Model ID (AppUserModelID) on Windows.
    This informs the Windows Shell and taskbar manager to treat this process as an
    independent application rather than a generic host, ensuring the taskbar button
    and Alt+Tab switcher display the application icon.
    Must be called BEFORE QApplication is instantiated.
    """
    if sys.platform == "win32":
        import ctypes
        app_id = "ramov.pdfstudio.app.1.0"
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not set AppUserModelID: {e}\n")


def get_resource_path(relative_name: str) -> Path:
    """
    Get absolute path to resource, compatible with PyInstaller bundles and dev mode.
    PyInstaller extracts bundled files to sys._MEIPASS when running in onefile mode.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir / relative_name


def load_app_icon() -> QIcon:
    """
    Loads the application icon combining both .ico (multi-resolution 16-256px)
    and .png (high-DPI 1024px) for crisp display in titlebar, taskbar, and Alt+Tab.
    """
    icon = QIcon()
    ico_path = get_resource_path("app_icon.ico")
    if ico_path.is_file():
        icon.addFile(str(ico_path))
    png_path = get_resource_path("app_icon.png")
    if png_path.is_file():
        icon.addFile(str(png_path))
    return icon


def main():
    setup_exception_hook()
    setup_windows_app_id()

    # Enable High DPI pixmaps
    app = QApplication(sys.argv)
    app.setApplicationName("Ramov PDF Studio")
    app.setOrganizationName("Ramov")

    # Set application & taskbar icon
    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # Clean default application font
    font = app.font()
    font.setFamily("Segoe UI" if os.name == "nt" else "Sans-Serif")
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()

    # Close the PyInstaller bootloader splash screen once MainWindow is visible
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass

    # If an argument is provided, attempt to load that PDF file
    if len(sys.argv) > 1:
        initial_file = sys.argv[1]
        if Path(initial_file).is_file():
            window.load_pdf(initial_file)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
