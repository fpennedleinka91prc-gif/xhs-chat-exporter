# -*- coding: utf-8 -*-
"""全局配置（v2.1.0 起：Chromium 内核随包分发）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _app_root() -> Path:
    """应用数据根目录（state.json / exports 都往这放）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).parent.resolve()


def _frozen_datas_root() -> Path:
    """frozen 模式下 PyInstaller 打包的数据根（_MEIPASS）。
    onefile 模式是解压临时目录；onedir / .app / Windows exe 是 _internal/。
    我们的 browsers、playwright driver 等 datas 都在这里。
    """
    return Path(getattr(sys, "_MEIPASS", _app_root()))


ROOT = _app_root()
_DATAS = _frozen_datas_root()

# 登录态 + 默认导出目录（可写，放 app_root 旁，不放只读 datas 里）
STATE_FILE = ROOT / "state.json"
DEFAULT_OUT = ROOT / "exports"

# 小红书入口
XHS_HOME = "https://www.xiaohongshu.com"
XHS_CHAT = "https://www.xiaohongshu.com/chat"

DEFAULT_SCROLL_MS = 45000

TYPE_LABELS = {
    0: "消息", 1: "文本", 2: "图片", 3: "笔记", 4: "系统", 5: "转发",
    9: "语音", 10: "提示", 11: "视频", 13: "表情", 16: "表情", 17: "通话",
}

APP_NAME = "小红书聊天记录导出"
APP_VERSION = "2.1.0"
APP_BUNDLE = "com.xhs.exporter"

# —— Chromium 内核打包位置（v2.1.0）——
# 构建时：PLAYWRIGHT_BROWSERS_PATH=<PROJECT_ROOT>/browsers playwright install chromium
#        → 产出 ./browsers/chromium-XXXX/
# 打包 spec：datas = [ ("./browsers", "browsers") ]
# 运行时：Playwright 期望 registry dir = PLAYWRIGHT_BROWSERS_PATH
#        里面直接是 chromium-XXXX/ 子目录
BUNDLED_BROWSERS_DIR = _DATAS / "browsers"


def setup_playwright_browser_env() -> dict:
    """设置 PLAYWRIGHT_BROWSERS_PATH + 返回诊断 dict。
    调用时机：**必须在第一次 import playwright 之前**（browser.py 顶部就调）。
    """
    info: dict = {}
    if BUNDLED_BROWSERS_DIR.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BUNDLED_BROWSERS_DIR)
        info["mode"] = "bundled"
        info["path"] = str(BUNDLED_BROWSERS_DIR)
        info["exists"] = True
        # 统计里面有哪些浏览器
        brows = sorted([p.name for p in BUNDLED_BROWSERS_DIR.iterdir()
                        if p.is_dir() and (p.name.startswith("chromium") or p.name.startswith("chrome"))])
        info["browsers"] = brows
    else:
        info["mode"] = "system-default"
        info["path"] = str(BUNDLED_BROWSERS_DIR)
        info["exists"] = False
    info["frozen"] = getattr(sys, "frozen", False)
    return info
