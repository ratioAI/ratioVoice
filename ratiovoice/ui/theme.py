"""Dunkles Studio-Theme."""

BG = "#14161b"
PANEL = "#1b1e25"
CARD = "#232731"
BORDER = "#2f3441"
TEXT = "#e6e8ee"
MUTED = "#8b93a5"
ACCENT = "#4fd1c5"
ACCENT_DIM = "#2c7a73"
ORIGINAL = "#7f8aa3"
RECORD = "#f0506e"

STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#panel {{ background: {PANEL}; }}
QWidget#transport {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLabel#title {{ font-size: 17px; font-weight: 600; }}
QLabel#section {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#muted, QLabel#value {{ color: {MUTED}; }}
QLabel#cardTitle {{ font-weight: 600; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT_DIM}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #555c6b; }}
QPushButton#primary {{ background: {ACCENT}; color: #0b1413; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #6fe0d5; }}
QPushButton#record:checked {{ background: {RECORD}; border-color: {RECORD}; color: white; }}
QPushButton#transportBtn {{ font-size: 15px; min-width: 44px; padding: 8px 12px; }}
QPushButton#mini {{ padding: 1px 6px; min-width: 14px; border-radius: 4px; color: {MUTED}; }}

QTreeWidget {{ background: transparent; border: none; outline: none; }}
QTreeWidget::item {{ padding: 5px 4px; border-radius: 5px; }}
QTreeWidget::item:hover {{ background: {CARD}; }}
QTreeWidget::item:selected {{ background: {ACCENT_DIM}; color: white; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}

QComboBox, QLineEdit, QSpinBox {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 5px; padding: 4px 8px; }}
QComboBox QAbstractItemView {{ background: {CARD}; selection-background-color: {ACCENT_DIM}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {BORDER}; border-radius: 4px; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}
"""
