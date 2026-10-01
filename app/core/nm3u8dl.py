"""N_m3u8DL-RE 命令行构建。

参数以 docs/NM3U8DL_CLI.txt（v0.6.0-beta 实测 --help）为唯一准据。

规则：
- 只把与 CLI 默认值不同的项写进命令行（默认值取 --help 里的 [default: ...]）。
- opt.extra_args 原样追加在最后，优先级最高（可覆盖前面的参数）。
- build_command 返回 argv 列表；preview_command 返回可直接粘贴进 cmd 的单行命令。
"""
from __future__ import annotations

from .model import DownloadOptions

# ---- v0.6.0-beta --help 里的默认值 ----
DEFAULT_THREAD_COUNT = 16
DEFAULT_RETRY_COUNT = 3
DEFAULT_HTTP_TIMEOUT = 100
DEFAULT_SUB_FORMAT = "SRT"
DEFAULT_MUXER = "ffmpeg"
DEFAULT_MUX_FORMAT = "mp4"
DEFAULT_DECRYPTION_ENGINE = "MP4DECRYPT"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_UI_LANGUAGE = "zh-CN"


def _mux_options(opt: DownloadOptions) -> str:
    """-M 的值：format=..:muxer=..[:bin_path=..]（见 --morehelp mux-after-done）。"""
    fmt = opt.mux_format or DEFAULT_MUX_FORMAT
    muxer = opt.muxer or DEFAULT_MUXER
    parts = [f"format={fmt}", f"muxer={muxer}"]
    # bin_path 指所选混流器本身的路径：只有 muxer=ffmpeg 时 ffmpeg_path 才适用
    if opt.ffmpeg_path and muxer.lower() == "ffmpeg":
        parts.append(f"bin_path={opt.ffmpeg_path}")
    return ":".join(parts)


def build_command(exe: str, opt: DownloadOptions) -> list[str]:
    """把 DownloadOptions 转成 argv 列表。

    :raises ValueError: opt.url 为空（没有输入流时命令行无意义）。
    """
    if not opt.url.strip():
        raise ValueError("下载地址（opt.url）不能为空")

    cmd: list[str] = [exe, opt.url]

    def value(switch: str, val: str | int | None) -> None:
        if val not in (None, ""):
            cmd.extend([switch, str(val)])

    def flag(switch: str, enabled: bool) -> None:
        if enabled:
            cmd.append(switch)

    def bool_value(switch: str, enabled: bool) -> None:
        """CLI 的 bool? 选项：只在需要否定 CLI 默认值时显式传 false。"""
        if not enabled:
            cmd.extend([switch, "false"])

    # 目录 / 命名
    value("--tmp-dir", opt.tmp_dir)
    value("--save-dir", opt.save_dir)
    value("--save-name", opt.save_name)

    # 网络
    if opt.thread_count != DEFAULT_THREAD_COUNT:
        value("--thread-count", opt.thread_count)
    if opt.retry_count != DEFAULT_RETRY_COUNT:
        value("--download-retry-count", opt.retry_count)
    if opt.http_timeout != DEFAULT_HTTP_TIMEOUT:
        value("--http-request-timeout", opt.http_timeout)
    bool_value("--use-system-proxy", opt.use_system_proxy)
    value("--custom-proxy", opt.custom_proxy)
    for header in opt.headers:
        if header.strip():
            cmd.extend(["-H", header])
    value("-R", opt.max_speed)

    # 流选择
    flag("--auto-select", opt.auto_select)
    value("-sv", opt.select_video)
    value("-sa", opt.select_audio)
    value("-ss", opt.select_subtitle)
    value("-dv", opt.drop_video)
    value("-da", opt.drop_audio)
    value("-ds", opt.drop_subtitle)
    flag("--sub-only", opt.sub_only)
    if opt.sub_format.upper() != DEFAULT_SUB_FORMAT:
        value("--sub-format", opt.sub_format.upper())
    bool_value("--auto-subtitle-fix", opt.auto_subtitle_fix)

    # 解密
    value("--key", opt.key)
    value("--key-text-file", opt.key_text_file)
    value("--custom-hls-key", opt.custom_hls_key)
    value("--custom-hls-method", opt.custom_hls_method)
    if opt.decryption_engine.upper() != DEFAULT_DECRYPTION_ENGINE:
        value("--decryption-engine", opt.decryption_engine.upper())
    value("--decryption-binary-path", opt.decryption_binary_path)

    # 合并 / 混流
    flag("--skip-merge", opt.skip_merge)
    flag("--binary-merge", opt.binary_merge)
    flag("--use-ffmpeg-concat-demuxer", opt.use_ffmpeg_concat_demuxer)
    if opt.mux_enabled:
        value("-M", _mux_options(opt))
    value("--ffmpeg-binary-path", opt.ffmpeg_path)
    flag("-mt", opt.concurrent_download)

    # 收尾行为
    bool_value("--del-after-done", opt.del_after_done)
    bool_value("--check-segments-count", opt.check_segments_count)
    bool_value("--write-meta-json", opt.write_meta_json)
    flag("--append-url-params", opt.append_url_params)

    # 日志
    flag("--no-log", opt.no_log)
    if opt.log_level.upper() != DEFAULT_LOG_LEVEL:
        value("--log-level", opt.log_level.upper())
    if opt.ui_language and opt.ui_language != DEFAULT_UI_LANGUAGE:
        value("--ui-language", opt.ui_language)
    # 这两条必须成对：--force-ansi-console 让 RE 认为终端可交互，从而输出真实
    # 速度/大小（否则非交互管道下恒为 0.00Bps）；--no-ansi-color 再去掉颜色转义。
    flag("--force-ansi-console", opt.force_ansi_console)
    flag("--no-ansi-color", opt.no_ansi_color)

    # 用户附加参数：原样追加，优先级最高
    cmd.extend(str(a) for a in opt.extra_args)
    return cmd


#: cmd.exe 下需要加引号的字符
_CMD_SPECIAL = set(' \t"&|<>^()%!,')


def _quote(arg: str) -> str:
    """按 Windows cmd 习惯给单个参数加引号（仅用于预览，不参与进程启动）。"""
    if arg == "":
        return '""'
    if any(ch in _CMD_SPECIAL for ch in arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def preview_command(exe: str, opt: DownloadOptions) -> str:
    """返回可复制到 cmd 的单行命令（含引号）。"""
    return " ".join(_quote(a) for a in build_command(exe, opt))
