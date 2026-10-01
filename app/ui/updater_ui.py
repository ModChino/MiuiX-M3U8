"""内核更新卡片的 Qt 胶水层。

单独一个文件是为了守住分层：app/core/updater.py 是纯标准库（连 QtCore 都不 import），
没有显示器也能自检；线程、信号这些 Qt 的东西全放这里。

**线程模型**：updater 里的动作是一次几十秒的同步调用（跑子进程 + 联网 + 下载），
放主线程会把界面冻住。所以丢进 Python 后台线程，结果用信号发回来 ——
Python 线程里 emit，接收者在 GUI 线程，Qt 会自动排队（与 runner.py 的读线程同一套）。
"""
from __future__ import annotations

import socket
import urllib.error

from PySide6.QtCore import QObject, Signal


class UpdateBridge(QObject):
    """后台线程 → 主线程的信号桥。"""

    #: 阶段名, 结果对象（"local" -> str；"remote" -> updater.Release）
    done = Signal(str, object)
    #: 阶段名, 人话错误
    failed = Signal(str, str)
    #: 已下载字节, 总字节（0 表示对面没给 Content-Length）
    progress = Signal(int, int)
    #: 版本号, 内核路径, 备份路径
    installed = Signal(str, str, str)


def human_error(exc: BaseException) -> str:
    """把网络/文件异常翻成用户看得懂的一句话。"""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 403:
            return "HTTP 403：GitHub 限流或加速服务拒绝，稍后再试或换加速地址"
        if exc.code == 404:
            return "HTTP 404：地址不对（加速地址格式写错了？）"
        return "HTTP %s %s" % (exc.code, exc.reason)
    if isinstance(exc, urllib.error.URLError):
        return "连不上：%s —— 检查网络，或在「更新代理」里填代理" % (exc.reason,)
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "超时：网络太慢或被墙，试试「更新代理」或加速地址"
    if isinstance(exc, PermissionError):
        return "写不进去：内核可能正被下载任务占用，先停掉相关任务再试"
    return "%s: %s" % (type(exc).__name__, exc)


def short_version(version: str) -> str:
    """显示用：`0.6.0+df70f0b3da0c630b...` -> `0.6.0+df70f0b3`。

    只为了界面好看；判"是不是同一个构建"时拿它去比前 8 位也够
    （updater.same_build 本来就用两边的较短长度去比）。
    """
    base, plus, commit = (version or "").partition("+")
    if plus and len(commit) > 8:
        return base + "+" + commit[:8]
    return version


def human_size(num: int) -> str:
    """字节数 -> 1.2 MB。"""
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (value, unit)
        value /= 1024
    return ""
