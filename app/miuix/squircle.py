"""Squircle（连续曲率圆角 / 超椭圆圆角）路径。

算法逐字翻译自 miuix 源码 `SquirclePath.kt`（见 docs/MIUIX_TOKENS.md §5.3）：

    tile   = min(cornerRadius × 1.1, min(width, height) / 2)
    handle = tile × (1 − 0.643)

QSS 的 `border-radius` 只能画四分之一圆弧、且**不裁剪子控件**，
所以 Card / Button / 输入框 / 卡片描边一律走本模块的 `QPainterPath`。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF
from PySide6.QtGui import QPainterPath

#: 官方 SquircleDefaults.Extension
EXTENSION: float = 1.1
#: 官方 SQUIRCLE_CONTROL：控制柄长度比例
CONTROL: float = 0.643


def squircle_path(rect: QRectF | QRect, radius: float, extension: float = EXTENSION) -> QPainterPath:
    """构造 squircle 路径。

    :param rect: 目标矩形（QRectF 或 QRect）
    :param radius: Miuix 圆角值（如 Card = 16）
    :param extension: 角部区域倍数，官方默认 1.1；1.0 等价于普通圆弧
    """
    r = QRectF(rect)
    w, h = r.width(), r.height()
    path = QPainterPath()
    if w <= 0 or h <= 0:
        return path
    limit = min(w, h) / 2.0
    if radius <= 0.5:
        path.addRect(r)
        return path
    if extension <= 1.0:
        rr = min(radius, limit)
        path.addRoundedRect(r, rr, rr)
        return path

    tile = min(radius * extension, limit)
    handle = tile * (1.0 - CONTROL)

    x0, y0 = r.left(), r.top()
    x1, y1 = r.right(), r.bottom()
    path.moveTo(x0 + tile, y0)
    path.lineTo(x1 - tile, y0)
    path.cubicTo(x1 - handle, y0, x1, y0 + handle, x1, y0 + tile)
    path.lineTo(x1, y1 - tile)
    path.cubicTo(x1, y1 - handle, x1 - handle, y1, x1 - tile, y1)
    path.lineTo(x0 + tile, y1)
    path.cubicTo(x0 + handle, y1, x0, y1 - handle, x0, y1 - tile)
    path.lineTo(x0, y0 + tile)
    path.cubicTo(x0, y0 + handle, x0 + handle, y0, x0 + tile, y0)
    path.closeSubpath()
    return path


def squircle_path_xy(x: float, y: float, w: float, h: float, radius: float,
                     extension: float = EXTENSION) -> QPainterPath:
    """便捷重载：直接给左上角与尺寸。"""
    return squircle_path(QRectF(x, y, w, h), radius, extension)


def squircle_border_path(rect: QRectF | QRect, radius: float, line_width: float,
                         extension: float = EXTENSION) -> QPainterPath:
    """构造描边路径：整体内缩半个线宽。

    与 Miuix `squircleBorder` 行为一致（描边不会溢出边界被裁掉一半），
    且必须基于 path 描边，否则 QSS 沿圆弧裁剪会出现断线。
    """
    half = line_width / 2.0
    inner = QRectF(rect).adjusted(half, half, -half, -half)
    if inner.width() <= 0 or inner.height() <= 0:
        return QPainterPath()
    return squircle_path(inner, max(radius - half, 0.0), extension)


def squircle_center(rect: QRectF | QRect) -> QPointF:
    """矩形中心点（自绘控件常用）。"""
    return QRectF(rect).center()
