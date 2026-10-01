"""Miuix 主题管理：ThemeManager + QSS 生成 + 字体回退。

契约见 docs/INTERFACES.md §3.2。主题切换流程：
    set_mode() → 重新计算 palette/dark → apply()（setStyleSheet + setFont + setPalette）→ changed.emit()

所有自绘控件都必须连接 `theme().changed` 并 update()（`widgets` 模块内已统一处理）。
"""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from .tokens import DARK, FONT_STACK, LIGHT, MONO_STACK, TEXT, Palette, TextStyle

_instance: "ThemeManager | None" = None

#: 开发机/受限环境下用于补全中文字体的候选字体文件（Windows 正式环境本身自带字体，不依赖它）
_FONT_FILE_CANDIDATES: list[str] = [
    "MiSans-Regular.ttf",
    "MiSans VF.ttf",
    "MiSans-Medium.ttf",
    "msyh.ttc",
    "NotoSansSC-VF.ttf",
    "NotoSansSC-Regular.otf",
    "SourceHanSansSC-Regular.otf",
    "wqy-microhei.ttc",
    "NotoSansCJK-Regular.ttc",
]


def _font_dirs() -> list[Path]:
    """可能存放字体文件的目录（Windows 字体目录 + 常见 Linux 路径 + 项目 assets）。"""
    dirs: list[Path] = [Path(__file__).resolve().parent / "assets"]
    windir = os.environ.get("WINDIR")
    if windir:
        dirs.append(Path(windir) / "Fonts")
    dirs += [
        Path("C:/Windows/Fonts"),
        Path("/mnt/c/Windows/Fonts"),
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts/truetype/wqy"),
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
    ]
    return dirs


def _resolve_families() -> list[str]:
    """返回实际可用的字体族列表（按 FONT_STACK 优先级过滤）。

    中文字体在 WSL/offscreen 环境下常常缺失，会渲染成方框；
    这里做一次 best-effort 的字体加载（缺字体时静默跳过，不影响 Windows 正式运行）。
    """
    have = set(QFontDatabase.families())
    for directory in _font_dirs():
        if not directory.is_dir():
            continue
        for name in _FONT_FILE_CANDIDATES:
            path = directory / name
            if not path.is_file():
                continue
            try:
                fid = QFontDatabase.addApplicationFont(str(path))
            except Exception:
                continue
            if fid != -1:
                have.update(QFontDatabase.applicationFontFamilies(fid))
    available = [f for f in FONT_STACK if f in have]
    # 兜底：一个中文字体都没有时把系统全部字体附在后面，避免中文变方框
    if not available:
        available = FONT_STACK
    extras = [f for f in ("Noto Sans SC", "Microsoft YaHei UI", "DejaVu Sans") if f in have and f not in available]
    return available + extras


def _system_dark(app: QApplication) -> bool:
    """跟随系统深浅色。"""
    try:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except Exception:
        pass
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


# --------------------------------------------------------------------------
# 颜色 / 字体工具
# --------------------------------------------------------------------------
def qcolor(value: str | QColor) -> QColor:
    """把 token 字符串转成 QColor（支持 `#AARRGGBB`）。"""
    return QColor(value) if isinstance(value, str) else QColor(value)


def qss_color(value: str | QColor) -> str:
    """把 token 转成 QSS 可用的颜色串（带 alpha 必须用 rgba()，Qt 的 #AARRGGBB 在 QSS 里无效）。"""
    c = qcolor(value)
    if not c.isValid():
        return "transparent"
    if c.alpha() == 255:
        return "#%02X%02X%02X" % (c.red(), c.green(), c.blue())
    return "rgba(%d, %d, %d, %.3f)" % (c.red(), c.green(), c.blue(), c.alphaF())


def blend(a: str | QColor, b: str | QColor, t: float) -> QColor:
    """线性混色：t=0 → a，t=1 → b（保留 a 的 alpha）。"""
    ca, cb = qcolor(a), qcolor(b)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
        ca.alpha(),
    )


def with_alpha(value: str | QColor, alpha: float) -> QColor:
    """覆盖 alpha（0..1）。"""
    c = qcolor(value)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def font_for(style: str = "body1", weight: int | None = None, mono: bool = False) -> QFont:
    """按文本样式名构造 QFont（px 字号，不用 pt，避免 DPI 误差）。"""
    ts: TextStyle = TEXT.get(style, TEXT["body1"])
    fams = MONO_STACK if (mono or style == "mono") else families()
    f = QFont()
    f.setFamilies(fams)
    f.setPixelSize(ts.size)
    f.setWeight(QFont.Weight(weight if weight is not None else ts.weight))
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def families() -> list[str]:
    """当前可用字体族（已按优先级解析）。"""
    return _instance.families if _instance is not None else list(FONT_STACK)


# --------------------------------------------------------------------------
# ThemeManager
# --------------------------------------------------------------------------
class ThemeManager(QObject):
    """主题管理器（单例由 `init_theme` 创建）。"""

    changed = Signal()

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._mode = "system"
        self._families = _resolve_families()
        self._dark = _system_dark(app)
        hints = app.styleHints()
        try:
            hints.colorSchemeChanged.connect(self._on_system_scheme)
        except Exception:  # pragma: no cover - 老版本 Qt 无此信号
            pass

    # ---- 只读属性 ----
    @property
    def palette(self) -> Palette:
        return DARK if self._dark else LIGHT

    @property
    def dark(self) -> bool:
        return self._dark

    @property
    def families(self) -> list[str]:
        return list(self._families)

    def mode(self) -> str:
        return self._mode

    # ---- 主题切换 ----
    def set_mode(self, mode: str) -> None:
        """`"system"` | `"light"` | `"dark"`；触发 changed 并重新 apply。"""
        if mode not in ("system", "light", "dark"):
            raise ValueError("mode 必须是 'system' | 'light' | 'dark'，收到 %r" % (mode,))
        old_dark = self._dark
        changed_mode = mode != self._mode
        self._mode = mode
        self._dark = _system_dark(self._app) if mode == "system" else (mode == "dark")
        if not changed_mode and self._dark == old_dark:
            return
        self.apply()
        self.changed.emit()

    def toggle(self) -> str:
        """在 light / dark 之间切换，返回新模式（便捷方法）。"""
        self.set_mode("light" if self._dark else "dark")
        return self._mode

    def _on_system_scheme(self, *_: object) -> None:
        if self._mode != "system":
            return
        dark = _system_dark(self._app)
        if dark == self._dark:
            return
        self._dark = dark
        self.apply()
        self.changed.emit()

    # ---- 应用 ----
    def apply(self) -> None:
        """把当前主题写入 QApplication（样式表 + 字体 + 调色板）。"""
        self._app.setPalette(self._build_palette())
        self._app.setFont(font_for("body1"))
        self._app.setStyleSheet(self.qss())
        try:
            from . import icons

            icons.clear_cache()
        except Exception:  # pragma: no cover
            pass

    def _build_palette(self) -> QPalette:
        """原生 QPalette（下拉弹窗、原生控件等 QSS 覆盖不到的地方）。"""
        p = self.palette
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, qcolor(p.surface))
        pal.setColor(QPalette.ColorRole.WindowText, qcolor(p.on_surface))
        pal.setColor(QPalette.ColorRole.Base, qcolor(p.surface_container))
        pal.setColor(QPalette.ColorRole.AlternateBase, qcolor(p.surface_container_high))
        pal.setColor(QPalette.ColorRole.Text, qcolor(p.on_surface))
        pal.setColor(QPalette.ColorRole.Button, qcolor(p.surface_container))
        pal.setColor(QPalette.ColorRole.ButtonText, qcolor(p.on_surface))
        pal.setColor(QPalette.ColorRole.Highlight, qcolor(p.primary))
        pal.setColor(QPalette.ColorRole.HighlightedText, qcolor(p.on_primary))
        pal.setColor(QPalette.ColorRole.ToolTipBase, qcolor(p.surface_container))
        pal.setColor(QPalette.ColorRole.ToolTipText, qcolor(p.on_surface))
        pal.setColor(QPalette.ColorRole.PlaceholderText, qcolor(p.on_surface_variant))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, qcolor(p.disabled))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, qcolor(p.disabled))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, qcolor(p.disabled))
        return pal

    def qss(self) -> str:
        """生成当前主题的 QSS（每次调用重新生成，供切换主题后 setStyleSheet）。"""
        p = self.palette
        t: dict[str, str] = {k: qss_color(v) for k, v in asdict(p).items()}
        t["scroll_handle"] = qss_color(with_alpha(p.on_surface_variant_actions, 0.55))
        t["scroll_handle_hover"] = qss_color(with_alpha(p.on_surface_variant, 0.75))
        t["input_bg"] = qss_color(p.surface_container_highest)
        t["input_border"] = qss_color(p.outline)
        t["hover_bg"] = qss_color(p.surface_container_high)
        return _QSS_TEMPLATE % t


# QSS：只写「结构性 / 原生控件」样式。所有 Miuix 自绘控件（Card/Button/Switch/...）在 paintEvent 里
# 用 squircle 路径绘制，不依赖 QSS 的 border-radius（无法做出连续曲率，也不会裁剪子控件）。
#
# 注意：QSS 的 font-* 属性会覆盖 widget.setFont()，因此这里**不设置全局字体**，
# 字体统一由 theme.font_for() + widget.setFont() 控制，只在弹窗等原生子控件上限定字号。
_QSS_TEMPLATE = """
/* ---------- 基础 ---------- */
QWidget { color: %(on_surface)s; }
QMainWindow, QDialog { background-color: %(surface)s; }
QStackedWidget { background: transparent; }
QLabel { background: transparent; }
QToolTip {
    background-color: %(surface_container)s;
    color: %(on_surface)s;
    border: 1px solid %(outline_variant)s;
    border-radius: 8px;
    padding: 6px 10px;
}
QMenu {
    background-color: %(surface_container)s;
    border: 1px solid %(outline_variant)s;
    border-radius: 13px;
    padding: 6px;
}
QMenu::item { padding: 7px 18px; border-radius: 8px; color: %(on_surface)s; }
QMenu::item:selected { background-color: %(tertiary_container)s; color: %(on_tertiary_container)s; }
QMenu::separator { height: 1px; background: %(divider_line)s; margin: 6px 10px; }

/* ---------- 滚动区域 / 滚动条 ---------- */
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QAbstractScrollArea::corner { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px 2px 2px 0; }
QScrollBar::handle:vertical { background: %(scroll_handle)s; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: %(scroll_handle_hover)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: transparent; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 2px 2px 2px; }
QScrollBar::handle:horizontal { background: %(scroll_handle)s; border-radius: 4px; min-width: 36px; }
QScrollBar::handle:horizontal:hover { background: %(scroll_handle_hover)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; background: transparent; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ---------- 输入控件（背景 + 圆角在 paintEvent 里用 squircle 自绘） ---------- */
QLineEdit.MiuixLineEdit, QComboBox.MiuixComboBox {
    background: transparent;
    border: none;
    padding: 0 16px;
    color: %(on_surface)s;
    selection-background-color: %(primary)s;
    selection-color: %(on_primary)s;
}
QPlainTextEdit.MiuixTextEdit {
    background-color: %(input_bg)s;
    color: %(on_surface)s;
    border: 1px solid %(input_border)s;
    border-radius: 18px;
    padding: 10px 12px;
    selection-background-color: %(primary)s;
    selection-color: %(on_primary)s;
}
QPlainTextEdit.MiuixTextEdit:focus { border: 2px solid %(primary)s; }
QComboBox.MiuixComboBox { padding-right: 44px; }
QComboBox.MiuixComboBox::drop-down { width: 0px; border: none; }
QComboBox.MiuixComboBox::down-arrow { image: none; width: 0px; height: 0px; }
QComboBox QAbstractItemView {
    background-color: %(surface_container)s;
    border: 1px solid %(outline_variant)s;
    border-radius: 13px;
    padding: 6px;
    outline: none;
    font-size: 16px;
    color: %(on_surface)s;
    selection-background-color: %(tertiary_container)s;
    selection-color: %(on_tertiary_container)s;
}
QComboBox QAbstractItemView::item { min-height: 34px; padding: 0 10px; border-radius: 8px; }
QComboBox QAbstractItemView::item:hover { background-color: %(hover_bg)s; }
"""


def init_theme(app: QApplication) -> ThemeManager:
    """创建全局 ThemeManager 并立即 apply（由 app/main.py 调用）。"""
    global _instance
    _instance = ThemeManager(app)
    _instance.apply()
    return _instance


def has_theme() -> bool:
    """主题是否已初始化（自绘控件在未初始化时回退到浅色 token，避免崩溃）。"""
    return _instance is not None


def theme() -> ThemeManager:
    """全局访问；未初始化则抛 RuntimeError。"""
    if _instance is None:
        raise RuntimeError("主题未初始化：请先调用 app.miuix.theme.init_theme(app)")
    return _instance


def current_palette() -> Palette:
    """安全取色：未初始化时返回浅色主题（供自绘控件使用）。"""
    return _instance.palette if _instance is not None else LIGHT


def current_style(name: str) -> TextStyle:
    """安全取文本样式。"""
    return TEXT.get(name, TEXT["body1"])