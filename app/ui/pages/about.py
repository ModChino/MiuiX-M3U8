"""关于页（导航第 4 项）。

签名与其它页面一致：AboutPage(runner, config, parent=None)，暴露 refresh()。
"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.core.config import Config
from app.core.runner import TaskRunner
from app.miuix.icons import icon
from app.miuix.theme import theme
from app.miuix.widgets import MiuixButton, MiuixLabel, MiuixListItem, toast
from app.ui import APP_DESCRIPTION, APP_NAME, APP_VERSION, PROJECT_URL
from app.ui.pagebase import PageBase

# 功能列表：(图标, 标题, 说明)
FEATURES: tuple[tuple[str, str, str], ...] = (
    ("download", "流选择", "自动选择最佳流，或按分辨率 / 编码 / 语言精确挑流"),
    ("film", "自动混流", "下载完成后调用 ffmpeg / mkvmerge 合并为 mp4 / mkv / ts"),
    ("key", "解密支持", "支持 --key、kid-key 文件与 mp4decrypt / shaka-packager 引擎"),
    ("list", "多任务并发", "队列化下载，可取消 / 重试 / 查看实时日志与速度"),
)

# 致谢：(名称, 说明)
CREDITS: tuple[tuple[str, str], ...] = (
    ("N_m3u8DL-RE", "下载内核（MIT License）"),
    ("PySide6 / Qt 6", "跨平台 GUI 框架（LGPL v3）"),
    ("Miuix", "视觉设计语言参考（小米澎湃 OS）"),
)


class AboutPage(PageBase):
    """关于：版本信息、功能简介、开源致谢与项目链接。"""

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.page_header("ℹ️ 关于"))

        scroll, body = self.build_scroll()
        root.addWidget(scroll, 1)

        body.addWidget(self._build_intro_card())
        body.addWidget(self._build_feature_card())
        body.addWidget(self._build_credits_card())
        body.addStretch(1)
        self._connect()

    def _build_intro_card(self) -> QWidget:
        card = self.card()
        card.body.addWidget(MiuixListItem(APP_NAME, f"{APP_DESCRIPTION}", icon="download"))
        card.body.addWidget(MiuixLabel(f"版本 {APP_VERSION}", style="body2"))
        self.config_label = MiuixLabel("", style="caption",
                                       color="on_surface_variant")
        card.body.addWidget(self.config_label)
        self.project_btn = MiuixButton("打开 N_m3u8DL-RE 项目主页", variant="tonal", icon=icon("external"))
        card.body.addWidget(self.spacer_row(self.project_btn, stretch_before=False))
        return card

    def _build_feature_card(self) -> QWidget:
        card = self.card("✨ 功能")
        for name, title, subtitle in FEATURES:
            card.body.addWidget(MiuixListItem(title, subtitle, icon=name))
        return card

    def _build_credits_card(self) -> QWidget:
        card = self.card("🙏 致谢")
        for name, subtitle in CREDITS:
            card.body.addWidget(MiuixListItem(name, subtitle, icon="check"))
        return card

    def _connect(self) -> None:
        self.project_btn.clicked.connect(self._open_project)

    def _open_project(self) -> None:
        if not QDesktopServices.openUrl(QUrl(PROJECT_URL)):
            toast(self, f"打开失败：{PROJECT_URL}", "error")

    def refresh(self) -> None:
        self.config_label.setText(f"配置文件：{Config.file()}")
