"""任务卡片组件（docs/INTERFACES.md §5）。

高频刷新策略：TaskRunner.taskUpdated 最快 80ms 一次，因此 update_from() 只改动
**内容有变化**的字段（先做字符串/数值比较），绝不重建布局，避免列表卡顿。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.core.model import DownloadTask, TaskStatus
from app.miuix.icons import icon
from app.miuix.theme import theme
from app.miuix.widgets import (
    MiuixBadge,
    MiuixCard,
    MiuixIconButton,
    MiuixLabel,
    MiuixProgressBar,
    MiuixTextEdit,
)
from app.ui.pagebase import ROW_SPACING

# 状态 → MiuixBadge tone
_BADGE_TONES: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "neutral",
    TaskStatus.RUNNING: "primary",
    TaskStatus.MUXING: "primary",
    TaskStatus.DONE: "success",
    TaskStatus.FAILED: "error",
    TaskStatus.CANCELED: "warning",
}

# 未结束的状态（这类任务显示「取消」，其余显示「重试」）
_ACTIVE_STATUS: tuple[TaskStatus, ...] = (
    TaskStatus.PENDING,
    TaskStatus.RUNNING,
    TaskStatus.MUXING,
)

_LOG_TAIL: int = 400  # 日志面板最多保留的行数


class TaskCard(MiuixCard):
    """单个下载任务的卡片：标题 / 状态徽标 / 进度 / 速度统计 / 操作按钮 / 可展开日志。"""

    cancelRequested = Signal(str)
    retryRequested = Signal(str)
    deleteRequested = Signal(str)
    openFolderRequested = Signal(str)
    copyRequested = Signal(str)

    def __init__(self, task: DownloadTask, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent, padding=16)
        self.task: DownloadTask = task
        self._cache: dict[str, object] = {}
        self._title_text: str = ""
        self._url_text: str = ""
        self._log_open: bool = False
        self._build()
        self.update_from(task)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        body = self.body
        body.setSpacing(ROW_SPACING)

        # 标题行：标题 + 状态徽标 + 操作按钮（右对齐）
        header = QWidget()
        self.header_layout = QHBoxLayout(header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(ROW_SPACING)

        self.title_label = MiuixLabel("", style="body1")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.badge = MiuixBadge(TaskStatus.PENDING.label, tone="neutral")

        self.log_btn = MiuixIconButton("chevron_down", tooltip="展开日志")
        self.copy_btn = MiuixIconButton("link", tooltip="复制链接")
        self.folder_btn = MiuixIconButton("folder", tooltip="打开所在文件夹")
        self.retry_btn = MiuixIconButton("refresh", tooltip="重试")
        self.cancel_btn = MiuixIconButton("stop", tooltip="取消任务")
        self.delete_btn = MiuixIconButton("trash", tooltip="删除任务")

        self.header_layout.addWidget(self.title_label, 1)
        self.header_layout.addWidget(self.badge)
        for button in (self.log_btn, self.copy_btn, self.folder_btn,
                       self.retry_btn, self.cancel_btn, self.delete_btn):
            self.header_layout.addWidget(button)
        body.addWidget(header)

        # 链接行
        self.url_label = MiuixLabel("", style="caption", color="on_surface_variant")
        self.url_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body.addWidget(self.url_label)

        # 进度条
        self.progress = MiuixProgressBar()
        self.progress.setValue(0)
        body.addWidget(self.progress)

        # 统计行：线程 / 速度 / 分段 / 剩余时间 / 大小 / 阶段备注 —— 一律做成胶囊，
        # 跟标题那枚状态徽标同一套视觉语言；空的就隐藏，不占位。
        self.stats_row = QWidget()
        self.stats_layout = QHBoxLayout(self.stats_row)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(ROW_SPACING)
        self.stats_pills: dict[str, MiuixBadge] = {}
        for key, tone in (("thread", "neutral"), ("speed", "primary"),
                          ("segments", "neutral"), ("eta", "neutral"),
                          ("size", "neutral"), ("note", "neutral")):
            pill = MiuixBadge("", tone=tone)
            pill.setVisible(False)
            self.stats_pills[key] = pill
            self.stats_layout.addWidget(pill)
        self.stats_layout.addStretch(1)
        body.addWidget(self.stats_row)

        # 日志面板（默认收起）
        self.log_view = MiuixTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(200)   # 固定高度：约 9 行日志，展开时不挤动相邻卡片
        self.log_view.setVisible(False)
        body.addWidget(self.log_view)

        self._connect()

    def _connect(self) -> None:
        self.log_btn.clicked.connect(self._toggle_log)
        self.copy_btn.clicked.connect(lambda: self.copyRequested.emit(self.task.id))
        self.folder_btn.clicked.connect(lambda: self.openFolderRequested.emit(self.task.id))
        self.retry_btn.clicked.connect(lambda: self.retryRequested.emit(self.task.id))
        self.cancel_btn.clicked.connect(lambda: self.cancelRequested.emit(self.task.id))
        self.delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self.task.id))

    # -------------------------------------------------------------- 高频刷新
    def update_from(self, task: DownloadTask) -> None:
        """用最新任务状态刷新卡片；只有变化的字段才会真正写回控件。"""
        self.task = task

        if self._changed("title", task.title):
            self._title_text = task.title
            self._relayout_text()
        if self._changed("url", task.options.url):
            self._url_text = task.options.url
            self._relayout_text()
        if self._changed("status", task.status):
            self._apply_status(task.status)

        # 合并阶段一律走"忙碌"滑动：实测合并时 parser 拿到的百分比是**下载残留**
        # （例如停在 98.4% 不动），当成真实进度显示反而更像卡死。
        busy = task.status is TaskStatus.MUXING
        if self._changed("busy", busy):
            self.progress.setBusy(busy)

        value = 1000 if task.status is TaskStatus.DONE else int(round(_clamp(task.percent) * 10))
        if self._changed("percent", value):
            self.progress.setValue(value)

        self._apply_stats(task)

        has_output = bool(task.output_path)
        if self._changed("output", has_output):
            self.folder_btn.setVisible(has_output)

        if self._log_open and self._changed("log", len(task.log)):
            self.log_view.setPlainText("\n".join(task.log[-_LOG_TAIL:]))
            bar = self.log_view.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _apply_stats(self, task: DownloadTask) -> None:
        """刷新统计胶囊：文案没变的 pill 直接跳过（高频刷新，别白写控件）。"""
        texts = _stat_pills(task)
        for key, pill in self.stats_pills.items():
            text = texts.get(key, "")
            visible = bool(text)
            if pill.text() == text and pill.isVisible() == visible:
                continue
            pill.setText(text)
            pill.setVisible(visible)

    def _changed(self, key: str, value: object) -> bool:
        """字段变化检测：返回值相同则跳过控件写入（高频刷新的关键）。"""
        if self._cache.get(key) == value:
            return False
        self._cache[key] = value
        return True

    def _apply_status(self, status: TaskStatus) -> None:
        """状态徽标：文案 + tone。tone 变化优先用 setTone，缺失时重建徽标。"""
        tone = _BADGE_TONES.get(status, "neutral")
        self.badge.setText(status.label)
        setter = getattr(self.badge, "setTone", None)
        if callable(setter):
            setter(tone)
        else:
            index = self.header_layout.indexOf(self.badge)
            self.header_layout.removeWidget(self.badge)
            self.badge.deleteLater()
            self.badge = MiuixBadge(status.label, tone=tone)
            self.header_layout.insertWidget(index, self.badge)

        active = status in _ACTIVE_STATUS
        self.cancel_btn.setVisible(active)
        self.retry_btn.setVisible(not active)

    # ------------------------------------------------------------------ 日志
    def _toggle_log(self) -> None:
        self._log_open = not self._log_open
        self.log_view.setVisible(self._log_open)
        self.log_btn.setToolTip("收起日志" if self._log_open else "展开日志")
        self.log_btn.setIcon(icon("chevron_right" if self._log_open else "chevron_down"))
        if self._log_open:
            self._cache.pop("log", None)  # 强制下次刷新写入日志
            self.update_from(self.task)

    # ------------------------------------------------------------------ 文本
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout_text()

    def _relayout_text(self) -> None:
        """长 URL / 长文件名按宽度省略，避免撑破卡片。"""
        _elide(self.title_label, self._title_text, self.title_label.width())
        _elide(self.url_label, self._url_text, self.url_label.width())


def _elide(label: QLabel, text: str, width: int) -> None:
    """按控件宽度做中部省略（QLabel 不会自己省略，长链接会撑破布局）。"""
    elided = label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, max(60, width))
    if label.text() != elided:
        label.setText(elided)


def _clamp(percent: float) -> float:
    return max(0.0, min(100.0, float(percent or 0.0)))


#: 失败原因胶囊最多显示多少个字（再长就省略 —— 完整原因在展开的日志里）
_PILL_MESSAGE_MAX = 44


def _stage_note(task: DownloadTask) -> str:
    """阶段备注胶囊：合并中 / 排队 / 耗时 / 失败原因 / 已取消。"""
    if task.status is TaskStatus.MUXING:
        # 合并阶段没有真实百分比，给明确的进行中提示 + 已用时
        return "🎬 正在合并音视频… · 已用 %.0fs" % task.elapsed
    if task.status is TaskStatus.PENDING:
        return "⏳ 等待空闲线程"
    if task.status is TaskStatus.DONE:
        return "✅ 耗时 %.0fs" % task.elapsed
    if task.status is TaskStatus.FAILED:
        text = (task.message or "下载失败").strip().replace("\n", " ")
        if len(text) > _PILL_MESSAGE_MAX:
            text = text[:_PILL_MESSAGE_MAX] + "…"
        return "❌ " + text
    if task.status is TaskStatus.CANCELED:
        return "🚫 已取消"
    return ""


def _stat_pills(task: DownloadTask) -> dict[str, str]:
    """统计胶囊的文案；值为空串表示这一枚不显示。

    线程数取自 **task.options** —— 扩展投递的任务可能单独指定了线程数，跟桌面端
    默认值不一样，所以不能去读 config.defaults。
    """
    pills: dict[str, str] = {}
    if task.options.thread_count:
        pills["thread"] = "🧵 %d 线程" % task.options.thread_count
    if task.speed:
        pills["speed"] = "⚡ " + task.speed
    if task.segments:
        pills["segments"] = "🧩 " + task.segments
    if task.eta:
        pills["eta"] = "⏱️ " + task.eta
    if task.size:
        pills["size"] = "💾 " + task.size
    note = _stage_note(task)
    if note:
        pills["note"] = note
    return pills
