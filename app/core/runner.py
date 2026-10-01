"""任务调度：跑 N_m3u8DL-RE、实时解析输出、节流发信号、取消/重试/清理。

只依赖 QtCore（QObject/Signal/QTimer/QCoreApplication），禁止 import QtWidgets。

为什么不用 QProcess（实测结论）：
1. Windows 弹黑窗：PyInstaller --windowed 打包后父进程没有控制台，CreateProcess 一个
   console 子程序会让系统给它新建控制台窗口 —— 每个任务弹一个黑窗。标准解法是
   CREATE_NO_WINDOW (0x08000000)，但 PySide6 6.11 没绑定 QProcess 的
   setCreateProcessArgumentsModifier，所以改用 subprocess.Popen 传 creationflags
   （再补 startupinfo SW_HIDE 兜底）。
2. POSIX 必须给伪终端：stdout 是普通管道时 v0.6.0-beta 会在开始下载瞬间崩溃
   （Spectre.Console LiveRenderable 越界 -> SIGABRT / exit 134），所以 POSIX 下用
   script -qec "<命令>" /dev/null 包一层；TERM 为空时进度条又完全不输出，
   故强制注入 TERM=xterm-256color 与 SHELL=/bin/sh。
3. Popen 的管道阻塞读会卡死 Qt 事件循环，所以每个任务一个后台读线程，
   线程里只发 Qt 信号（跨线程自动 QueuedConnection），所有状态改动仍在主线程做。

详情与原始样例见 docs/nm3u8dl-sample-output.txt。
"""
from __future__ import annotations

import codecs
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from .config import exe_dir
from .model import DownloadOptions, DownloadTask, TaskStatus
from .nm3u8dl import build_command
from .parser import Event, OutputParser, resolve_output_path

#: 子进程输出到 UI 的最小间隔（毫秒），避免刷爆界面
THROTTLE_MS = 80
#: 每个任务最多保留的日志行数
MAX_LOG_LINES = 2000
#: 读线程每次读取的字节数
READ_CHUNK = 65536
#: 合并阶段主动刷新的间隔（ms）。RE 在合并时零输出，只能靠定时器维持界面活性。
MUX_TICK_MS = 500

#: ffmpeg 转发进 RE 日志的重复告警前缀。大文件混流时可达数万条，
#: 全部记进日志既无意义又会拖垮 UI，按类折叠成一条计数。
_NOISE_PREFIXES = (
    "[in#", "[out#", "[vost#", "[mpegts @", "[mp4 @", "[matroska @",
    "Invalid DTS", "Invalid timestamps", "Non-monotonic DTS",
)


def default_save_dir() -> str:
    """save_dir 留空时的落盘目录。

    界面提示写的是"留空则使用程序当前目录"，所以这里必须返回**程序所在目录**：
    打包后是 exe 所在目录，开发时是项目根。早先直接用了系统临时目录，
    结果产物静静躺在 %TEMP% 里，用户根本找不到 —— 提示与行为不符。

    与配置文件同源（core.config.exe_dir），所以「配置」和「下载产物」永远在同一个
    地方 —— 便携版拷走整个目录就都带走了。
    """
    return str(exe_dir())


def _pick_work_dir(save_dir: str) -> str:
    """挑子进程的工作目录：指定的保存目录 > 程序目录（不可写时退回临时目录）。

    RE 在没有 --save-dir 时把产物写到自己的 cwd，所以这个目录**就是**最终落盘位置。
    """
    if save_dir:
        return save_dir if os.path.isdir(save_dir) else tempfile.gettempdir()
    base = default_save_dir()
    if os.path.isdir(base) and os.access(base, os.W_OK):
        return base
    return tempfile.gettempdir()


def _noise_key(text: str) -> str | None:
    """判断是否属于可折叠的 ffmpeg 噪声，返回类别名；否则 None。"""
    for prefix in _NOISE_PREFIXES:
        if prefix in text:
            return prefix
    return None

#: Windows：不新建控制台窗口
CREATE_NO_WINDOW = 0x08000000

#: 日志行前缀，用来给 UI 显示更干净的 message
_LINE_PREFIX = re.compile(
    r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+(?:TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s*:\s?"
)


def _creation_kwargs(platform_name: str | None = None) -> dict:
    """跨平台进程创建参数。

    - Windows：CREATE_NO_WINDOW + STARTUPINFO(SW_HIDE)，避免 GUI 程序弹黑色控制台窗口；
    - POSIX：start_new_session=True，让子进程自成进程组，方便整组 SIGKILL。

    platform_name 可显式传入（"nt"/"posix"），方便在 Linux 上自检 Windows 分支。
    """
    name = os.name if platform_name is None else platform_name
    if name == "nt":
        kwargs: dict = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW)}
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        if startupinfo_cls is not None:          # 非 Windows 上取不到这个类
            info = startupinfo_cls()
            info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
            info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = info
        return kwargs
    return {"start_new_session": True}


def _pty_available() -> bool:
    """POSIX 上是否有 util-linux 的 script（提供伪终端）。"""
    return os.name != "nt" and shutil.which("script") is not None


def _wrap_pty(argv: list[str]) -> tuple[str, list[str]]:
    """把 argv 包进伪终端；不可用时原样返回。"""
    if not _pty_available():
        return argv[0], argv[1:]
    script_exe = shutil.which("script") or "script"
    return script_exe, ["-qec", shlex.join(argv), "/dev/null"]


def _descendants(pid: int) -> list[int]:
    """列出 pid 的全部后代进程（读 /proc，仅 Linux；失败返回空表）。"""
    if pid <= 0 or not os.path.isdir("/proc"):
        return []
    children: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/" + entry + "/stat", "rb") as handle:
                tail = handle.read().rsplit(b")", 1)[-1].split()
            ppid = int(tail[1])
        except (OSError, IndexError, ValueError):
            continue
        children.setdefault(ppid, []).append(int(entry))
    found: list[int] = []
    stack = [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def _signal_pid(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        pass


class _StreamDecoder:
    """子进程 stdout 解码器：UTF-8 优先，乱码时回退 GB18030(GBK)。

    N_m3u8DL-RE 是 .NET 程序：Windows 下 stdout 重定向到管道时用的是控制台输出编码
    （中文系统通常是 GBK/936），未必是 UTF-8；Linux 上是 UTF-8。样例实测见
    docs/nm3u8dl-sample-output.txt：只有 ASCII + UTF-8 的制表符/盲文，没有中文。

    判定依据（低成本、不引入新依赖）：GBK 一个汉字是 2 个高位字节，按 UTF-8 解会变成
    连续两个 U+FFFD；正常 UTF-8 日志里出现连续替换符的概率极低。于是：
    1. 试读期：先攒字节（遇到 \r / \n 或满 4KB 就定），按 UTF-8 解；一旦发现连续
       替换符就换成 GB18030，并用原始字节把这段重放一遍；
    2. 之后就一路用选定的增量解码器；之后若又出现连续替换符，再做一次兜底切换；
    3. 全程 errors="replace"，任何情况下都不会让解析流水线抛异常。
    """

    PROBE_BYTES = 4096
    RUN_LIMIT = 2          # 连续替换符达到这个长度就判定不是 UTF-8
    RATIO_LIMIT = 0.15     # 散落的替换符：占比超过它也算
    RATIO_MIN_CHARS = 32

    def __init__(self) -> None:
        self.encoding = "utf-8"
        self.switched = False
        self._decoder = codecs.getincrementaldecoder(self.encoding)("replace")
        self._probe = bytearray()
        self._probed = False

    # -------------------------------------------------------------- 内部
    @staticmethod
    def _worst_run(text: str) -> int:
        """最长的连续 U+FFFD 长度。"""
        worst = run = 0
        for char in text:
            if char == "\ufffd":
                run += 1
                worst = max(worst, run)
            else:
                run = 0
        return worst

    def _looks_broken(self, text: str) -> bool:
        broken = text.count("\ufffd")
        if not broken:
            return False
        if self._worst_run(text) >= self.RUN_LIMIT:
            return True
        return len(text) >= self.RATIO_MIN_CHARS and broken / len(text) > self.RATIO_LIMIT

    def _switch(self) -> None:
        self.encoding = "gb18030"
        self.switched = True
        self._decoder = codecs.getincrementaldecoder("gb18030")("replace")

    # -------------------------------------------------------------- 对外
    def decode(self, data: bytes, final: bool = False) -> str:
        """解码一段字节；final=True 时把试读期里剩下的字节也吐出来。"""
        if not self._probed:
            self._probe += data
            if not final and len(self._probe) < self.PROBE_BYTES \
                    and b"\n" not in self._probe and b"\r" not in self._probe:
                return ""
            raw = bytes(self._probe)
            self._probe = bytearray()
            self._probed = True
            if not raw:
                return ""
            text = self._decoder.decode(raw)
            if self._looks_broken(text):
                self._switch()
                text = self._decoder.decode(raw)
            return text
        text = self._decoder.decode(data, final)
        if text and self.encoding == "utf-8" and self._looks_broken(text):
            self._switch()
            text = self._decoder.decode(data)
        return text


class TaskRunner(QObject):
    """下载任务调度器。契约见 docs/INTERFACES.md §4.4。"""

    taskAdded = Signal(str)             # task_id
    taskUpdated = Signal(str)           # task_id
    taskFinished = Signal(str, int)     # task_id, exit_code

    # 内部信号：读线程 -> 主线程（跨线程自动 QueuedConnection）
    _chunkReady = Signal(str, object)
    _procExited = Signal(str, int)

    def __init__(self, parent: QObject | None = None, max_concurrent: int = 2) -> None:
        super().__init__(parent)
        self._exe: str = ""
        self._max_concurrent: int = max(1, int(max_concurrent))
        self._tasks: dict[str, DownloadTask] = {}
        self._order: list[str] = []                 # 新 -> 旧
        self._procs: dict[str, subprocess.Popen] = {}
        self._readers: dict[str, threading.Thread] = {}
        self._parsers: dict[str, OutputParser] = {}
        self._decoders: dict[str, _StreamDecoder] = {}
        self._noise: dict[str, tuple[str, int]] = {}   # task_id -> (类别, 已折叠条数)
        self._throttled: set[str] = set()              # 被服务端限流过的任务
        self._pending: list[str] = []               # 排队中的任务 id
        self._canceled: set[str] = set()
        self._dirty: set[str] = set()
        self._last_emit: dict[str, float] = {}
        self._env_noted: set[str] = set()

        self._chunkReady.connect(self._on_chunk)
        self._procExited.connect(self._on_proc_exit)

        self._timer = QTimer(self)
        self._timer.setInterval(THROTTLE_MS)
        self._timer.timeout.connect(self._flush_dirty)

        # 合并阶段 N_m3u8DL-RE 一行输出都没有（实测一次二进制合并持续 168 秒、
        # 期间零事件），界面完全静止会被当成卡死。这里主动定期刷新，
        # 让"已用 Ns"和进度条滑动动画持续动起来。
        self._mux_timer = QTimer(self)
        self._mux_timer.setInterval(MUX_TICK_MS)
        self._mux_timer.timeout.connect(self._tick_mux)

        app = QCoreApplication.instance()
        if app is not None:                          # 退出时别把子进程留在后台
            app.aboutToQuit.connect(self._kill_all)

    # ------------------------------------------------------------ 配置
    def set_exe(self, path: str) -> None:
        """设置 N_m3u8DL-RE 可执行文件路径。"""
        self._exe = path or ""

    def exe(self) -> str:
        return self._exe

    def set_max_concurrent(self, n: int) -> None:
        """设置并发上限；调大后立刻把排队任务放出去。"""
        self._max_concurrent = max(1, int(n))
        self._pump()

    # ------------------------------------------------------------ 查询
    @property
    def tasks(self) -> list[DownloadTask]:
        """全部任务，新 -> 旧。"""
        return [self._tasks[tid] for tid in self._order if tid in self._tasks]

    def get(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    def running_count(self) -> int:
        return len(self._procs)

    # ------------------------------------------------------------ 提交
    def submit(self, opt: DownloadOptions) -> str:
        """新建任务并立即排队（有空位就开始跑），返回任务 id。"""
        task = DownloadTask(options=opt.copy())
        self._tasks[task.id] = task
        self._order.insert(0, task.id)
        self._pending.append(task.id)
        self.taskAdded.emit(task.id)
        self._pump()
        return task.id

    def cancel(self, task_id: str) -> None:
        """取消：排队中的直接出队；运行中的连根杀掉进程树。"""
        task = self._tasks.get(task_id)
        if task is None or task.status.is_final:
            return
        self._canceled.add(task_id)
        if task_id in self._pending:
            self._pending.remove(task_id)
            task.status = TaskStatus.CANCELED
            task.message = "已取消"
            task.finished_at = time.time()
            self._emit_now(task_id)
            self.taskFinished.emit(task_id, -1)
            return
        proc = self._procs.get(task_id)
        if proc is not None:
            self._kill_tree(proc)
        task.status = TaskStatus.CANCELED
        task.message = "已取消"
        self._emit_now(task_id)

    def retry(self, task_id: str) -> str:
        """用同样的参数新建一个任务，返回新任务 id（原任务保留）。

        若该任务被服务端限流过（429/503 等），自动**降速重试**：
        线程数减半、重试次数与超时上调 —— 这类失败原地重试通常继续失败。
        """
        old = self._tasks.get(task_id)
        if old is None:
            raise KeyError("任务不存在: " + task_id)
        if not old.status.is_final:
            self.cancel(task_id)
        opt = old.options.copy()
        if task_id in self._throttled:
            before = opt.thread_count
            opt.thread_count = max(4, int(before) // 2)
            opt.retry_count = max(int(opt.retry_count), 8)
            opt.http_timeout = max(int(opt.http_timeout), 120)
            new_id = self.submit(opt)
            self._throttled.discard(task_id)
            new_task = self._tasks.get(new_id)
            if new_task is not None:
                new_task.message = "上次被限流，已自动降为 %d 线程并加大重试重试" % opt.thread_count
                self._emit_now(new_id)
            return new_id
        return self.submit(opt)

    def remove(self, task_id: str) -> None:
        """移除任务（还在跑就先取消）。"""
        task = self._tasks.get(task_id)
        if task is None:
            return
        if not task.status.is_final:
            self.cancel(task_id)
        self._forget(task_id)

    def clear_finished(self) -> list[str]:
        """移除所有已结束任务，返回被移除的 id 列表（新 -> 旧）。"""
        removed: list[str] = []
        for task_id in list(self._order):
            task = self._tasks.get(task_id)
            if task is not None and task.status.is_final:
                self._forget(task_id)
                removed.append(task_id)
        return removed

    # ------------------------------------------------------------ 调度
    def _pump(self) -> None:
        while self._pending and len(self._procs) < self._max_concurrent:
            task_id = self._pending.pop(0)
            task = self._tasks.get(task_id)
            if task is None or task.status.is_final:
                continue
            self._start(task_id)

    def _start(self, task_id: str) -> None:
        task = self._tasks[task_id]
        if not self._exe:
            self._fail(task_id, "未配置 N_m3u8DL-RE 可执行文件（设置页里指定路径）")
            self._pump()
            return
        try:
            argv = build_command(self._exe, task.options)
        except ValueError as exc:
            self._fail(task_id, str(exc))
            self._pump()
            return

        program, args = _wrap_pty(argv)
        env = os.environ.copy()
        if _pty_available():
            # script 用 $SHELL -c 执行命令，必须固定成 sh；TERM 决定进度表是否输出
            env["SHELL"] = "/bin/sh"
            env["TERM"] = "xterm-256color"
        # 没配 --save-dir 时 RE 会写到自己的 cwd —— 这里必须落成"程序当前目录"，
        # 才能和界面提示一致（见 default_save_dir）。
        work_dir = _pick_work_dir(task.options.save_dir)
        cwd = work_dir if os.path.isdir(work_dir) else None
        try:
            proc = subprocess.Popen(
                [program] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,       # 合并 stderr（契约要求）
                bufsize=0,
                cwd=cwd,
                env=env,
                **_creation_kwargs(),
            )
        except OSError as exc:
            self._fail(task_id, "无法启动进程：%s（%s）" % (self._exe, exc))
            self._pump()
            return

        self._procs[task_id] = proc
        self._parsers[task_id] = OutputParser()
        self._decoders[task_id] = _StreamDecoder()
        self._canceled.discard(task_id)
        reader = threading.Thread(
            target=self._reader_loop, args=(task_id, proc),
            name="miuix-m3u8-reader-" + task_id, daemon=True,
        )
        self._readers[task_id] = reader
        reader.start()

        task.status = TaskStatus.RUNNING
        task.message = "启动中…"
        self._emit_now(task_id)

    def _fail(self, task_id: str, message: str) -> None:
        """不入队直接失败（启动前的配置错误）。"""
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = TaskStatus.FAILED
        task.message = message
        task.exit_code = -1
        task.finished_at = time.time()
        task.log.append(message)
        self._emit_now(task_id)
        self.taskFinished.emit(task_id, -1)

    # ------------------------------------------------------------ 读线程
    def _reader_loop(self, task_id: str, proc: subprocess.Popen) -> None:
        """后台线程：阻塞读子进程输出（bufsize=0，读到多少发多少）。"""
        stream = proc.stdout
        fd = stream.fileno() if stream is not None else -1
        try:
            while fd >= 0:
                try:
                    data = os.read(fd, READ_CHUNK)
                except OSError:
                    break
                if not data:
                    break
                self._chunkReady.emit(task_id, data)
        finally:
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
            try:
                code = proc.wait()
            except OSError:
                code = -1
            self._procExited.emit(task_id, int(code))

    # ------------------------------------------------------------ 主线程槽
    def _on_chunk(self, task_id: str, data: object) -> None:
        parser = self._parsers.get(task_id)
        decoder = self._decoders.get(task_id)
        if parser is None or decoder is None or not data:
            return
        text = decoder.decode(bytes(data))
        if decoder.switched and task_id not in self._env_noted:
            self._env_noted.add(task_id)
            task = self._tasks.get(task_id)
            if task is not None:
                self._append_log(task, "（子进程输出不是 UTF-8，已按 " + decoder.encoding + " 解码）")
        if text:
            self._apply(task_id, parser.feed(text))

    def _apply(self, task_id: str, events: list[Event]) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        changed = False
        for ev in events:
            if ev.kind == "progress":
                if ev.percent is not None:
                    task.percent = ev.percent
                if ev.speed:
                    task.speed = ev.speed
                if ev.size:
                    task.size = ev.size
                if ev.eta:
                    task.eta = ev.eta
                if ev.segments_done is not None and ev.segments_total is not None:
                    task.segments = str(ev.segments_done) + "/" + str(ev.segments_total)
                changed = True
                continue
            self._append_log(task, ev.text)
            changed = True
            if ev.kind == "throttle":
                # 被服务端限流：记下来，让"重试"能对症下药（自动降速）
                self._throttled.add(task_id)
                code = parser.detect_throttle(ev.text) if parser is not None else ""
                hint = ("HTTP " + code) if code.isdigit() else "限流"
                if task.status is TaskStatus.RUNNING:
                    task.message = "被服务器限流（%s），正在重试…重试时会自动降速" % hint
                changed = True
                continue
            if ev.kind == "mux":
                task.status = TaskStatus.MUXING
                # 合并阶段 ffmpeg 的海量告警会被 RE 原样转发，别让它们顶掉状态文案
                task.message = "正在合并音视频…"
                if not self._mux_timer.isActive():
                    self._mux_timer.start()
                changed = True
                continue
            if ev.kind == "done" and ev.path:
                task.output_path = ev.path
            # 合并阶段保持固定文案：此刻 RE 转发的都是 ffmpeg 告警，
            # 一旦让它们参与赋值，_apply 结束时发出去的 message 就变成告警刷屏。
            if ev.text and task.status is not TaskStatus.MUXING:
                task.message = _LINE_PREFIX.sub("", ev.text)[:200]
        if changed:
            self._touch(task_id)

    def _append_log(self, task: DownloadTask, text: str) -> None:
        if not text:
            return
        # ffmpeg 混流大文件时，N_m3u8DL-RE 会把它的告警原样转发 —— 实测一次下载里
        # "Invalid DTS"/"Invalid timestamps" 各 2.6 万条，占全部输出 99.8%。
        # 同类告警只留首条 + 一个折叠计数，否则日志会被刷爆、UI 直接卡死。
        key = _noise_key(text)
        if key is not None:
            cur = self._noise.get(task.id)
            if cur is not None and cur[0] == key:
                self._noise[task.id] = (key, cur[1] + 1)
                return
            self._flush_noise(task)
            self._noise[task.id] = (key, 1)
        else:
            self._flush_noise(task)
        task.log.append(text)
        # 批量裁剪（摊还 O(1)）：原来每追加一行都 del log[:1]，5 万行 × 2000 元素
        # 的搬移量就是"合并完未响应"的主因。
        if len(task.log) > MAX_LOG_LINES * 2:
            del task.log[: len(task.log) - MAX_LOG_LINES]

    def _flush_noise(self, task: DownloadTask) -> None:
        """把上一类被折叠的 ffmpeg 告警计数落进日志。"""
        cur = self._noise.pop(task.id, None)
        if cur is not None and cur[1] > 1:
            task.log.append("（已折叠 %d 条同类 ffmpeg 告警：%s）" % (cur[1] - 1, cur[0]))

    # ------------------------------------------------------------ 结束
    def _on_proc_exit(self, task_id: str, code: int) -> None:
        # 收尾：把解析缓冲区里的最后一点输出处理掉
        parser = self._parsers.get(task_id)
        decoder = self._decoders.get(task_id)
        if parser is not None and decoder is not None:
            tail = decoder.decode(b"", final=True)
            if tail:
                self._apply(task_id, parser.feed(tail))
            self._apply(task_id, parser.flush())
        self._procs.pop(task_id, None)
        self._readers.pop(task_id, None)
        self._decoders.pop(task_id, None)
        self._env_noted.discard(task_id)

        task = self._tasks.get(task_id)
        if task is None:                    # 任务已被 remove()
            self._pump()
            return

        self._flush_noise(task)         # 把最后一段被折叠的告警计数落盘
        task.exit_code = int(code)
        task.finished_at = time.time()
        if task_id in self._canceled:
            task.status = TaskStatus.CANCELED
            task.message = "已取消"
        elif code == 0:
            task.status = TaskStatus.DONE
            # --no-ansi-color / TERM=dumb 下进度刷新很稀，快流可能一帧进度都没有；
            # 既然退出码是 0，进度按 100% 记（否则卡片会停在 0% 显示"已完成"）
            task.percent = 100.0
            self._resolve_output(task_id, task, parser)
        else:
            task.status = TaskStatus.FAILED
            task.message = task.message or ("下载失败（exit=" + str(code) + "）")

        self._canceled.discard(task_id)
        self._emit_now(task_id)
        self.taskFinished.emit(task_id, int(code))
        self._pump()

    def _resolve_output(self, task_id: str, task: DownloadTask, parser: OutputParser | None) -> None:
        """任务成功后确定最终产物路径。

        只扫一次目录：parser 的行与 task.log 内容基本重合，早先分两路各扫一遍，
        而下载目录里可能有上千个分片，重复扫描会明显拖慢收尾（表现为"合并完卡一下"）。
        """
        fmt = task.options.mux_format if task.options.mux_enabled else ""
        lines = (parser.lines() if parser is not None else []) + list(task.log)
        path = resolve_output_path(lines, task.options.save_dir, task.options.save_name, fmt)
        if path:
            task.output_path = path
            task.message = "已完成：" + path
        elif task.status is TaskStatus.DONE:
            # 实在定位不到产物也要给个明确文案，别停在"正在合并音视频…"
            task.message = "已完成"
        self._parsers.pop(task_id, None)

    # ------------------------------------------------------------ 节流发信号
    def _touch(self, task_id: str) -> None:
        """标记变化：距上次发射 >= THROTTLE_MS 立即发，否则攒着让定时器统一发。"""
        now = time.monotonic()
        if (now - self._last_emit.get(task_id, 0.0)) * 1000.0 >= THROTTLE_MS:
            self._emit_now(task_id)
        else:
            self._dirty.add(task_id)
            if not self._timer.isActive():
                self._timer.start()

    def _tick_mux(self) -> None:
        """合并阶段没有子进程输出，主动推送刷新（否则界面静止像卡死）。"""
        live = [tid for tid, t in self._tasks.items() if t.status is TaskStatus.MUXING]
        if not live:
            self._mux_timer.stop()
            return
        for tid in live:
            self._emit_now(tid)

    def _flush_dirty(self) -> None:
        for task_id in list(self._dirty):
            self._emit_now(task_id)
        if not self._dirty:
            self._timer.stop()

    def _emit_now(self, task_id: str) -> None:
        self._dirty.discard(task_id)
        self._last_emit[task_id] = time.monotonic()
        self.taskUpdated.emit(task_id)

    # ------------------------------------------------------------ 清理
    def _forget(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._parsers.pop(task_id, None)
        self._decoders.pop(task_id, None)
        self._last_emit.pop(task_id, None)
        self._noise.pop(task_id, None)
        self._env_noted.discard(task_id)
        self._dirty.discard(task_id)
        self._canceled.discard(task_id)
        if task_id in self._pending:
            self._pending.remove(task_id)
        if task_id in self._order:
            self._order.remove(task_id)

    def _kill_all(self) -> None:
        """退出前收掉所有还活着的子进程（不触发信号）。"""
        for proc in list(self._procs.values()):
            self._kill_tree(proc)

    def _kill_tree(self, proc: subprocess.Popen) -> None:
        """杀掉进程树：script 包出来的下载进程会自己 setsid，只杀外层不够。"""
        pid = int(proc.pid or 0)
        victims = _descendants(pid)
        if os.name == "nt" and pid:
            try:                            # 系统自带，连根杀
                subprocess.Popen(["taskkill", "/PID", str(pid), "/T", "/F"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 **_creation_kwargs())
            except OSError:
                pass
        for victim in victims:
            _signal_pid(victim, signal.SIGKILL)
        if os.name != "nt" and pid:
            # start_new_session=True 让外层自成进程组，整组一起杀
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
        try:
            proc.kill()
        except OSError:
            pass
