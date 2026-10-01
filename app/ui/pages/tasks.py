"""任务列表页（docs/INTERFACES.md §5）。

签名：TasksPage(runner: TaskRunner, config: Config, parent=None)，暴露 refresh()。
刷新策略：runner.taskAdded / taskUpdated / taskFinished 只动对应卡片，
绝不整表重建；refresh() 仅在页面切换或增删任务时做增量对齐。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app.core.config import Config
from app.core.model import DownloadTask, TaskStatus
from app.core.runner import TaskRunner
from app.miuix.icons import icon
from app.miuix.theme import theme
from app.miuix.widgets import (
    MiuixButton,
    MiuixLabel,
    toast,
)
from app.ui.pagebase import PAGE_MARGIN, ROW_SPACING, PageBase
from app.ui.taskcard import TaskCard


class TasksPage(PageBase):
    """任务卡片列表 + 顶部工具条（全部开始 / 清理已完成）。"""

    def __init__(self, runner: TaskRunner, config: Config, parent: QWidget | None = None) -> None:
        self._cards: dict[str, TaskCard] = {}   # 必须在 super().__init__ 之前初始化（基类会调 _build）
        self._tasks_layout: QVBoxLayout | None = None
        self._count_text: str = ""
        super().__init__(runner, config, parent)
        self._connect_runner()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.page_header("📋 任务"))
        root.addWidget(self._build_toolbar())

        scroll, body = self.build_scroll()
        root.addWidget(scroll, 1)

        self.empty_label = MiuixLabel("📭 暂无任务，去「下载」页新建一个吧", style="body1",
                                      color="on_surface_variant")
        self.empty_label.setContentsMargins(0, 48, 0, 0)
        body.addWidget(self.empty_label)

        self._tasks_layout = body
        body.addStretch(1)
        self._connect()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(PAGE_MARGIN, 0, PAGE_MARGIN, ROW_SPACING)
        layout.setSpacing(ROW_SPACING)

        self.count_label = MiuixLabel("共 0 个任务", style="body2",
                                      color="on_surface_variant")
        layout.addWidget(self.count_label)
        layout.addStretch(1)

        self.start_all_btn = MiuixButton("全部开始", variant="tonal", icon=icon("play"))
        self.start_all_btn.setToolTip("重新开始所有失败 / 已取消的任务")
        self.clear_btn = MiuixButton("清理已完成", variant="outlined", icon=icon("trash"))
        layout.addWidget(self.start_all_btn)
        layout.addWidget(self.clear_btn)
        return bar

    def _connect(self) -> None:
        self.start_all_btn.clicked.connect(self._start_all)
        self.clear_btn.clicked.connect(self._clear_finished)

    def _connect_runner(self) -> None:
        """订阅 runner 信号（高频刷新走这里，不重建列表）。"""
        self.runner.taskAdded.connect(self._on_task_added)
        self.runner.taskUpdated.connect(self._on_task_updated)
        self.runner.taskFinished.connect(self._on_task_finished)

    # ------------------------------------------------------------ 任务同步
    def refresh(self) -> None:
        """与 runner.tasks 增量对齐：补新增、删已移除、复用已有卡片。"""
        tasks = self.runner.tasks
        alive = {task.id for task in tasks}
        for task_id in list(self._cards):
            if task_id not in alive:
                self._drop_card(task_id)
        for row, task in enumerate(tasks):     # runner.tasks 为新 → 旧
            card = self._cards.get(task.id)
            if card is None:
                card = self._make_card(task)
            card.update_from(task)
            if self._tasks_layout is not None:
                self._tasks_layout.insertWidget(row, card)
        self._sync_status()

    def _make_card(self, task: DownloadTask) -> TaskCard:
        card = TaskCard(task)
        card.cancelRequested.connect(self.runner.cancel)
        card.retryRequested.connect(self._retry)
        card.deleteRequested.connect(self._delete)
        card.openFolderRequested.connect(self._open_folder)
        card.copyRequested.connect(self._copy_link)
        self._cards[task.id] = card
        return card

    def _drop_card(self, task_id: str) -> None:
        card = self._cards.pop(task_id, None)
        if card is not None:
            card.setParent(None)
            card.deleteLater()

    def _on_task_added(self, task_id: str) -> None:
        task = self.runner.get(task_id)
        if task is None or task_id in self._cards:
            return
        card = self._make_card(task)
        if self._tasks_layout is not None:
            self._tasks_layout.insertWidget(0, card)
        self._sync_status()

    def _on_task_updated(self, task_id: str) -> None:
        """进度刷新：只更新对应卡片，绝不重建列表。"""
        card = self._cards.get(task_id)
        task = self.runner.get(task_id)
        if card is None:
            if task is not None:
                self._on_task_added(task_id)
            return
        if task is not None:
            card.update_from(task)
            self._sync_status()   # 计数文案只在状态变化时真正写回（见 _sync_status）

    def _on_task_finished(self, task_id: str, exit_code: int) -> None:
        self._on_task_updated(task_id)
        task = self.runner.get(task_id)
        if task is None:
            return
        if task.status is TaskStatus.DONE:
            toast(self, f"「{task.title}」下载完成", "success")
        elif task.status is TaskStatus.FAILED:
            toast(self, f"「{task.title}」下载失败（退出码 {exit_code}）", "error")

    def _sync_status(self) -> None:
        """更新计数与空状态；文案没变就不写回控件（会被 taskUpdated 高频调用）。"""
        tasks = self.runner.tasks
        running = sum(1 for task in tasks if task.status in (TaskStatus.RUNNING, TaskStatus.MUXING))
        pending = sum(1 for task in tasks if task.status is TaskStatus.PENDING)
        text = f"共 {len(tasks)} 个任务 · 进行中 {running} · 排队 {pending}"
        if self._count_text != text:
            self._count_text = text
            self.count_label.setText(text)
        self.empty_label.setVisible(not tasks)
        self.clear_btn.setEnabled(any(task.status.is_final for task in tasks))

    # ------------------------------------------------------------ 工具条动作
    def _start_all(self) -> None:
        restarted = 0
        for task in self.runner.tasks:
            if task.status in (TaskStatus.FAILED, TaskStatus.CANCELED):
                self.runner.retry(task.id)
                restarted += 1
        if restarted:
            toast(self, f"已重新开始 {restarted} 个任务", "primary")
        else:
            toast(self, "没有可重新开始的任务（排队中的任务会自动开始）", "neutral")

    def _clear_finished(self) -> None:
        removed = self.runner.clear_finished()
        for task_id in removed:
            self._drop_card(task_id)
        self.refresh()
        toast(self, f"已清理 {len(removed)} 个已完成任务" if removed else "没有可清理的任务",
              "success" if removed else "neutral")

    # ------------------------------------------------------------ 卡片动作
    def _retry(self, task_id: str) -> None:
        self.runner.retry(task_id)
        task = self.runner.get(task_id)
        if task is not None:
            toast(self, f"已重新开始「{task.title}」", "primary")

    def _delete(self, task_id: str) -> None:
        self.runner.remove(task_id)
        self._drop_card(task_id)
        self.refresh()

    def _open_folder(self, task_id: str) -> None:
        task = self.runner.get(task_id)
        if task is None or not task.output_path:
            return
        target = task.output_path if os.path.isdir(task.output_path) else os.path.dirname(task.output_path)
        if not target:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(target)):
            toast(self, f"打开目录失败：{target}", "error")

    def _copy_link(self, task_id: str) -> None:
        task = self.runner.get(task_id)
        if task is None:
            return
        QGuiApplication.clipboard().setText(task.options.url)
        toast(self, "链接已复制", "success")
