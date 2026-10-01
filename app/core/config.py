"""配置持久化（原子写）与外部工具探测。

契约见 docs/INTERFACES.md §4.5。配置文件位置：
- Windows：%APPDATA%/MiuiX-M3U8/config.json
- 其它平台：~/.config/MiuiX-M3U8/config.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field, fields
from pathlib import Path

from .model import DownloadOptions

APP_DIR_NAME = "MiuiX-M3U8"
CONFIG_FILE_NAME = "config.json"

#: 探测项 -> tools 目录里的文件名前缀
_TOOL_STEMS = {
    "nm3u8dl": "N_m3u8DL-RE",
    "ffmpeg": "ffmpeg",
    "mp4decrypt": "mp4decrypt",
    "shaka": "shaka-packager",
}
#: 探测项 -> PATH 里的候选命令名
_TOOL_COMMANDS = {
    "nm3u8dl": ("N_m3u8DL-RE", "nm3u8dl-re"),
    "ffmpeg": ("ffmpeg",),
    "mp4decrypt": ("mp4decrypt",),
    "shaka": ("shaka-packager",),
}
#: tools 目录里要忽略的后缀（压缩包、校验文件、说明文档）
_SKIP_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".7z", ".rar", ".txt", ".md",
                  ".json", ".sha256", ".sig", ".log")

_STR_FIELDS = ("theme_mode", "nm3u8dl_path", "ffmpeg_path", "save_dir", "window_geometry",
               "server_token", "update_accel_prefix", "update_proxy")


def exe_dir() -> Path:
    """程序"自己所在"的目录：打包后是 exe 旁边，开发时是项目根。

    ⚠️ 与 _base_dir() 的区别：frozen 下 _base_dir() 指向 PyInstaller 的**临时解包
    目录**（每次启动都换、退出即删），拿它放配置或下载产物都会丢。两者别混用。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _user_config_dir() -> Path:
    """用户级配置目录（老版本放配置的地方，现在只作为只读回退 + 迁移来源）。"""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base)
    return Path.home() / ".config"


def legacy_config_files() -> list[Path]:
    """配置的历史位置。

    早期版本把配置放在 %APPDATA%/MiuiX-M3U8（非 Windows 是 ~/.config/MiuiX-M3U8），
    后来改成跟程序放一起（便携版该有的样子）。**读的时候要回这里找一次**，
    否则老用户升级上来设置全丢。
    """
    return [_user_config_dir() / APP_DIR_NAME / CONFIG_FILE_NAME]


_WRITABLE_CACHE: dict[Path, bool] = {}


def _writable(directory: Path) -> bool:
    """目录能不能写。Windows 上 os.access 对目录不可靠，所以真的写一个探针文件试试。"""
    cached = _WRITABLE_CACHE.get(directory)
    if cached is not None:
        return cached
    ok = False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".miuix-write-probe"
        probe.write_bytes(b"")
        probe.unlink()
        ok = True
    except OSError:
        ok = False
    _WRITABLE_CACHE[directory] = ok
    return ok


def _base_dir() -> Path:
    """项目根目录。

    PyInstaller 打包后不存在项目目录，优先用解包目录 sys._MEIPASS；
    否则取本文件的上两级（app/core/config.py -> 项目根）。
    """
    if getattr(sys, "frozen", False):
        meipass = str(getattr(sys, "_MEIPASS", "") or "")
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _find_in_dir(directory: Path, stem: str) -> str:
    """在 directory 里找名为 stem 或 stem+平台后缀 的可执行文件。"""
    if not directory.is_dir():
        return ""
    # 精确名优先：Windows 认 .exe，POSIX 只认无扩展名的本地可执行文件
    # （POSIX 上绝不能误选同名 .exe，那是给 Windows 用的）
    exts = (".exe", "") if os.name == "nt" else ("",)
    for ext in exts:
        candidate = directory / (stem + ext)
        if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            return str(candidate)
    # 通配：N_m3u8DL-RE-linux-x64 这类带平台后缀的名字
    for item in sorted(directory.glob(stem + "*")):
        if not item.is_file():
            continue
        lower = item.name.lower()
        if lower.endswith(_SKIP_SUFFIXES):
            continue
        if os.name != "nt":
            if lower.endswith(".exe"):
                continue
            if not os.access(item, os.X_OK):
                continue
        return str(item)
    return ""


@dataclass
class Config:
    """应用配置。字段与 docs/INTERFACES.md §4.5 一致。"""

    theme_mode: str = "system"
    nm3u8dl_path: str = ""
    ffmpeg_path: str = ""
    save_dir: str = ""
    max_concurrent: int = 2
    window_geometry: str = ""
    defaults: DownloadOptions = field(default_factory=DownloadOptions)

    # ---- 浏览器扩展对接（本地接收端，见 app/core/server.py）----
    #: 默认关闭：接口能建下载任务，必须由用户显式开启
    server_enabled: bool = False
    #: 监听端口；0 表示尚未分配，首次开启时自动挑一个未占用的五位数端口
    server_port: int = 0
    #: 访问令牌，首次开启时随机生成；扩展必须带上它
    server_token: str = ""

    # ---- 内核更新（N_m3u8DL-RE，见 app/core/updater.py）----
    #: 下载内核更新时是否走 GitHub 加速地址
    update_accel_enabled: bool = False
    #: 加速地址：写 {url} 表示替换点（如 https://服务域名/{url}），没写就当前缀拼接。
    #: 刻意不给默认值 —— 这类服务的域名和路径格式各不相同，填错了比不填更难查。
    update_accel_prefix: str = ""
    #: 只给"检查更新 / 下载内核"用的代理（如 http://127.0.0.1:7890）；留空则跟随系统
    update_proxy: str = ""

    # ------------------------------------------------------------ 位置
    @staticmethod
    def file() -> Path:
        """配置文件路径：**程序所在目录**（便携版该有的样子 —— 拷走整个目录，
        设置和下载记录一起带走）。

        目录写不进去时（装在 Program Files、只读介质）退回用户配置目录，
        否则用户一改设置就报错。
        """
        home = exe_dir()
        if _writable(home):
            return home / CONFIG_FILE_NAME
        return _user_config_dir() / APP_DIR_NAME / CONFIG_FILE_NAME

    # ------------------------------------------------------------ 读写
    @staticmethod
    def load() -> "Config":
        """读配置；文件不存在或损坏时返回默认配置（不抛异常）。

        程序目录里没有时回老位置找一次（配置从用户目录搬到了程序目录，不这样做
        老用户升级上来设置会全丢）。找到后不立刻回写 —— 下次 save() 自然落到新位置。
        """
        data = None
        for path in (Config.file(), *legacy_config_files()):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                break
            data = None
        if not isinstance(data, dict):
            return Config()

        cfg = Config()
        for key, value in data.items():
            if key == "defaults":
                cfg.defaults = DownloadOptions.from_dict(value if isinstance(value, dict) else None)
            elif key == "max_concurrent":
                try:
                    cfg.max_concurrent = max(1, int(value))
                except (TypeError, ValueError):
                    pass
            elif key in ("server_enabled", "update_accel_enabled"):
                setattr(cfg, key, bool(value))
            elif key == "server_port":
                try:
                    cfg.server_port = max(0, min(65535, int(value)))
                except (TypeError, ValueError):
                    pass
            elif key in _STR_FIELDS and isinstance(value, str):
                setattr(cfg, key, value)
        return cfg

    def to_dict(self) -> dict[str, object]:
        return {
            "theme_mode": self.theme_mode,
            "nm3u8dl_path": self.nm3u8dl_path,
            "ffmpeg_path": self.ffmpeg_path,
            "save_dir": self.save_dir,
            "max_concurrent": self.max_concurrent,
            "window_geometry": self.window_geometry,
            "server_enabled": self.server_enabled,
            "server_port": self.server_port,
            "server_token": self.server_token,
            "update_accel_enabled": self.update_accel_enabled,
            "update_accel_prefix": self.update_accel_prefix,
            "update_proxy": self.update_proxy,
            "defaults": self.defaults.to_dict(),
        }

    def save(self) -> None:
        """原子写：同目录临时文件 + fsync + os.replace，避免半截文件。"""
        path = self.file()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def detect_tools(base_dir: Path | None = None) -> dict[str, str]:
    """探测外部工具，返回 {"nm3u8dl": path|"", "ffmpeg": ..., "mp4decrypt": ..., "shaka": ...}。

    查找顺序：配置里的路径 -> tools 目录（含带平台后缀的名字）-> PATH。

    tools 目录有两个候选：程序根目录，以及 **exe 所在目录** —— 单文件打包时
    ffmpeg / N_m3u8DL-RE 刻意不进包，就放在 exe 旁边（见 build.bat）。
    """
    config = Config.load()
    roots = [Path(base_dir) if base_dir is not None else _base_dir()]
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    configured = {"nm3u8dl": config.nm3u8dl_path, "ffmpeg": config.ffmpeg_path}

    result: dict[str, str] = {}
    for key, stem in _TOOL_STEMS.items():
        found = ""
        explicit = configured.get(key, "")
        if explicit and Path(explicit).is_file():
            found = str(Path(explicit))
        if not found:
            for root in roots:
                found = _find_in_dir(root / "tools", stem)
                if found:
                    break
        if not found:
            for command in _TOOL_COMMANDS[key]:
                hit = shutil.which(command)
                if hit:
                    found = hit
                    break
        result[key] = found
    return result
