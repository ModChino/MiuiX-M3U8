"""沉浸式窗口标题栏（无边框窗口的自绘标题栏）。

为什么自绘：Windows 原生标题栏使用系统配色与字体，和 Miuix 界面割裂。
这里所有窗口按钮图标都用 QPainter 画，不依赖 icons.py，保持模块自洽。

规格取自 docs/MIUIX_TOKENS.md：
- 高度 52px（对齐 Miuix TopAppBar CollapsedHeight）
- 背景 palette.surface
- 标题 17px / Medium(500)、on_surface，水平内边距 26px（Miuix TitlePadding）
- 窗口按钮 46x36、圆角 8px（squircle）
  hover 背景 surface_container_high；关闭按钮 hover 背景 palette.error、图标 on_error
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.miuix.squircle import squircle_path
from app.miuix.theme import theme

TITLEBAR_HEIGHT = 52
BUTTON_W = 46
BUTTON_H = 36
BUTTON_RADIUS = 8
TITLE_PAD = 26          # Miuix TopAppBar TitlePadding
ICON_BOX = 10.0         # 窗口按钮图标外接方框边长
STROKE = 1.15           # 图标线宽


class _WindowButton(QWidget):
    """单个窗口按钮（最小化 / 最大化 / 还原 / 关闭），全自绘。"""

    MIN = "min"
    MAX = "max"
    RESTORE = "restore"
    CLOSE = "close"

    clicked = Signal()

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._hover = False
        self._pressed = False
        self.setFixedSize(BUTTON_W, BUTTON_H)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        theme().changed.connect(self.update)

    def setKind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    def kind(self) -> str:
        return self._kind

    # ---------------------------------------------------------- 交互
    def enterEvent(self, event) -> None:      # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:      # noqa: N802
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()      # 必须吞掉，否则会冒泡成窗口拖动
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            inside = self.rect().contains(event.position().toPoint())
            self._pressed = False
            self.update()
            event.accept()
            if inside:
                self.clicked.emit()
            return
        super().mouseReleaseEvent(event)

    # ---------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:      # noqa: N802
        pal = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        is_close = self._kind == self.CLOSE
        active = self._hover or self._pressed
        if active:
            bg = QColor(pal.error) if is_close else QColor(pal.surface_container_high)
            painter.fillPath(squircle_path(QRectF(self.rect()), BUTTON_RADIUS), bg)

        if is_close and active:
            fg = QColor(pal.on_error)
        else:
            fg = QColor(pal.on_surface)

        pen = QPen(fg)
        pen.setWidthF(STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        h = ICON_BOX / 2.0
        left, right = cx - h, cx + h
        top, bottom = cy - h, cy + h

        if self._kind == self.MIN:
            painter.drawLine(QPointF(left, cy), QPointF(right, cy))
        elif self._kind == self.MAX:
            painter.drawRect(QRectF(left, top, ICON_BOX, ICON_BOX))
        elif self._kind == self.RESTORE:
            off = ICON_BOX * 0.30
            painter.drawRect(QRectF(left, top + off, ICON_BOX - off, ICON_BOX - off))
            painter.drawLine(QPointF(left + off, top + off), QPointF(left + off, top))
            painter.drawLine(QPointF(left + off, top), QPointF(right, top))
            painter.drawLine(QPointF(right, top), QPointF(right, bottom - off))
        else:  # CLOSE
            painter.drawLine(QPointF(left, top), QPointF(right, bottom))
            painter.drawLine(QPointF(right, top), QPointF(left, bottom))
        painter.end()


class MiuixTitleBar(QWidget):
    """沉浸式标题栏：左侧应用名，右侧窗口按钮；单击拖动、双击切换最大化。

    接口与 docs/INTERFACES.md 冻结签名一致。
    """

    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()

    def __init__(self, title: str = "", icon=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setObjectName("MiuixTitleBar")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(TITLE_PAD, 0, 6, 0)
        lay.setSpacing(0)

        self._title = QLabel(title, self)
        f = QFont(self._title.font())
        f.setPixelSize(17)
        f.setWeight(QFont.Weight.Medium)
        self._title.setFont(f)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._title)
        lay.addStretch(1)

        self._btn_min = _WindowButton(_WindowButton.MIN, self)
        self._btn_max = _WindowButton(_WindowButton.MAX, self)
        self._btn_close = _WindowButton(_WindowButton.CLOSE, self)
        self._btn_min.clicked.connect(self.minimizeRequested)
        self._btn_max.clicked.connect(self.maximizeRequested)
        self._btn_close.clicked.connect(self.closeRequested)
        for btn in (self._btn_min, self._btn_max, self._btn_close):
            lay.addWidget(btn)

        theme().changed.connect(self._on_theme)
        self._on_theme()

    # ---------------------------------------------------------- 公开接口
    def setTitle(self, text: str) -> None:      # noqa: N802
        self._title.setText(text)

    def setMaximized(self, maximized: bool) -> None:   # noqa: N802
        """切换"最大化 / 还原"按钮图标。"""
        self._btn_max.setKind(_WindowButton.RESTORE if maximized else _WindowButton.MAX)

    # 供自检使用
    def button(self, kind: str) -> _WindowButton:
        return {_WindowButton.MIN: self._btn_min,
                _WindowButton.MAX: self._btn_max,
                _WindowButton.RESTORE: self._btn_max,
                _WindowButton.CLOSE: self._btn_close}[kind]

    # ---------------------------------------------------------- 主题
    def _on_theme(self) -> None:
        self._title.setStyleSheet(
            f"color: {theme().palette.on_surface}; background: transparent;"
        )
        self.update()

    def paintEvent(self, event) -> None:      # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme().palette.surface))
        painter.end()

    # ---------------------------------------------------------- 拖动 / 双击
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                # 交给系统处理：保留 Windows 的 Aero Snap / 多屏拖动
                handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:   # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximizeRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
