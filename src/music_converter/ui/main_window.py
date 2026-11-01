"""Main PySide6 window for batch audio and NCM conversion."""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from music_converter import __version__
from music_converter.lyrics import candidate_summary
from music_converter.media.ffmpeg import (
    FORMAT_LABELS,
    LOSSY_FORMATS,
    FFmpeg,
)
from music_converter.models import (
    ConversionOptions,
    ConversionResult,
    JobStatus,
    LyricsStatus,
    OverwritePolicy,
)
from music_converter.pipeline import ConversionEngine, collect_audio_files
from music_converter.ui.theme import COLORS, apply_theme, enable_mica, make_app_icon
from music_converter.ui.widgets import DropZone, EmptyState, SectionCard, StatBadge

STATUS_LABELS = {
    JobStatus.PENDING: "等待",
    JobStatus.RUNNING: "转换中",
    JobStatus.SUCCESS: "已完成",
    JobStatus.FAILED: "失败",
    JobStatus.CANCELLED: "已取消",
    JobStatus.SKIPPED: "已跳过",
}

LYRICS_LABELS = {
    LyricsStatus.NOT_REQUESTED: "未开启",
    LyricsStatus.EMBEDDED: "内嵌歌词",
    LyricsStatus.LOCAL_FILE: "本地 LRC",
    LyricsStatus.ONLINE: "联网歌词",
    LyricsStatus.INSTRUMENTAL: "纯音乐",
    LyricsStatus.PENDING: "待确认",
    LyricsStatus.NOT_FOUND: "未找到",
    LyricsStatus.ERROR: "查询失败",
}


@dataclass(slots=True)
class QueueEntry:
    """UI state for one queued source."""

    source: Path
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    result: ConversionResult | None = None


class TaskSignals(QObject):
    """Thread-safe signals emitted by a conversion task."""

    progress = Signal(int, int)
    finished = Signal(int, object)


class ConversionTask(QRunnable):
    """Run one conversion on the Qt thread pool."""

    def __init__(self, row_id: int, source: Path, options: ConversionOptions) -> None:
        """Store task parameters."""
        super().__init__()
        self.row_id = row_id
        self.source = source
        self.options = options
        self.cancel_event = threading.Event()
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        """Execute the conversion and emit progress/finish signals."""
        last_percent = -1

        def progress(value: float) -> None:
            nonlocal last_percent
            percent = int(max(0.0, min(value, 1.0)) * 100)
            if percent != last_percent:
                last_percent = percent
                self.signals.progress.emit(self.row_id, percent)

        try:
            engine = ConversionEngine(self.options)
            result = engine.convert(
                self.source,
                progress_callback=progress,
                cancel_event=self.cancel_event,
            )
        except Exception as exc:
            result = ConversionResult(
                source=self.source,
                status=JobStatus.FAILED,
                message=f"任务异常：{exc}",
            )
        self.signals.finished.emit(self.row_id, result)


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(
        self,
        *,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Create the main window and its models."""
        super().__init__(parent)
        self.settings = settings or QSettings("CodexProjects", "MusicFormatConverter")
        self.queue_entries: list[QueueEntry] = []
        self.progress_bars: dict[int, QProgressBar] = {}
        self.active_tasks: dict[int, ConversionTask] = {}
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(2)
        self._mica_enabled = False

        self.setWindowTitle("韶律 · 音乐格式转换器")
        self.setWindowIcon(make_app_icon())
        self.resize(1280, 820)
        self.setMinimumSize(1080, 700)
        self._build_ui()
        self._load_settings()
        self._refresh_summary()
        self._append_log("应用已启动。拖入音乐文件即可开始。")
        QTimer.singleShot(150, self._initial_environment_check)

    def showEvent(self, event) -> None:
        """Enable Mica once the native window handle exists."""
        super().showEvent(event)
        if not self._mica_enabled:
            self._mica_enabled = enable_mica(self)

    def _build_ui(self) -> None:
        """Construct the complete interface."""
        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._build_conversion_page())
        self.page_stack.addWidget(self._build_lyrics_page())
        self.page_stack.addWidget(self._build_history_page())
        self.page_stack.addWidget(self._build_settings_page())
        root_layout.addWidget(self.page_stack, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")

    def _build_sidebar(self) -> QWidget:
        """Build the deep-blue navigation rail."""
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(218)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 26, 18, 20)
        layout.setSpacing(9)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        seal = QLabel("韶")
        seal.setAlignment(Qt.AlignCenter)
        seal.setFixedSize(46, 46)
        seal.setStyleSheet(
            f"background: {COLORS['gold']}; color: {COLORS['ink_blue']};"
            "border-radius: 13px; font-size: 23px; font-weight: 800;"
        )
        brand_row.addWidget(seal)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("韶律")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("MUSIC WORKSHOP")
        subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_row.addLayout(brand_text)
        layout.addLayout(brand_row)
        layout.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_specs = [
            ("转   转换队列", 0),
            ("词   歌词待确认", 1),
            ("录   转换记录", 2),
            ("设   环境与设置", 3),
        ]
        self.nav_buttons: list[QPushButton] = []
        for text, index in nav_specs:
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda checked=False, i=index: self._show_page(i))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)

        privacy = QLabel("本地转换 · 不上传音频\n仅歌词查询发送歌曲元数据")
        privacy.setWordWrap(True)
        privacy.setStyleSheet("color: #9FB7C5; font-size: 11px; line-height: 1.5;")
        layout.addWidget(privacy)
        version = QLabel(f"v{__version__}")
        version.setStyleSheet("color: #7898A9; font-size: 10px;")
        layout.addWidget(version)
        return sidebar

    def _show_page(self, index: int) -> None:
        """Switch the main content page."""
        self.page_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    @staticmethod
    def _page_header(title_text: str, subtitle_text: str) -> tuple[QWidget, QVBoxLayout]:
        """Create a standard page header."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        title = QLabel(title_text)
        title.setObjectName("PageTitle")
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return widget, layout

    def _build_conversion_page(self) -> QWidget:
        """Build the primary queue page."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(28, 24, 28, 20)
        page_layout.setSpacing(15)

        header_row = QHBoxLayout()
        header, _ = self._page_header("批量转换", "让每一种声音，都有合适的归处")
        header_row.addWidget(header, 1)
        self.tool_pill = QLabel("正在检测音频工具…")
        self.tool_pill.setStyleSheet(
            f"background: {COLORS['mist_blue']}; color: {COLORS['stone_blue']};"
            "border-radius: 12px; padding: 7px 12px; font-size: 11px; font-weight: 600;"
        )
        header_row.addWidget(self.tool_pill, alignment=Qt.AlignTop)
        page_layout.addLayout(header_row)

        self.drop_zone = DropZone()
        self.drop_zone.paths_dropped.connect(self._add_paths)
        self.drop_zone.browse_requested.connect(self._choose_files)
        page_layout.addWidget(self.drop_zone)

        workspace = QHBoxLayout()
        workspace.setSpacing(15)
        workspace.addWidget(self._build_queue_card(), 1)
        workspace.addWidget(self._build_settings_card())
        page_layout.addLayout(workspace, 1)
        return page

    def _build_queue_card(self) -> QWidget:
        """Build the queue table and action bar."""
        card = SectionCard()
        toolbar = QHBoxLayout()
        title = QLabel("转换队列")
        title.setObjectName("SectionTitle")
        self.queue_count = QLabel("0 首")
        self.queue_count.setObjectName("HintLabel")
        toolbar.addWidget(title)
        toolbar.addWidget(self.queue_count)
        toolbar.addStretch(1)
        self.add_file_button = QPushButton("添加文件")
        self.add_file_button.setObjectName("GhostButton")
        self.add_file_button.clicked.connect(self._choose_files)
        self.add_folder_button = QPushButton("添加文件夹")
        self.add_folder_button.setObjectName("GhostButton")
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.remove_button = QPushButton("移除选中")
        self.remove_button.setObjectName("GhostButton")
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("GhostButton")
        self.clear_button.clicked.connect(self._clear_queue)
        for button in (
            self.add_file_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
        ):
            toolbar.addWidget(button)
        card.body.addLayout(toolbar)

        self.queue_stack = QStackedWidget()
        self.queue_empty = EmptyState(
            "队列还是空的",
            "将音乐文件或整个文件夹拖入上方区域",
            seal_text="音",
        )
        self.queue_stack.addWidget(self.queue_empty)
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(["源文件", "歌曲信息", "歌词", "状态", "进度"])
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setShowGrid(False)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.queue_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.queue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(False)
        self.queue_table.setWordWrap(True)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(4, 118)
        self.queue_table.setMinimumHeight(320)
        self.queue_stack.addWidget(self.queue_table)
        card.body.addWidget(self.queue_stack, 1)

        stats_row = QHBoxLayout()
        self.total_badge = StatBadge("总任务")
        self.success_badge = StatBadge("已处理")
        self.pending_badge = StatBadge("待处理")
        for widget in (self.total_badge, self.success_badge, self.pending_badge):
            stats_row.addWidget(widget, 1)
        card.body.addLayout(stats_row)

        action_row = QHBoxLayout()
        self.summary_label = QLabel("选择输出目录后即可开始")
        self.summary_label.setObjectName("HintLabel")
        action_row.addWidget(self.summary_label, 1)
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setObjectName("GhostButton")
        self.open_output_button.clicked.connect(self._open_output_dir)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("DangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_batch)
        self.start_button = QPushButton("开始转换")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self._start_batch)
        action_row.addWidget(self.open_output_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.start_button)
        card.body.addLayout(action_row)
        return card

    def _build_settings_card(self) -> QWidget:
        """Build the right-side conversion settings panel."""
        outer = QFrame()
        outer.setObjectName("Card")
        outer.setFixedWidth(348)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("转换设置")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        layout.addWidget(self._field_label("输出目录"))
        output_row = QHBoxLayout()
        output_row.setSpacing(6)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("请选择输出文件夹")
        self.output_browse_button = QPushButton("浏览")
        self.output_browse_button.setObjectName("GhostButton")
        self.output_browse_button.clicked.connect(self._choose_output_dir)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_browse_button)
        layout.addLayout(output_row)

        format_row = QHBoxLayout()
        format_column = QVBoxLayout()
        format_column.addWidget(self._field_label("目标格式"))
        self.format_combo = QComboBox()
        for key, label in FORMAT_LABELS.items():
            self.format_combo.addItem(label, key)
        format_column.addWidget(self.format_combo)
        bitrate_column = QVBoxLayout()
        bitrate_column.addWidget(self._field_label("比特率"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.setEditable(True)
        self.bitrate_combo.addItems(["128 kbps", "192 kbps", "256 kbps", "320 kbps"])
        self.bitrate_combo.setCurrentText("320 kbps")
        bitrate_column.addWidget(self.bitrate_combo)
        format_row.addLayout(format_column, 3)
        format_row.addLayout(bitrate_column, 2)
        layout.addLayout(format_row)
        self.bitrate_hint = QLabel("默认 320 kbps；无损格式不设置码率。")
        self.bitrate_hint.setObjectName("HintLabel")
        self.bitrate_hint.setWordWrap(True)
        layout.addWidget(self.bitrate_hint)

        layout.addSpacing(5)
        layout.addWidget(self._field_label("文件夹分类"))
        group_row = QHBoxLayout()
        group_row.setSpacing(12)
        self.artist_check = QCheckBox("歌手")
        self.genre_check = QCheckBox("风格")
        self.album_check = QCheckBox("专辑")
        group_row.addWidget(self.artist_check)
        group_row.addWidget(self.genre_check)
        group_row.addWidget(self.album_check)
        group_row.addStretch(1)
        layout.addLayout(group_row)
        self.group_hint = QLabel("默认不分类，全部输出到指定目录")
        self.group_hint.setObjectName("HintLabel")
        layout.addWidget(self.group_hint)

        layout.addSpacing(5)
        self.rename_check = QCheckBox("按模板重命名")
        self.rename_check.setChecked(True)
        self.rename_check.toggled.connect(self._rename_toggled)
        layout.addWidget(self.rename_check)
        self.name_template_edit = QLineEdit("{artist} - {title}")
        self.name_template_edit.setPlaceholderText("{artist} - {title}")
        self.name_template_edit.setToolTip("支持 {artist}、{title}、{album}、{genre}")
        layout.addWidget(self.name_template_edit)

        layout.addSpacing(5)
        self.lyrics_check = QCheckBox("自动匹配歌词")
        self.lyrics_check.setChecked(True)
        self.unsynced_check = QCheckBox("允许无时间轴歌词")
        layout.addWidget(self.lyrics_check)
        layout.addWidget(self.unsynced_check)

        layout.addSpacing(5)
        overwrite_worker = QHBoxLayout()
        overwrite_col = QVBoxLayout()
        overwrite_col.addWidget(self._field_label("同名文件"))
        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItem("自动编号", OverwritePolicy.RENAME.value)
        self.overwrite_combo.addItem("覆盖", OverwritePolicy.REPLACE.value)
        self.overwrite_combo.addItem("跳过", OverwritePolicy.SKIP.value)
        overwrite_col.addWidget(self.overwrite_combo)
        worker_col = QVBoxLayout()
        worker_col.addWidget(self._field_label("并发数"))
        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(1, 8)
        self.worker_spin.setValue(2)
        worker_col.addWidget(self.worker_spin)
        overwrite_worker.addLayout(overwrite_col, 3)
        overwrite_worker.addLayout(worker_col, 2)
        layout.addLayout(overwrite_worker)

        note = QLabel("音频转码在后台执行，可随时取消。歌词查询只发送歌曲元数据。")
        note.setObjectName("HintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        self._format_changed()
        return outer

    @staticmethod
    def _field_label(text: str) -> QLabel:
        """Create a compact form label."""
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _build_lyrics_page(self) -> QWidget:
        """Build a page that lists low-confidence lyric candidates."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(15)
        header, _ = self._page_header("歌词待确认", "低置信度结果不会自动写入，双击可查看候选")
        layout.addWidget(header)
        card = SectionCard()
        self.lyrics_stack = QStackedWidget()
        self.lyrics_empty = EmptyState(
            "暂无待确认歌词",
            "转换后，未能可靠匹配的歌曲会集中显示在这里",
        )
        self.lyrics_stack.addWidget(self.lyrics_empty)
        self.pending_table = QTableWidget(0, 5)
        self.pending_table.setHorizontalHeaderLabels(["源文件", "歌曲", "来源", "置信度", "原因"])
        self.pending_table.verticalHeader().setVisible(False)
        self.pending_table.setShowGrid(False)
        self.pending_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pending_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pending_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            self.pending_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeToContents,
            )
        self.pending_table.cellDoubleClicked.connect(self._show_pending_detail)
        self.lyrics_stack.addWidget(self.pending_table)
        card.body.addWidget(self.lyrics_stack)
        layout.addWidget(card, 1)
        return page

    def _build_history_page(self) -> QWidget:
        """Build the conversion log page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(15)
        header = QHBoxLayout()
        title_widget, _ = self._page_header("转换记录", "查看本次会话中的转换、歌词与警告信息")
        header.addWidget(title_widget, 1)
        clear = QPushButton("清空记录")
        clear.setObjectName("GhostButton")
        clear.clicked.connect(lambda: self.log_browser.clear())
        header.addWidget(clear, alignment=Qt.AlignTop)
        layout.addLayout(header)
        self.log_browser = QTextBrowser()
        self.log_browser.setOpenExternalLinks(True)
        layout.addWidget(self.log_browser, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        """Build environment, privacy, and about content."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(15)
        header, _ = self._page_header("环境与设置", "检查本地工具、查看数据边界和项目信息")
        layout.addWidget(header)

        env_card = SectionCard("运行环境")
        self.environment_label = QLabel("正在检查…")
        self.environment_label.setWordWrap(True)
        self.environment_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        env_card.body.addWidget(self.environment_label)
        check_button = QPushButton("重新检查")
        check_button.setObjectName("GhostButton")
        check_button.clicked.connect(self._check_environment)
        env_card.body.addWidget(check_button, alignment=Qt.AlignLeft)
        layout.addWidget(env_card)

        privacy_card = SectionCard("数据与隐私")
        privacy_text = QLabel(
            "音频与 NCM 解密全部在本机完成，不会上传音频。"
            "当需要自动歌词时，仅将歌曲名、歌手、专辑和时长发送到 LRCLIB；"
            "可在转换设置中关闭歌词匹配。"
        )
        privacy_text.setWordWrap(True)
        privacy_text.setObjectName("HintLabel")
        privacy_card.body.addWidget(privacy_text)
        layout.addWidget(privacy_card)

        about_card = SectionCard("关于韶律")
        about = QLabel(
            f"Music Format Converter v{__version__}\n"
            "PySide6 · FFmpeg · Monkey’s Audio · Mutagen · LRCLIB\n\n"
            "NCM 仅处理用户合法取得的本地文件；本软件不提供音乐下载或内容分享能力。"
        )
        about.setWordWrap(True)
        about.setObjectName("HintLabel")
        about_card.body.addWidget(about)
        layout.addWidget(about_card)
        layout.addStretch(1)
        return page

    def _choose_files(self) -> None:
        """Select one or more source audio files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音乐文件",
            str(Path.home()),
            "音乐文件 (*.ncm *.mp3 *.flac *.wav *.ape *.m4a *.aac "
            "*.ogg *.opus *.wma *.aiff *.aif *.alac);;所有文件 (*)",
        )
        if files:
            self._add_paths([Path(path) for path in files])

    def _choose_folder(self) -> None:
        """Select a source folder."""
        folder = QFileDialog.getExistingDirectory(self, "选择音乐文件夹", str(Path.home()))
        if folder:
            self._add_paths([Path(folder)])

    def _choose_output_dir(self) -> None:
        """Select the output root directory."""
        initial = self.output_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录", initial)
        if folder:
            self.output_edit.setText(folder)

    def _add_paths(self, paths: list[Path]) -> None:
        """Expand dropped paths and append new files to the queue."""
        files = collect_audio_files(paths, recursive=True)
        existing = {entry.source for entry in self.queue_entries}
        added = 0
        for path in files:
            if path in existing:
                continue
            self.queue_entries.append(QueueEntry(path))
            existing.add(path)
            added += 1
        if not added:
            if files:
                self.statusBar().showMessage("这些文件已在队列中。", 3500)
            else:
                self.statusBar().showMessage("没有发现受支持的音频文件。", 4500)
            return
        self._rebuild_queue_table()
        self._append_log(f"已添加 {added} 个文件。")
        self.statusBar().showMessage(f"已添加 {added} 个文件", 3500)

    def _rebuild_queue_table(self) -> None:
        """Rebuild the queue table from model state."""
        self.queue_table.setRowCount(len(self.queue_entries))
        self.queue_stack.setCurrentIndex(1 if self.queue_entries else 0)
        self.progress_bars.clear()
        for row, entry in enumerate(self.queue_entries):
            self.queue_table.setRowHeight(row, 54)
            file_item = QTableWidgetItem(entry.source.name)
            file_item.setToolTip(str(entry.source))
            file_item.setData(Qt.UserRole, str(entry.source))
            self.queue_table.setItem(row, 0, file_item)

            song_item = QTableWidgetItem("待识别")
            song_item.setToolTip("转换完成后会显示规范化后的歌曲信息")
            self.queue_table.setItem(row, 1, song_item)

            lyrics_item = QTableWidgetItem(self._lyrics_text(entry.result))
            self.queue_table.setItem(row, 2, lyrics_item)
            status_item = QTableWidgetItem(STATUS_LABELS[entry.status])
            self._color_status_item(status_item, entry.status)
            self.queue_table.setItem(row, 3, status_item)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(entry.progress)
            progress.setFixedHeight(8)
            progress.setTextVisible(False)
            self.progress_bars[row] = progress
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(8, 0, 8, 0)
            cell_layout.addWidget(progress)
            self.queue_table.setCellWidget(row, 4, cell)
        self._refresh_summary()

    @staticmethod
    def _lyrics_text(result: ConversionResult | None) -> str:
        """Return a short lyric status label."""
        if not result or not result.lyrics:
            return "待处理"
        return LYRICS_LABELS.get(result.lyrics.status, result.lyrics.status.value)

    @staticmethod
    def _color_status_item(item: QTableWidgetItem, status: JobStatus) -> None:
        """Apply semantic status colors to a table item."""
        colors = {
            JobStatus.SUCCESS: COLORS["success"],
            JobStatus.FAILED: COLORS["cinnabar"],
            JobStatus.RUNNING: COLORS["stone_blue"],
            JobStatus.SKIPPED: COLORS["muted"],
            JobStatus.CANCELLED: COLORS["muted"],
            JobStatus.PENDING: COLORS["text"],
        }
        item.setForeground(QBrush(QColor(colors[status])))

    def _remove_selected(self) -> None:
        """Remove selected non-running rows."""
        if self.active_tasks:
            self.statusBar().showMessage("转换进行中，暂时不能移除文件。", 3500)
            return
        rows = sorted({index.row() for index in self.queue_table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.queue_entries):
                self.queue_entries.pop(row)
        if rows:
            self._rebuild_queue_table()

    def _clear_queue(self) -> None:
        """Clear the queue when idle."""
        if self.active_tasks:
            self.statusBar().showMessage("请先取消当前转换。", 3500)
            return
        self.queue_entries.clear()
        self._rebuild_queue_table()

    def _format_changed(self) -> None:
        """Update bitrate enablement and helper text."""
        output_format = self.format_combo.currentData()
        lossy = output_format in LOSSY_FORMATS
        self.bitrate_combo.setEnabled(lossy)
        if lossy:
            self.bitrate_hint.setText("默认 320 kbps，适用于有损输出格式。")
        else:
            self.bitrate_hint.setText("该格式为无损/无压缩输出，比特率设置已自动禁用。")

    def _rename_toggled(self, checked: bool) -> None:
        """Enable the template only when renaming is active."""
        self.name_template_edit.setEnabled(checked)

    def _collect_options(self) -> ConversionOptions:
        """Build and validate conversion options from the UI."""
        output_text = self.output_edit.text().strip()
        if not output_text:
            raise ValueError("请先选择输出目录。")
        bitrate_text = self.bitrate_combo.currentText().lower().replace("kbps", "").strip()
        try:
            bitrate = int(float(bitrate_text))
        except ValueError as exc:
            raise ValueError("比特率格式无效，请填写如 320 kbps。") from exc
        group_by: list[str] = []
        if self.artist_check.isChecked():
            group_by.append("artist")
        if self.genre_check.isChecked():
            group_by.append("genre")
        if self.album_check.isChecked():
            group_by.append("album")
        options = ConversionOptions(
            output_dir=Path(output_text).expanduser().resolve(),
            output_format=str(self.format_combo.currentData()),
            bitrate_kbps=bitrate,
            rename=self.rename_check.isChecked(),
            name_template=self.name_template_edit.text().strip() or "{artist} - {title}",
            group_by=tuple(group_by),
            fetch_lyrics=self.lyrics_check.isChecked(),
            allow_unsynced_lyrics=self.unsynced_check.isChecked(),
            overwrite_policy=OverwritePolicy(str(self.overwrite_combo.currentData())),
            workers=self.worker_spin.value(),
        )
        options.validate()
        return options

    def _start_batch(self) -> None:
        """Start all pending or previously failed jobs."""
        if self.active_tasks:
            return
        try:
            options = self._collect_options()
        except ValueError as exc:
            QMessageBox.warning(self, "无法开始转换", str(exc))
            return
        runnable_rows = [
            index
            for index, entry in enumerate(self.queue_entries)
            if entry.status
            in {JobStatus.PENDING, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.SUCCESS}
        ]
        if not runnable_rows:
            QMessageBox.information(self, "没有可转换任务", "请先添加音乐文件。")
            return
        for row in runnable_rows:
            self.queue_entries[row].status = JobStatus.PENDING
            self.queue_entries[row].progress = 0
            self.queue_entries[row].result = None
            progress = self.progress_bars.get(row)
            if progress:
                progress.setValue(0)
        self.thread_pool.setMaxThreadCount(options.workers)
        self._set_running(True)
        target_label = FORMAT_LABELS.get(options.output_format, options.output_format)
        self._append_log(
            f"开始批量转换：{len(runnable_rows)} 个文件，目标 {target_label}。"
        )
        for row in runnable_rows:
            entry = self.queue_entries[row]
            task = ConversionTask(row, entry.source, options)
            task.signals.progress.connect(self._on_task_progress)
            task.signals.finished.connect(self._on_task_finished)
            self.active_tasks[row] = task
            self.thread_pool.start(task)

    def _set_running(self, running: bool) -> None:
        """Toggle controls according to batch state."""
        for button in (
            self.add_file_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
            self.output_browse_button,
            self.output_edit,
            self.start_button,
        ):
            button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.drop_zone.setEnabled(not running)

    def _on_task_progress(self, row: int, percent: int) -> None:
        """Update one row's progress."""
        if not 0 <= row < len(self.queue_entries):
            return
        entry = self.queue_entries[row]
        entry.status = JobStatus.RUNNING
        entry.progress = percent
        progress = self.progress_bars.get(row)
        if progress:
            progress.setValue(percent)
        status = self.queue_table.item(row, 3)
        if status:
            status.setText(STATUS_LABELS[JobStatus.RUNNING])
            self._color_status_item(status, JobStatus.RUNNING)
        self.statusBar().showMessage(f"正在处理：{entry.source.name} · {percent}%")

    def _on_task_finished(self, row: int, raw_result: Any) -> None:
        """Record a completed job and refresh aggregate status."""
        result = raw_result if isinstance(raw_result, ConversionResult) else None
        if result is None:
            fallback_source = (
                self.queue_entries[row].source
                if 0 <= row < len(self.queue_entries)
                else Path("")
            )
            result = ConversionResult(
                source=fallback_source,
                status=JobStatus.FAILED,
                message="任务未返回有效结果。",
            )
        self.active_tasks.pop(row, None)
        if 0 <= row < len(self.queue_entries):
            entry = self.queue_entries[row]
            entry.status = result.status
            entry.result = result
            entry.progress = 100 if result.status is JobStatus.SUCCESS else entry.progress
            progress = self.progress_bars.get(row)
            if progress and result.status is JobStatus.SUCCESS:
                progress.setValue(100)
            status_item = self.queue_table.item(row, 3)
            if status_item:
                status_item.setText(STATUS_LABELS[result.status])
                self._color_status_item(status_item, result.status)
            lyrics_item = self.queue_table.item(row, 2)
            if lyrics_item:
                lyrics_item.setText(self._lyrics_text(result))
            if result.metadata:
                song_item = self.queue_table.item(row, 1)
                if song_item:
                    song_item.setText(
                        f"{result.metadata.artist_text or '未知歌手'}\n"
                        f"{result.metadata.title or '未知歌曲'}"
                    )
        self._log_result(result)
        self._refresh_summary()
        self._refresh_pending_page()
        if not self.active_tasks:
            self._set_running(False)
            success = sum(entry.status is JobStatus.SUCCESS for entry in self.queue_entries)
            failed = sum(entry.status is JobStatus.FAILED for entry in self.queue_entries)
            self.statusBar().showMessage(f"批量任务结束：成功 {success}，失败 {failed}")
            self._append_log(f"批量任务结束：成功 {success}，失败 {failed}。")

    def _cancel_batch(self) -> None:
        """Request cancellation of all active and queued jobs."""
        if not self.active_tasks:
            return
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("正在取消剩余任务…")
        for task in self.active_tasks.values():
            task.cancel_event.set()
        self._append_log("已请求取消转换任务。")

    def _refresh_summary(self) -> None:
        """Update queue totals and captions."""
        total = len(self.queue_entries)
        done = sum(
            entry.status in {JobStatus.SUCCESS, JobStatus.SKIPPED}
            for entry in self.queue_entries
        )
        pending = total - done
        self.queue_count.setText(f"{total} 首")
        self.total_badge.set_value(str(total))
        self.success_badge.set_value(str(done))
        self.pending_badge.set_value(str(max(0, pending)))
        lrc_count = sum(
            bool(entry.result and entry.result.lrc_path)
            for entry in self.queue_entries
        )
        if total:
            self.summary_label.setText(
                f"已完成 {done}/{total}，LRC {lrc_count} 个，待处理 {max(0, pending)}"
            )
        else:
            self.summary_label.setText("选择输出目录后即可开始")

    def _refresh_pending_page(self) -> None:
        """Rebuild the lyric pending table from current results."""
        pending = [
            entry.result
            for entry in self.queue_entries
            if entry.result
            and entry.result.lyrics
            and entry.result.lyrics.status is LyricsStatus.PENDING
        ]
        self.pending_table.setRowCount(len(pending))
        for row, result in enumerate(pending):
            assert result.lyrics is not None
            self.pending_table.setRowHeight(row, 48)
            source_item = QTableWidgetItem(result.source.name)
            source_item.setData(Qt.UserRole, str(result.source))
            self.pending_table.setItem(row, 0, source_item)
            song = (
                f"{result.metadata.artist_text} - {result.metadata.title}"
                if result.metadata
                else result.source.stem
            )
            self.pending_table.setItem(row, 1, QTableWidgetItem(song))
            self.pending_table.setItem(row, 2, QTableWidgetItem(result.lyrics.provider))
            self.pending_table.setItem(
                row,
                3,
                QTableWidgetItem(f"{result.lyrics.confidence:.0%}"),
            )
            self.pending_table.setItem(row, 4, QTableWidgetItem(result.lyrics.message))
        self.lyrics_stack.setCurrentIndex(1 if pending else 0)

    def _show_pending_detail(self, row: int, column: int) -> None:
        """Show lyric candidate details for a pending item."""
        source_item = self.pending_table.item(row, 0)
        if not source_item:
            return
        source = Path(source_item.data(Qt.UserRole))
        result = next(
            (
                entry.result
                for entry in self.queue_entries
                if entry.result and entry.result.source == source
            ),
            None,
        )
        if not result or not result.lyrics:
            return
        details = result.lyrics.message or "无详细说明"
        if result.lyrics.candidates:
            details += "\n\n候选歌词：\n" + candidate_summary(result.lyrics.candidates)
        QMessageBox.information(self, "歌词候选详情", details)

    def _open_output_dir(self) -> None:
        """Open the selected output directory, creating it if necessary."""
        path_text = self.output_edit.text().strip()
        if not path_text:
            QMessageBox.information(self, "尚未选择目录", "请先选择输出目录。")
            return
        path = Path(path_text).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法打开目录", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _log_result(self, result: ConversionResult) -> None:
        """Append one conversion result to the session log."""
        label = STATUS_LABELS[result.status]
        identity = (
            f"{result.metadata.artist_text} - {result.metadata.title}"
            if result.metadata
            else result.source.name
        )
        line = f"[{label}] {identity}"
        if result.output_path:
            line += f" → {result.output_path}"
        if result.message:
            line += f"\n  {result.message}"
        for warning in result.warnings:
            line += f"\n  警告：{warning}"
        self._append_log(line)

    def _append_log(self, text: str) -> None:
        """Append a timestamped line to the log page."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        existing = self.log_browser.toHtml()
        if existing:
            self.log_browser.append(f'<span style="color:#6A7882">[{timestamp}]</span> {safe_text}')
        else:
            self.log_browser.setHtml(
                f'<div style="line-height:1.65"><span style="color:#6A7882">[{timestamp}]</span> '
                f"{safe_text}</div>"
            )

    def _initial_environment_check(self) -> None:
        """Run a fast local tool check after the window appears."""
        try:
            doctor = FFmpeg().doctor()
        except Exception:
            doctor = {"ffmpeg_ready": False, "ape_output_ready": False}
        self._apply_format_capabilities(doctor)
        if doctor.get("ffmpeg_ready"):
            suffix = " · APE 可用" if doctor.get("ape_output_ready") else ""
            self.tool_pill.setText(f"本地工具已就绪{suffix}")
            self.tool_pill.setStyleSheet(
                f"background: #DFEEE5; color: {COLORS['success']};"
                "border-radius: 12px; padding: 7px 12px; font-size: 11px; font-weight: 600;"
            )
        else:
            self.tool_pill.setText("FFmpeg 未就绪")
            self.tool_pill.setStyleSheet(
                f"background: {COLORS['cinnabar_light']}; color: {COLORS['cinnabar']};"
                "border-radius: 12px; padding: 7px 12px; font-size: 11px; font-weight: 600;"
            )

    def _check_environment(self) -> None:
        """Refresh and display detailed tool readiness."""
        doctor = FFmpeg().doctor()
        self._apply_format_capabilities(doctor)
        lines = [
            f"FFmpeg：{doctor.get('ffmpeg') or '未找到'}",
            f"FFprobe：{doctor.get('ffprobe') or '未找到'}",
            f"Monkey’s Audio：{doctor.get('monkeys_audio') or '未找到'}",
            "",
            "可用输出格式：" + "、".join(
                FORMAT_LABELS.get(name, name)
                for name, ready in doctor.get("formats", {}).items()
                if ready
            ),
        ]
        self.environment_label.setText("\n".join(lines))
        self._initial_environment_check()

    def _apply_format_capabilities(self, doctor: dict) -> None:
        """Disable output formats that the current platform cannot encode."""
        available = doctor.get("formats", {})
        selected_data = self.format_combo.currentData()
        selected_disabled = False
        for index in range(self.format_combo.count()):
            output_format = self.format_combo.itemData(index)
            supported = bool(available.get(output_format, False))
            item = self.format_combo.model().item(index)
            if item:
                item.setEnabled(supported)
            if output_format == selected_data and not supported:
                selected_disabled = True
        if selected_disabled:
            mp3_index = self.format_combo.findData("mp3")
            if mp3_index >= 0:
                self.format_combo.setCurrentIndex(mp3_index)

    def _load_settings(self) -> None:
        """Load persisted UI values."""
        self.output_edit.setText(self.settings.value("output_dir", "", str))
        output_format = self.settings.value("format", "mp3", str)
        index = self.format_combo.findData(output_format)
        self.format_combo.setCurrentIndex(max(0, index))
        self.bitrate_combo.setCurrentText(self.settings.value("bitrate", "320 kbps", str))
        self.rename_check.setChecked(self.settings.value("rename", True, bool))
        self.name_template_edit.setText(
            self.settings.value("name_template", "{artist} - {title}", str)
        )
        groups = set(self.settings.value("groups", "", str).split(","))
        self.artist_check.setChecked("artist" in groups)
        self.genre_check.setChecked("genre" in groups)
        self.album_check.setChecked("album" in groups)
        self.lyrics_check.setChecked(self.settings.value("lyrics", True, bool))
        self.unsynced_check.setChecked(self.settings.value("unsynced", False, bool))
        overwrite = self.settings.value("overwrite", OverwritePolicy.RENAME.value, str)
        overwrite_index = self.overwrite_combo.findData(overwrite)
        self.overwrite_combo.setCurrentIndex(max(0, overwrite_index))
        self.worker_spin.setValue(self.settings.value("workers", 2, int))
        self._rename_toggled(self.rename_check.isChecked())

    def _save_settings(self) -> None:
        """Persist current UI settings."""
        self.settings.setValue("output_dir", self.output_edit.text().strip())
        self.settings.setValue("format", self.format_combo.currentData())
        self.settings.setValue("bitrate", self.bitrate_combo.currentText())
        self.settings.setValue("rename", self.rename_check.isChecked())
        self.settings.setValue("name_template", self.name_template_edit.text())
        groups = [
            name
            for name, checkbox in (
                ("artist", self.artist_check),
                ("genre", self.genre_check),
                ("album", self.album_check),
            )
            if checkbox.isChecked()
        ]
        self.settings.setValue("groups", ",".join(groups))
        self.settings.setValue("lyrics", self.lyrics_check.isChecked())
        self.settings.setValue("unsynced", self.unsynced_check.isChecked())
        self.settings.setValue("overwrite", self.overwrite_combo.currentData())
        self.settings.setValue("workers", self.worker_spin.value())
        self.settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Confirm closing while jobs are active and persist settings."""
        if self.active_tasks:
            answer = QMessageBox.question(
                self,
                "转换仍在进行",
                "仍有任务正在执行。关闭窗口将取消剩余任务，是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer is not QMessageBox.Yes:
                event.ignore()
                return
            for task in self.active_tasks.values():
                task.cancel_event.set()
            self.thread_pool.waitForDone(3000)
        self._save_settings()
        event.accept()


def main() -> int:
    """Application entry point."""
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("MusicFormatConverter")
    app.setOrganizationName("CodexProjects")
    app.setApplicationDisplayName("韶律 · 音乐格式转换器")
    app.setWindowIcon(make_app_icon())
    apply_theme(app)
    window = MainWindow()
    window.show()
    if os.environ.get("MUSIC_CONVERTER_SMOKE_TEST") == "1":
        QTimer.singleShot(750, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

