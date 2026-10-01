"""设置页（docs/INTERFACES.md §5）。

签名：SettingsPage(runner: TaskRunner, config: Config, parent=None)，暴露 refresh()。
主题切换：theme().set_mode(...) + 回写 config.theme_mode（契约 §5）。
工具探测：调用 core.config.detect_tools()，不自己拼路径。
"""
from __future__ import annotations

import secrets
import shutil
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QSystemTrayIcon, QVBoxLayout, QWidget

from app.core import updater
from app.core.config import Config, detect_tools
from app.core.runner import TaskRunner
from app.core.server import ReceiveServer, pick_free_port
from app.miuix.icons import icon
from app.miuix.theme import theme
from app.miuix.widgets import (
    MiuixButton,
    MiuixComboBox,
    MiuixIconButton,
    MiuixLabel,
    MiuixLineEdit,
    MiuixSwitch,
    toast,
)
from app.ui import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.ui.pagebase import PageBase, combo_int
from app.ui.updater_ui import UpdateBridge, human_error, human_size, short_version

# 主题模式：显示名 → theme().set_mode() 的取值
THEME_MODES: tuple[tuple[str, str], ...] = (
    ("跟随系统", "system"),
    ("浅色", "light"),
    ("深色", "dark"),
)
CONCURRENCY_CHOICES: tuple[str, ...] = ("1", "2", "3", "4", "6", "8")


class SettingsPage(PageBase):
    """设置：工具路径 / 浏览器扩展 / 保存目录 / 外观 / 关于。

    下载参数（线程数、重试次数、自动选择、自动混流）不在这里 —— 它们由「新建下载」页
    在提交任务时写回 config，见 app/ui/pages/download.py 的 _start_download。
    """

    def __init__(self, runner: TaskRunner, config: Config,
                 server: ReceiveServer | None = None, parent: QWidget | None = None) -> None:
        # 必须在 super() 之前赋值：基类 __init__ 末尾会调用 _build()
        self.server = server
        super().__init__(runner, config, parent)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.page_header("⚙️ 设置"))

        scroll, body = self.build_scroll()
        root.addWidget(scroll, 1)

        body.addWidget(self._build_tools_card())
        body.addWidget(self._build_update_card())
        body.addWidget(self._build_server_card())
        body.addWidget(self._build_download_card())
        body.addWidget(self._build_appearance_card())
        body.addWidget(self._build_tray_card())
        body.addWidget(self._build_about_card())
        body.addStretch(1)
        self._connect()
        self._load_from_config()

    # ------------------------------------------------------------ 工具路径
    def _build_tools_card(self) -> QWidget:
        card = self.card("🛠️ 工具路径")
        self.nm3u8dl_edit = MiuixLineEdit()
        self.nm3u8dl_edit.setPlaceholderText("N_m3u8DL-RE 可执行文件路径")
        self.nm3u8dl_btn = MiuixIconButton("folder", tooltip="选择 N_m3u8DL-RE")
        card.body.addWidget(self.form_row("N_m3u8DL-RE", self.inline(self.nm3u8dl_edit, self.nm3u8dl_btn)))

        self.ffmpeg_edit = MiuixLineEdit()
        self.ffmpeg_edit.setPlaceholderText("ffmpeg 可执行文件路径（混流用）")
        self.ffmpeg_btn = MiuixIconButton("folder", tooltip="选择 ffmpeg")
        card.body.addWidget(self.form_row("ffmpeg", self.inline(self.ffmpeg_edit, self.ffmpeg_btn)))

        self.detect_btn = MiuixButton("自动探测", variant="tonal", icon=icon("search"))
        self.detect_btn.setToolTip("按「配置路径 → 项目 tools 目录 → PATH」顺序查找")
        card.body.addWidget(self.spacer_row(self.detect_btn, stretch_before=False))
        return card

    # ------------------------------------------------------------ 内核更新
    def _build_update_card(self) -> QWidget:
        card = self.card("⬆️ 内核更新")
        self.local_ver_label = MiuixLabel("未检测", style="body2")
        card.body.addWidget(self.form_row("本地版本", self.local_ver_label))

        self.remote_ver_label = MiuixLabel("点「检查更新」查询", style="body2",
                                           color="on_surface_variant")
        card.body.addWidget(self.form_row("最新版本", self.remote_ver_label))

        self.accel_switch = MiuixSwitch()
        self.accel_switch.setText("走加速地址")
        card.body.addWidget(self.form_row(
            "加速下载", self.accel_switch,
            "关掉则直连 GitHub。这类服务的域名和路径格式各家不同，填错了比不填更难查"))

        self.accel_edit = MiuixLineEdit()
        self.accel_edit.setPlaceholderText("https://服务域名/{url}   或   https://服务域名/")
        card.body.addWidget(self.form_row(
            "加速地址", self.accel_edit,
            "两种写法都行：{url} 是替换点；不写 {url} 就当作前缀拼接"))

        self.proxy_edit = MiuixLineEdit()
        self.proxy_edit.setPlaceholderText("http://127.0.0.1:7890")
        card.body.addWidget(self.form_row(
            "更新代理", self.proxy_edit,
            "只用于检查更新与下载内核；留空则直连（跟随系统代理）"))

        self.check_btn = MiuixButton("检查更新", variant="tonal", icon=icon("search"))
        self.update_btn = MiuixButton("下载并更新", variant="primary", icon=icon("download"))
        self.update_btn.setEnabled(False)      # 查过之后才知道有没有必要
        card.body.addWidget(self.spacer_row(self.check_btn, self.update_btn))

        self.update_status = MiuixLabel("", style="caption", color="on_surface_variant")
        card.body.addWidget(self.update_status)
        return card

    # ------------------------------------------------------------ 浏览器扩展
    def _build_server_card(self) -> QWidget:
        card = self.card("🧩 浏览器扩展")
        self.server_switch = MiuixSwitch()
        self.server_switch.setText("启用本地接收端")
        card.body.addWidget(self.form_row(
            "接收端", self.server_switch,
            "开启后浏览器扩展才能投递下载任务；只监听 127.0.0.1，且必须带令牌",
        ))

        self.port_edit = MiuixLineEdit()
        self.port_edit.setFixedWidth(140)
        self.port_edit.setPlaceholderText("五位数端口")
        self.port_rand_btn = MiuixButton("随机", variant="tonal")
        self.port_rand_btn.setToolTip("换一个当前空闲的五位数端口")
        # 端口框是固定宽度，不锁住按钮就会被它吃掉右侧全部剩余空间（Preferred 策略）
        self.port_rand_btn.setFixedWidth(88)
        card.body.addWidget(self.form_row("端口", self.inline(self.port_edit, self.port_rand_btn)))

        self.token_edit = MiuixLineEdit()
        self.token_edit.setReadOnly(True)
        self.token_edit.setPlaceholderText("开启后自动生成")
        self.token_reset_btn = MiuixIconButton("refresh", tooltip="重新生成令牌")
        self.token_copy_btn = MiuixIconButton("copy", tooltip="复制令牌")
        card.body.addWidget(self.form_row(
            "访问令牌",
            self.inline(self.token_edit, self.token_reset_btn, self.token_copy_btn),
            "扩展设置里要填这个令牌；重置后需同步更新扩展",
        ))

        self.server_status = MiuixLabel("未启用", style="caption",
                                        color="on_surface_variant")
        card.body.addWidget(self.form_row("状态", self.server_status))

        self.open_ext_btn = MiuixButton("打开扩展目录", variant="tonal", icon=icon("folder"))
        self.open_ext_btn.setToolTip("把该文件夹加载到 chrome://extensions（开发者模式）")
        card.body.addWidget(self.spacer_row(self.open_ext_btn, stretch_before=False))
        return card

    # ------------------------------------------------------------ 下载
    def _build_download_card(self) -> QWidget:
        card = self.card("⚡ 下载")
        self.save_dir_edit = MiuixLineEdit()
        self.save_dir_edit.setPlaceholderText("默认保存目录")
        self.save_dir_btn = MiuixIconButton("folder", tooltip="选择默认保存目录")
        card.body.addWidget(self.form_row(
            "默认目录", self.inline(self.save_dir_edit, self.save_dir_btn),
            "「新建下载」页开着「使用默认目录」时落到这里；留空则用程序所在目录"))

        self.concurrent_combo = MiuixComboBox()
        self.concurrent_combo.addItems(list(CONCURRENCY_CHOICES))
        card.body.addWidget(self.form_row("最大并发", self.concurrent_combo, "同时运行的任务数，超出后排队"))
        return card

    # ------------------------------------------------------------ 外观
    def _build_appearance_card(self) -> QWidget:
        card = self.card("🎨 外观")
        self.theme_combo = MiuixComboBox()
        self.theme_combo.addItems([label for label, _ in THEME_MODES])
        card.body.addWidget(self.form_row("主题模式", self.theme_combo, "切换后立即生效并写入配置"))
        return card

    # 注：曾经这里有一张「默认参数」卡片（线程数 / 重试次数 / 自动选择 / 自动混流）。
    # 它和「新建下载」页的同名控件是同一份数据、两个入口，改这边那边不跟着变，
    # 用起来像"冲突"。已删除 —— 现在由下载页在提交任务时把这几项写回 config，
    # 下次打开就是上次用的值，只有一个地方能改。

    # ------------------------------------------------------------ 系统托盘
    def _build_tray_card(self) -> QWidget:
        card = self.card("🖥️ 系统托盘")
        tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
        if not tray_ok:
            card.body.addWidget(self.hint("当前系统没有可用的托盘，下面两项不会生效"))

        self.min_tray_switch = MiuixSwitch()
        self.min_tray_switch.setText("最小化到托盘")
        self.min_tray_switch.setEnabled(tray_ok)
        card.body.addWidget(self.form_row(
            "最小化", self.min_tray_switch, "点最小化按钮时收进托盘，而不是缩到任务栏"))

        self.close_tray_switch = MiuixSwitch()
        self.close_tray_switch.setText("关闭到托盘")
        self.close_tray_switch.setEnabled(tray_ok)
        card.body.addWidget(self.form_row(
            "关闭窗口", self.close_tray_switch,
            "点关闭按钮只收进托盘，程序继续在后台跑 —— 此时要退出请右键托盘图标选「退出」"))

        card.body.addWidget(self.hint("托盘图标：双击显示 / 收起主窗口；右键可退出程序"))
        return card

    # ------------------------------------------------------------ 关于
    def _build_about_card(self) -> QWidget:
        card = self.card("ℹ️ 关于")
        card.body.addWidget(MiuixLabel(f"{APP_NAME} {APP_VERSION}", style="body1"))
        card.body.addWidget(self.hint(APP_DESCRIPTION))
        self.config_dir_label = MiuixLabel("", style="caption",
                                           color="on_surface_variant")
        card.body.addWidget(self.config_dir_label)
        self.open_config_btn = MiuixButton("打开配置目录", variant="text", icon=icon("folder"))
        card.body.addWidget(self.spacer_row(self.open_config_btn, stretch_before=False))
        return card

    # ------------------------------------------------------------ 交互
    def _connect(self) -> None:
        self.nm3u8dl_btn.clicked.connect(lambda: self._pick_executable(self.nm3u8dl_edit))
        self.ffmpeg_btn.clicked.connect(lambda: self._pick_executable(self.ffmpeg_edit))
        self.save_dir_btn.clicked.connect(self._pick_save_dir)
        self.detect_btn.clicked.connect(self._detect)
        self.open_config_btn.clicked.connect(self._open_config_dir)

        self.nm3u8dl_edit.editingFinished.connect(self._apply_paths)
        self.ffmpeg_edit.editingFinished.connect(self._apply_paths)
        self.save_dir_edit.editingFinished.connect(self._apply_save_dir)
        self.concurrent_combo.currentIndexChanged.connect(self._apply_concurrency)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)

        self.server_switch.toggled.connect(self._toggle_server)
        self.port_edit.editingFinished.connect(self._apply_port)
        self.port_rand_btn.clicked.connect(self._random_port)
        self.token_reset_btn.clicked.connect(self._reset_token)
        self.token_copy_btn.clicked.connect(self._copy_token)
        self.open_ext_btn.clicked.connect(self._open_extension_dir)

        self.check_btn.clicked.connect(self._check_update)
        self.update_btn.clicked.connect(self._download_update)
        self.min_tray_switch.toggled.connect(self._apply_tray)
        self.close_tray_switch.toggled.connect(self._apply_tray)
        self.accel_switch.toggled.connect(self._apply_update_settings)
        self.accel_edit.editingFinished.connect(self._apply_update_settings)
        self.proxy_edit.editingFinished.connect(self._apply_update_settings)

        # 后台线程用信号回主线程（updater 本身不碰 Qt）
        self._bridge = UpdateBridge(self)
        self._bridge.done.connect(self._on_update_done)
        self._bridge.failed.connect(self._on_update_failed)
        self._bridge.progress.connect(self._on_update_progress)
        self._bridge.installed.connect(self._on_update_installed)

    # ------------------------------------------------------------ 浏览器扩展
    def _refresh_server_status(self) -> None:
        running = bool(self.server and self.server.is_running())
        if running:
            text = "运行中 · " + self.server.base_url()
        elif self.config.server_enabled:
            text = "已启用但未运行（端口可能被占用）"
        else:
            text = "未启用"
        self.server_status.setText(text)

    def _toggle_server(self, enabled: bool) -> None:
        cfg = self.config
        cfg.server_enabled = bool(enabled)
        if enabled:
            if not cfg.server_token:
                cfg.server_token = secrets.token_urlsafe(24)
            if not cfg.server_port:
                cfg.server_port = pick_free_port()
            self.token_edit.setText(cfg.server_token)
            self.port_edit.setText(str(cfg.server_port))
            port = self.server.start(cfg.server_port, cfg.server_token) if self.server else 0
            if port:
                if port != cfg.server_port:
                    cfg.server_port = port        # 启动时换过端口，回写真实值
                    self.port_edit.setText(str(port))
                toast(self, "接收端已启动：" + self.server.base_url(), "success")
            else:
                toast(self, "接收端启动失败（端口都被占用？）", "error")
        else:
            if self.server:
                self.server.stop()
            toast(self, "接收端已停止", "neutral")
        self._refresh_server_status()
        self._save()

    def _apply_port(self) -> None:
        raw = self.port_edit.text().strip()
        try:
            port = int(raw)
        except ValueError:
            toast(self, "端口必须是数字", "error")
            self.port_edit.setText(str(self.config.server_port))
            return
        if not (10000 <= port <= 65535):
            toast(self, "请用五位数端口（10000-65535）", "error")
            self.port_edit.setText(str(self.config.server_port))
            return
        self._switch_port(port)

    def _random_port(self) -> None:
        port = pick_free_port()
        if not port:
            toast(self, "没找到空闲端口", "error")
            return
        self._switch_port(port)
        toast(self, "端口已改为 %d" % port, "success")

    def _switch_port(self, port: int) -> None:
        """换端口：正在跑就先停再起（监听地址变了，不能让扩展连着旧端口）。"""
        self.config.server_port = port
        self.port_edit.setText(str(port))
        if self.config.server_enabled and self.server:
            self.server.stop()
            actual = self.server.start(port, self.config.server_token)
            if actual and actual != port:
                self.config.server_port = actual
                self.port_edit.setText(str(actual))
        self._refresh_server_status()
        self._save()

    def _reset_token(self) -> None:
        self.config.server_token = secrets.token_urlsafe(24)
        self.token_edit.setText(self.config.server_token)
        if self.config.server_enabled and self.server:
            self.server.stop()
            self.server.start(self.config.server_port, self.config.server_token)
        self._refresh_server_status()
        self._save()
        toast(self, "令牌已重置，记得同步更新扩展设置", "warning")

    def _copy_token(self) -> None:
        token = self.token_edit.text().strip()
        if not token:
            toast(self, "还没有令牌，先开启接收端", "error")
            return
        QGuiApplication.clipboard().setText(token)
        toast(self, "令牌已复制", "success")

    def _open_extension_dir(self) -> None:
        """打开随程序分发的扩展目录。

        源码在独立项目 MiuiX-M3U8-Extension，打包时被复制一份进包内。
        单文件模式（--onefile）下包内容是解到 %TEMP% 下 _MEIxxxx 临时目录的，
        退出就删 —— 让用户从那里"加载已解压的扩展"等于下次启动必然失效，
        所以先把它复制到 exe 旁边，再打开那个稳定路径。
        """
        from app.core.config import _base_dir
        source = _base_dir() / "extension"
        if not source.is_dir():
            toast(self, "没找到 extension 目录", "error")
            return

        target = source
        if getattr(sys, "frozen", False):
            beside = Path(sys.executable).resolve().parent / "extension"
            if not beside.is_dir():
                try:
                    shutil.copytree(source, beside)
                except OSError as exc:
                    toast(self, "复制扩展目录失败：" + str(exc), "error")
                    return
            target = beside
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _pick_executable(self, edit: MiuixLineEdit) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "选择可执行文件", edit.text().strip(), "可执行文件 (*.exe);;所有文件 (*)")
        if chosen:
            edit.setText(chosen)
            self._apply_paths()

    def _pick_save_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择默认保存目录", self.save_dir_edit.text().strip())
        if chosen:
            self.save_dir_edit.setText(chosen)
            self._apply_save_dir()

    def _detect(self) -> None:
        """自动探测 N_m3u8DL-RE / ffmpeg（core.config.detect_tools）。"""
        try:
            found = detect_tools()
        except Exception as exc:
            toast(self, f"探测失败：{exc}", "error")
            return
        hit: list[str] = []
        if found.get("nm3u8dl"):
            self.nm3u8dl_edit.setText(found["nm3u8dl"])
            hit.append("N_m3u8DL-RE")
        if found.get("ffmpeg"):
            self.ffmpeg_edit.setText(found["ffmpeg"])
            hit.append("ffmpeg")
        if hit:
            self._apply_paths()
            toast(self, "已找到：" + "、".join(hit), "success")
        else:
            toast(self, "未找到，请手动指定路径", "warning")

    def _open_config_dir(self) -> None:
        path = Config.file().parent
        path.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            toast(self, f"打开失败：{path}", "error")

    # ------------------------------------------------------------ 托盘
    def _apply_tray(self) -> None:
        """两个托盘开关 —— 改完即存（窗口的 closeEvent / changeEvent 直接读 config）。"""
        self.config.minimize_to_tray = self.min_tray_switch.isChecked()
        self.config.close_to_tray = self.close_tray_switch.isChecked()
        self._save()

    # ------------------------------------------------------------ 内核更新动作
    def _apply_update_settings(self) -> None:
        """加速开关 / 加速地址 / 更新代理 —— 改完即存。"""
        cfg = self.config
        cfg.update_accel_enabled = self.accel_switch.isChecked()
        cfg.update_accel_prefix = self.accel_edit.text().strip()
        cfg.update_proxy = self.proxy_edit.text().strip()
        self._save()

    def _set_update_busy(self, text: str) -> None:
        self.check_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self.update_status.setText(text)

    def _check_update(self) -> None:
        if not self.config.nm3u8dl_path:
            toast(self, "先指定 N_m3u8DL-RE 路径", "error")
            return
        self._set_update_busy("正在检测本地内核版本…")
        threading.Thread(target=self._work_check, daemon=True).start()

    def _work_check(self) -> None:
        """后台线程：本地 --version → GitHub 最新 release。"""
        try:
            version = updater.local_version(self.config.nm3u8dl_path)
        except Exception as exc:      # noqa: BLE001
            self._bridge.failed.emit("check", human_error(exc))
            return
        self._bridge.done.emit("local", version)
        try:
            self._bridge.done.emit("remote", updater.fetch_latest(self.config.update_proxy))
        except Exception as exc:      # noqa: BLE001
            self._bridge.failed.emit("check", human_error(exc))

    def _download_update(self) -> None:
        self._set_update_busy("准备下载…")
        threading.Thread(target=self._work_update, daemon=True).start()

    def _work_update(self) -> None:
        try:
            tag, path, backup = updater.update_to(self.config, self._bridge.progress.emit)
        except Exception as exc:      # noqa: BLE001
            self._bridge.failed.emit("update", human_error(exc))
            return
        self._bridge.installed.emit(tag, path, backup)

    # ---- 下面四个都在主线程（信号自动排队回来）----
    def _on_update_done(self, stage: str, payload: object) -> None:
        if stage == "local":
            self.local_ver_label.setText(short_version(str(payload))
                                         or "未知（路径不对或文件缺失）")
            # 本地那步很快，远端要联网 —— 状态行要说清现在卡在哪一步
            self.update_status.setText("正在查询 GitHub 最新版本…")
        elif stage == "remote":
            self._show_release(payload)

    def _show_release(self, release) -> None:
        """拿到远端版本后判定：有新版本 / 同版本同构建 / 同版本不同构建。"""
        self.check_btn.setEnabled(True)
        self.update_btn.setEnabled(True)
        text = release.tag
        if release.published:
            text += "（%s）" % release.published
        self.remote_ver_label.setText(text)

        local = self.local_ver_label.text()
        if updater.is_newer(release.tag, local):
            self.update_status.setText("发现新版本 %s —— 点「下载并更新」升级" % release.tag)
        elif updater.same_build(release.commit, local):
            self.update_status.setText("已是最新（与远端构建一致）")
        else:
            self.update_status.setText("版本号相同但构建不同，可以重装一遍试试")

    def _on_update_progress(self, done: int, total: int) -> None:
        if total:
            self.update_status.setText("下载中 %d%% · %s / %s"
                                       % (done * 100 // total, human_size(done), human_size(total)))
        else:
            self.update_status.setText("下载中 " + human_size(done))

    def _on_update_installed(self, tag: str, path: str, backup: str) -> None:
        self.local_ver_label.setText(short_version(updater.local_version(path)) or tag)
        self.check_btn.setEnabled(True)
        self.update_btn.setEnabled(True)
        note = ("旧内核备份在 " + Path(backup).name) if backup else "没有旧内核可备份"
        self.update_status.setText("已更新到 %s（%s）" % (tag, note))
        toast(self, "内核已更新到 " + tag, "success")

    def _on_update_failed(self, stage: str, message: str) -> None:
        self.check_btn.setEnabled(True)
        self.update_btn.setEnabled(True)
        head = "检查失败：" if stage == "check" else "更新失败："
        self.update_status.setText(head + message)
        toast(self, message, "error")

    # ------------------------------------------------------------ 应用变更
    def _apply_paths(self) -> None:
        self.config.nm3u8dl_path = self.nm3u8dl_edit.text().strip()
        self.config.ffmpeg_path = self.ffmpeg_edit.text().strip()
        self.config.defaults.ffmpeg_path = self.config.ffmpeg_path
        self.runner.set_exe(self.config.nm3u8dl_path)
        # 换了内核文件，之前测出来的版本就不算数了
        self.local_ver_label.setText("未检测")
        self.remote_ver_label.setText("点「检查更新」查询")
        self.update_status.setText("")
        self.update_btn.setEnabled(False)
        self._save()

    def _apply_save_dir(self) -> None:
        self.config.save_dir = self.save_dir_edit.text().strip()
        self._save()

    def _apply_concurrency(self) -> None:
        value = combo_int(self.concurrent_combo, self.config.max_concurrent)
        self.config.max_concurrent = value
        self.runner.set_max_concurrent(value)
        self._save()

    def _apply_theme(self) -> None:
        mode = THEME_MODES[self.theme_combo.currentIndex()][1]
        self.config.theme_mode = mode
        theme().set_mode(mode)
        self._save()

    def _save(self) -> None:
        try:
            self.config.save()
        except Exception as exc:  # 磁盘/权限问题不应该让界面崩掉
            toast(self, f"配置保存失败：{exc}", "error")

    # ------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        self._load_from_config()

    def _load_from_config(self) -> None:
        """把 config 的值灌回控件（不触发保存）。"""
        config = self.config
        guarded = (self.nm3u8dl_edit, self.ffmpeg_edit, self.save_dir_edit,
                   self.concurrent_combo, self.theme_combo,
                   self.server_switch, self.port_edit,
                   self.accel_switch, self.accel_edit, self.proxy_edit,
                   self.min_tray_switch, self.close_tray_switch)
        for widget in guarded:
            widget.blockSignals(True)   # 载入时不写回配置
        self.nm3u8dl_edit.setText(config.nm3u8dl_path)
        self.ffmpeg_edit.setText(config.ffmpeg_path)
        self.save_dir_edit.setText(config.save_dir)
        self._select_text(self.concurrent_combo, str(config.max_concurrent))
        self.theme_combo.setCurrentIndex(self._theme_index(config.theme_mode))
        self.server_switch.setChecked(config.server_enabled)
        self.port_edit.setText(str(config.server_port) if config.server_port else "")
        self.token_edit.setText(config.server_token)
        self.accel_switch.setChecked(config.update_accel_enabled)
        self.accel_edit.setText(config.update_accel_prefix)
        self.proxy_edit.setText(config.update_proxy)
        self.min_tray_switch.setChecked(config.minimize_to_tray)
        self.close_tray_switch.setChecked(config.close_to_tray)
        for widget in guarded:
            widget.blockSignals(False)
        self._refresh_server_status()
        for edit in (self.nm3u8dl_edit, self.ffmpeg_edit, self.save_dir_edit):
            edit.setCursorPosition(0)   # 长路径默认展示开头
        self.config_dir_label.setText(f"配置文件：{Config.file()}")

    @staticmethod
    def _select_text(combo: MiuixComboBox, text: str) -> None:
        if combo.findText(text) < 0:
            combo.addItem(text)
        combo.setCurrentText(text)

    @staticmethod
    def _theme_index(mode: str) -> int:
        for index, (_, value) in enumerate(THEME_MODES):
            if value == mode:
                return index
        return 0
