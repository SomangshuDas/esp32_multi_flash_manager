"""
theme.py
========
Dark and light QSS stylesheets. Kept as plain Python strings (rather than
separate .qss resource files loaded at runtime) so the app has zero
external-file dependencies for its own look-and-feel — it always renders
correctly even if resources/ is missing, which matters for a single-EXE
PyInstaller build.

Also duplicated as .qss files under resources/themes/ for reference /
easy tweaking by whoever maintains the app later.
"""

from __future__ import annotations

DARK_QSS = """
QWidget {
    background-color: #1e1f22;
    color: #e6e6e6;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #1e1f22; }
QToolBar {
    background-color: #26272b;
    border: none;
    padding: 4px;
    spacing: 6px;
}
QStatusBar { background-color: #26272b; }
QMenuBar { background-color: #26272b; }
QMenuBar::item:selected { background-color: #3a3c42; }
QMenu { background-color: #2a2b30; border: 1px solid #3a3c42; }
QMenu::item {
    padding: 6px 32px 6px 24px;
    min-width: 220px;
}
QMenu::item:selected { background-color: #3a6df0; }
QMenu::separator { height: 1px; background: #3a3c42; margin: 4px 8px; }

QGroupBox {
    border: 1px solid #3a3c42;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QPushButton {
    background-color: #34363c;
    border: 1px solid #45474e;
    border-radius: 5px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #3f4148; }
QPushButton:pressed { background-color: #2a2c31; }
QPushButton:disabled { color: #6b6d72; background-color: #2a2b2f; }
QPushButton#primaryButton { background-color: #3a6df0; border: 1px solid #3a6df0; color: white; font-weight: 600; }
QPushButton#primaryButton:hover { background-color: #4c7bf5; }
QPushButton#dangerButton { background-color: #b0362c; border: 1px solid #b0362c; color: white; }
QPushButton#dangerButton:hover { background-color: #c8433a; }

QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #26272b;
    border: 1px solid #3a3c42;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #3a6df0;
}
QComboBox QAbstractItemView { background-color: #26272b; selection-background-color: #3a6df0; }

/* Disabled state -- anything the user can't currently interact with (a
   greyed-out field belonging to "no device selected", a locked-out menu
   action, etc.) is visually muted here so it reads as inactive at a
   glance, distinct from every enabled control around it. */
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: #29292c;
    color: #6b6d72;
    border: 1px solid #303236;
}
QLabel:disabled { color: #5f6167; }
QCheckBox:disabled, QRadioButton:disabled { color: #5f6167; }
QMenuBar::item:disabled { color: #5f6167; }
QMenu::item:disabled { color: #5a5c62; }
QTabBar::tab:disabled { color: #5a5c62; }
QGroupBox:disabled { color: #5f6167; }
QToolBar QToolButton:disabled { color: #5f6167; }

QTableWidget, QTreeWidget, QListWidget {
    background-color: #202124;
    alternate-background-color: #24252a;
    gridline-color: #34363c;
    border: 1px solid #3a3c42;
    border-radius: 4px;
}
QHeaderView::section {
    background-color: #2a2b30;
    color: #cfd0d4;
    padding: 6px;
    border: none;
    border-right: 1px solid #34363c;
    font-weight: 600;
}
QTableWidget::item:selected { background-color: #2f4a8f; }

QTabWidget::pane { border: 1px solid #3a3c42; border-radius: 4px; }
QTabBar::tab {
    background-color: #26272b;
    padding: 8px 16px;
    border: 1px solid #3a3c42;
    border-bottom: none;
}
QTabBar::tab:selected { background-color: #2f4a8f; }

QProgressBar {
    background-color: #26272b;
    border: 1px solid #3a3c42;
    border-radius: 4px;
    text-align: center;
    color: #e6e6e6;
}
QProgressBar::chunk { background-color: #3a6df0; border-radius: 3px; }

QDockWidget { titlebar-close-icon: none; }
QDockWidget::title {
    background-color: #2a2b30;
    padding: 6px;
    font-weight: 600;
}
QSplitter::handle { background-color: #3a3c42; }
QScrollBar:vertical { background: #1e1f22; width: 12px; }
QScrollBar::handle:vertical { background: #45474e; border-radius: 5px; min-height: 24px; }
"""

LIGHT_QSS = """
QWidget {
    background-color: #f5f6f8;
    color: #202124;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #f5f6f8; }
QToolBar { background-color: #ffffff; border: none; padding: 4px; spacing: 6px; }
QStatusBar { background-color: #ffffff; }
QMenuBar { background-color: #ffffff; }
QMenuBar::item:selected { background-color: #e4e8f5; }
QMenu { background-color: #ffffff; border: 1px solid #d5d8dd; }
QMenu::item {
    padding: 6px 32px 6px 24px;
    min-width: 220px;
}
QMenu::item:selected { background-color: #3a6df0; color: white; }
QMenu::separator { height: 1px; background: #d5d8dd; margin: 4px 8px; }

QGroupBox {
    border: 1px solid #d5d8dd;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QPushButton {
    background-color: #ffffff;
    border: 1px solid #c7cbd1;
    border-radius: 5px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #eef1f7; }
QPushButton:pressed { background-color: #dfe3ea; }
QPushButton:disabled { color: #a2a6ad; background-color: #f0f1f3; }
QPushButton#primaryButton { background-color: #3a6df0; border: 1px solid #3a6df0; color: white; font-weight: 600; }
QPushButton#primaryButton:hover { background-color: #4c7bf5; }
QPushButton#dangerButton { background-color: #d9463b; border: 1px solid #d9463b; color: white; }
QPushButton#dangerButton:hover { background-color: #e2564b; }

QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #c7cbd1;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #3a6df0;
}
QComboBox QAbstractItemView { background-color: #ffffff; selection-background-color: #3a6df0; }

/* Disabled state -- see the matching comment in DARK_QSS. */
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: #eceef1;
    color: #a2a6ad;
    border: 1px solid #d5d8dd;
}
QLabel:disabled { color: #a2a6ad; }
QCheckBox:disabled, QRadioButton:disabled { color: #a2a6ad; }
QMenuBar::item:disabled { color: #a2a6ad; }
QMenu::item:disabled { color: #b0b4bb; }
QTabBar::tab:disabled { color: #b0b4bb; }
QGroupBox:disabled { color: #a2a6ad; }
QToolBar QToolButton:disabled { color: #a2a6ad; }

QTableWidget, QTreeWidget, QListWidget {
    background-color: #ffffff;
    alternate-background-color: #f5f6f8;
    gridline-color: #e2e4e8;
    border: 1px solid #d5d8dd;
    border-radius: 4px;
}
QHeaderView::section {
    background-color: #eef0f3;
    color: #45474e;
    padding: 6px;
    border: none;
    border-right: 1px solid #d5d8dd;
    font-weight: 600;
}
QTableWidget::item:selected { background-color: #cfe0ff; }

QTabWidget::pane { border: 1px solid #d5d8dd; border-radius: 4px; }
QTabBar::tab {
    background-color: #eef0f3;
    padding: 8px 16px;
    border: 1px solid #d5d8dd;
    border-bottom: none;
}
QTabBar::tab:selected { background-color: #cfe0ff; }

QProgressBar {
    background-color: #eef0f3;
    border: 1px solid #d5d8dd;
    border-radius: 4px;
    text-align: center;
    color: #202124;
}
QProgressBar::chunk { background-color: #3a6df0; border-radius: 3px; }

QDockWidget::title { background-color: #eef0f3; padding: 6px; font-weight: 600; }
QSplitter::handle { background-color: #d5d8dd; }
QScrollBar:vertical { background: #f5f6f8; width: 12px; }
QScrollBar::handle:vertical { background: #c7cbd1; border-radius: 5px; min-height: 24px; }
"""


def stylesheet_for(theme_name: str) -> str:
    return DARK_QSS if theme_name == "dark" else LIGHT_QSS
