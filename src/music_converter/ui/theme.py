"""Windows 11 inspired Chinese traditional color theme."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QWidget

from music_converter.config import resource_root

COLORS = {
    "paper": "#F4EFE4",
    "paper_light": "#FBF8F1",
    "ink_blue": "#173B57",
    "ink_blue_2": "#214D6B",
    "stone_blue": "#2D6A8A",
    "mist_blue": "#DDEAF0",
    "gold": "#E2B84E",
    "gold_dark": "#BE8E22",
    "gold_light": "#F4D98C",
    "cinnabar": "#B44A3A",
    "cinnabar_light": "#F5DCD6",
    "text": "#183044",
    "muted": "#6A7882",
    "line": "#D8D1C4",
    "white": "#FFFFFF",
    "success": "#2F7A5A",
}

_FONTS_LOADED = False
_BODY_FONT_FAMILY = "Segoe UI"
_DISPLAY_FONT_FAMILY = "Georgia"


def load_application_fonts() -> tuple[str, str]:
    """Register bundled Noto fonts and return the body and display families."""
    global _FONTS_LOADED, _BODY_FONT_FAMILY, _DISPLAY_FONT_FAMILY
    if _FONTS_LOADED:
        return _BODY_FONT_FAMILY, _DISPLAY_FONT_FAMILY

    font_dir = project_root() / "assets" / "fonts"
    registered: list[str] = []
    for filename in ("NotoSansSC-Variable.ttf", "NotoSerifSC-Variable.ttf"):
        path = font_dir / filename
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            registered.extend(QFontDatabase.applicationFontFamilies(font_id))

    families = list(dict.fromkeys(QFontDatabase.families() + registered))
    _BODY_FONT_FAMILY = next(
        (
            candidate
            for candidate in (
                "Noto Sans SC",
                "Microsoft YaHei UI",
                "Microsoft YaHei",
                "Noto Sans CJK SC",
                "Segoe UI",
            )
            if candidate in families
        ),
        QApplication.font().family(),
    )
    _DISPLAY_FONT_FAMILY = next(
        (
            candidate
            for candidate in (
                "Noto Serif SC",
                "Source Han Serif SC",
                "SimSun",
                _BODY_FONT_FAMILY,
            )
            if candidate in families
        ),
        _BODY_FONT_FAMILY,
    )
    _FONTS_LOADED = True
    return _BODY_FONT_FAMILY, _DISPLAY_FONT_FAMILY


def preferred_font_family() -> str:
    """Return the best installed Chinese UI font."""
    body_family, _ = load_application_fonts()
    families = set(QFontDatabase.families())
    for candidate in (body_family, "Noto Sans SC", "Microsoft YaHei UI", "Segoe UI"):
        if candidate in families:
            return candidate
    return QApplication.font().family()


def apply_theme(app: QApplication) -> None:
    """Apply the Fusion base style, font, and global stylesheet."""
    app.setStyle("Fusion")
    body_family, display_family = load_application_fonts()
    font = QFont(body_family, 10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)
    app.setStyleSheet(
        f"""
        QWidget {{
            color: {COLORS["text"]};
            font-family: "{body_family}";
            font-size: 14px;
        }}
        QMainWindow, QWidget#AppRoot {{
            background: {COLORS["paper"]};
        }}
        QFrame#Sidebar {{
            background: {COLORS["ink_blue"]};
            border: none;
            border-radius: 0;
        }}
        QLabel#BrandTitle {{
            color: #FFFFFF;
            font-family: "{display_family}";
            font-size: 23px;
            font-weight: 700;
            letter-spacing: 2px;
        }}
        QLabel#BrandSubtitle {{
            color: #B8CEDB;
            font-size: 11px;
        }}
        QPushButton#NavButton {{
            color: #C9D9E2;
            text-align: left;
            padding: 12px 16px;
            border: none;
            border-radius: 10px;
            font-size: 14px;
            background: transparent;
        }}
        QPushButton#NavButton:hover {{
            color: #FFFFFF;
            background: rgba(255, 255, 255, 0.07);
        }}
        QPushButton#NavButton:checked {{
            color: {COLORS["ink_blue"]};
            background: {COLORS["gold"]};
            font-weight: 700;
        }}
        QLabel#PageTitle {{
            color: {COLORS["ink_blue"]};
            font-family: "{display_family}";
            font-size: 28px;
            font-weight: 700;
        }}
        QLabel#PageSubtitle {{
            color: {COLORS["muted"]};
            font-size: 13px;
        }}
        QLabel#SectionTitle {{
            color: {COLORS["ink_blue"]};
            font-family: "{display_family}";
            font-size: 16px;
            font-weight: 700;
        }}
        QLabel#FieldLabel {{
            color: {COLORS["muted"]};
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#HintLabel {{
            color: {COLORS["muted"]};
            font-size: 11px;
        }}
        QLabel#AccentLabel {{
            color: {COLORS["gold_dark"]};
            font-weight: 700;
        }}
        QFrame#Card {{
            background: {COLORS["paper_light"]};
            border: 1px solid {COLORS["line"]};
            border-radius: 14px;
        }}
        QFrame#SoftCard {{
            background: rgba(255, 255, 255, 0.55);
            border: 1px solid {COLORS["line"]};
            border-radius: 12px;
        }}
        QFrame#DropZone {{
            background: {COLORS["mist_blue"]};
            border: 2px dashed #8CB0C3;
            border-radius: 16px;
        }}
        QFrame#DropZone[dragActive="true"] {{
            background: #CFE3EB;
            border-color: {COLORS["stone_blue"]};
        }}
        QLabel#DropTitle {{
            color: {COLORS["ink_blue"]};
            font-family: "{display_family}";
            font-size: 18px;
            font-weight: 700;
        }}
        QLabel#DropHint {{
            color: {COLORS["stone_blue"]};
            font-size: 12px;
        }}
        QPushButton {{
            border: 1px solid {COLORS["line"]};
            border-radius: 9px;
            padding: 8px 14px;
            background: {COLORS["paper_light"]};
            color: {COLORS["text"]};
        }}
        QPushButton:hover {{
            border-color: #B6AA97;
            background: #FFFFFF;
        }}
        QPushButton:pressed {{
            background: #ECE5D8;
        }}
        QPushButton:disabled {{
            color: #9DA6AA;
            background: #EEEAE2;
            border-color: #DDD7CC;
        }}
        QPushButton#PrimaryButton {{
            color: {COLORS["ink_blue"]};
            background: {COLORS["gold"]};
            border: 1px solid {COLORS["gold_dark"]};
            border-radius: 11px;
            padding: 11px 24px;
            font-size: 15px;
            font-weight: 700;
        }}
        QPushButton#PrimaryButton:hover {{
            background: #EDC962;
        }}
        QPushButton#PrimaryButton:pressed {{
            background: #C99C30;
        }}
        QPushButton#DangerButton {{
            color: {COLORS["cinnabar"]};
            background: {COLORS["cinnabar_light"]};
            border-color: #DEB3A9;
        }}
        QPushButton#GhostButton {{
            background: transparent;
            border-color: {COLORS["line"]};
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background: #FFFFFF;
            border: 1px solid {COLORS["line"]};
            border-radius: 9px;
            padding: 8px 10px;
            selection-background-color: {COLORS["stone_blue"]};
            min-height: 20px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {COLORS["stone_blue"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 28px;
        }}
        QComboBox QAbstractItemView {{
            background: #FFFFFF;
            border: 1px solid {COLORS["line"]};
            selection-background-color: {COLORS["mist_blue"]};
            selection-color: {COLORS["ink_blue"]};
            outline: none;
        }}
        QCheckBox {{
            spacing: 8px;
            color: {COLORS["text"]};
        }}
        QCheckBox::indicator {{
            width: 17px;
            height: 17px;
            border-radius: 5px;
            border: 1px solid #A99F8E;
            background: #FFFFFF;
        }}
        QCheckBox::indicator:checked {{
            background: {COLORS["stone_blue"]};
            border-color: {COLORS["stone_blue"]};
        }}
        QCheckBox::indicator:hover {{
            border-color: {COLORS["stone_blue"]};
        }}
        QTableWidget {{
            background: transparent;
            border: none;
            gridline-color: transparent;
            outline: none;
        }}
        QTableWidget::item {{
            padding: 8px;
            border-bottom: 1px solid #E9E3D8;
        }}
        QTableWidget::item:selected {{
            background: {COLORS["mist_blue"]};
            color: {COLORS["ink_blue"]};
        }}
        QHeaderView::section {{
            background: transparent;
            color: {COLORS["muted"]};
            font-size: 12px;
            font-weight: 600;
            border: none;
            border-bottom: 1px solid {COLORS["line"]};
            padding: 8px;
        }}
        QProgressBar {{
            background: #E6E0D5;
            border: none;
            border-radius: 4px;
            height: 8px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background: {COLORS["gold"]};
            border-radius: 4px;
        }}
        QScrollBar:vertical {{
            width: 10px;
            background: transparent;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: #C7BFAF;
            min-height: 30px;
            border-radius: 5px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QTextBrowser, QTextEdit {{
            background: #FFFFFF;
            border: 1px solid {COLORS["line"]};
            border-radius: 10px;
            padding: 10px;
        }}
        QStatusBar {{
            background: transparent;
            color: {COLORS["muted"]};
        }}
        QToolTip {{
            background: {COLORS["ink_blue"]};
            color: #FFFFFF;
            border: none;
            padding: 6px;
        }}
        QMessageBox {{
            background: {COLORS["paper_light"]};
        }}
        """
    )


def enable_mica(window: QWidget) -> bool:
    """Try to enable Windows 11 Mica while keeping a styled fallback."""
    if os.name != "nt":
        return False
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(2)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            38,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return result == 0
    except Exception:
        return False


def make_app_icon() -> QIcon:
    """Draw a small Chinese-palette application icon."""
    size = 128
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor(COLORS["ink_blue"]))
    gradient.setColorAt(1, QColor(COLORS["stone_blue"]))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(4, 4, 120, 120), 28, 28)
    painter.setBrush(QColor(COLORS["gold"]))
    painter.drawEllipse(QRectF(25, 25, 78, 78))
    painter.setPen(QPen(QColor(COLORS["ink_blue"]), 4, Qt.SolidLine, Qt.RoundCap))
    painter.drawArc(QRectF(40, 34, 48, 52), 20 * 16, 300 * 16)
    painter.drawLine(72, 55, 72, 91)
    painter.drawLine(72, 91, 84, 81)
    painter.end()
    return QIcon(pixmap)


def project_root() -> Path:
    """Return the source or PyInstaller resource root."""
    return resource_root()

