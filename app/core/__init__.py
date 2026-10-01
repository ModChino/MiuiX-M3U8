"""MiuiX M3U8 核心引擎：命令行构建、输出解析、任务调度、配置持久化。

契约见 docs/INTERFACES.md §4。本包只依赖 QtCore，禁止 import QtWidgets。
"""
from __future__ import annotations

__all__ = ["config", "model", "nm3u8dl", "parser", "runner"]
