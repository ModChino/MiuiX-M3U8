"""N_m3u8DL-RE stdout/stderr 解析：ANSI 剥离 + \r/\n 分帧 -> Event。

真实样例见 docs/nm3u8dl-sample-output.txt（v0.6.0-beta 实测），本文件的正则全部按该样例写成。

实测结论（详见样例文件顶部注释）：
1. 进程 stdout 被重定向到管道（非 TTY）时，v0.6.0-beta 会在开始下载的瞬间崩溃
   （Spectre.Console LiveRenderable 异常，SIGABRT / exit 134），因此 runner 在
   POSIX 上用伪终端（script -qec）启动子进程。
2. 有 TTY 且带 ANSI 时，进度是 CR 原地重绘的表格行；
   而 --no-ansi-color 下程序把整条进度**原地重写且不加任何分隔符**
   （实测一次 52KB 的输出里只有 9 个 CR、9 个 LF），多次刷新直接首尾相连：
   "...Vid 320x184 | 246 Kbps  0/9 0.00% -0.00Bps --:--:--Vid 320x184 | 246 Kbps ..."
   只认 CR/LF 分帧的解析器会一直憋到进程退出才吐进度（UI 进度条全程不动）。
   所以本文件做了两件事：一帧内用 finditer 逐个解析多次进度（相邻重复去重）；
   缓冲区长时间没有分隔符时以"最后一个百分比"为界提前切开，保证边读边出。
3. 日志行之间也可能不换行（"Content Matched: ..." 与下一条粘在同一行），
   按"行首时间戳"二次切分。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------- ANSI

_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"              # CSI：颜色 / 光标移动 / 清行
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC：窗口标题等
    r"|\x1b(?!\[|\])[ -/]*[0-~]"             # 其它转义：ESC= ESC> ESC(B ...
    # 末尾的 (?!\[|\]) 很关键：被 chunk 切断的半个 CSI（如 "\x1b[?25"）不能被当成
    # 单字符转义吃掉，否则会留下 "?25" 这种脏字符，日志行就再也匹配不上了。
)

#: 只有装饰字符（进度条 / 盲文转轮 / 空白）的帧，直接丢弃
_DECOR_RE = re.compile(r"[\s\u2500-\u257f\u2580-\u259f\u2800-\u28ff]+")

#: 无分隔符长流水时的切分参数（--no-ansi-color 的进度是原地重写、整段不带 CR/LF）
_NO_DELIM_MIN = 128          # 缓冲区超过这么多字符才考虑提前切开
_PROGRESS_LINE_MAX = 96      # 单次进度行最长大概这么多字符
#: 单次解析的帧长度上限。Windows 上 RE 没有 PTY，实测一次下载 10MB 输出里只有 10 个
#: CR/LF，单段可达 MB 级且几乎全是逐分片原地重绘（一份样本里有 5.3 万个 "100.00%"）。
#: 进度以最新值为准，超出部分只保留尾部，否则会被切成几万个 piece 逐个跑正则卡死主线程。
_HEAD_MAX = 65536

# ---------------------------------------------------------------- 行结构

#: 完整日志行：20:05:28.043 INFO : Extracted, there are 5 streams
_LOG_RE = re.compile(
    r"^(?P<ts>\d{2}:\d{2}:\d{2}[.,]\d{3})\s+"
    r"(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s*:\s?(?P<msg>.*)$"
)
#: 行内出现的下一个日志行起始（非交互模式下多行会粘在一起）
_LOG_HEAD_RE = re.compile(
    r"(?<![\d:])\d{2}:\d{2}:\d{2}[.,]\d{3}\s+(?:TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s*:"
)

#: 进度：3/5 60.00%（ANSI 模式下是完整表格行）
_RE_SEG_PCT = re.compile(
    r"(?<![\d/.])(?P<done>\d+)\s*/\s*(?P<total>\d+)\s+(?P<pct>\d{1,3}(?:\.\d+)?)\s*%"
)
#: 兜底：只有百分比（TERM=dumb 下形如 "Vid 1927 Kbps: 80%"）
_RE_PCT = re.compile(r"(?<![\d.])(?P<pct>\d{1,3}(?:\.\d+)?)\s*%")

#: 进度行里的流标签。N_m3u8DL-RE 对**每条正在下载的流各刷一行进度**，
#: 实测音视频分离的流上 Vid / Aud / Sub 三行交错刷新，各自带自己的 done/total。
_RE_STREAM = re.compile(r"(?P<kind>UnknownVid|Vid|Aud|Sub|Video|Audio|Subtitle)\b")


def _stream_key(prefix: str) -> str:
    """从进度行前缀里认流标签（取最后一个）；认不出来返回空串 = 归到同一个桶。"""
    hits = _RE_STREAM.findall(prefix)
    if not hits:
        return ""
    # 归一化：同一路流在不同渲染里可能叫 Vid / Video、Aud / Audio
    return {"UnknownVid": "Vid", "Video": "Vid", "Audio": "Aud", "Subtitle": "Sub"}.get(
        hits[-1], hits[-1])
#: 已下载 / 总大小，如 7.52MB/12.53MB（后面不能紧跟字母，避免吃掉 7.52MBps）
_RE_SIZE = re.compile(
    r"(?<![\w.])(?P<a>\d+(?:\.\d+)?)\s*(?P<ua>[KMGTP]?i?B)"
    r"(?:\s*/\s*(?P<b>\d+(?:\.\d+)?)\s*(?P<ub>[KMGTP]?i?B))?(?![A-Za-z])"
)
#: 速度，如 7.52MBps / 1.2MB/s / 0.00Bps。
#: 边界只能用 (?<![\d.])：Windows 实测速度紧贴在总大小后面且**没有空格**，
#: 形如 "... 16.87MB/1017.92MB16.87MBps00:00:14"，速度前一个字符是 B。
#: 若沿用 (?<![\w.])（后面是单词字符就否决），真实速度会被整个漏掉，
#: 只剩早期那些 "-0.00Bps" 能被解析 —— 这正是"速度一直不变"的原因。
_RE_SPEED = re.compile(r"(?<![\d.])(?P<sp>\d+(?:\.\d+)?\s*[KMGTP]?i?B(?:ps|/s))")
#: ETA，如 00:00:00 / --:--:-- / 01:20
_RE_ETA = re.compile(r"(?<![\d:])(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{2})(?![\d:])")

#: 从日志里认路径用的绝对路径（/tmp/x.ts 或 D:\x.ts）
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/)[^\s\"'<>|*?]+")
#: DEBUG 行：... ; saveDir: /tmp/s1; saveName: bipbop
_RE_SAVE_DIR = re.compile(r"saveDir:\s*(?P<dir>.+?)\s*;\s*saveName:\s*(?P<name>[^;\s]+)")
#: INFO 行：Save Name: bipbop（用 search，容忍行首还有时间戳等前缀）
#: 保存文件名。实测 zh-CN 下打的是 "保存文件名: xxx"，只认英文会一个都匹配不到。
#: 保存文件名。实测 zh-CN 下打的是 "保存文件名: xxx"，只认英文会一个都匹配不到。
#: 注意：这里**必须**限制字符类与长度。用 ".+? 配向前断言" 写会在文本里没有
#: 时间戳时逐字符回溯 —— 粘连输出下是 O(n^2)，能把主线程卡死上百秒（实测 168s）。
_RE_SAVE_NAME = re.compile(
    r"(?:Save Name|\u4fdd\u5b58\u6587\u4ef6\u540d)\s*[:\uff1a]\s*"
    r"(?P<name>[^\r\n:\uff1a]{1,160}?)"
    r"(?=\d{2}:\d{2}:\d{2}[.,]\d{3}\s|\s*$)"
)
#: 混流结束后的改名行："Rename to xxx.mp4"（后面常直接粘着下一条日志的时间戳）
#: 同样限制长度，避免黏连文本下的回溯放大。
_RE_RENAME = re.compile(
    r"Rename to\s+(?P<name>[^\s]{1,160}?\.(?:mp4|mkv|ts|m2ts|m4a|m4v|flv|mov|webm|avi|aac|srt|vtt|ass|ssa))",
    re.IGNORECASE,
)

#: 行首时间戳（不要求 ^），用来修掉被 ANSI 残渣污染的帧首
_LOG_ANY_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s+(?:TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s*:"
)
#: 非日志行里出现这些字样也算错误
_ERROR_HINTS = ("Unhandled exception", "System.Exception", "FATAL", "ERROR:")

#: HTTP 状态码（含 RE 各种写法：HTTP 429 / HTTP/1.1 429 / status code: 429）
_RE_HTTP_ERR = re.compile(
    r"(?i)(?:\bHTTP(?:/\s*[\d.]+)?\s*(?:status\s*(?:code)?\s*)?[:=]?\s*"
    r"|\bstatus\s*code\s*[:=]?\s*)(?P<code>[45]\d{2})\b"
)
#: 限流类提示词（命中即认为是会被"降速"解决的服务端拒绝）
_THROTTLE_HINTS = (
    "too many requests", "rate limit", "rate-limit", "ratelimit",
    "\u9650\u6d41", "\u8bf7\u6c42\u8fc7\u4e8e\u9891\u7e41", "\u670d\u52a1\u5668\u7e41\u5fd9",
)
#: 重试类提示词
_RETRY_HINTS = ("retry", "retrying", "\u91cd\u8bd5")
#: 需要降速的 HTTP 码：429 限流 / 503 过载最典型，5xx 一并算上
_THROTTLE_CODES = {"429", "503", "502", "504", "500", "403"}


def detect_throttle(text: str) -> str:
    """识别"被服务端限流/拒绝"的日志，返回状态码或描述；正常返回空串。

    RE 自己会按 --download-retry-count 重试，但 429/503 这类是**速率**问题，
    原样重试多半继续失败 —— 需要提示用户并支持降速重试。
    """
    low = text.lower()
    m = _RE_HTTP_ERR.search(text)
    if m:
        code = m.group("code")
        if code in _THROTTLE_CODES:
            return code
    if any(h in low for h in _THROTTLE_HINTS):
        return "429"
    if any(h in low for h in _RETRY_HINTS) and ("http" in low or "\u5931\u8d25" in text):
        return "retry"
    return ""

#: 混流 / 合并
#: 合并阶段标志。实测 zh-CN 下 N_m3u8DL-RE 输出 "调用ffmpeg合并中..."，
#: 原来的英文词一个都匹配不上，状态因此永远不会切到"混流中"。
_MUX_KEYWORDS = (
    "调用ffmpeg合并中", "调用 ffmpeg 合并中", "合并中", "开始合并",
    "Binary merging", "merging...", "Muxing", "muxing", "mux after done",
)
#: 产物扩展名（用于在目录里挑最终文件）
_MEDIA_EXTS = {
    ".mp4", ".mkv", ".ts", ".m2ts", ".m4a", ".m4v", ".m4s", ".aac", ".mp3",
    ".flv", ".mov", ".webm", ".avi", ".wmv", ".srt", ".vtt", ".ass", ".ssa", ".sup",
}
#: 一定不是产物的扩展名
_SIDE_EXTS = {".log", ".json", ".txt", ".tmp", ".part", ".bak", ".ytdl", ".md"}


def strip_ansi(text: str) -> str:
    """去掉 ANSI 转义序列（颜色、光标移动、清行等）。"""
    return _ANSI_RE.sub("", text)


@dataclass
class Event:
    """解析出来的一条事件。字段与 docs/INTERFACES.md §4.3 一致。"""

    kind: str                       # "info" | "progress" | "mux" | "done" | "error" | "selected"
    percent: float | None = None
    speed: str | None = None
    size: str | None = None
    segments_done: int | None = None
    segments_total: int | None = None
    eta: str | None = None
    path: str | None = None
    text: str = ""


def _split_glued(frame: str) -> list[str]:
    """把同一帧里粘连的多条日志行切开（非交互模式下日志行不换行）。"""
    starts = [m.start() for m in _LOG_HEAD_RE.finditer(frame)]
    if len(starts) < 2:
        return [frame]
    out: list[str] = []
    if starts[0] > 0:
        out.append(frame[: starts[0]])
    for i, begin in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(frame)
        out.append(frame[begin:end])
    return out


def _extract_progress(text: str) -> Event | None:
    """从一行文本里抽进度字段；没有百分比就返回 None。"""
    seg = _RE_SEG_PCT.search(text)
    done: int | None = None
    total: int | None = None
    percent: float | None = None
    if seg:
        done = int(seg.group("done"))
        total = int(seg.group("total"))
        percent = float(seg.group("pct"))
    else:
        pct = _RE_PCT.search(text)
        if not pct:
            return None
        percent = float(pct.group("pct"))

    size = None
    m_size = _RE_SIZE.search(text)
    if m_size:
        size = m_size.group(0).strip()
    speed = None
    m_speed = _RE_SPEED.search(text)
    if m_speed:
        speed = m_speed.group("sp").replace(" ", "")
    eta = None
    m_eta = _RE_ETA.search(text)
    if m_eta:
        eta = m_eta.group(0)
    return Event(
        kind="progress",
        percent=percent,
        speed=speed,
        size=size,
        segments_done=done,
        segments_total=total,
        eta=eta,
        text=text.strip(),
    )


#: 日志绝对路径探测上限。每命中一个候选就要做一次 isfile()，粘连输出下候选
#: 可能上千条；实测慢盘上这一步曾把主线程卡住 168 秒（界面"未响应"）。
_PATH_PROBE_LIMIT = 120


def _probe_abs_paths(lines: list[str]) -> str:
    """兜底：在日志里找**真实存在**的媒体文件绝对路径。

    只认带媒体扩展名的候选，去重并封顶探测次数 —— 见 _PATH_PROBE_LIMIT。
    """
    seen: set[str] = set()
    probed = 0
    found: list[str] = []
    for line in reversed(lines):          # 产物名通常出现在日志结尾
        for m in _ABS_PATH_RE.finditer(line):
            cand = m.group(0).rstrip(".,;)]}\"'")
            if cand in seen:
                continue
            seen.add(cand)
            if os.path.splitext(cand)[1].lower() not in _MEDIA_EXTS:
                continue
            probed += 1
            if probed > _PATH_PROBE_LIMIT:
                return found[-1] if found else ""
            if os.path.isfile(cand):
                found.append(cand)
    return found[-1] if found else ""


def resolve_output_path(
    log_lines: list[str],
    save_dir: str = "",
    save_name: str = "",
    mux_format: str = "",
) -> str:
    """从日志（+ 落盘结果）推断最终产物路径，找不到返回空串。

    顺序：
    1. 日志里出现过且真实存在的绝对路径（DEBUG 级别常见）；
    2. 日志里的 saveDir/saveName（DEBUG 行），或调用方给的 --save-dir/--save-name；
    3. 在 saveDir 下找 <saveName>.<ext> 中最后修改的那个（排除 .log/.json/.tmp）。
    """
    lines = [strip_ansi(ln).strip() for ln in log_lines if ln and ln.strip()]

    # 顺序很重要：先做**零成本**的字符串解析与精确拼接，把会碰文件系统的
    # "逐条探测绝对路径"放到最后兜底。原来把它放在第一步，下载目录稍大
    # 就会在主线程里卡住（实测 168 秒）。

    # 1) 日志里的 saveDir / saveName
    for line in lines:
        m = _RE_SAVE_DIR.search(line)
        if m:
            save_dir = m.group("dir") or save_dir
            save_name = m.group("name") or save_name
    # 0) 混流结束后的 "Rename to xxx.mp4" 是最权威的产物名（优先于猜测的保存名）
    renamed = ""
    for line in reversed(lines):
        m = _RE_RENAME.search(line)
        if m:
            renamed = m.group("name")
            break

    if not save_name:
        for line in reversed(lines):
            m = _RE_SAVE_NAME.search(line)
            if m:
                save_name = m.group("name").strip()
                break
    if not save_name and not renamed:
        return _probe_abs_paths(lines)

    # renamed 来自 "Rename to xxx.mp4"，**自带扩展名**；save_name 一般不带。
    # 早先把两者一视同仁地再拼一次容器后缀，得到 "xxx.mp4.mp4" 必然落空，
    # 于是"已完成"的任务永远解析不出产物路径、打开文件夹按钮也不可用。
    stem = Path(renamed or save_name).name
    name = Path(stem).stem
    ext_hint = Path(stem).suffix.lstrip(".").lower()

    directory = Path(save_dir) if save_dir else Path.cwd()
    if not os.path.isdir(directory):
        return ""

    # 3) 优先精确命中：先按 -M 指定的容器格式，再按 rename 自带的扩展名
    fmt = (mux_format or "").lstrip(".").lower()
    for want in (fmt, ext_hint):
        if want:
            exact = directory / (name + "." + want)
            if exact.is_file():
                return str(exact)

    best: Path | None = None
    best_mtime = -1.0
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return ""
    # 下载目录里可能有成千上万个分片，绝不能对每个文件都 stat()（会阻塞主线程）：
    # 先用纯字符串做名字/扩展名过滤，命中的才去碰文件系统。
    for item in entries:
        if item.stem != name and not item.name.startswith(name + "."):
            continue
        ext = item.suffix.lower()
        if ext in _SIDE_EXTS:
            continue
        if ext and ext not in _MEDIA_EXTS and ext.lstrip(".") != fmt:
            continue
        try:
            if not item.is_file():
                continue
            mtime = item.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best, best_mtime = item, mtime
    if best is not None:
        return str(best)

    # 4) 最后兜底：日志里点名的、真实存在的媒体文件（限额探测，见 _probe_abs_paths）
    return _probe_abs_paths(lines)


class OutputParser:
    """把 stdout 片段喂进来，吐出 Event 列表。

    支持 \r 分帧（原地重绘）、ANSI 剥离，以及多条日志粘在一行的情况。
    """

    #: 缓冲区上限，防止没有换行的滚动输出把内存撑爆
    MAX_BUFFER = 65536
    #: 为路径解析保留的最近日志行数
    KEEP_LINES = 300

    def __init__(self) -> None:
        self._buf = ""
        self._lines: list[str] = []
        self.percent: float = 0.0
        self.segments_done: int | None = None
        self.segments_total: int | None = None
        self.save_dir: str = ""
        self.save_name: str = ""
        self._last_progress: tuple | None = None
        #: 每条流各自的分片进度（流标签 -> (done, total)），对外报合计
        self._streams: dict[str, tuple[int, int]] = {}
        #: 认不出流标签时的兜底值（只有一条流的下载走这里）
        self._fallback: tuple[int, int] | None = None

    # ------------------------------------------------------------ 对外
    def reset(self) -> None:
        """清空缓冲区与累计状态（重试前调用）。"""
        self._buf = ""
        self._lines.clear()
        self.percent = 0.0
        self.segments_done = None
        self.segments_total = None
        self.save_dir = ""
        self.save_name = ""
        self._last_progress: tuple | None = None
        self._streams.clear()
        self._fallback = None

    def feed(self, chunk: str) -> list[Event]:
        """喂入一段原始输出，返回本次解析出的事件。"""
        if not chunk:
            return []
        # 对整个缓冲区剥 ANSI：转义序列可能被读取边界切断，
        # 逐 chunk 剥会把半截序列当成正文留在缓冲里
        self._buf = strip_ansi(self._buf + chunk)

        # \r 与 \n 都是分帧符；最后一个分隔符之后是半行，留在缓冲区等下一段
        cut = max(self._buf.rfind("\r"), self._buf.rfind("\n"))
        if cut >= 0:
            head, self._buf = self._buf[: cut + 1], self._buf[cut + 1 :]
            # 见 _HEAD_MAX 说明：大段无分隔符的原地重绘只保留尾部
            if len(head) > _HEAD_MAX:
                head = head[-_HEAD_MAX:]
        else:
            head = ""
            # 一个分隔符都没有也不能干等：--no-ansi-color 下进度是原地重写、整段不带
            # CR/LF（实测 52KB 输出里只有 9 个换行），干等会让 UI 直到进程退出才看到
            # 进度。以"最后一个百分比"为界切开，只留下可能还没写完的那一次刷新。
            if len(self._buf) > _NO_DELIM_MIN:
                marks = [m.start() for m in _RE_PCT.finditer(self._buf)]
                if len(marks) >= 2:
                    keep_from = max(0, marks[-1] - _PROGRESS_LINE_MAX)
                    if keep_from > 0:
                        head, self._buf = self._buf[:keep_from], self._buf[keep_from:]
        # 长时间没有分隔符（例如一直原地重绘）：强制冲刷，避免无限增长
        if len(self._buf) > self.MAX_BUFFER:
            head += self._buf
            self._buf = ""

        events: list[Event] = []
        for frame in re.split(r"[\r\n]", head):
            for piece in _split_glued(frame):
                events.extend(self._parse_frame(piece))
        return events

    def flush(self) -> list[Event]:
        """进程结束时把缓冲区里的半行解析掉。"""
        tail, self._buf = self._buf, ""
        events: list[Event] = []
        for piece in _split_glued(tail):
            events.extend(self._parse_frame(piece))
        return events

    def lines(self) -> list[str]:
        """返回保留的最近日志行（供 runner 复用，避免重复扫描目录）。"""
        return list(self._lines)

    def output_path(self, mux_format: str = "") -> str:
        """基于已见日志推断最终产物路径。"""
        return resolve_output_path(self._lines, self.save_dir, self.save_name, mux_format)

    # ------------------------------------------------------------ 内部
    def _remember(self, text: str) -> None:
        self._lines.append(text)
        if len(self._lines) > self.KEEP_LINES:
            del self._lines[: len(self._lines) - self.KEEP_LINES]

    def _parse_frame(self, frame: str) -> list[Event]:
        text = frame.strip()
        if not text:
            return []
        if not _DECOR_RE.sub("", text).strip():
            return []           # 纯进度条 / 转轮字符

        # 帧首可能残留 ANSI 碎片（例如 "?25l20:05:30.930 INFO : ..."），先对齐到时间戳
        hit = _LOG_ANY_RE.search(text)
        if hit is not None and 0 < hit.start() <= 8:
            text = text[hit.start():]

        m = _LOG_RE.match(text)
        if m:
            # 无分隔符输出下，一条日志后面会直接粘上大段进度刷新。实测单帧可达 12 万
            # 字符，其中 99% 是原地重绘的进度行（含真实速度）。若整帧按日志处理，
            # 进度与速度会被全部丢弃 —— 这正是"速度一直不变/不显示"的根因。
            # 这里把日志行切出来单独解析，剩下的交给进度分支。
            # 注意：_LOG_RE 的 msg 是贪婪的 (.*)，而无分隔符文本里根本没有换行，
            # 于是它一路吃到帧尾 —— 不能用 m.end() 定位，必须用 _LOG_HEAD_RE
            # 拿"日志头"（时间戳+级别+冒号）的真实结束位置作为搜索起点。
            head_m = _LOG_HEAD_RE.match(text)
            start = head_m.end() if head_m is not None else m.end()
            end = len(text)
            nxt_log = _LOG_HEAD_RE.search(text, start)
            if nxt_log is not None:
                end = min(end, nxt_log.start())
            prog = _RE_SEG_PCT.search(text, start)
            if prog is not None and prog.start() < end:
                end = prog.start()
            if start < end < len(text):
                head, tail = text[:end], text[end:]
                events = self._parse_log_line(head, _LOG_RE.match(head)) if head.strip() else []
                events.extend(self._parse_frame(tail))
                return events
            return self._parse_log_line(text, m)

        # 非日志行：多半是原地重绘的进度行
        self._scan_names(text)
        if any(hint in text for hint in _ERROR_HINTS):
            return [Event(kind="error", text=text)]
        events = self._progress_series(text)
        if events:
            return events
        if _RE_PCT.search(text):
            return []           # 是进度行，只是和上一条完全重复（原地重绘的常态）
        return [Event(kind="info", text=text)]

    def _progress_series(self, text: str) -> list[Event]:
        """一帧里可能粘连了多次进度刷新（无 CR/LF 时），逐个解析并去重。

        实测：--no-ansi-color 下 N_m3u8DL-RE 把整条进度原地重写，两次刷新之间没有
        任何分隔符，形如
        "...Vid 320x184 | 246 Kbps  0/9 0.00% -0.00Bps --:--:--Vid 320x184 | 246 Kbps ..."
        """
        matches = list(_RE_SEG_PCT.finditer(text))
        if not matches:
            matches = list(_RE_PCT.finditer(text))
        if not matches:
            return []
        events: list[Event] = []
        last_stream = ""
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            # 流标签在计数器**之前**：单独取前面那一段来认，字段本身仍从计数器处取
            # （从上一段切起会把上一条的大小 / 速度也吃进来，实测速度会串行）。
            begin = matches[index - 1].end() if index else 0
            stream = _stream_key(text[begin:match.start()])
            if stream:
                last_stream = stream
            else:
                stream = last_stream    # 同一行原地重绘时，标签只在行首出现一次
            ev = _extract_progress(text[match.start():end])
            if ev is None:
                continue
            self._track(ev, stream)
            key = (ev.percent, ev.segments_done, ev.segments_total, ev.size, ev.speed, ev.eta)
            if key == self._last_progress:
                continue
            self._last_progress = key
            events.append(ev)
        return events

    def _scan_names(self, text: str) -> None:
        """从任意一行里捞 saveDir / saveName（DEBUG 行可能被终端折行切开）。"""
        if "saveDir:" in text:
            hit = _RE_SAVE_DIR.search(text)
            if hit:
                self.save_dir = hit.group("dir").strip() or self.save_dir
                self.save_name = hit.group("name").strip() or self.save_name
        if "Save Name:" in text:
            hit = _RE_SAVE_NAME.search(text)
            if hit:
                self.save_name = hit.group("name").strip() or self.save_name

    def _parse_log_line(self, text: str, m: re.Match) -> list[Event]:
        level = m.group("level")
        msg = m.group("msg").strip()
        events: list[Event] = []
        self._remember(text)

        # 限流要优先于普通 error 上报：它的处置方式是"降速重试"，不是直接失败
        throttled = detect_throttle(msg)
        if throttled:
            events.append(Event(kind="throttle", text=text))
            self._remember(text)
            return events

        if level in ("ERROR", "FATAL") or "Unhandled exception" in msg:
            events.append(Event(kind="error", text=text))
            return events

        self._scan_names(msg)

        if msg.startswith("Selected streams"):
            events.append(Event(kind="selected", text=text))
        elif any(k in msg for k in _MUX_KEYWORDS):
            events.append(Event(kind="mux", text=text))
        elif msg.startswith("Done"):
            events.append(Event(kind="done", text=text, path=self.output_path() or None))
        else:
            events.append(Event(kind="info", text=text))

        # 非交互模式下进度行会粘在日志行尾部（形如 "...NaN: UnknownVid 1927 Kbps: 80%"）
        tail = _extract_progress(msg)
        if tail is not None and tail.percent is not None:
            self._track(tail, _stream_key(msg))
            events.append(tail)
        return events

    def _track(self, ev: Event, stream: str = "") -> None:
        """记录进度累计状态。

        多条流各自报自己的 done/total，直接覆盖会让界面上的分片数来回跳
        （实测音视频分离时在 900 和 200 之间反复横跳 252 次）。这里按流分桶、
        对外报**合计**：单调递增，语义也正是"这次下载一共多少个分片"。

        认不出流标签的那条（RE 第一帧只画计数器、日志行尾粘着的进度也不带标签）
        不能建桶 —— 否则会凭空多出一条流，把总分片数抬高（实测 303 变 404）。
        它先作为"兜底值"顶着（只有一条流的下载仍然照常显示），一旦出现带标签的
        流就作废 —— 那条兜底值本来就是其中某条流。
        """
        if ev.segments_total is not None:
            if stream:
                self._streams[stream] = (ev.segments_done or 0, ev.segments_total)
            elif not self._streams:
                self._fallback = (ev.segments_done or 0, ev.segments_total)
            done, total = self._totals()
            if total:
                ev.segments_done, ev.segments_total = done, total
                self.segments_done, self.segments_total = done, total
                if len(self._streams) > 1:
                    # 多流并发才需要合计百分比；单流时保留 RE 自己报的百分比
                    ev.percent = round(done * 100.0 / total, 2)
        if ev.percent is not None:
            self.percent = ev.percent

    def _totals(self) -> tuple[int, int]:
        """对外报的分片进度：所有流合计；还没有带标签的流就用兜底值。"""
        if self._streams:
            return (sum(d for d, _ in self._streams.values()),
                    sum(t for _, t in self._streams.values()))
        return self._fallback or (0, 0)
