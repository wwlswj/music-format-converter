"""Reusable PySide6 widgets for the converter interface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class DropZone(QFrame):
    """Drag-and-drop target that accepts audio files and directories."""

    paths_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the drop zone UI."""
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self.setMinimumHeight(124)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 17, 22, 17)
        layout.setSpacing(18)

        self.mark = QLabel("音")
        self.mark.setAlignment(Qt.AlignCenter)
        self.mark.setFixedSize(58, 58)
        self.mark.setStyleSheet(
            "background: #173B57; color: #E2B84E; border-radius: 17px;"
            "font-size: 25px; font-weight: 700;"
        )
        layout.addWidget(self.mark)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        title = QLabel("拖入音乐文件或整个文件夹")
        title.setObjectName("DropTitle")
        hint = QLabel("支持 NCM 及常见无损、有损音乐格式")
        hint.setObjectName("DropHint")
        text_layout.addWidget(title)
        text_layout.addWidget(hint)
        layout.addLayout(text_layout, 1)

        self.browse_button = QPushButton("选择文件")
        self.browse_button.setObjectName("PrimaryButton")
        self.browse_button.clicked.connect(self.browse_requested)
        layout.addWidget(self.browse_button)

    def _set_active(self, active: bool) -> None:
        """Update the drag-active pseudo state."""
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept file and directory drags."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)
        else:
            super().dragEnterEvent(event)

    def dragLeaveEvent(self, event) -> None:
        """Clear the visual drag state."""
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Emit local paths after a drop."""
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        self._set_active(False)
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()


class SectionCard(QFrame):
    """Rounded card with an optional title row."""

    def __init__(
        self,
        title: str | None = None,
        *,
        soft: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Create a card and expose its body layout."""
        super().__init__(parent)
        self.setObjectName("SoftCard" if soft else "Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)
        self.title_label: QLabel | None = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("SectionTitle")
            outer.addWidget(self.title_label)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)


class StatBadge(QWidget):
    """Compact number-and-caption status badge."""

    def __init__(self, caption: str, value: str = "0", parent: QWidget | None = None) -> None:
        """Create the badge."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #173B57;")
        caption_label = QLabel(caption)
        caption_label.setObjectName("HintLabel")
        layout.addWidget(self.value_label)
        layout.addWidget(caption_label)

    def set_value(self, value: str) -> None:
        """Update the displayed statistic."""
        self.value_label.setText(value)


class EmptyState(QWidget):
    """Centered empty-state placeholder."""

    def __init__(
        self,
        title: str,
        detail: str,
        *,
        seal_text: str = "词",
        parent: QWidget | None = None,
    ) -> None:
        """Create the placeholder."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        seal = QLabel(seal_text)
        seal.setAlignment(Qt.AlignCenter)
        seal.setFixedSize(58, 58)
        seal.setStyleSheet(
            "background: #DDEAF0; color: #2D6A8A; border-radius: 16px;"
            "font-size: 23px; font-weight: 700;"
        )
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        title_label.setAlignment(Qt.AlignCenter)
        detail_label = QLabel(detail)
        detail_label.setObjectName("HintLabel")
        detail_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(seal, alignment=Qt.AlignCenter)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)


def path_cover_pixmap(path: Path, size: int = 40) -> QPixmap | None:
    """Load a cover image if the path points to a readable image."""
    if not path.is_file():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

