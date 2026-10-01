"""Miuix 设计 token（颜色 / 文本样式 / 圆角 / 间距 / 图标尺寸）。

数值来源：`docs/MIUIX_TOKENS.md`（从 miuix 源码 `Colors.kt` / `TextStyles.kt` 逐行抄录，
并经官方文档 https://compose-miuix-ui.github.io/miuix/zh_CN/guide/theme 交叉验证）。
字段名严格遵循 `docs/INTERFACES.md` §3.1 冻结契约（只增不删）。

颜色写法：Qt 原生 `#AARRGGBB`（不透明时可写 `#RRGGBB`）。
QSS 中需要 alpha 时必须用 `rgba(r,g,b,a)`，由 `theme.qss_color()` 自动转换。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """一套完整配色。字段分两段：契约字段（无默认值）+ Miuix 扩展字段（带默认值）。"""

    # ---- docs/INTERFACES.md §3.1 冻结字段 ----
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary: str
    on_secondary: str
    secondary_container: str
    on_secondary_container: str
    tertiary: str
    on_tertiary: str
    tertiary_container: str
    on_tertiary_container: str
    background: str
    on_background: str
    surface: str
    on_surface: str
    surface_container: str
    surface_container_high: str
    on_surface_variant: str
    outline: str
    outline_variant: str
    error: str
    on_error: str
    error_container: str
    success: str
    warning: str
    disabled: str
    on_disabled: str
    scrim: str

    # ---- Miuix 源码补充 token（Colors.kt，命名转 snake_case）----
    on_error_container: str = "#410002"
    primary_variant: str = "#3482FF"
    on_primary_variant: str = "#AECDFF"
    secondary_variant: str = "#F0F0F0"
    on_secondary_variant: str = "#303030"
    secondary_container_variant: str = "#F0F0F0"
    on_secondary_container_variant: str = "#A8A8A8"
    tertiary_container_variant: str = "#EAF2FF"
    surface_variant: str = "#FFFFFF"
    on_surface_container: str = "#000000"
    on_surface_container_variant: str = "#959595"
    surface_container_highest: str = "#E8E8E8"
    on_surface_container_highest: str = "#000000"
    on_surface_container_high: str = "#A2A2A2"
    on_surface_secondary: str = "#CC000000"
    on_surface_variant_summary: str = "#99000000"
    on_surface_variant_actions: str = "#66000000"
    on_background_variant: str = "#8C93B0"
    disabled_primary: str = "#C2D9FF"
    disabled_on_primary: str = "#F3F8FF"
    disabled_primary_button: str = "#C2D9FF"
    disabled_on_primary_button: str = "#FFFFFF"
    disabled_primary_slider: str = "#B8CFF5"
    disabled_secondary: str = "#F0F0F0"
    disabled_on_secondary: str = "#FCFCFC"
    disabled_secondary_variant: str = "#F2F2F2"
    disabled_on_secondary_variant: str = "#B2B2B2"
    disabled_on_surface: str = "#B2B2B2"
    divider_line: str = "#E0E0E0"
    window_dimming: str = "#4D000000"
    slider_key_point: str = "#4DA3B3CD"
    slider_key_point_foreground: str = "#6EB5FF"
    slider_background: str = "#0F000000"

    def get(self, name: str, default: str = "#000000") -> str:
        """按名字取色，供 QSS 模板与自绘控件统一使用。"""
        return getattr(self, name, default)


# --------------------------------------------------------------------------
# 浅色主题（Colors.kt L341 起，Light）
# --------------------------------------------------------------------------
LIGHT = Palette(
    primary="#3482FF",
    on_primary="#FFFFFF",
    primary_container="#5D9BFF",
    on_primary_container="#FFFFFF",
    secondary="#E6E6E6",
    on_secondary="#FFFFFF",
    secondary_container="#F0F0F0",
    on_secondary_container="#A9A9A9",
    # Miuix 未定义 tertiary / onTertiary，这里取 onTertiaryContainer 的蓝作为强调色
    tertiary="#3482FF",
    on_tertiary="#FFFFFF",
    tertiary_container="#EAF2FF",
    on_tertiary_container="#3482FF",
    background="#FFFFFF",
    on_background="#000000",
    surface="#F7F7F7",
    on_surface="#000000",
    surface_container="#FFFFFF",
    surface_container_high="#E8E8E8",
    on_surface_variant="#99000000",          # onSurfaceVariantSummary 60%
    outline="#D9D9D9",
    outline_variant="#E0E0E0",               # dividerLine
    error="#E94634",
    on_error="#FFFFFF",
    error_container="#FDF6F4",
    # Miuix 未定义 success / warning，按 HyperOS 语义色补充
    success="#12B76A",
    warning="#FF8A00",
    disabled="#B2B2B2",                      # disabledOnSurface
    on_disabled="#FCFCFC",                   # disabledOnSecondary
    scrim="#4D000000",                       # windowDimming 30%
    on_error_container="#410002",
    primary_variant="#3482FF",
    on_primary_variant="#AECDFF",
    secondary_variant="#F0F0F0",
    on_secondary_variant="#303030",
    secondary_container_variant="#F0F0F0",
    on_secondary_container_variant="#A8A8A8",
    tertiary_container_variant="#EAF2FF",
    surface_variant="#FFFFFF",
    on_surface_container="#000000",
    on_surface_container_variant="#959595",
    surface_container_highest="#E8E8E8",
    on_surface_container_highest="#000000",
    on_surface_container_high="#A2A2A2",
    on_surface_secondary="#CC000000",        # 80%
    on_surface_variant_summary="#99000000",  # 60%
    on_surface_variant_actions="#66000000",  # 40%
    on_background_variant="#8C93B0",
    disabled_primary="#C2D9FF",
    disabled_on_primary="#F3F8FF",
    disabled_primary_button="#C2D9FF",
    disabled_on_primary_button="#FFFFFF",
    disabled_primary_slider="#B8CFF5",
    disabled_secondary="#F0F0F0",
    disabled_on_secondary="#FCFCFC",
    disabled_secondary_variant="#F2F2F2",
    disabled_on_secondary_variant="#B2B2B2",
    disabled_on_surface="#B2B2B2",
    divider_line="#E0E0E0",
    window_dimming="#4D000000",
    slider_key_point="#4DA3B3CD",
    slider_key_point_foreground="#6EB5FF",
    slider_background="#0F000000",           # 6% 黑
)

# --------------------------------------------------------------------------
# 深色主题（Colors.kt Dark）
# --------------------------------------------------------------------------
DARK = Palette(
    primary="#277AF7",
    on_primary="#FFFFFF",
    primary_container="#338FE4",
    on_primary_container="#FFFFFF",
    secondary="#505050",
    on_secondary="#FFFFFF",
    secondary_container="#434343",
    on_secondary_container="#7C7C7C",
    tertiary="#4788FF",
    on_tertiary="#FFFFFF",
    tertiary_container="#2B3B54",
    on_tertiary_container="#4788FF",
    background="#242424",
    on_background="#E6FFFFFF",               # 90%
    surface="#000000",
    on_surface="#F2F2F2",
    surface_container="#242424",
    surface_container_high="#242424",
    on_surface_variant="#80FFFFFF",          # onSurfaceVariantSummary 50%
    outline="#404040",
    outline_variant="#393939",               # dividerLine
    error="#F12522",
    on_error="#FFFFFF",
    error_container="#2E0603",
    success="#3EDC81",
    warning="#FFB021",
    disabled="#666666",
    on_disabled="#797979",
    scrim="#99000000",                       # windowDimming 60%
    on_error_container="#FFDAD6",
    primary_variant="#0073DD",
    on_primary_variant="#99C7F1",
    secondary_variant="#434343",
    on_secondary_variant="#D9D9D9",
    secondary_container_variant="#4F4F4F",
    on_secondary_container_variant="#959595",
    tertiary_container_variant="#505050",
    surface_variant="#242424",
    on_surface_container="#E6FFFFFF",
    on_surface_container_variant="#737373",
    surface_container_highest="#2D2D2D",
    on_surface_container_highest="#E9E9E9",
    on_surface_container_high="#666666",
    on_surface_secondary="#CCFFFFFF",
    on_surface_variant_summary="#80FFFFFF",
    on_surface_variant_actions="#66FFFFFF",
    on_background_variant="#787E96",
    disabled_primary="#253E64",
    disabled_on_primary="#677993",
    disabled_primary_button="#253E64",
    disabled_on_primary_button="#677893",
    disabled_primary_slider="#44587C",
    disabled_secondary="#3F3F3F",
    disabled_on_secondary="#797979",
    disabled_secondary_variant="#404040",
    disabled_on_secondary_variant="#707170",
    disabled_on_surface="#666666",
    divider_line="#393939",
    window_dimming="#99000000",
    slider_key_point="#4D7A8AA6",
    slider_key_point_foreground="#5DAAFF",
    slider_background="#26FFFFFF",           # 15% 白
)


@dataclass(frozen=True)
class TextStyle:
    """文本样式。size/line_height 单位为 px（1dp = 1px @1x）；line_height = 0 表示用字体自然行高。"""

    size: int
    weight: int          # QFont.Weight 数值：400 / 500 / 600 / 700
    line_height: int = 0


# 全部取自 TextStyles.kt：只有 subtitle 加粗(700)，只有 paragraph 有 1.2em 行高，其余无行高、无字间距。
TEXT: dict[str, TextStyle] = {
    "title1": TextStyle(32, 400),
    "title2": TextStyle(24, 400),
    "title3": TextStyle(20, 400),
    "title4": TextStyle(18, 400),
    "headline": TextStyle(17, 400),          # = headline1
    "headline1": TextStyle(17, 400),
    "headline2": TextStyle(16, 400),
    "main": TextStyle(17, 400),
    "paragraph": TextStyle(17, 400, 20),     # 1.2em × 17 ≈ 20px
    "body1": TextStyle(16, 400),
    "body2": TextStyle(14, 400),
    "button": TextStyle(17, 400),
    "subtitle": TextStyle(14, 700),
    "footnote1": TextStyle(13, 400),
    "footnote2": TextStyle(11, 400),
    # 契约要求存在的补充键（语义别名）
    "label": TextStyle(14, 400),             # = body2
    "caption": TextStyle(11, 400),           # = footnote2
    "mono": TextStyle(13, 400),              # 等宽（日志/命令行）
}

# 字体族优先级：MiSans（HyperOS 官方）→ 微软雅黑 → Noto Sans SC → Segoe UI
FONT_STACK: list[str] = [
    "MiSans",
    "MiSans VF",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans SC",
    "Source Han Sans SC",
    "PingFang SC",
    "Segoe UI",
    "sans-serif",
]

MONO_STACK: list[str] = ["MiSans Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]

# 圆角：8 / 12 / 16 / 28 / 50（对应 Miuix 各组件），pill 用于胶囊
RADIUS: dict[str, int] = {
    "xs": 8,
    "sm": 12,
    "md": 16,
    "lg": 28,
    "xl": 50,
    "pill": 999,
}

# 间距：官方卡片间距 16、卡片内元素 8、页面（卡片外侧）留白 16；
# 注意：Miuix 并未定义「页面边距」token，26dp 只是 TopAppBar 的标题内边距（见 METRIC["topbar_pad"]）。
SPACING: dict[str, int] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "page": 16,
}

# 图标尺寸：默认 24，按钮内 20，导航栏 26~28
ICON_SIZE: dict[str, int] = {
    "sm": 20,
    "md": 24,
    "lg": 28,
}

# 组件几何常量（单位 px，来源见 MIUIX_TOKENS.md §3）
METRIC: dict[str, float] = {
    "button_h": 40,
    "button_min_w": 58,
    "button_pad_h": 16,
    "button_pad_v": 13,
    "icon_button": 40,
    "field_h": 45,
    "switch_w": 49,
    "switch_h": 28,
    "switch_thumb": 20,
    "switch_off": 4,
    "switch_on": 25,
    "switch_press_scale": 1.127,
    "slider_h": 28,
    "slider_thumb": 20.16,
    "keypoint_r": 3.855,
    "topbar_h": 52,
    "rail_w": 240,
    "rail_icon": 28,
    "list_h": 56,
    "list_pad": 16,
    "card_pad": 16,
    "progress_h": 6,
    "checkbox": 26,
    "divider": 0.75,
    "tabrow_h": 42,
    "seg_min_w": 76,
    "squircle_ext": 1.1,
    "squircle_ctrl": 0.643,
}
