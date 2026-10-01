"""N_m3u8DL-RE 内核的版本检测与自动更新。

只用标准库（urllib / zipfile / tarfile）—— 为一个"检查更新"引 requests 不值得。

这里**不 import 任何 Qt**：网络与文件动作全是同步函数，由 UI 层丢到工作线程里跑。
这样核心逻辑在没有显示器的环境里也能直接自检（与 runner.py 同一条原则）。

实测事实（v0.6.0-beta，2026-06）：
- `N_m3u8DL-RE.exe --disable-update-check --version` -> `0.6.0+df70f0b3da0c...`
- release tag 形如 `v0.6.0-beta`，资产名形如
  `N_m3u8DL-RE_v0.6.0-beta_win-x64_20260629.zip`（Windows 是 zip，其它平台是 tar.gz）
- `--disable-update-check` 必须带上：RE 自己也会联网查更新，我们只想静静问一句版本
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
import tarfile
from dataclasses import dataclass
from pathlib import Path

OWNER_REPO = "nilaoda/N_m3u8DL-RE"
API_LATEST = "https://api.github.com/repos/%s/releases/latest" % OWNER_REPO
API_COMMIT = "https://api.github.com/repos/%s/commits/" % OWNER_REPO
USER_AGENT = "MiuiX-M3U8-Updater"
TIMEOUT = 20
EXE_STEM = "N_m3u8DL-RE"

_RE_VERSION = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)")


@dataclass
class Release:
    """GitHub 上的最新 release（已挑好当前平台的资产）。"""
    tag: str            # v0.6.0-beta
    name: str           # N_m3u8DL-RE_v0.6.0-beta
    published: str      # 2026-06-28
    asset_name: str     # N_m3u8DL-RE_v0.6.0-beta_win-x64_20260629.zip
    asset_url: str
    commit: str = ""    # 尽力而为；拿不到不影响主流程


# --------------------------------------------------------------------------
# 加速地址
# --------------------------------------------------------------------------
def accelerate(url: str, enabled: bool, prefix: str) -> str:
    """把 GitHub 直链换成加速地址。

    prefix 里写 `{url}` 表示替换点（如 `https://服务域名/{url}`）；没写就当前缀拼接
    （如 `https://服务域名/`）。关掉开关或没填前缀则原样返回 —— 加速地址是用户自己填的，
    这里不做任何猜测。
    """
    p = (prefix or "").strip()
    if not enabled or not p or not url:
        return url
    if "{url}" in p:
        return p.replace("{url}", url)
    return (p if p.endswith("/") else p + "/") + url


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _opener(proxy: str):
    """按需带代理的 opener；proxy 留空则跟随系统设置（urllib 默认行为）。"""
    proxy = (proxy or "").strip()
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def _get(url: str, proxy: str = "") -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with _opener(proxy).open(request, timeout=TIMEOUT) as response:
        return response.read()


# --------------------------------------------------------------------------
# 版本
# --------------------------------------------------------------------------
def _no_window_kwargs() -> dict:
    """Windows 下别让子进程弹黑窗（与 runner 同一套）。"""
    if os.name != "nt":
        return {}
    kwargs: dict = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0
        kwargs["startupinfo"] = info
    except AttributeError:
        pass
    return kwargs


def parse_version(text: str) -> str:
    """从 `--version` 的输出里抠出版本号。实测是单行 `0.6.0+<sha>`。"""
    for line in (text or "").splitlines():
        hit = _RE_VERSION.search(line.strip())
        if hit:
            return hit.group(1)
    return ""


def local_version(exe: str) -> str:
    """跑一次 --version 拿到本地版本；失败返回空串（调用方显示"未知"）。"""
    if not exe or not Path(exe).is_file():
        return ""
    try:
        done = subprocess.run(
            [exe, "--disable-update-check", "--version"],
            capture_output=True, timeout=15, **_no_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        return ""
    blob = (done.stdout or b"") + b"\n" + (done.stderr or b"")
    return parse_version(blob.decode("utf-8", "replace"))


def split_version(version: str) -> tuple[tuple[int, ...], str]:
    """`0.6.0+sha` / `v0.6.0-beta` -> ((0, 6, 0), "sha")。

    数字部分用于比较，后半段（commit）用于判断"同版本不同构建"。
    """
    base, _, commit = (version or "").partition("+")
    base = base.split("-")[0].lstrip("vV")
    numbers = []
    for part in base.split("."):
        digits = re.match(r"\d+", part)
        numbers.append(int(digits.group()) if digits else 0)
    return tuple(numbers), commit


def is_newer(remote: str, local: str) -> bool:
    """远端是否比本地新。只比数字部分，忽略 -beta 之类预发布后缀。"""
    remote_numbers, _ = split_version(remote)
    local_numbers, _ = split_version(local)
    return remote_numbers > local_numbers


def same_build(remote_commit: str, local_version_str: str) -> bool:
    """远端 commit 与本地版本里带的 sha 是不是同一个构建（短 sha 也算）。"""
    _, local_commit = split_version(local_version_str)
    if not remote_commit or not local_commit:
        return False
    short = min(len(remote_commit), len(local_commit))
    return remote_commit[:short].lower() == local_commit[:short].lower()


def platform_tag() -> str:
    """当前平台在资产名里的那一段（实测：win-x64 / win-arm64 / linux-x64 / osx-arm64 …）。"""
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform == "win32":
        return "win-arm64" if arm else "win-x64"
    if sys.platform == "darwin":
        return "osx-arm64" if arm else "osx-x64"
    return "linux-arm64" if arm else "linux-x64"


# --------------------------------------------------------------------------
# 查询 / 下载 / 安装
# --------------------------------------------------------------------------
def fetch_latest(proxy: str = "") -> Release:
    """查最新 release 并挑出当前平台的资产。失败抛异常，由 UI 层翻成人话。"""
    data = json.loads(_get(API_LATEST, proxy).decode("utf-8", "replace"))
    tag = str(data.get("tag_name") or "")
    assets = [a for a in (data.get("assets") or []) if isinstance(a, dict)]
    want = platform_tag()
    hit = next((a for a in assets if want in str(a.get("name") or "")), None)
    if hit is None:
        raise LookupError("该版本没有适合当前平台（%s）的资产" % want)

    commit = ""
    try:      # 只是用来区分"同版本不同构建"，拿不到不影响主流程
        blob = _get(API_COMMIT + urllib.parse.quote(tag, safe=""), proxy)
        commit = str(json.loads(blob.decode("utf-8", "replace")).get("sha") or "")
    except Exception:      # noqa: BLE001
        commit = ""

    return Release(
        tag=tag,
        name=str(data.get("name") or tag),
        published=str(data.get("published_at") or "")[:10],
        asset_name=str(hit.get("name") or ""),
        asset_url=str(hit.get("browser_download_url") or ""),
        commit=commit,
    )


def download(url: str, dest_dir: Path, proxy: str = "", progress=None) -> Path:
    """流式下载到 dest_dir，返回落地路径。progress(已下载字节, 总字节) 可为 None。"""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urllib.parse.urlparse(url).path).name or "N_m3u8DL-RE.zip"
    dest = dest_dir / name

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener(proxy).open(request, timeout=TIMEOUT) as response:
        try:
            total = int(response.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total = 0
        done = 0
        with open(dest, "wb") as handle:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    return dest


def _guard(root: Path, names) -> None:
    """压缩包成员防越界：加速地址是用户自己填的，不能让人塞个 ../ 上跳路径进来。"""
    base = str(Path(root).resolve())
    for name in names:
        target = str((Path(root) / name).resolve())
        if target != base and not target.startswith(base + os.sep):
            raise ValueError("压缩包里含越界路径：%s" % name)


def find_binary(directory: Path) -> Path:
    """在解出来的目录里找内核可执行文件（包里可能还套一层目录）。"""
    want = EXE_STEM + (".exe" if os.name == "nt" else "")
    files = [p for p in sorted(Path(directory).rglob("*")) if p.is_file()]
    for path in files:
        if path.name == want:
            return path
    for path in files:      # 退一步：名字带前缀就行（资产里可能带版本号）
        if path.name.startswith(EXE_STEM) and not path.name.endswith((".zip", ".tar.gz")):
            return path
    raise FileNotFoundError("压缩包里没找到 %s" % want)


def extract_binary(archive: Path, dest_dir: Path) -> Path:
    """从 zip / tar.gz 里解出内核，返回解出来的文件路径。"""
    archive = Path(archive)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if archive.name.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as handle:
            _guard(dest_dir, handle.namelist())
            handle.extractall(dest_dir)
    else:
        with tarfile.open(archive, "r:*") as handle:
            names = [m.name for m in handle.getmembers()]
            _guard(dest_dir, names)
            try:
                handle.extractall(dest_dir, filter="data")   # 3.12+ 的默认安全过滤器
            except TypeError:
                handle.extractall(dest_dir)
    return find_binary(dest_dir)


def install(binary: Path, target: str) -> str:
    """把新内核装到 target，旧的原样留一份 .bak（可以手工回滚）。返回备份路径。

    目标被占用时（正在下载）Windows 会拒绝写入 —— OSError 原样抛出，由 UI 层翻成人话。
    """
    target_path = Path(target)
    backup = ""
    if target_path.is_file():
        backup_path = target_path.with_name(target_path.name + ".bak")
        shutil.copy2(target_path, backup_path)
        backup = str(backup_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, target_path)
    try:
        os.chmod(target_path, 0o755)
    except OSError:
        pass
    return backup


def update_to(config, progress=None) -> tuple[str, str, str]:
    """完整流程：查最新 -> （按需加速）下载 -> 解包 -> 装回原位。

    返回 (版本号, 新内核路径, 备份路径)。任何一步失败都抛异常，UI 层负责提示。
    """
    exe = config.nm3u8dl_path
    if not exe:
        raise ValueError("还没有指定 N_m3u8DL-RE 路径")
    release = fetch_latest(config.update_proxy)
    url = accelerate(release.asset_url, config.update_accel_enabled,
                     config.update_accel_prefix)
    with TempDir() as work:
        archive = download(url, work, config.update_proxy, progress)
        binary = extract_binary(archive, work / "unpacked")
        backup = install(binary, exe)
    return release.tag, exe, backup


class TempDir:
    """with 语句里的临时目录（标准库的 TemporaryDirectory 在 Windows 上偶尔删不掉，多试一次）。"""

    def __init__(self) -> None:
        import tempfile
        self.path = Path(tempfile.mkdtemp(prefix="miuix-m3u8-update-"))

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
