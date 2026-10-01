"""内联 SVG 图标集（复刻 Miuix 图标观感）。

不依赖任何图标文件：每个图标是 24×24 网格上的内联 SVG 片段，
用 ``QSvgRenderer`` 渲染成 ``QPixmap``（``PySide6.QtSvg`` 随 pyside6-essentials 提供）。

风格：描边式圆头线条（stroke-width 1.9，round cap/join），与 Miuix 图标的圆润观感一致。
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24×24 网格上的图标主体；{c} 为当前颜色占位符
_ICONS: dict[str, str] = {
    "download": '<path d="M12 3.6v11"/><path d="M7.2 10.2 12 15l4.8-4.8"/><path d="M4.6 19.6h14.8"/>',
    "list": (
        '<circle cx="5" cy="6.5" r="1.3" fill="{c}" stroke="none"/>'
        '<circle cx="5" cy="12" r="1.3" fill="{c}" stroke="none"/>'
        '<circle cx="5" cy="17.5" r="1.3" fill="{c}" stroke="none"/>'
        '<path d="M9.6 6.5h9.8M9.6 12h9.8M9.6 17.5h9.8"/>'
    ),
    "settings": (
        '<path d="M4 7.6h4.7M13.3 7.6H20"/><circle cx="11" cy="7.6" r="2.4"/>'
        '<path d="M4 16.4h8.7M17.3 16.4H20"/><circle cx="15" cy="16.4" r="2.4"/>'
    ),
    "info": '<circle cx="12" cy="12" r="8.6"/><path d="M12 11.2v5"/>'
            '<circle cx="12" cy="7.9" r="1" fill="{c}" stroke="none"/>',
    "play": '<path d="M8.6 5.5v13a.85.85 0 0 0 1.3.72l10.1-6.5a.85.85 0 0 0 0-1.44L9.9 4.78a.85.85 0 0 0-1.3.72z" fill="{c}" stroke="none"/>',
    "pause": '<rect x="7.6" y="5.2" width="3.4" height="13.6" rx="1.7" fill="{c}" stroke="none"/>'
             '<rect x="13" y="5.2" width="3.4" height="13.6" rx="1.7" fill="{c}" stroke="none"/>',
    "stop": '<rect x="5.8" y="5.8" width="12.4" height="12.4" rx="3.8" fill="{c}" stroke="none"/>',
    "trash": '<path d="M4.5 6.6h15"/>'
             '<path d="M9.5 6.6V5.2a1.7 1.7 0 0 1 1.7-1.7h1.6a1.7 1.7 0 0 1 1.7 1.7v1.4"/>'
             '<path d="M6.6 6.6l.86 12.1a1.8 1.8 0 0 0 1.8 1.7h5.48a1.8 1.8 0 0 0 1.8-1.7l.86-12.1"/>'
             '<path d="M10.3 10.6v6M13.7 10.6v6"/>',
    "folder": '<path d="M3.6 7.6a2.1 2.1 0 0 1 2.1-2.1h3l2.1 2.6h7.5a2.1 2.1 0 0 1 2.1 2.1v7.6a2.1 2.1 0 0 1-2.1 2.1H5.7a2.1 2.1 0 0 1-2.1-2.1z"/>',
    "link": '<path d="M10.2 13.8a4.1 4.1 0 0 0 6.2.44l2.2-2.2a4.1 4.1 0 0 0-5.8-5.8L11.55 7.5"/>'
            '<path d="M13.8 10.2a4.1 4.1 0 0 0-6.2-.44l-2.2 2.2a4.1 4.1 0 0 0 5.8 5.8L12.45 16.5"/>',
    "check": '<path d="M4.8 12.6 9.6 17.4 19.2 6.8"/>',
    "close": '<path d="M6.2 6.2 17.8 17.8M17.8 6.2 6.2 17.8"/>',
    "chevron_right": '<path d="M9.4 5.8 15.6 12l-6.2 6.2"/>',
    "chevron_left": '<path d="M14.6 5.8 8.4 12l6.2 6.2"/>',
    "chevron_down": '<path d="M5.8 9.4 12 15.6l6.2-6.2"/>',
    "chevron_up": '<path d="M5.8 14.6 12 8.4l6.2 6.2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "refresh": '<path d="M20.2 12a8.2 8.2 0 1 1-2.4-5.85"/><path d="M20.6 4.2v4.7h-4.7"/>',
    "sun": '<circle cx="12" cy="12" r="4.1"/>'
           '<path d="M12 2.6v2.2M12 19.2v2.2M4.6 12H2.4M21.6 12h-2.2M6.7 6.7 5.2 5.2M18.8 18.8l-1.5-1.5M17.3 6.7l1.5-1.5M5.2 18.8l1.5-1.5"/>',
    "moon": '<path d="M20.4 14.6A8.7 8.7 0 0 1 9.4 3.6a8.7 8.7 0 1 0 11 11z"/>',
    "copy": '<rect x="8.4" y="8.4" width="11.6" height="11.6" rx="2.6"/>'
            '<path d="M15.6 5.6A2.2 2.2 0 0 0 13.4 4H6.2A2.2 2.2 0 0 0 4 6.2v7.2a2.2 2.2 0 0 0 1.6 2.1"/>',
    "alert": '<path d="M10.6 4.9 2.9 18.3a1.6 1.6 0 0 0 1.4 2.4h15.4a1.6 1.6 0 0 0 1.4-2.4L13.4 4.9a1.6 1.6 0 0 0-2.8 0z"/>'
             '<path d="M12 9.4v4.4"/><circle cx="12" cy="17" r="1" fill="{c}" stroke="none"/>',
    "search": '<circle cx="11" cy="11" r="6.4"/><path d="M15.7 15.7 20.4 20.4"/>',
    "film": '<rect x="3.4" y="4.6" width="17.2" height="14.8" rx="2.4"/>'
            '<path d="M8 4.6v14.8M16 4.6v14.8M3.4 9.2h4.6M3.4 14.8h4.6M16 9.2h4.6M16 14.8h4.6"/>',
    "music": '<path d="M9.2 18.2V6.6l10-2.1v11.6"/>'
             '<ellipse cx="6.6" cy="18.4" rx="2.6" ry="2.4"/><ellipse cx="16.6" cy="16.1" rx="2.6" ry="2.4"/>',
    "subtitles": '<rect x="3.4" y="5.2" width="17.2" height="13.6" rx="2.8"/>'
                 '<path d="M7 12.2h4.6M14.2 12.2H17M7 15.4h7.4"/>',
    "clock": '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.2v5l3.4 2"/>',
    "speed": '<path d="M3.6 17.6a8.6 8.6 0 1 1 16.8 0"/><path d="M12 17.2 15.9 11"/>'
             '<circle cx="12" cy="17.4" r="1.2" fill="{c}" stroke="none"/>',
    "shield": '<path d="M12 3.4 19.2 6v6.1c0 4.2-3 7.6-7.2 8.7-4.2-1.1-7.2-4.5-7.2-8.7V6z"/>',
    "file": '<path d="M13.6 3.4H6.9a1.9 1.9 0 0 0-1.9 1.9v13.4a1.9 1.9 0 0 0 1.9 1.9h10.2a1.9 1.9 0 0 0 1.9-1.9V8.8z"/>'
            '<path d="M13.6 3.4v5.4h5.4"/>',
    "key": '<circle cx="7.6" cy="16.4" r="3.6"/><path d="M10.2 13.8 19.4 4.6"/>'
           '<path d="M16.4 7.6 18.6 9.8M18.8 5.2 21 7.4"/>',
    "tools": '<path d="M14.1 3.6a5.1 5.1 0 0 0-4.68 7.15L3.9 16.27a2.1 2.1 0 0 0 2.97 2.97l5.52-5.52A5.1 5.1 0 0 0 19.6 7.6l-3.1 3.1-2.7-2.7 3.1-3.1a5.1 5.1 0 0 0-2.8-1.3z"/>',
    "external": '<path d="M13.8 4.2h6v6"/><path d="M19.8 4.2 10.6 13.4"/>'
                '<path d="M18 14.4v4.2a1.8 1.8 0 0 1-1.8 1.8H5.4a1.8 1.8 0 0 1-1.8-1.8V7.8A1.8 1.8 0 0 1 5.4 6h4.2"/>',
    # 补充图标（导航 / 菜单常用）
    "edit": '<path d="M4.5 19.5h4.2L19.2 9a2.4 2.4 0 0 0-3.4-3.4L5.3 16.1z"/>',
    "more": ('<circle cx="5.6" cy="12" r="1.7" fill="{c}" stroke="none"/>'
             '<circle cx="12" cy="12" r="1.7" fill="{c}" stroke="none"/>'
             '<circle cx="18.4" cy="12" r="1.7" fill="{c}" stroke="none"/>'),
    "home": '<path d="M3.8 10.4 12 3.6l8.2 6.8v8.1a1.9 1.9 0 0 1-1.9 1.9H5.7a1.9 1.9 0 0 1-1.9-1.9z"/>'
            '<path d="M9.6 20.4v-6.2h4.8v6.2"/>',
    "back": '<path d="M19.5 12H5.2"/><path d="M11.2 5.4 4.6 12l6.6 6.6"/>',
}

#: 契约要求必须支持的图标名集合
ICON_NAMES: set[str] = set(_ICONS)

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
    'fill="none" stroke="{c}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" '
    'stroke-opacity="{o}">{body}</svg>'
)

_cache: dict[tuple[str, str, int, int], QIcon] = {}


def _split_color(color: str) -> tuple[str, float]:
    """把 `#AARRGGBB` / `#RRGGBB` 拆成 SVG 可用的 `#RRGGBB` + 不透明度。"""
    c = QColor(color)
    if not c.isValid():
        c = QColor("#000000")
    return c.name(QColor.NameFormat.HexRgb), c.alphaF()


def _default_color() -> str:
    """未指定颜色时取当前主题的 on_surface（未初始化主题则用浅色主题）。"""
    try:
        from . import tokens
        from .theme import has_theme, theme

        return theme().palette.on_surface if has_theme() else tokens.LIGHT.on_surface
    except Exception:  # pragma: no cover - 主题模块异常时不应影响图标
        return "#000000"


def svg_source(name: str, color: str | None = None) -> str:
    """返回某个图标的完整 SVG 源码（调试/测试用）。"""
    body = _ICONS.get(name, _ICONS["file"])
    hex_color, opacity = _split_color(color or _default_color())
    return _SVG_TEMPLATE.format(c=hex_color, o="%.3f" % opacity, body=body.replace("{c}", hex_color))


def icon_pixmap(name: str, color: str | None = None, size: int = 20, dpr: int = 2) -> QPixmap:
    """渲染成 `dpr` 倍的 `QPixmap`（默认 2×，保证高分屏锐利）。"""
    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_source(name, color).encode("utf-8")))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(float(dpr))
    return pm


def icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    """按名字取图标；`color=None` 时使用当前主题的 `on_surface`。"""
    resolved = color or _default_color()
    key = (name, resolved, int(size), 2)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    result.addPixmap(icon_pixmap(name, resolved, size, dpr=2))
    result.addPixmap(icon_pixmap(name, resolved, size, dpr=1))
    _cache[key] = result
    return result


def clear_cache() -> None:
    """清空图标缓存（主题切换后由 theme 调用，避免旧颜色残留）。"""
    _cache.clear()
