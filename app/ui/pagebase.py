"""页面公共基类与布局辅助。

契约见 docs/INTERFACES.md §5：页面由 main.py 注入 runner/config（页面不得自建），
页面 → 主导航的跳转统一用 gotoRequested 信号冒泡给 MainWindow。

尺寸遵循 Miuix 官方 token（见 docs/MIUIX_TOKENS.md）：
页面内容左右边距 16px、分组卡片间距 16px、卡内元素间距 8px。
所有颜色都取自 theme().palette，不写死任何色值。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.runner import TaskRunner
from app.miuix.theme import theme
from app.miuix.tokens import SPACING
from app.miuix.widgets import (
    MiuixCard,
    MiuixLabel,
    MiuixScrollArea,
    MiuixSectionHeader,
    MiuixTopBar,
)

# ---- 尺寸一律取 Miuix token（不写死数值）----
PAGE_MARGIN: int = SPACING["page"]      # 页面内容左右边距（卡片外侧留白；26px 只是 TopBar 标题内边距）
CARD_SPACING: int = SPACING["lg"]       # 分组卡片之间的垂直间距
ROW_SPACING: int = SPACING["sm"]        # 卡内元素间距
ACTION_BAR_HEIGHT: int = 40 + SPACING["sm"] * 3      # 底部固定操作栏（40 按钮 + 上下留白）
SCROLL_BOTTOM_EXTRA: int = ACTION_BAR_HEIGHT + SPACING["lg"]  # 有操作栏的页面留给滚动内容的底部空间
LABEL_WIDTH: int = 112                  # 表单标签列宽（够放 "N_m3u8DL-RE"，再窄会被裁字）
FIELD_ROW_GAP: int = SPACING["md"]      # 表单标签与控件之间的水平间距


class PageBase(QWidget):
    """三页共用的基类：统一背景、边距、runner/config 注入与背景色跟随主题。"""

    gotoRequested = Signal(int)

    def __init__(self, runner: TaskRunner, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.runner = runner
        self.config = config
        self.setObjectName("MiuixPageRoot")
        self._apply_background()
        theme().changed.connect(self._apply_background)
        self._build()

    # ---- 子类实现 ----
    def _build(self) -> None:
        """子类在此构建界面（基类 __init__ 末尾调用）。"""

    def refresh(self) -> None:
        """页面被切到前台时调用；子类按需覆写。"""

    # ---- 背景 ----
    def _apply_background(self) -> None:
        """页面底色取 palette.surface（浅 #F7F7F7 / 深 #000000）。

        不用 palette.background：浅色下它与 surface_container 同为 #FFFFFF，
        卡片会完全看不见；surface 才能把白色卡片衬出来。
        滚动内容区复用同一个 objectName，从而继承这条规则。
        """
        self.setStyleSheet(
            f"QWidget#MiuixPageRoot {{ background: {theme().palette.surface}; }}"
        )

    # ---- 布局辅助 ----
    def page_header(self, title: str) -> MiuixTopBar:
        """页面顶栏（Miuix TopBar，高 52px、水平内边距 26px）。"""
        return MiuixTopBar(title)

    def build_scroll(self, bottom_extra: int = 0) -> tuple[MiuixScrollArea, QVBoxLayout]:
        """创建页面主体：透明滚动区 + 页边距的纵向内容布局。

        bottom_extra：给底部固定操作栏预留的高度，保证最后一个控件能完整滚到操作栏上方
        （下载页底部有"预览命令 / 开始下载"操作栏，传 SCROLL_BOTTOM_EXTRA）。
        """
        scroll = MiuixScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("MiuixPageRoot")  # 复用页面背景规则
        layout = QVBoxLayout(content)
        layout.setContentsMargins(PAGE_MARGIN, ROW_SPACING * 2, PAGE_MARGIN,
                                  PAGE_MARGIN + bottom_extra)
        layout.setSpacing(CARD_SPACING)
        scroll.setWidget(content)
        return scroll, layout

    def card(self, title: str = "", padding: int = 16) -> MiuixCard:
        """建一张分组卡片；Miuix 官方 Card 内边距为 0，这里显式传 padding。"""
        card = MiuixCard(padding=padding)
        if title:
            card.body.addWidget(MiuixSectionHeader(title))
        return card

    def form_row(self, label: str, field: QWidget, hint: str = "") -> QWidget:
        """一行表单：左固定宽标签 + 右侧控件（可选下方说明文字）。"""
        row = QWidget()
        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        line = QWidget()
        line_layout = QHBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(FIELD_ROW_GAP)
        text = MiuixLabel(label, style="body1")
        text.setFixedWidth(LABEL_WIDTH)
        text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        line_layout.addWidget(text)
        if field.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed:
            # 固定宽控件（开关 / 复选框）不吸收多余宽度：若不给弹簧，
            # QHBoxLayout 会把剩余宽度平均分到各间隙，把左侧标签挤到行中间。
            line_layout.addWidget(field)
            line_layout.addStretch(1)
        else:
            line_layout.addWidget(field, 1)
        outer.addWidget(line)
        if hint:
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(LABEL_WIDTH + FIELD_ROW_GAP, 0, 0, 0)
            holder_layout.setSpacing(0)
            holder_layout.addWidget(self.hint(hint))
            outer.addWidget(holder)
        return row

    def hint(self, text: str) -> MiuixLabel:
        """次要说明文字（caption 字号 + on_surface_variant 颜色）。"""
        label = MiuixLabel(text, style="caption", color="on_surface_variant")
        label.setWordWrap(True)
        return label

    def inline(self, field: QWidget, *trailing: QWidget) -> QWidget:
        """输入框 + 右侧按钮的组合行（例：路径框 + 选择按钮）。

        注意：**不能无脑 addWidget(field, 1)**。像端口框那种 setFixedWidth 的控件，
        setFixedWidth 只改 min/max、**不改 sizePolicy**，于是 stretch 分不出去，
        Qt 会把多余空间摊到两端 —— 端口框就跑到行中间去了，和上下行的输入框对不齐。
        所以这里按"能否变宽"分两种排法：能变宽的吸收空白，不能的靠左、用弹簧把
        后续按钮顶到行尾。
        """
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ROW_SPACING)
        if field.maximumWidth() >= 16777215:      # QWIDGETSIZE_MAX：还能长宽
            layout.addWidget(field, 1)
        else:
            layout.addWidget(field)
            layout.addStretch(1)
        for widget in trailing:
            layout.addWidget(widget)
        return holder

    def spacer_row(self, *widgets: QWidget, stretch_before: bool = True) -> QWidget:
        """右对齐（默认）或左对齐的一行控件。"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ROW_SPACING)
        if stretch_before:
            layout.addStretch(1)
        for widget in widgets:
            layout.addWidget(widget)
        if not stretch_before:
            layout.addStretch(1)
        return row


def combo_int(combo: QComboBox, default: int) -> int:
    """安全读取下拉框里的整数（可编辑框留空时回退默认值）。"""
    try:
        return int(str(combo.currentText()).strip())
    except (TypeError, ValueError):
        return default
