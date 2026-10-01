"""主窗口（docs/INTERFACES.md §5 + 沉浸式标题栏改造）。

MainWindow = 自绘标题栏 + 左侧 MiuixNavRail（下载 / 任务 / 设置 / 关于）+ 右侧 QStackedWidget。

窗口没有系统边框，标题栏与界面同风格（见 app/ui/titlebar.py）。为保证 Windows 上
仍有原生体验，做了三件事：
1. 边缘缩放走 nativeEvent 的 WM_NCHITTEST，返回 HTLEFT/HTTOP 等 —— 拉边、双击标题栏
   最大化、Aero Snap 全部由系统处理，比纯 Qt 手搓缩放稳得多；
2. 最大化时对齐 screen().availableGeometry()，否则无边框窗口会盖住任务栏；
3. 用 DWM 给窗口补 Windows 11 的系统圆角（失败静默忽略）。
非 Windows 平台这些分支全部跳过，不影响 Linux/macOS 开发。
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QByteArray, QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.runner import TaskRunner
from app.miuix.theme import theme
from app.miuix.widgets import MiuixNavRail
from app.ui import APP_NAME
from app.ui.pagebase import PageBase
from app.ui.pages import AboutPage, DownloadPage, SettingsPage, TasksPage
from app.ui.titlebar import MiuixTitleBar

# 导航项：(图标名, 文案)，顺序与 QStackedWidget 一致
NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("download", "下载"),
    ("list", "任务"),
    ("settings", "设置"),
    ("info", "关于"),
)

WINDOW_SIZE: tuple[int, int] = (1040, 720)
MINIMUM_SIZE: tuple[int, int] = (880, 600)

_IS_WIN = sys.platform == "win32"

# ---- Win32 常量 ----
WM_NCHITTEST = 0x0084
HTLEFT, HTRIGHT, HTTOP = 10, 11, 12
HTTOPLEFT, HTTOPRIGHT = 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
RESIZE_MARGIN = 8          # 拉边热区宽度(px)

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


class _MSG(ctypes.Structure):
    """Win32 MSG 结构（只用到 message 与 lParam）。"""

    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


class MainWindow(QMainWindow):
    """主窗口：沉浸式标题栏 + 导航栏 + 页面栈。"""

    def __init__(self, runner: TaskRunner, config: Config, server=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.runner = runner
        self.config = config
        self.server = server
        self.setWindowTitle(APP_NAME)
        # 托盘状态：必须在 _build_ui 之前就位 —— 构造函数里 _on_nav_changed 会切页，
        # 而 changeEvent 读得到 self.tray
        self.tray: QSystemTrayIcon | None = None
        self._force_quit = False        # 托盘菜单「退出」用：绕开「关闭到托盘」
        self._tray_hinted = False       # 「已收进托盘」只提示一次
        # 无系统边框；Qt.Window 必须保留，否则 Windows 上任务栏项/焦点行为会异常
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self._restore_geometry()
        self._build_ui()
        self._apply_background()
        self._setup_tray()

    # ------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("MiuixWindowRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 沉浸式标题栏（横跨整个窗口宽度）
        self.titlebar = MiuixTitleBar(APP_NAME)
        self.titlebar.minimizeRequested.connect(self.showMinimized)
        self.titlebar.maximizeRequested.connect(self._toggle_maximized)
        self.titlebar.closeRequested.connect(self.close)
        outer.addWidget(self.titlebar)

        body = QWidget()
        body.setObjectName("MiuixWindowBody")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.nav = MiuixNavRail()
        for icon_name, text in NAV_ITEMS:
            self.nav.addItem(icon_name, text)

        # 页面**按需创建**：四个页面全建实测要 ~975ms（构建控件 + 生成 QSS），
        # 而首屏只看得到第一页。先放占位控件保证索引与导航一致，
        # 切到哪页才建哪页，省掉启动时的大头开销。
        self.stack = QStackedWidget()
        self.pages: list[PageBase | None] = [None] * len(NAV_ITEMS)
        self._placeholders: list[QWidget] = []
        for _ in NAV_ITEMS:
            holder = QWidget()
            self._placeholders.append(holder)
            self.stack.addWidget(holder)
        self._ensure_page(0)

        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        outer.addWidget(body, 1)
        self.setCentralWidget(root)

        self.nav.currentChanged.connect(self._on_nav_changed)
        self.nav.setCurrentIndex(0)
        # 必须再显式走一次切换：addItem 时 nav 的 _index 就已是 0，setCurrentIndex(0)
        # 会提前 return 不发信号；而上面占位符换页会把 stack 的当前索引从 0 顶到 1，
        # 结果导航高亮在「下载」、右侧却是一个空占位控件（整页白板）。
        self._on_nav_changed(0)
        theme().changed.connect(self._apply_background)

    def _apply_background(self) -> None:
        """窗口底色跟随主题（取 palette.surface，与标题栏/页面底色一致）。"""
        self.setStyleSheet(
            f"QWidget#MiuixWindowRoot, QWidget#MiuixWindowBody "
            f"{{ background: {theme().palette.surface}; }}"
        )

    # ------------------------------------------------------------ 窗口按钮
    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ------------------------------------------------------------ 系统托盘
    def _setup_tray(self) -> None:
        """建托盘图标。没有托盘的环境（部分 Linux 桌面）安静跳过，功能自动降级。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        self.tray.setContextMenu(self._build_tray_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_tray_menu(self) -> QMenu:
        pal = theme().palette
        menu = QMenu(self)
        # 跟界面同一套 token，别弹出一块系统灰
        menu.setStyleSheet(
            f"QMenu {{ background: {pal.surface_container}; color: {pal.on_surface};"
            f" border: 1px solid {pal.outline_variant}; border-radius: 10px; padding: 6px; }}"
            f"QMenu::item {{ padding: 7px 22px; border-radius: 7px; }}"
            f"QMenu::item:selected {{ background: {pal.primary}; color: {pal.on_primary}; }}"
            f"QMenu::separator {{ height: 1px; background: {pal.outline_variant};"
            f" margin: 5px 8px; }}"
        )
        show_action = QAction("显示主窗口", menu)
        show_action.triggered.connect(self._restore_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("退出 " + APP_NAME, menu)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)
        return menu

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """双击（Windows 上单击也可能是 Trigger）切换显示 / 收起。"""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        """托盘菜单里的「退出」。绕开「关闭到托盘」，真的退。"""
        self._force_quit = True
        self.close()
        QApplication.quit()

    def _to_tray(self, message: str) -> None:
        """收进托盘并提示一次（同一句话只提示一次，别烦人）。"""
        self.hide()
        if self.tray is not None and not self._tray_hinted:
            self._tray_hinted = True
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 2500)

    # ------------------------------------------------------------ 事件
    def changeEvent(self, event) -> None:      # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.titlebar.setMaximized(self.isMaximized())
            if (self.isMinimized() and self.config.minimize_to_tray
                    and self.tray is not None):
                # 稍等一拍再收：立刻 hide() 的话窗口会先闪一下才消失
                QTimer.singleShot(0, lambda: self._to_tray("已最小化到托盘，双击图标可重新打开"))
                return
            # 无边框窗口最大化会盖住任务栏，等状态落定后对齐可用工作区
            QTimer.singleShot(0, self._fit_maximized_geometry)

    def _fit_maximized_geometry(self) -> None:
        if not self.isMaximized():
            return
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        if self.geometry() != geo:
            self.setGeometry(geo)

    def showEvent(self, event) -> None:        # noqa: N802
        super().showEvent(event)
        self._apply_round_corners()

    def _apply_round_corners(self) -> None:
        """Windows 11：给无边框窗口补上系统圆角（失败静默忽略）。"""
        if not _IS_WIN:
            return
        try:
            hwnd = ctypes.c_void_p(int(self.winId()))
            value = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass

    # ------------------------------------------------------------ 边缘缩放
    def nativeEvent(self, eventType, message):   # noqa: N802
        if _IS_WIN and eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == WM_NCHITTEST and not self.isMaximized():
                    # lParam 低 16 位 = 屏幕 x，高 16 位 = 屏幕 y（有符号）
                    sx = ctypes.c_short(msg.lParam & 0xFFFF).value
                    sy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    hit = self._hit_test(self.mapFromGlobal(QPoint(sx, sy)))
                    if hit is not None:
                        return True, hit
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _hit_test(self, pos: QPoint) -> int | None:
        """客户区坐标 → HT* 命中码；返回 None 表示交回系统默认处理。"""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = RESIZE_MARGIN
        left, right = x <= m, x >= w - m
        top, bottom = y <= m, y >= h - m
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return None

    # ------------------------------------------------------------ 导航
    def goto_page(self, index: int) -> None:
        """切到指定页（页面 gotoRequested 信号的目标槽）。"""
        self.nav.setCurrentIndex(index)

    # ------------------------------------------------------------ 页面懒加载
    def _page_factory(self, index: int) -> PageBase:
        if index == 1:
            return TasksPage(self.runner, self.config)
        if index == 2:
            return SettingsPage(self.runner, self.config, server=self.server)
        if index == 3:
            return AboutPage(self.runner, self.config)
        return DownloadPage(self.runner, self.config)

    def _ensure_page(self, index: int) -> PageBase | None:
        """返回第 index 页，不存在就现建（占位控件原地替换，保持索引不变）。"""
        if not 0 <= index < len(self.pages):
            return None
        page = self.pages[index]
        if page is not None:
            return page
        page = self._page_factory(index)
        page.gotoRequested.connect(self.goto_page)   # 页面 → 主导航跳转
        holder = self._placeholders[index]
        self.stack.removeWidget(holder)
        holder.deleteLater()
        self.stack.insertWidget(index, page)
        self.pages[index] = page
        return page

    def page(self, index: int) -> PageBase | None:
        """外部取页面统一走这里（会自动创建），不要直接索引 self.pages。"""
        return self._ensure_page(index)

    def page_count(self) -> int:
        return len(self.pages)

    def _on_nav_changed(self, index: int) -> None:
        """切页。懒加载的页面在这里现场构造。

        ⚠️ 构造 + 切换期间必须把绘制关掉。否则会看到"闪几个白色小方块"：
        页面已经 setCurrentIndex 显示出来了，可里面的卡片还没跑过一次布局，
        Qt 就先照着控件的初始几何画了一遍（卡片是白的，页面底是 #F7F7F7，
        于是几块白方块闪一下）。实测复现不了不是因为它不存在 —— 而是 grab()
        渲染的是完全就绪的状态；屏幕上闪的是没布局好的那一帧。
        关掉绘制 → 构造 → 切换 → refresh → 强制跑完布局 → 再一次性打开，
        用户看到的就是直接到位。
        """
        if not 0 <= index < self.stack.count():
            return
        self.stack.setUpdatesEnabled(False)
        try:
            page = self._ensure_page(index)
            self.stack.setCurrentIndex(index)
            if isinstance(page, PageBase):
                page.refresh()
            if isinstance(page, PageBase):
                page.ensurePolished()
                layout = page.layout()
                if layout is not None:
                    layout.activate()      # 立刻算完，别等下一个事件循环
        finally:
            self.stack.setUpdatesEnabled(True)

    # ------------------------------------------------------------ 窗口状态
    def _restore_geometry(self) -> None:
        saved = self.config.window_geometry
        if not saved:
            return
        try:
            self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))
        except Exception:   # 配置损坏时用默认尺寸，不影响启动
            pass

    def closeEvent(self, event: QCloseEvent) -> None:   # noqa: N802
        try:
            self.config.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.config.save()
        except Exception:
            pass
        # 「关闭到托盘」：拦下这次关闭，只把窗口藏起来。托盘菜单里的「退出」会先把
        # _force_quit 置真，所以那条路不受影响。
        if (self.config.close_to_tray and self.tray is not None
                and not self._force_quit):
            event.ignore()
            self._to_tray("已收进托盘，双击图标可重新打开")
            return
        super().closeEvent(event)
