"""MiuiX M3U8 程序入口。

启动顺序（契约 §5）：init_theme → Config.load → TaskRunner → MainWindow → exec。
另起一个可选的本地接收端（app/core/server.py），供浏览器扩展投递下载任务。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.config import _base_dir, Config, detect_tools
from app.core.model import DownloadOptions, clean_thread_count
from app.core.runner import TaskRunner
from app.core.server import ReceiveServer
from app.miuix.theme import init_theme
from app.ui import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.ui.window import MainWindow

#: 文件名里不能出现的字符（Windows 限制）与控制字符
_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
#: 文件名长度上限（给路径总长留余量）
_MAX_NAME = 120


def _tool_ok(path: str) -> bool:
    """外部工具路径是否还指着一个真实存在的文件。"""
    return bool(path) and Path(path).is_file()


def clean_title(title: str) -> str:
    """把网页标题清洗成安全的文件名。

    扩展会把 document.title 之类原样发过来，里面常有 '|'、':'、站点后缀、
    表情符号和超长尾巴 —— 不处理的话 RE 会因为文件名非法直接失败。
    """
    name = _BAD_NAME_CHARS.sub("_", title or "")
    name = re.sub(r"\s+", " ", name).strip(" ._-")
    return name[:_MAX_NAME]


def build_extension_options(config: Config, payload: dict) -> DownloadOptions:
    """把扩展投递的 payload 变成一次下载的 options。

    关键是把 Referer / Cookie / User-Agent 透传给 RE —— 有加密 m3u8 的站点
    通常对 key 请求也做防盗链，缺了这几个头就解不开。
    """
    opt = config.defaults.copy()
    opt.url = str(payload.get("url") or "")
    title = clean_title(str(payload.get("title") or ""))
    if title:
        opt.save_name = title

    headers: list[str] = []
    for label, value in (("Referer", payload.get("referer")),
                         ("Cookie", payload.get("cookie")),
                         ("User-Agent", payload.get("user_agent"))):
        if value:
            headers.append("%s: %s" % (label, value))
    extra = payload.get("headers")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if str(key).lower() in ("referer", "cookie", "user-agent"):
                continue            # 上面已处理，避免重复
            headers.append("%s: %s" % (key, value))
    if headers:
        opt.headers = headers

    # 扩展显式指定的线程数只作用于**这一个任务**，不写回 config.defaults ——
    # 那会造出第二个数据源（设置页那张「默认参数」卡片当年就是这么被删掉的）。
    #   · 键不存在  -> clean_thread_count(None) = None -> 沿用 defaults
    #   · 白名单外  -> 同样 None -> 沿用 defaults（服务端已挡过一层，这里再挡一次，
    #                  因为本函数也会被自检/其它调用方直接喂 payload）
    threads = clean_thread_count(payload.get("thread_count"))
    if threads is not None:
        opt.thread_count = threads
    return opt


def build_app(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    """建 QApplication / 主题 / 配置 / runner / 接收端 / 主窗口；供 main() 与自检脚本复用。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)

    # 窗口/任务栏图标。不设这个的话，Windows 任务栏显示的是系统默认的空白程序图标
    # （exe 文件本身的图标只在资源管理器里生效，不会自动变成窗口图标）。
    # 图标随 --add-data "docs\icon;docs\icon" 打进来，frozen 时在 _MEIPASS 下。
    icon_path = _base_dir() / "docs" / "icon" / "MiuiX-M3U8.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    manager = init_theme(app)          # 1. 初始化 Miuix 主题
    config = Config.load()             # 2. 载入配置
    manager.set_mode(config.theme_mode or "system")

    # 3. 补全外部工具路径（配置 → tools 目录 → PATH）。
    #    判据是"文件还在不在"，不是"字段空不空" —— 移动过 exe、或者换过打包方式时，
    #    配置里存的老路径会失效，只看空字段就会拿着死路径去启动下载。
    if not _tool_ok(config.nm3u8dl_path) or not _tool_ok(config.ffmpeg_path):
        found = detect_tools()
        if found.get("nm3u8dl"):
            config.nm3u8dl_path = found["nm3u8dl"]
        if found.get("ffmpeg"):
            config.ffmpeg_path = found["ffmpeg"]
        config.defaults.ffmpeg_path = config.ffmpeg_path

    runner = TaskRunner(max_concurrent=config.max_concurrent)   # 4. 任务调度器
    runner.set_exe(config.nm3u8dl_path)

    # 5. 本地接收端（浏览器扩展）。默认关闭，由设置页开启 —— 这个接口能建任务，
    #    不能让它在用户不知情时监听着。
    server = ReceiveServer()

    def _on_extension_task(payload: dict) -> None:
        """扩展投递的任务：主线程建任务后回填 id（HTTP 线程正阻塞等结果）。"""
        task_id = ""
        try:
            task_id = runner.submit(build_extension_options(config, payload))
        except Exception:
            task_id = ""
        server.submit_result(task_id)

    server.taskRequested.connect(_on_extension_task)
    app.aboutToQuit.connect(server.stop)

    window = MainWindow(runner, config, server=server)           # 6. 主窗口
    window.setWindowTitle(APP_NAME)
    # 注意：别在主窗口上 setToolTip —— Qt 会把父控件的 tooltip 继承给所有没有
    # 自己 tooltip 的子控件，鼠标停在界面任意位置都会弹出这句描述。
    # 该描述已经在「关于」页与设置页展示。

    if config.server_enabled and config.server_token:
        server.start(config.server_port, config.server_token)
    return app, window


def main() -> int:
    app, window = build_app()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
