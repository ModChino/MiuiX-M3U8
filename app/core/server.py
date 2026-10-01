"""浏览器扩展对接用的本地接收端。

只监听 127.0.0.1，提供两个接口：

    GET  /ping   -> {"ok": true, "app": "MiuiX M3U8"}
    POST /add    -> {"ok": true, "task_id": "..."}
                    body: {token, url, title?, referer?, cookie?, user_agent?, headers?,
                           thread_count?}
                    thread_count 省略 = 沿用桌面端默认；取值必须是 4/8/16/32/64，
                    其它值静默忽略（不报错）。

为什么必须带 token：任何网页都能往 localhost 发请求。没有令牌的话，
随便打开一个恶意页面就能往下载器里塞任务或者拿它探测内网。

安全约定（不能省）：
    1. 只绑回环地址，绝不监听 0.0.0.0
    2. token 必填，用 compare_digest 做常数时间比较
    3. 请求体大小上限，超限直接拒
    4. 只做一件事：建下载任务。不碰文件系统、不执行命令、不泄露本机信息
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from PySide6.QtCore import QObject, Signal

from app.core.model import clean_thread_count

#: 请求体上限（扩展只发几十字节的 URL 和头，64KB 足够且能挡住滥用）
MAX_BODY = 64 * 1024
PORT_LOW = 10000          # 五位数端口下界
PORT_HIGH = 65535
PORT_TRIES = 32
#: 等主线程建任务的超时（秒）
TASK_TIMEOUT = 8.0


def random_port() -> int:
    """随机取一个五位数端口号（不保证空闲）。"""
    return secrets.randbelow(PORT_HIGH - PORT_LOW + 1) + PORT_LOW


def pick_free_port(tries: int = PORT_TRIES) -> int:
    """挑一个当前空闲的五位数端口。

    先试绑再释放，严格说存在竞态，但这是自用端口、碰撞概率极低；
    真撞上了 start() 会继续换下一个重试。
    """
    for _ in range(tries):
        port = random_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    return 0


class _Handler(BaseHTTPRequestHandler):
    """请求处理器；token 与回调由 ReceiveServer 在子类化时注入。"""

    token: str = ""
    on_task: Callable[[dict], str] | None = None
    server_version = "MiuiX M3U8"
    protocol_version = "HTTP/1.1"

    # 别把每个请求都打到 stderr
    def log_message(self, *args) -> None:  # noqa: D102
        pass

    # ---------------------------------------------------------------- 工具
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 允许扩展直接 fetch（虽然油猴用 GM_xmlhttpRequest 可绕过，但浏览器里
        # 手动测接口时方便）。真正的鉴权靠 token，不靠 Origin。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    # ---------------------------------------------------------------- 路由
    def do_OPTIONS(self) -> None:      # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:          # noqa: N802
        if self._path() == "/ping":
            self._send(200, {"ok": True, "app": "MiuiX M3U8"})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:         # noqa: N802
        if self._path() != "/add":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self._send(400, {"ok": False, "error": "empty body"})
            return
        if length > MAX_BODY:
            self._send(413, {"ok": False, "error": "body too large"})
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(data, dict):
            self._send(400, {"ok": False, "error": "invalid payload"})
            return

        given = str(data.get("token") or "")
        if not self.token or not secrets.compare_digest(given, self.token):
            self._send(403, {"ok": False, "error": "bad token"})
            return

        url = str(data.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            self._send(400, {"ok": False, "error": "url must be http(s)"})
            return

        extra = data.get("headers")
        # 白名单是"重建一个 dict"、只放行下面这几个键 —— 新增字段忘了加进来就会
        # **静默丢弃**（扩展传了也当没传，很难查）。加字段务必同步这里。
        payload = {
            "url": url,
            "title": str(data.get("title") or "")[:200],
            "referer": str(data.get("referer") or "")[:1000],
            "cookie": str(data.get("cookie") or "")[:8000],
            "user_agent": str(data.get("user_agent") or "")[:500],
            "headers": {str(k)[:80]: str(v)[:800]
                        for k, v in (extra.items() if isinstance(extra, dict) else [])},
        }
        # 扩展显式指定的下载线程数。契约：**键不存在 = 不覆盖**，所以只有拿到合法值
        # 才放进 payload（0 / null 都不是"跟随"的意思，见 SPEC-thread-count.md §3）。
        thread_count = clean_thread_count(data.get("thread_count"))
        if thread_count is not None:
            payload["thread_count"] = thread_count
        task_id = ""
        if self.on_task is not None:
            try:
                task_id = self.on_task(payload) or ""
            except Exception:      # 回调出错不能让 HTTP 线程崩
                task_id = ""
        if task_id:
            self._send(200, {"ok": True, "task_id": task_id})
        else:
            self._send(500, {"ok": False, "error": "submit failed"})


class ReceiveServer(QObject):
    """本地接收端：HTTP 服务跑在后台线程，建任务的活交给主线程。

    跨线程回填 task_id 的做法：HTTP 线程发 taskRequested 信号（排队到主线程），
    主线程处理完调用 submit_result() 唤醒等待中的 HTTP 线程。
    """

    taskRequested = Signal(dict)
    started = Signal(int)
    stopped = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port = 0
        self._slot: dict = {}
        self._done = threading.Event()

    # ---------------------------------------------------------------- 查询
    def port(self) -> int:
        return self._port

    def is_running(self) -> bool:
        return self._httpd is not None

    def base_url(self) -> str:
        return "http://127.0.0.1:%d" % self._port if self._port else ""

    # ---------------------------------------------------------------- 生命周期
    def start(self, port: int, token: str, prefer_port: bool = True) -> int:
        """启动服务，返回实际端口；0 表示失败。port=0 时自动挑空闲端口。"""
        if self._httpd is not None:
            return self._port
        if not token:
            self.failed.emit("缺少访问令牌")
            return 0

        handler = type("_BoundHandler", (_Handler,),
                       {"token": token, "on_task": self._request_task})
        candidates: list[int] = []
        if prefer_port and port:
            candidates.append(int(port))
        for _ in range(PORT_TRIES):
            free = pick_free_port(tries=1)
            if free:
                candidates.append(free)
        if port and port not in candidates:
            candidates.insert(0, int(port))

        for candidate in candidates:
            try:
                httpd = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            except OSError:
                continue
            httpd.daemon_threads = True
            self._httpd = httpd
            self._port = int(httpd.server_address[1])
            self._thread = threading.Thread(
                target=httpd.serve_forever, name="miuix-m3u8-http", daemon=True)
            self._thread.start()
            self.started.emit(self._port)
            return self._port

        self.failed.emit("无法绑定本地端口（都被占用或权限不足）")
        return 0

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        self._port = 0
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except OSError:
                pass
        self._done.set()          # 放掉可能在等结果的 HTTP 线程
        self.stopped.emit()

    # ---------------------------------------------------------------- 跨线程
    def _request_task(self, payload: dict) -> str:
        """HTTP 线程调用：请主线程建任务并等它回填 id。"""
        self._slot = {}
        self._done.clear()
        self.taskRequested.emit(payload)
        self._done.wait(TASK_TIMEOUT)
        return str(self._slot.get("task_id") or "")

    def submit_result(self, task_id: str) -> None:
        """主线程建完任务后调用，唤醒等待中的 HTTP 线程。"""
        self._slot = {"task_id": task_id or ""}
        self._done.set()
