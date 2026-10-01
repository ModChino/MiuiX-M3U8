"""Miuix 设计系统（颜色 token / 主题 / 组件 / 图标）。

用法：
    from app.miuix.theme import init_theme, theme
    from app.miuix.widgets import MiuixCard, MiuixButton
    init_theme(app)          # 必须在使用控件前调用
    theme().set_mode("dark") # 切换主题（会触发 changed 信号）
"""
from __future__ import annotations

from . import icons, squircle, theme, tokens, widgets

__all__ = ["icons", "squircle", "theme", "tokens", "widgets"]
