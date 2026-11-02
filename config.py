# -*- coding: utf-8 -*-
"""全局配置。

frozen / 源码模式统一：
- 登录态、导出目录放在「可执行文件同级目录」或「源码目录」；
- Playwright driver/浏览器内核对 PyInstaller frozen 不敏感（--collect-all playwright 时会随包进 _MEIPASS）。
"""
from __future__ import annotations

import sys
from pathlib import Path


def _app_root() -> Path:
    """返回应用数据根目录（state.json / exports 都往这放）。

    - PyInstaller onefile：可执行文件所在目录（不是 _MEIPASS 临时解压目录）
    - PyInstaller onedir / macOS .app：可执行文件所在目录
    - 源码模式：项目根（config.py 所在目录）
    """
    if getattr(sys, "frozen", False):
        # frozen 模式下 sys.executable 就是真正的 exe / app / binary
        return Path(sys.executable).resolve().parent
    return Path(__file__).parent.resolve()


ROOT = _app_root()

# 登录态文件（Playwright 的 storage_state JSON）
STATE_FILE = ROOT / "state.json"

# 默认导出目录
DEFAULT_OUT = ROOT / "exports"

# 小红书入口
XHS_HOME = "https://www.xiaohongshu.com"
XHS_CHAT = "https://www.xiaohongshu.com/chat"

# 采集默认滚动时长（毫秒）
DEFAULT_SCROLL_MS = 45000

# 消息类型标签（与网页版 content_type 对齐）
TYPE_LABELS = {
    0: "消息", 1: "文本", 2: "图片", 3: "笔记", 4: "系统", 5: "转发",
    9: "语音", 10: "提示", 11: "视频", 13: "表情", 16: "表情", 17: "通话",
}

# 应用信息（GUI / 打包用）
APP_NAME = "小红书聊天记录导出"
APP_VERSION = "2.0.0"
APP_BUNDLE = "com.xhs.exporter"


def play_right_browser_path() -> Path:
    """Playwright Chromium 浏览器可执行文件路径。

    frozen onedir 下 Playwright 自己管理路径（首次 install 会放到用户目录），
    我们不需要关心；这个函数主要给诊断用。
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path or "")
    except Exception:
        return Path("")
