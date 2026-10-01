"""新建下载页（docs/INTERFACES.md §5）。

签名：DownloadPage(runner: TaskRunner, config: Config, parent=None)，暴露 refresh()。
runner / config 由 main.py 注入，本页不得自建，也不得重新 load Config。
布局：顶栏 + 滚动内容（基础信息 / 流选择 / 混流 / 网络 / 解密）+ 固定底部操作栏。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.model import THREAD_CHOICES, DownloadOptions
from app.core.nm3u8dl import preview_command
from app.core.runner import TaskRunner, default_save_dir
from app.miuix.icons import icon
from app.miuix.theme import theme
from app.miuix.widgets import (
    MiuixButton,
    MiuixComboBox,
    MiuixDialog,
    MiuixIconButton,
    MiuixLabel,
    MiuixLineEdit,
    MiuixSwitch,
    MiuixTextEdit,
    toast,
)
from app.ui.pagebase import PAGE_MARGIN, ROW_SPACING, SCROLL_BOTTOM_EXTRA, PageBase, combo_int

# 重试次数候选值（与 N_m3u8DL-RE 默认 3 对齐）
RETRY_CHOICES: tuple[str, ...] = ("0", "1", "2", "3", "5", "10")
MUX_FORMATS: tuple[str, ...] = ("mp4", "mkv", "ts")
MUXERS: tuple[str, ...] = ("ffmpeg", "mkvmerge")
SUB_FORMATS: tuple[str, ...] = ("SRT", "VTT")
DECRYPTION_ENGINES: tuple[str, ...] = ("MP4DECRYPT", "FFMPEG", "SHAKA_PACKAGER")


class DownloadPage(PageBase):
    """新建下载：链接、保存位置、流选择、混流、网络与解密参数。"""

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.page_header("📥 新建下载"))

        scroll, body = self.build_scroll(bottom_extra=SCROLL_BOTTOM_EXTRA)
        root.addWidget(scroll, 1)
        root.addWidget(self._build_action_bar())

        body.addWidget(self._build_basic_card())
        body.addWidget(self._build_stream_card())
        body.addWidget(self._build_mux_card())
        body.addWidget(self._build_network_card())
        body.addWidget(self._build_decrypt_card())
        body.addStretch(1)
        self._connect()

    # ------------------------------------------------------------ 基础信息
    def _build_basic_card(self) -> QWidget:
        card = self.card("📋 基础信息")
        # 多行输入：每行一个链接，一次提交即批量建任务
        self.url_edit = MiuixTextEdit()
        self.url_edit.setPlaceholderText(
            "每行一个链接，可批量下载（支持 m3u8 / mpd / 直链）"
        )
        self.url_edit.setFixedHeight(96)      # 约 4 行
        # 链接**刻意不回填**：这东西属于一次性输入（带 token 的地址、只在当次有效的
        # 链接），记住它弊大于利。下载链接永久不写进配置，见 _persist_defaults。
        card.body.addWidget(self.form_row(
            "链接", self.url_edit,
            "每行一个链接即可批量下载；空行与 # 开头的行会被忽略",
        ))

        # 保存目录：默认走「设置页的默认目录 → 程序所在目录」，要自定义就关掉开关。
        # 以前只有一个输入框、留空即默认 —— 但提示写的是程序目录，实际却先落到设置页那个
        # 目录；而且切回本页时还会把默认目录当字面值填进输入框，看着像用户自己选的。
        # 说的和做的不一致，就是"默认目录和保存目录打架"。现在用一个显式开关分开两种意图。
        self.dir_switch = MiuixSwitch()
        self.dir_switch.setText("使用默认目录")
        self.dir_switch.setChecked(True)
        card.body.addWidget(self.form_row(
            "保存目录", self.dir_switch,
            "默认目录 = 设置页的「默认目录」；那里没填则用程序所在目录"))

        self.dir_edit = MiuixLineEdit()
        self.dir_btn = MiuixIconButton("folder", tooltip="选择保存目录")
        card.body.addWidget(self.form_row("", self.inline(self.dir_edit, self.dir_btn)))
        self._apply_dir_mode()

        self.name_edit = MiuixLineEdit()
        self.name_edit.setPlaceholderText("留空则使用 N_m3u8DL-RE 自动命名")
        card.body.addWidget(self.form_row("文件名", self.name_edit))

        self.thread_combo = MiuixComboBox()
        self.thread_combo.addItems(list(THREAD_CHOICES))
        self.thread_combo.setCurrentText(str(self.config.defaults.thread_count))
        card.body.addWidget(self.form_row("线程数", self.thread_combo, "并发下载分片的数量"))

        self.retry_combo = MiuixComboBox()
        self.retry_combo.addItems(list(RETRY_CHOICES))
        self.retry_combo.setCurrentText(str(self.config.defaults.retry_count))
        card.body.addWidget(self.form_row("重试次数", self.retry_combo, "单个分片下载失败后的重试次数"))

        # 以前只有"成功提交一次下载"才会把这组参数写回 config.defaults，于是想改
        # 浏览器扩展任务的线程数，得先去假下一次单 —— 这个按钮就是给那条路开的直通车。
        self.apply_btn = MiuixButton("应用为默认", variant="tonal", icon=icon("check"))
        self.apply_btn.setToolTip("把这组参数存成默认值，浏览器扩展投递的任务也会用它")
        card.body.addWidget(self.spacer_row(self.apply_btn, stretch_before=False))
        return card

    # ------------------------------------------------------------ 流选择
    def _build_stream_card(self) -> QWidget:
        card = self.card("🎞️ 流选择")
        self.auto_select_switch = MiuixSwitch()
        self.auto_select_switch.setText("自动选择最佳流")
        self.auto_select_switch.setChecked(self.config.defaults.auto_select)
        card.body.addWidget(self.form_row("自动选择", self.auto_select_switch,
                                          "--auto-select：自动挑选分辨率最高的视频与最佳音轨。"
                                          "关掉后若没填下面的「选择视频」，内核会退化成交互式选流菜单"
                                          "——GUI 下没有控制台，那种情况会直接崩，所以仍会回退成自动选择"))

        self.video_edit = MiuixLineEdit()
        self.video_edit.setPlaceholderText("如 best 或 res=1080&codecs=avc")
        card.body.addWidget(self.form_row("选择视频", self.video_edit))

        self.audio_edit = MiuixLineEdit()
        self.audio_edit.setPlaceholderText("如 lang=zh&codecs=ec-3")
        card.body.addWidget(self.form_row("选择音频", self.audio_edit))

        self.subtitle_edit = MiuixLineEdit()
        self.subtitle_edit.setPlaceholderText("如 lang=zh 或 best")
        card.body.addWidget(self.form_row("选择字幕", self.subtitle_edit))

        self.drop_video_edit = MiuixLineEdit()
        self.drop_video_edit.setPlaceholderText("如 res=720")
        card.body.addWidget(self.form_row("丢弃视频", self.drop_video_edit))

        self.drop_audio_edit = MiuixLineEdit()
        self.drop_audio_edit.setPlaceholderText("如 lang=en")
        card.body.addWidget(self.form_row("丢弃音频", self.drop_audio_edit))

        self.drop_subtitle_edit = MiuixLineEdit()
        self.drop_subtitle_edit.setPlaceholderText("如 lang=en")
        card.body.addWidget(self.form_row("丢弃字幕", self.drop_subtitle_edit))

        self.sub_only_switch = MiuixSwitch()
        self.sub_only_switch.setText("仅下载字幕")
        card.body.addWidget(self.form_row("仅字幕", self.sub_only_switch, "--sub-only"))

        self.sub_format_combo = MiuixComboBox()
        self.sub_format_combo.addItems(list(SUB_FORMATS))
        card.body.addWidget(self.form_row("字幕格式", self.sub_format_combo, "--sub-format"))
        return card

    # ------------------------------------------------------------ 混流
    def _build_mux_card(self) -> QWidget:
        card = self.card("🎬 混流")
        self.mux_switch = MiuixSwitch()
        self.mux_switch.setText("下载完成后自动混流")
        self.mux_switch.setChecked(self.config.defaults.mux_enabled)
        card.body.addWidget(self.form_row("混流", self.mux_switch, "-M mux-after-done：音视频下载完成后自动合并"))

        self.mux_format_combo = MiuixComboBox()
        self.mux_format_combo.addItems(list(MUX_FORMATS))
        self.mux_format_combo.setCurrentText(self.config.defaults.mux_format)
        card.body.addWidget(self.form_row("输出格式", self.mux_format_combo))

        self.muxer_combo = MiuixComboBox()
        self.muxer_combo.addItems(list(MUXERS))
        self.muxer_combo.setCurrentText(self.config.defaults.muxer)
        card.body.addWidget(self.form_row("混流器", self.muxer_combo, "ffmpeg 兼容性最好，mkvmerge 更擅长 MKV"))
        return card

    # ------------------------------------------------------------ 网络
    def _build_network_card(self) -> QWidget:
        card = self.card("🌐 网络")
        self.proxy_switch = MiuixSwitch()
        self.proxy_switch.setText("使用系统代理")
        self.proxy_switch.setChecked(self.config.defaults.use_system_proxy)
        card.body.addWidget(self.form_row("系统代理", self.proxy_switch, "--use-system-proxy"))

        self.proxy_edit = MiuixLineEdit()
        self.proxy_edit.setPlaceholderText("http://127.0.0.1:7890")
        card.body.addWidget(self.form_row("自定义代理", self.proxy_edit, "--custom-proxy"))

        self.header_edit = MiuixTextEdit()
        self.header_edit.setPlaceholderText("Cookie: sessionid=xxx\nUser-Agent: Mozilla/5.0")
        self.header_edit.setFixedHeight(88)
        card.body.addWidget(self.form_row("请求头", self.header_edit, "每行一条 -H 头，格式 Name: Value"))
        return card

    # ------------------------------------------------------------ 解密
    def _build_decrypt_card(self) -> QWidget:
        card = self.card("🔑 解密")
        self.key_edit = MiuixLineEdit()
        self.key_edit.setPlaceholderText("KID:KEY 或单一 KEY（--key）")
        card.body.addWidget(self.form_row("解密密钥", self.key_edit))

        self.key_file_edit = MiuixLineEdit()
        self.key_file_edit.setPlaceholderText("kid-key 文本文件（--key-text-file）")
        self.key_file_btn = MiuixIconButton("folder", tooltip="选择密钥文件")
        card.body.addWidget(self.form_row("密钥文件", self.inline(self.key_file_edit, self.key_file_btn)))

        self.engine_combo = MiuixComboBox()
        self.engine_combo.addItems(list(DECRYPTION_ENGINES))
        self.engine_combo.setCurrentText(self.config.defaults.decryption_engine)
        card.body.addWidget(self.form_row("解密引擎", self.engine_combo, "--decryption-engine"))
        return card

    # ------------------------------------------------------------ 底部操作栏
    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(PAGE_MARGIN, ROW_SPACING, PAGE_MARGIN, ROW_SPACING * 2)
        layout.setSpacing(ROW_SPACING)
        layout.addStretch(1)
        self.preview_btn = MiuixButton("预览命令", variant="outlined", icon=icon("tools"))
        self.start_btn = MiuixButton("开始下载", variant="filled", icon=icon("download"))
        layout.addWidget(self.preview_btn)
        layout.addWidget(self.start_btn)
        return bar

    # ------------------------------------------------------------ 交互
    def _connect(self) -> None:
        """信号连接（在 _build 末尾由子类调用，保证控件都已创建）。"""
        self.dir_switch.toggled.connect(self._apply_dir_mode)
        self.apply_btn.clicked.connect(self._apply_defaults_now)
        self.dir_btn.clicked.connect(self._pick_dir)
        self.key_file_btn.clicked.connect(self._pick_key_file)
        self.preview_btn.clicked.connect(self._preview_command)
        self.start_btn.clicked.connect(self._start_download)

    def _default_dir(self) -> str:
        """用默认目录时真正的落盘位置：设置页的默认目录 > 程序所在目录。

        与 runner._pick_work_dir() 的链条一致（collect() 给空串，runner 就按这个顺序落）。
        """
        return self.config.save_dir or default_save_dir()

    def _apply_dir_mode(self) -> None:
        """「使用默认目录」开关 → 输入框可用性与占位提示。

        用默认时清空并禁用输入框（collect() 拿不到值，自然回落到默认目录链）；
        自己指定时启用，留空也仍回落默认 —— 不制造"必须先选目录"的报错。
        """
        use_default = self.dir_switch.isChecked()
        if use_default:
            self.dir_edit.clear()
        self.dir_edit.setEnabled(not use_default)
        self.dir_btn.setEnabled(not use_default)
        self.dir_edit.setPlaceholderText(
            self._default_dir() if use_default else "选择或输入保存目录")

    def _pick_dir(self) -> None:
        start = self.dir_edit.text().strip() or self._default_dir()
        chosen = QFileDialog.getExistingDirectory(self, "选择保存目录", start)
        if chosen:
            self.dir_edit.setText(chosen)

    def _pick_key_file(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "选择 key 文件", "", "文本文件 (*.txt);;所有文件 (*)")
        if chosen:
            self.key_file_edit.setText(chosen)

    def _collect(self) -> DownloadOptions:
        """把表单内容写进 options（以配置里的默认参数为底）。"""
        opt = self.config.defaults.copy()
        opt.url = ""      # 单条 URL 由 _start_download / _preview_command 逐条填充
        # 表单留空 -> 回落到设置页的"默认保存目录"；两者都空时由 runner 用程序目录
        # （早先这里直接填空串，设置页里的默认目录形同虚设）
        opt.save_dir = self.dir_edit.text().strip() or self.config.save_dir
        opt.save_name = self.name_edit.text().strip()
        opt.thread_count = combo_int(self.thread_combo, opt.thread_count)
        opt.retry_count = combo_int(self.retry_combo, opt.retry_count)

        opt.auto_select = self.auto_select_switch.isChecked()
        opt.select_video = self.video_edit.text().strip()
        opt.select_audio = self.audio_edit.text().strip()
        opt.select_subtitle = self.subtitle_edit.text().strip()
        opt.drop_video = self.drop_video_edit.text().strip()
        opt.drop_audio = self.drop_audio_edit.text().strip()
        opt.drop_subtitle = self.drop_subtitle_edit.text().strip()
        opt.sub_only = self.sub_only_switch.isChecked()
        opt.sub_format = self.sub_format_combo.currentText()

        opt.mux_enabled = self.mux_switch.isChecked()
        opt.mux_format = self.mux_format_combo.currentText()
        opt.muxer = self.muxer_combo.currentText()

        opt.use_system_proxy = self.proxy_switch.isChecked()
        opt.custom_proxy = self.proxy_edit.text().strip()
        opt.headers = [line.strip() for line in self.header_edit.toPlainText().splitlines() if line.strip()]

        opt.key = self.key_edit.text().strip()
        opt.key_text_file = self.key_file_edit.text().strip()
        opt.decryption_engine = self.engine_combo.currentText()
        return opt

    def _urls(self) -> list[str]:
        """多行输入 -> 去重后的链接列表（忽略空行与 # 注释行）。"""
        seen: set[str] = set()
        urls: list[str] = []
        for line in self.url_edit.toPlainText().splitlines():
            url = line.strip()
            if not url or url.startswith("#") or url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    def _persist_defaults(self, base: DownloadOptions | None = None) -> bool:
        """把当前这组**参数**写回 config.defaults 并落盘（链接除外，见下）。

        这几项以前只能靠"成功提交一次下载"才会写回，而浏览器扩展投递的任务是以
        config.defaults 为底的 —— 所以想让扩展任务用上新的线程数，得先去假下一次单。
        「应用为默认」按钮走的就是这个函数（download.py 的 _apply_defaults_now）。
        """
        opt = base if base is not None else self._collect()
        defaults = self.config.defaults
        # 注意：**不存链接**。前面几项是"下次还想用"的参数，而链接是一次性的
        # （带 token 的地址、只在当次有效的链接），记住它弊大于利。
        defaults.thread_count = opt.thread_count
        defaults.retry_count = opt.retry_count
        defaults.auto_select = opt.auto_select
        defaults.mux_enabled = opt.mux_enabled
        try:
            self.config.save()
            return True
        except OSError:
            return False

    def _apply_defaults_now(self) -> None:
        """「应用为默认」：立刻把这组参数存成默认值，不用先下点什么。"""
        if not self._persist_defaults():
            toast(self, "保存失败：配置文件写不进去", "error")
            return
        toast(self, "已存为默认参数：%d 线程 · 重试 %d 次"
              % (self.config.defaults.thread_count, self.config.defaults.retry_count), "success")

    def _task_options(self, base: DownloadOptions, url: str, index: int,
                      total: int) -> DownloadOptions:
        """为批量里的第 index 条生成 options；同名会互相覆盖，批量时自动加序号。"""
        opt = base.copy()
        opt.url = url
        if total > 1 and base.save_name:
            opt.save_name = "%s-%d" % (base.save_name, index)
        return opt

    def _start_download(self) -> None:
        urls = self._urls()
        if not urls:
            toast(self, "请先填写视频链接", "error")
            self.url_edit.setFocus()
            return
        # 保存目录留空是**合法**的：runner 会落到程序目录（见 runner.default_save_dir）。
        base = self._collect()
        submitted = 0
        for index, url in enumerate(urls, start=1):
            try:
                self.runner.submit(self._task_options(base, url, index, len(urls)))
            except Exception as exc:  # 提交失败不能把整个窗口带崩
                toast(self, "第 %d 条创建失败：%s" % (index, exc), "error")
                break
            submitted += 1
        if not submitted:
            return
        # 记下这次用的参数，下次打开还是它们（见 _persist_defaults）
        self._persist_defaults(base)
        if submitted == 1:
            if base.save_dir:
                toast(self, "已加入下载队列", "success")
            else:
                toast(self, "已加入下载队列，将保存到 " + default_save_dir(), "success")
        else:
            toast(self, "已批量加入 %d 个任务" % submitted, "success")
        self.gotoRequested.emit(1)

    def _preview_command(self) -> None:
        exe = self.runner.exe() or self.config.nm3u8dl_path
        urls = self._urls()
        if not urls:
            toast(self, "请先填写视频链接", "error")
            return
        base = self._collect()
        parts: list[str] = []
        for index, url in enumerate(urls, start=1):
            if len(urls) > 1:
                parts.append("# ---------- %d/%d ----------" % (index, len(urls)))
            try:
                parts.append(preview_command(
                    exe, self._task_options(base, url, index, len(urls))))
            except Exception as exc:
                parts.append("命令生成失败：%s" % exc)
        CommandPreviewDialog(self, "\n".join(parts)).exec()

    # ------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        """切回本页时补齐默认值，不覆盖用户已填内容。

        默认目录可能刚在设置页改过，所以开关状态与提示要重算一遍；
        但用户自己填的目录不动（_apply_dir_mode 只在"用默认"时才清空）。
        """
        self._apply_dir_mode()


class CommandPreviewDialog(MiuixDialog):
    """预览命令弹窗：只读展示 preview_command() 结果，可一键复制。"""

    def __init__(self, parent: QWidget | None, command: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("预览命令")
        self.resize(760, 320)

        layout = QVBoxLayout()
        layout.setSpacing(ROW_SPACING)
        layout.addWidget(MiuixLabel("N_m3u8DL-RE 命令行", style="title2"))

        self.command_view = MiuixTextEdit()
        self.command_view.setPlainText(command)
        self.command_view.setReadOnly(True)
        self.command_view.setMinimumHeight(150)
        layout.addWidget(self.command_view)

        layout.addWidget(MiuixLabel("复制后可直接在 cmd / PowerShell 中执行", style="caption",
                                    color="on_surface_variant"))
        self.setBodyLayout(layout)

        self.copy_btn = self.addButton("复制命令", "tonal")
        self.copy_btn.clicked.connect(self._copy)
        close_btn = self.addButton("关闭", "text")
        close_btn.clicked.connect(self.reject)

    def _copy(self) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self.command_view.toPlainText())
        toast(self, "命令已复制到剪贴板", "success")
