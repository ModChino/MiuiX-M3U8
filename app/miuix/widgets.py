"""Miuix 基础组件（QSS + 少量自绘控件）。

契约见 docs/INTERFACES.md §3.3；视觉数值见 docs/MIUIX_TOKENS.md。
所有自绘控件连接 `theme().changed` 并 update()，切换主题立即生效。
"""
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtCore import QPropertyAnimation as _QPropertyAnimation  # noqa: F401  (保持 import 稳定)
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .squircle import squircle_border_path, squircle_path
from .theme import (
    blend,
    current_palette,
    font_for,
    has_theme,
    qcolor,
    qss_color,
    theme,
    with_alpha,
)
from .tokens import ICON_SIZE, METRIC, RADIUS, SPACING, Palette

__all__ = [
    "MiuixCard",
    "MiuixButton",
    "MiuixIconButton",
    "MiuixLineEdit",
    "MiuixTextEdit",
    "MiuixComboBox",
    "MiuixSwitch",
    "MiuixCheckBox",
    "MiuixProgressBar",
    "MiuixSlider",
    "MiuixLabel",
    "MiuixTopBar",
    "MiuixNavRail",
    "MiuixSectionHeader",
    "MiuixListItem",
    "MiuixSegmented",
    "MiuixScrollArea",
    "MiuixBadge",
    "MiuixDialog",
    "MiuixDivider",
    "toast",
]

# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------


def _pal() -> Palette:
    """当前配色（主题未初始化时回退浅色，避免控件构造即崩溃）。"""
    return current_palette()


def _bind_theme(widget: QWidget, slot=None) -> None:
    """把 `theme().changed` 连到 widget.update（自绘控件必须做，否则切主题不重绘）。"""
    if not has_theme():
        return
    try:
        theme().changed.connect(slot if slot is not None else widget.update)
    except Exception:  # pragma: no cover
        pass


def _resolve_color(value: str | QColor | None, pal: Palette, default: str = "on_surface") -> QColor:
    """把「token 名 / #RRGGBB / QColor / None」统一解析成 QColor。"""
    if value is None:
        return qcolor(getattr(pal, default, pal.on_surface))
    if isinstance(value, QColor):
        return QColor(value)
    text = str(value)
    if text.startswith("#") or text.startswith("rgb"):
        return qcolor(text)
    if text and hasattr(pal, text):
        return qcolor(getattr(pal, text))
    return qcolor(getattr(pal, default, pal.on_surface))


def _as_icon(value: str | QIcon | None, size: int = 20, color: str | None = None) -> QIcon:
    """图标参数同时容忍「图标名」和「QIcon」。"""
    if isinstance(value, QIcon):
        return value
    if isinstance(value, str) and value:
        return icons.icon(value, color, size)
    return QIcon()


def _icon_label(name_or_icon: str | QIcon, size: int, color: str) -> QLabel:
    """把图标包成固定尺寸的 QLabel（列表项左侧图标用）。"""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setPixmap(_as_icon(name_or_icon, size, color).pixmap(size, size))
    label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    return label


def _button_colors(variant: str, pal: Palette) -> tuple[str | None, str]:
    """按钮变体的（底色, 文字色）；底色 None 表示透明。"""
    if variant == "filled":
        return pal.primary, pal.on_primary
    if variant == "tonal":
        return pal.tertiary_container, pal.on_tertiary_container
    if variant == "secondary":
        return pal.secondary_variant, pal.on_secondary_variant
    if variant == "danger":
        return pal.error, pal.on_error
    if variant == "outlined":
        return None, pal.on_surface
    return None, pal.primary  # text


# --------------------------------------------------------------------------
# 容器
# --------------------------------------------------------------------------
class MiuixCard(QFrame):
    """圆角卡片（squircle 16dp，无边框无阴影，靠底色与页面分层）。

    用法：`card = MiuixCard(); card.body.addWidget(...)`（`.body` 是 QVBoxLayout）。
    """

    def __init__(self, parent: QWidget | None = None, padding: int = METRIC["card_pad"],
                 radius: int = RADIUS["md"], variant: str = "default") -> None:
        super().__init__(parent)
        self._padding = int(padding)
        self._radius = int(radius)
        self._variant = variant
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.body = QVBoxLayout(self)
        self._apply_margins()
        self.body.setSpacing(SPACING["sm"])
        _bind_theme(self)

    def _apply_margins(self) -> None:
        m = self._padding
        self.body.setContentsMargins(m, m, m, m)

    def setPadding(self, padding: int) -> None:
        self._padding = int(padding)
        self._apply_margins()
        self.update()

    def padding(self) -> int:
        return self._padding

    def setRadius(self, radius: int) -> None:
        self._radius = int(radius)
        self.update()

    def setVariant(self, variant: str) -> None:
        """default | high | primary | outlined"""
        self._variant = variant
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        pal = _pal()
        bg = {
            "default": pal.surface_container,
            "high": pal.surface_container_high,
            "primary": pal.primary,
            "outlined": pal.surface_container,
        }.get(self._variant, pal.surface_container)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.fillPath(squircle_path(rect, self._radius), qcolor(bg))
        if self._variant == "outlined":
            painter.setPen(QPen(qcolor(pal.outline_variant), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(squircle_border_path(rect, self._radius, 1.0))


# --------------------------------------------------------------------------
# 按钮
# --------------------------------------------------------------------------
class MiuixButton(QPushButton):
    """Miuix 按钮：高 40、圆角 16、字 17/400。

    variant: `filled`（primary 实底）|`tonal`（浅蓝 container）|`secondary`（Miuix 默认灰）|
    `outlined`|`text`|`danger`。`icon` 同时支持图标名与 QIcon。
    """

    def __init__(self, text: str = "", parent: QWidget | None = None, variant: str = "filled",
                 icon: str | QIcon | None = None) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self._icon_size = ICON_SIZE["sm"]
        self._hover = False
        self._pressed = False
        self.setFont(font_for("button"))
        self.setMinimumHeight(METRIC["button_h"])
        self.setMinimumWidth(METRIC["button_min_w"])
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if icon is not None:
            self.setIcon(icon)
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        _bind_theme(self)

    def setVariant(self, variant: str) -> None:
        self._variant = variant
        self.update()

    def variant(self) -> str:
        return self._variant

    def setIcon(self, icon) -> None:  # noqa: N802
        """容忍字符串图标名与 QIcon。"""
        super().setIcon(_as_icon(icon, self._icon_size, self._icon_color()))

    def _icon_color(self) -> str:
        pal = _pal()
        if not self.isEnabled():
            return pal.disabled
        _, fg = _button_colors(self._variant, pal)
        return fg

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        bg, fg = _button_colors(self._variant, pal)
        enabled = self.isEnabled()
        if not enabled:
            if self._variant in ("filled", "tonal", "danger"):
                bg = pal.disabled_primary_button
                fg = pal.disabled_on_primary_button
            else:
                bg = pal.disabled_secondary_variant
                fg = pal.disabled_on_secondary_variant

        rect = QRectF(self.rect())
        radius = RADIUS["md"]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = squircle_path(rect, radius)

        if bg is not None:
            color = qcolor(bg)
            if enabled and self._hover:
                color = color.lighter(108)
            if enabled and self._pressed:
                color = color.darker(112)
            painter.fillPath(path, color)
        else:
            if enabled and (self._hover or self._pressed):
                painter.fillPath(path, with_alpha(fg, 0.10 if self._hover else 0.16))
            if self._variant == "outlined":
                border = pal.primary if (enabled and self._hover) else pal.outline
                painter.setPen(QPen(qcolor(border), 1.4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(squircle_border_path(rect, radius, 1.4))

        # 图标 + 文字手动排版（保证与 Miuix 的 16/13 内边距一致）
        text = self.text()
        icon = self.icon()
        font = self.font()
        painter.setFont(font)
        painter.setPen(qcolor(fg))
        fm = QFontMetrics(font)
        iw = self._icon_size if not icon.isNull() else 0
        gap = SPACING["sm"] if (iw and text) else 0
        tw = fm.horizontalAdvance(text) if text else 0
        x = (self.width() - (iw + gap + tw)) / 2.0
        if iw:
            icon.paint(painter, QRect(int(x), int((self.height() - iw) / 2.0), iw, iw))
            x += iw + gap
        if text:
            painter.drawText(QRectF(x, 0, tw + 2, self.height()),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)


class MiuixIconButton(QPushButton):
    """圆形图标按钮（默认 36，契约签名 size=36）。"""

    def __init__(self, icon_name: str, parent: QWidget | None = None, size: int = 36,
                 tooltip: str = "") -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._size = int(size)
        self._hover = False
        self._pressed = False
        self._manual_icon = False
        self.setFixedSize(self._size, self._size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(int(self._size * 0.55), int(self._size * 0.55)))
        if tooltip:
            self.setToolTip(tooltip)
        super().setIcon(icons.icon(icon_name, None, int(self._size * 0.55)))
        _bind_theme(self, self._on_theme)

    def _on_theme(self) -> None:
        if not self._manual_icon and self._icon_name:
            super().setIcon(icons.icon(self._icon_name, None, int(self._size * 0.55)))
        self.update()

    def setIconName(self, name: str) -> None:  # noqa: N802
        self._icon_name = name
        self._manual_icon = False
        super().setIcon(icons.icon(name, None, int(self._size * 0.55)))
        self.update()

    def setIcon(self, icon) -> None:  # noqa: N802
        """支持 QIcon / 图标名；手动设置后主题切换不再覆盖。"""
        if isinstance(icon, QIcon):
            self._manual_icon = not icon.isNull()
            super().setIcon(icon)
        else:
            super().setIcon(_as_icon(icon, int(self._size * 0.55)))
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        if self._hover or self._pressed:
            alpha = 0.12 if self._pressed else 0.07
            painter.fillPath(squircle_path(rect, rect.height() / 2.0), with_alpha(pal.on_surface, alpha))
        side = int(self._size * 0.55)
        # 手动设过图标就尊重调用方，否则按当前主题/禁用态重新取色
        icon = self.icon() if self._manual_icon else icons.icon(
            self._icon_name, None if self.isEnabled() else pal.disabled, side)
        if not icon.isNull():
            icon.paint(painter, QRect(int((self.width() - side) / 2.0), int((self.height() - side) / 2.0), side, side))


# --------------------------------------------------------------------------
# 输入控件
# --------------------------------------------------------------------------
class MiuixLineEdit(QLineEdit):
    """单行输入框：高 45、squircle 16、focus 时 primary 描边。"""

    def __init__(self, parent: QWidget | None = None, placeholder: str = "") -> None:
        super().__init__(parent)
        self._radius = RADIUS["md"]
        self._focus = False
        self.setMinimumHeight(METRIC["field_h"])
        self.setMinimumWidth(160)
        self.setFont(font_for("body1"))
        self.setPlaceholderText(placeholder)
        self.setFrame(False)
        _bind_theme(self)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._focus = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._focus = False
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        bg = pal.surface_container_highest if self.isEnabled() else pal.disabled_secondary
        painter.fillPath(squircle_path(rect, self._radius), qcolor(bg))
        width = 1.6 if self._focus else 1.0
        border = pal.primary if self._focus else pal.outline
        painter.setPen(QPen(qcolor(border), width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(squircle_border_path(rect, self._radius, width))
        painter.end()
        super().paintEvent(event)


class MiuixTextEdit(QPlainTextEdit):
    """多行文本域（底色/圆角由 QSS 提供，大矩形用 14px 圆弧近似 squircle）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(font_for("mono"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


class MiuixComboBox(QComboBox):
    """下拉框：高 45、squircle 16、右侧自绘 chevron。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._radius = RADIUS["md"]
        self._focus = False
        self.setMinimumHeight(METRIC["field_h"])
        self.setFont(font_for("body1"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaxVisibleItems(10)
        _bind_theme(self)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._focus = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._focus = False
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        bg = pal.surface_container_highest if self.isEnabled() else pal.disabled_secondary
        painter.fillPath(squircle_path(rect, self._radius), qcolor(bg))
        width = 1.6 if self._focus else 1.0
        border = pal.primary if self._focus else pal.outline
        painter.setPen(QPen(qcolor(border), width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(squircle_border_path(rect, self._radius, width))
        painter.end()
        super().paintEvent(event)
        side = ICON_SIZE["sm"]
        arrow = icons.icon("chevron_down", pal.on_surface_variant, side)
        painter2 = QPainter(self)
        painter2.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter2.drawPixmap(QRect(self.width() - side - 16, int((self.height() - side) / 2.0), side, side),
                            arrow.pixmap(side, side))
        painter2.end()


class MiuixSwitch(QCheckBox):
    """自绘胶囊开关：轨道 49×28、圆点 20、偏移 4→25、按压缩放 1.127、支持横向拖拽。"""

    switchPosition = Property(float, lambda self: self._pos, lambda self, v: self._set_pos(v))
    switchScale = Property(float, lambda self: self._scale, lambda self, v: self._set_scale(v))

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._pos = 0.0
        self._scale = 1.0
        self._drag_px = 0.0
        self._press_x: float | None = None
        self._dragging = False
        self._hover = False
        self.setFont(font_for("body1"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._pos_anim = QPropertyAnimation(self, b"switchPosition", self)
        self._pos_anim.setDuration(220)
        pos_curve = QEasingCurve(QEasingCurve.Type.OutBack)
        pos_curve.setOvershoot(1.2)  # 接近 Miuix spring(dampingRatio = 0.7, stiffness = 987)
        self._pos_anim.setEasingCurve(pos_curve)
        self._scale_anim = QPropertyAnimation(self, b"switchScale", self)
        self._scale_anim.setDuration(140)
        self._scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pos = 1.0 if self.isChecked() else 0.0
        self.toggled.connect(self._on_toggled)
        _bind_theme(self)

    # ---- 动画属性 ----
    def _set_pos(self, value: float) -> None:
        self._pos = float(value)
        self.update()

    def _set_scale(self, value: float) -> None:
        self._scale = float(value)
        self.update()

    def _animate_pos(self, target: float) -> None:
        self._pos_anim.stop()
        self._pos_anim.setStartValue(self._pos)
        self._pos_anim.setEndValue(float(target))
        self._pos_anim.start()

    def _animate_scale(self, target: float) -> None:
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self._scale)
        self._scale_anim.setEndValue(float(target))
        self._scale_anim.start()

    def _on_toggled(self, checked: bool) -> None:
        self._drag_px = 0.0
        self._animate_pos(1.0 if checked else 0.0)

    def checkStateSet(self) -> None:  # noqa: N802
        """setChecked 之后同步圆点位置。

        圆点位置是**动画属性** _pos，平时靠 toggled -> _animate_pos 推动。
        但用 blockSignals(True) + setChecked() 从配置恢复控件时（设置页就是这么干的），
        toggled 不会发、动画不会启动，_pos 就停在旧值 —— 开着的开关被画成关着。
        实测踩过：设置页「接收端」显示关闭，卡片下面却写着「运行中」。
        用户点击时信号没被挡，走原来的动画，不受影响。
        """
        super().checkStateSet()
        if self.signalsBlocked():
            self._pos_anim.stop()
            self._pos = 1.0 if self.isChecked() else 0.0
            self.update()

    # ---- 交互 ----
    def sizeHint(self) -> QSize:  # noqa: N802
        w = int(METRIC["switch_w"])
        if self.text():
            w += SPACING["sm"] + QFontMetrics(self.font()).horizontalAdvance(self.text()) + 2
        return QSize(w, int(METRIC["switch_h"]))

    def _track_rect(self) -> QRectF:
        h = METRIC["switch_h"]
        return QRectF(0.0, (self.height() - h) / 2.0, METRIC["switch_w"], h)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_x = event.position().x()
            self._drag_px = 0.0
            self._animate_scale(METRIC["switch_press_scale"])
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_x is None:
            super().mouseMoveEvent(event)
            return
        dx = event.position().x() - self._press_x
        if abs(dx) > 3:
            self._dragging = True
        # 拖拽位移除以 2 做阻尼（与 Miuix 一致）
        self._drag_px = max(-26.0, min(26.0, dx / 2.0))
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._press_x is None:
            super().mouseReleaseEvent(event)
            return
        dx = event.position().x() - self._press_x
        self._press_x = None
        if self._dragging:
            if abs(dx) > 6:
                self.setChecked(dx > 0)
            else:
                self.toggle()
        else:
            self.toggle()
        self._dragging = False
        self._drag_px = 0.0
        self._animate_scale(METRIC["switch_press_scale"] if self._hover else 1.0)
        self.update()
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._animate_scale(METRIC["switch_press_scale"])
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        if self._press_x is None:
            self._animate_scale(1.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = self._track_rect()
        enabled = self.isEnabled()

        off = float(METRIC["switch_off"])
        on = float(METRIC["switch_on"])
        left = off + self._pos * (on - off) + self._drag_px

        if enabled:
            track_color = blend(pal.secondary, pal.primary, self._pos)
            thumb_color = blend(pal.on_secondary, pal.on_primary, self._pos)
        else:
            track_color = blend(pal.disabled_secondary, pal.disabled_primary, self._pos)
            thumb_color = blend(pal.disabled_on_secondary, pal.disabled_on_primary, self._pos)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawPath(squircle_path(track, track.height() / 2.0))

        thumb_d = METRIC["switch_thumb"] * self._scale
        cx = left + METRIC["switch_thumb"] / 2.0
        cy = track.center().y()
        painter.setBrush(thumb_color)
        painter.drawEllipse(QPointF(cx, cy), thumb_d / 2.0, thumb_d / 2.0)

        text = self.text()
        if text:
            painter.setPen(qcolor(pal.on_surface if enabled else pal.disabled))
            painter.setFont(self.font())
            painter.drawText(
                QRectF(track.right() + SPACING["sm"], 0, self.width() - track.right() - SPACING["sm"], self.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )


class MiuixCheckBox(QCheckBox):
    """自绘圆形复选框（Miuix Checkbox 为 26dp 正圆）。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._hover = False
        self._box = float(METRIC["checkbox"])
        self.setFont(font_for("body1"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        _bind_theme(self)

    def sizeHint(self) -> QSize:  # noqa: N802
        w = int(self._box) + 2
        if self.text():
            w += SPACING["sm"] + QFontMetrics(self.font()).horizontalAdvance(self.text())
        return QSize(w, int(self._box) + 4)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self._box
        rect = QRectF(0.0, (self.height() - box) / 2.0, box, box)
        enabled = self.isEnabled()
        checked = self.isChecked()

        if checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(pal.primary if enabled else pal.disabled_primary))
            painter.drawEllipse(rect)
            pen = QPen(qcolor(pal.on_primary), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(rect.left() + box * 0.29, rect.top() + box * 0.52)
            path.lineTo(rect.left() + box * 0.44, rect.top() + box * 0.67)
            path.lineTo(rect.left() + box * 0.72, rect.top() + box * 0.34)
            painter.drawPath(path)
        else:
            ring = pal.outline
            if not enabled:
                ring = pal.disabled
            elif self._hover:
                ring = pal.primary
            painter.setPen(QPen(qcolor(ring), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(0.8, 0.8, -0.8, -0.8))

        text = self.text()
        if text:
            painter.setPen(qcolor(pal.on_surface if enabled else pal.disabled))
            painter.setFont(self.font())
            painter.drawText(
                QRectF(box + SPACING["sm"], 0, self.width() - box - SPACING["sm"], self.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )


# --------------------------------------------------------------------------
# 进度 / 滑块
# --------------------------------------------------------------------------
class MiuixProgressBar(QProgressBar):
    """自绘圆角进度条。`setValue(0..1000)`，对外读数用 `percent()`（0..100）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(int(METRIC["progress_h"]))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._busy = False
        self._busy_pos = 0.0
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(16)            # ~60fps，来回滑动
        self._busy_timer.timeout.connect(self._tick_busy)
        _bind_theme(self)

    def setBusy(self, busy: bool) -> None:  # noqa: N802
        """切换到不确定态（合并/混流阶段 RE 不给百分比时用）。"""
        busy = bool(busy)
        if busy == self._busy:
            return
        self._busy = busy
        if busy:
            self._busy_pos = 0.0
            self._busy_timer.start()
        else:
            self._busy_timer.stop()
        self.update()

    def isBusy(self) -> bool:  # noqa: N802
        return self._busy

    def _tick_busy(self) -> None:
        self._busy_pos = (self._busy_pos + 0.010) % 2.0
        self.update()

    def percent(self) -> float:
        """当前百分比 0..100。"""
        return self.value() / 10.0

    def setPercent(self, value: float) -> None:  # noqa: N802
        """按百分比设置（0..100）。"""
        self.setValue(max(0, min(1000, int(round(value * 10)))))

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = self.height()
        painter.fillPath(squircle_path(QRectF(0.0, 0.0, self.width(), h), h / 2.0),
                         qcolor(pal.slider_background))
        if self._busy:
            # 三角波往返：phase 0..2 → pos 0..1 → 0
            phase = self._busy_pos
            pos = phase if phase <= 1.0 else 2.0 - phase
            span = 0.30
            x = pos * (1.0 - span) * self.width()
            filled = QRectF(x, 0.0, max(float(h), span * self.width()), float(h))
            painter.fillPath(squircle_path(filled, h / 2.0), qcolor(pal.primary))
            return
        ratio = (self.value() - self.minimum()) / max(1.0, float(self.maximum() - self.minimum()))
        if ratio > 0:
            filled = QRectF(0.0, 0.0, max(float(h), self.width() * ratio), float(h))
            painter.fillPath(squircle_path(filled, h / 2.0), qcolor(pal.primary))


class MiuixSlider(QSlider):
    """自绘滑块：整根轨道是 28dp 粗的胶囊，圆点（20.16dp）画在胶囊内部。"""

    def __init__(self, parent: QWidget | None = None, orientation: Qt.Orientation = Qt.Orientation.Horizontal) -> None:
        super().__init__(orientation, parent)
        self._pressed = False
        self._hover = False
        self.setRange(0, 100)
        self.setValue(0)
        self.setFixedHeight(int(METRIC["slider_h"]))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        _bind_theme(self)

    # ---- 自管鼠标映射（不依赖 QStyle 的 groove/handle 几何） ----
    def _value_from_x(self, x: float) -> int:
        r = METRIC["slider_h"] / 2.0
        span = max(1.0, self.width() - 2 * r)
        ratio = max(0.0, min(1.0, (x - r) / span))
        return int(round(self.minimum() + ratio * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.setSliderDown(True)
            self.setValue(self._value_from_x(event.position().x()))
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._pressed:
            self.setValue(self._value_from_x(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._pressed:
            self._pressed = False
            self.setSliderDown(False)
            self.setValue(self._value_from_x(event.position().x()))
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        step = max(1, (self.maximum() - self.minimum()) // 20)
        self.setValue(self.value() + (step if event.angleDelta().y() > 0 else -step))
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = float(self.height())
        painter.fillPath(squircle_path(QRectF(0.0, 0.0, float(self.width()), h), h / 2.0),
                         qcolor(pal.slider_background))

        r = METRIC["slider_h"] / 2.0
        span = max(1.0, self.width() - 2 * r)
        ratio = (self.value() - self.minimum()) / max(1.0, float(self.maximum() - self.minimum()))
        cx = r + span * ratio

        filled = QRectF(0.0, 0.0, max(h, cx), h)
        fg = pal.primary if self.isEnabled() else pal.disabled_primary_slider
        painter.fillPath(squircle_path(filled, h / 2.0), qcolor(fg))
        if self._pressed:
            painter.fillPath(squircle_path(filled, h / 2.0), QColor(0, 0, 0, 11))  # 拖动时叠加 0.044 黑

        thumb_d = METRIC["slider_thumb"] * (1.06 if (self._hover or self._pressed) else 1.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(pal.on_primary if self.isEnabled() else pal.disabled_on_primary))
        painter.drawEllipse(QPointF(cx, h / 2.0), thumb_d / 2.0, thumb_d / 2.0)


# --------------------------------------------------------------------------
# 文本 / 结构
# --------------------------------------------------------------------------
class MiuixLabel(QLabel):
    """按 Miuix 文本样式渲染的标签。`style` 取 tokens.TEXT 的键名，`color` 可传 token 名。"""

    def __init__(self, text: str = "", style: str = "body1", color: str | QColor | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._style = style
        self._color = color
        self.setFont(font_for(style))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._apply_color()
        _bind_theme(self, self._on_theme)

    def _apply_color(self) -> None:
        self.setStyleSheet("color: %s;" % qss_color(_resolve_color(self._color, _pal())))

    def _on_theme(self) -> None:
        self._apply_color()
        self.update()

    def setTextStyle(self, style: str) -> None:  # noqa: N802
        self._style = style
        self.setFont(font_for(style))
        self.updateGeometry()

    def textStyle(self) -> str:  # noqa: N802
        return self._style

    def setColor(self, color: str | QColor | None) -> None:  # noqa: N802
        self._color = color
        self._apply_color()


class MiuixSectionHeader(QWidget):
    """分组小标题（Miuix SmallTitle：14sp / Bold，缩进对齐卡片内容）。"""

    def __init__(self, text: str, parent: QWidget | None = None, indent: int = SPACING["lg"]) -> None:
        super().__init__(parent)
        self._text = text
        self._indent = int(indent)
        self.setFont(font_for("subtitle"))
        self.setFixedHeight(SPACING["sm"] * 2 + 20)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        _bind_theme(self)

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text
        self.update()

    def text(self) -> str:
        return self._text

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(self.font())
        painter.setPen(qcolor(_pal().on_surface_variant))
        painter.drawText(
            QRectF(self._indent, 0, self.width() - self._indent, self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._text,
        )


class MiuixListItem(QWidget):
    """列表项（最小高 56、内边距 16、圆角 16，可带图标 / 副标题 / 右侧控件）。"""

    clicked = Signal()

    def __init__(self, title: str, subtitle: str = "", icon: str | QIcon | None = None,
                 trailing: QWidget | str | None = None, parent: QWidget | None = None,
                 chevron: bool = False, clickable: bool = True) -> None:
        super().__init__(parent)
        self._hover = False
        self._pressed = False
        self._clickable = clickable
        self._icon_src: str | QIcon | None = icon
        self.setMinimumHeight(int(METRIC["list_h"]))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        pad = int(METRIC["list_pad"])
        row = QHBoxLayout(self)
        row.setContentsMargins(pad, SPACING["md"], pad, SPACING["md"])
        row.setSpacing(SPACING["md"])

        self._icon_label: QLabel | None = None
        if icon is not None:
            self._icon_label = _icon_label(icon, ICON_SIZE["md"], _pal().on_surface_container_variant)
            row.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self._title = MiuixLabel(title, "main")
        self._subtitle = MiuixLabel(subtitle, "footnote1", "on_surface_variant")
        self._subtitle.setVisible(bool(subtitle))
        text_box.addWidget(self._title)
        text_box.addWidget(self._subtitle)
        row.addLayout(text_box, 1)

        self._trailing: QWidget | None = None
        if isinstance(trailing, str):
            self._trailing = MiuixLabel(trailing, "body2", "on_surface_variant")
        else:
            self._trailing = trailing
        if self._trailing is not None:
            row.addWidget(self._trailing, 0, Qt.AlignmentFlag.AlignVCenter)
        self._chevron: QLabel | None = None
        if chevron:
            self._chevron = _icon_label("chevron_right", ICON_SIZE["sm"], _pal().on_surface_variant_actions)
            row.addWidget(self._chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        _bind_theme(self, self._on_theme)

    def _on_theme(self) -> None:
        self._refresh_icons()
        self.update()

    def _refresh_icons(self) -> None:
        size = ICON_SIZE["md"]
        if self._icon_label is not None and self._icon_src is not None:
            self._icon_label.setPixmap(
                _as_icon(self._icon_src, size, _pal().on_surface_container_variant).pixmap(size, size))
        if self._chevron is not None:
            side = ICON_SIZE["sm"]
            self._chevron.setPixmap(
                icons.icon("chevron_right", _pal().on_surface_variant_actions, side).pixmap(side, side))

    def title(self) -> str:
        return self._title.text()

    def subtitle(self) -> str:
        return self._subtitle.text()

    def setSubtitle(self, text: str) -> None:  # noqa: N802
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def setTrailing(self, widget: QWidget | None) -> None:  # noqa: N802
        self._trailing = widget

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        was_pressed = self._pressed
        self._pressed = False
        self.update()
        if was_pressed and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not (self._hover or self._pressed):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        alpha = 0.10 if self._pressed else 0.05
        painter.fillPath(squircle_path(QRectF(self.rect()), RADIUS["md"]),
                         with_alpha(_pal().on_surface, alpha))


class MiuixSegmented(QWidget):
    """分段控件（TabRow 高度 42，选中项为滑动胶囊）。"""

    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[str] = []
        self._index = -1
        self._hover = -1
        self._indicator = 0.0
        self.setFont(font_for("main"))
        self.setFixedHeight(int(METRIC["tabrow_h"]))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"indicator", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        _bind_theme(self)

    indicator = Property(float, lambda self: self._indicator, lambda self, v: self._set_indicator(v))

    def _set_indicator(self, value: float) -> None:
        self._indicator = float(value)
        self.update()

    # ---- 数据 ----
    def addItem(self, text: str) -> int:  # noqa: N802
        self._items.append(text)
        if self._index < 0:
            self._index = 0
            self._indicator = 0.0
        self.setMinimumWidth(int(METRIC["seg_min_w"]) * len(self._items))
        self.update()
        return len(self._items) - 1

    def count(self) -> int:
        return len(self._items)

    def currentIndex(self) -> int:  # noqa: N802
        return self._index

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, int(index)))
        if index == self._index:
            return
        self._index = index
        self._animate_to(index)
        self.currentChanged.emit(index)

    def itemText(self, index: int) -> str:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else ""

    def _item_rect(self, index: int) -> QRectF:
        w = self.width() / max(1, len(self._items))
        return QRectF(index * w, 0.0, w, float(self.height()))

    def _index_at(self, x: float) -> int:
        n = max(1, len(self._items))
        return min(n - 1, max(0, int(x / max(1.0, self.width() / n))))

    def _animate_to(self, index: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._indicator)
        self._anim.setEndValue(float(index))
        self._anim.start()

    # ---- 交互 ----
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._items:
            self.setCurrentIndex(self._index_at(event.position().x()))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._items:
            return
        index = self._index_at(event.position().x())
        if index != self._hover:
            self._hover = index
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        pad = 3.0
        painter.fillPath(squircle_path(rect, rect.height() / 2.0), qcolor(pal.surface_container_highest))
        if self._index >= 0 and self._items:
            item_w = self.width() / len(self._items)
            x = pad + self._indicator * item_w
            pill = QRectF(x + pad / 2.0, pad, item_w - pad, self.height() - pad * 2)
            painter.fillPath(squircle_path(pill, pill.height() / 2.0), qcolor(pal.background))
        painter.setFont(self.font())
        for i, text in enumerate(self._items):
            selected = i == self._index
            painter.setPen(qcolor(pal.on_surface if selected else pal.on_surface_variant))
            painter.drawText(self._item_rect(i), int(Qt.AlignmentFlag.AlignCenter), text)


class MiuixScrollArea(QScrollArea):
    """无边框、透明背景、平滑滚动的滚动区域。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        _bind_theme(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        """透明背景：自身不画底，透出父级/页面底色。"""
        pass


class MiuixDivider(QWidget):
    """分隔线（Miuix Divider 厚 0.75dp，Qt 画不出亚像素实线 → 用 1px + 官方 dividerLine 色）。"""

    def __init__(self, parent: QWidget | None = None, inset: int = 0) -> None:
        super().__init__(parent)
        self._inset = int(inset)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _bind_theme(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        width = max(0, self.width() - self._inset * 2)
        painter.fillRect(QRect(self._inset, 0, width, 1), qcolor(_pal().divider_line))


class MiuixBadge(QLabel):
    """胶囊标签（tone: neutral | success | error | warning | primary）。"""

    def __init__(self, text: str, tone: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._tone = tone
        self.setFont(font_for("footnote1"))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        _bind_theme(self)

    def setTone(self, tone: str) -> None:  # noqa: N802
        self._tone = tone
        self.update()

    def _colors(self) -> tuple[QColor, QColor]:
        pal = _pal()
        tone = self._tone
        if tone == "success":
            return with_alpha(pal.success, 0.16), qcolor(pal.success)
        if tone == "error":
            return with_alpha(pal.error, 0.16), qcolor(pal.error)
        if tone == "warning":
            return with_alpha(pal.warning, 0.18), qcolor(pal.warning)
        if tone == "primary":
            return with_alpha(pal.primary, 0.16), qcolor(pal.primary)
        return qcolor(pal.secondary), qcolor(pal.on_secondary_variant)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + SPACING["md"] * 2, fm.height() + 6)

    def paintEvent(self, event) -> None:  # noqa: N802
        bg, fg = self._colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.fillPath(squircle_path(rect, rect.height() / 2.0), bg)
        painter.setPen(fg)
        painter.setFont(self.font())
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self.text())


class MiuixTopBar(QWidget):
    """顶部栏（折叠高 52、左右内边距 26、底色 surface）。"""

    backClicked = Signal()

    def __init__(self, title: str, back: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self.setFixedHeight(int(METRIC["topbar_h"]))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACING["page"], 0, SPACING["page"], 0)
        row.setSpacing(SPACING["sm"])
        self._row = row
        self._back_btn: MiuixIconButton | None = None
        if back:
            self._back_btn = MiuixIconButton("back", self, 36, "返回")
            self._back_btn.clicked.connect(self.backClicked.emit)
            row.addWidget(self._back_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._label = MiuixLabel(title, "main")
        row.addWidget(self._label, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        _bind_theme(self)

    def setTitle(self, title: str) -> None:  # noqa: N802
        self._title = title
        self._label.setText(title)

    def title(self) -> str:
        return self._title

    def addAction(self, widget: QWidget) -> None:  # noqa: N802
        """在右侧追加一个操作控件。"""
        self._row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), qcolor(_pal().surface))


class MiuixNavRail(QWidget):
    """左侧导航栏（展开宽 240、项高 52、选中为圆角 16 的浅蓝胶囊）。"""

    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None, title: str = "") -> None:
        super().__init__(parent)
        self._items: list[tuple[str, str]] = []
        self._index = -1
        self._hover = -1
        self._press = -1
        self._title = title
        self._item_h = 52
        self._top = 24 + (36 if title else 0)
        self.setFixedWidth(int(METRIC["rail_w"]))
        self.setFont(font_for("body1"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        _bind_theme(self)

    # ---- 数据 ----
    def addItem(self, icon_name: str, text: str) -> int:  # noqa: N802
        self._items.append((icon_name, text))
        if self._index < 0:
            self._index = 0
        self.update()
        return len(self._items) - 1

    def count(self) -> int:
        return len(self._items)

    def currentIndex(self) -> int:  # noqa: N802
        return self._index

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, int(index)))
        if index == self._index:
            return
        self._index = index
        self.update()
        self.currentChanged.emit(index)

    def _item_rect(self, index: int) -> QRectF:
        return QRectF(SPACING["md"], self._top + index * self._item_h,
                      self.width() - SPACING["md"] * 2, self._item_h - 4)

    def _index_at(self, y: float) -> int:
        for i in range(len(self._items)):
            if self._item_rect(i).contains(QPointF(self.width() / 2.0, y)):
                return i
        return -1

    # ---- 交互 ----
    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._press = self._index_at(event.position().y())
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position().y())
        if index != self._hover:
            self._hover = index
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position().y())
        self._press = -1
        if index >= 0:
            self.setCurrentIndex(index)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self._press = -1
        self.update()
        super().leaveEvent(event)

    # ---- 绘制 ----
    def paintEvent(self, event) -> None:  # noqa: N802
        pal = _pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), qcolor(pal.surface))
        # 桌面端补一条 1px 分隔线（Miuix 移动端靠 Scaffold 同色，桌面窗口需要边界）
        painter.fillRect(QRect(self.width() - 1, 0, 1, self.height()), qcolor(pal.divider_line))

        if self._title:
            painter.setFont(font_for("title4"))
            painter.setPen(qcolor(pal.on_surface))
            painter.drawText(QRectF(SPACING["xl"], 24, self.width() - SPACING["xl"] * 2, 36),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self._title)

        for i, (icon_name, text) in enumerate(self._items):
            rect = self._item_rect(i)
            selected = i == self._index
            if selected:
                painter.fillPath(squircle_path(rect, RADIUS["md"]), qcolor(pal.tertiary_container))
            elif i == self._hover:
                painter.fillPath(squircle_path(rect, RADIUS["md"]),
                                 with_alpha(pal.on_surface, 0.10 if i == self._press else 0.05))

            color = pal.on_tertiary_container if selected else pal.on_surface_variant
            side = ICON_SIZE["lg"]
            ic = icons.icon(icon_name, color, side)
            painter.drawPixmap(QRect(int(rect.left() + 14), int(rect.center().y() - side / 2.0), side, side),
                               ic.pixmap(side, side))

            painter.setFont(self.font())
            painter.setPen(qcolor(color))
            painter.drawText(
                QRectF(rect.left() + 14 + side + SPACING["lg"], rect.top(), rect.width() - 30 - side, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )


# --------------------------------------------------------------------------
# 对话框 / 提示
# --------------------------------------------------------------------------


class MiuixDialog(QDialog):
    """圆角无边框对话框基类（squircle 28，内边距 24）。"""

    def __init__(self, parent: QWidget | None = None, title: str = "") -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self._radius = RADIUS["lg"]
        self._pad = SPACING["xl"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._pad, self._pad, self._pad, self._pad)
        outer.setSpacing(SPACING["lg"])
        self._title_label: MiuixLabel | None = None
        if title:
            self._title_label = MiuixLabel(title, "title4")
            outer.addWidget(self._title_label)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(SPACING["md"])
        outer.addLayout(self._body, 1)
        self._buttons = QHBoxLayout()
        self._buttons.setContentsMargins(0, 0, 0, 0)
        self._buttons.setSpacing(SPACING["md"])
        self._buttons.addStretch(1)
        outer.addLayout(self._buttons)
        _bind_theme(self)

    def setTitle(self, title: str) -> None:  # noqa: N802
        if self._title_label is None:
            self._title_label = MiuixLabel(title, "title4")
            self.layout().insertWidget(0, self._title_label)
        else:
            self._title_label.setText(title)

    def setBodyLayout(self, layout) -> None:  # noqa: N802
        """把调用方的布局挂到对话框主体区。"""
        self._body.addLayout(layout)

    def addButton(self, text: str, variant: str = "filled") -> MiuixButton:  # noqa: N802
        """在右下角追加一个按钮并返回（调用方可直接连 clicked）。"""
        button = MiuixButton(text, self, variant)
        self._buttons.addWidget(button)
        return button

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(squircle_path(QRectF(self.rect()), self._radius), qcolor(_pal().surface_container))


_toasts: list["_Toast"] = []


class _Toast(QWidget):
    """顶部淡入淡出提示（内部实现，请用 `toast()`）。"""

    def __init__(self, parent: QWidget, text: str, tone: str) -> None:
        super().__init__(parent)
        self._label = MiuixBadge(text, tone, self)
        self._label.setFont(font_for("body2"))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)

    def _layout_toast(self) -> None:
        hint = self._label.sizeHint()
        w = hint.width() + SPACING["lg"]
        h = max(hint.height() + SPACING["sm"], 34)
        self._label.setGeometry(0, 0, w, h)
        parent = self.parentWidget()
        x = int((parent.width() - w) / 2) if parent else 0
        self.setGeometry(max(0, x), SPACING["xl"], w, h)

    def show_message(self, duration_ms: int = 2200) -> None:
        self._layout_toast()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._cleanup)
        self._anim.start()

    def _cleanup(self) -> None:
        try:
            self._anim.finished.disconnect(self._cleanup)
        except Exception:
            pass
        if self in _toasts:
            _toasts.remove(self)
        self.hide()
        self.deleteLater()


def toast(parent: QWidget, text: str, tone: str = "neutral") -> None:
    """在 parent 顶部居中淡入淡出一条提示；`tone` 同 MiuixBadge。"""
    if parent is None:
        return
    tip = _Toast(parent, text, tone)
    _toasts.append(tip)
    tip.show_message()