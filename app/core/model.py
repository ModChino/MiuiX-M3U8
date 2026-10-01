"""数据模型：下载选项与任务状态。

接口契约见 docs/INTERFACES.md §4.1。本文件由 Lead 冻结，字段只增不删。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    MUXING = "muxing"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def is_final(self) -> bool:
        return self in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELED)


#: 线程数合法档位。**只有这一份** —— 下载页下拉、浏览器扩展契约、服务端校验共用。
#: 放在 core 而不是 UI：服务端不该 import app.ui（见 SPEC-thread-count.md §5.1）。
THREAD_CHOICES: tuple[str, ...] = ("4", "8", "16", "32", "64")


def clean_thread_count(value: object) -> int | None:
    """把外部传来的线程数收敛到白名单；不合法一律 None（语义 = 不覆盖）。

    浏览器扩展可能被改过、也可能有人手搓请求直接打本地接口，所以服务端要自己再验
    一遍 —— 绝不能拿任意数字去拼命令行。
    """
    try:
        count = int(value)          # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return count if str(count) in THREAD_CHOICES else None


#: 状态显示名。带 emoji —— 任务列表里一眼扫过去就能分辨状态，不用读字。
_LABELS = {
    TaskStatus.PENDING: "⏳ 排队中",
    TaskStatus.RUNNING: "⬇️ 下载中",
    TaskStatus.MUXING: "🎬 合并中",
    TaskStatus.DONE: "✅ 已完成",
    TaskStatus.FAILED: "❌ 失败",
    TaskStatus.CANCELED: "🚫 已取消",
}


@dataclass
class DownloadOptions:
    """一次下载的全部可配置项。字段与 N_m3u8DL-RE v0.6.0-beta 参数一一对应。"""

    url: str = ""
    save_dir: str = ""
    save_name: str = ""
    tmp_dir: str = ""

    thread_count: int = 16
    retry_count: int = 3
    http_timeout: int = 100

    auto_select: bool = True
    select_video: str = ""
    select_audio: str = ""
    select_subtitle: str = ""
    drop_video: str = ""
    drop_audio: str = ""
    drop_subtitle: str = ""
    sub_only: bool = False
    sub_format: str = "SRT"
    auto_subtitle_fix: bool = True

    mux_enabled: bool = True
    mux_format: str = "mp4"
    muxer: str = "ffmpeg"
    ffmpeg_path: str = ""

    use_system_proxy: bool = True
    custom_proxy: str = ""
    headers: list[str] = field(default_factory=list)

    key: str = ""
    key_text_file: str = ""
    custom_hls_key: str = ""
    custom_hls_method: str = ""
    decryption_engine: str = "MP4DECRYPT"
    decryption_binary_path: str = ""

    max_speed: str = ""
    concurrent_download: bool = False

    skip_merge: bool = False
    binary_merge: bool = False
    use_ffmpeg_concat_demuxer: bool = False
    del_after_done: bool = True
    check_segments_count: bool = True
    write_meta_json: bool = True
    append_url_params: bool = False

    no_log: bool = False
    log_level: str = "INFO"
    ui_language: str = "zh-CN"
    no_ansi_color: bool = True
    #: 非交互终端（GUI 管道）下 RE 默认不输出真实速度，恒为 0.00Bps。
    #: 开启 --force-ansi-console 让它走交互式进度表给出真实速度与大小，
    #: 同时保留 --no-ansi-color 抹掉颜色转义（实测 ESC 数为 0，解析干净）。
    force_ansi_console: bool = True

    extra_args: list[str] = field(default_factory=list)

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DownloadOptions":
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def copy(self) -> "DownloadOptions":
        return DownloadOptions.from_dict(self.to_dict())


@dataclass
class DownloadTask:
    """一个运行中/已完成的任务。进度字段由 TaskRunner 更新。"""

    options: DownloadOptions
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.PENDING
    percent: float = 0.0
    speed: str = ""
    size: str = ""
    segments: str = ""
    eta: str = ""
    message: str = ""
    output_path: str = ""
    log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    exit_code: int | None = None

    @property
    def title(self) -> str:
        if self.options.save_name:
            return self.options.save_name
        return self.options.url[:80] or "(未命名)"

    @property
    def elapsed(self) -> float:
        return (self.finished_at or time.time()) - self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "options": self.options.to_dict(),
            "status": self.status.value,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DownloadTask":
        return cls(
            id=data.get("id") or uuid.uuid4().hex[:12],
            options=DownloadOptions.from_dict(data.get("options")),
            status=TaskStatus(data.get("status", "pending")),
            output_path=data.get("output_path", ""),
            created_at=data.get("created_at", time.time()),
            finished_at=data.get("finished_at", 0.0),
            exit_code=data.get("exit_code"),
            message=data.get("message", ""),
        )
