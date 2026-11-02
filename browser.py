# -*- coding: utf-8 -*-
"""浏览器生命周期 + 登录态持久化（v2.1.0：Chromium 随包分发 + channel 兜底）。

启动顺序（关键）：
1. import config → config.setup_playwright_browser_env() 先跑，把 PLAYWRIGHT_BROWSERS_PATH 设好
2. 再 import playwright.sync_api
这样 Playwright 启动时就读到了我们准备好的路径。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

# ★ 在 Playwright 之前设置好环境变量（必须，否则 Playwright 读不到）
from config import STATE_FILE, XHS_HOME, setup_playwright_browser_env
_BROWSER_ENV_INFO = setup_playwright_browser_env()

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PWTimeout  # noqa: E402


# —— 浏览器可执行文件定位诊断 ——

def _diagnose_browser() -> dict:
    """尝试定位可用的 Chromium / Chrome / Edge。返回 dict 含路径 + 可用状态。"""
    info: dict = {"bundled_dir": str(_BROWSER_ENV_INFO.get("path", ""))}
    bundled = _BROWSER_ENV_INFO.get("exists")
    info["bundled"] = bundled

    # 检查 bundled 里有没有 chromium 可执行
    bundled_bin: Optional[str] = None
    if bundled:
        d = Path(_BROWSER_ENV_INFO["path"])
        for sub in sorted(d.iterdir()):
            if not sub.is_dir() or not sub.name.startswith("chromium"):
                continue
            # macOS: chrome-mac/Chromium.app/Contents/MacOS/Chromium
            # Windows: chrome-win/chrome.exe
            # Linux:  chrome-linux/chrome
            for cand in [
                sub / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
                sub / "chrome-win" / "chrome.exe",
                sub / "chrome-linux" / "chrome",
            ]:
                if cand.is_file():
                    bundled_bin = str(cand)
                    break
            if bundled_bin:
                break
    info["bundled_bin"] = bundled_bin
    info["bundled_ok"] = bundled_bin is not None

    # 系统 channel 可执行是否存在（macOS Chrome, Windows Chrome/Edge）
    system_channels = {"chrome": False, "msedge": False}
    if sys.platform == "darwin":
        chrome_app = Path("/Applications/Google Chrome.app")
        system_channels["chrome"] = chrome_app.is_dir()
    elif sys.platform.startswith("win"):
        # Playwright 会自己找 Windows Chrome/Edge，我们先只标记"是否理论可试"
        system_channels["chrome"] = True   # Windows 上有大概率装了
        system_channels["msedge"] = True
    info["system_channels_available"] = system_channels
    return info


# —— 关键：选哪个浏览器启动 ——

def _launch_browser(pw, headless: bool = False) -> Tuple[Browser, dict]:
    """按优先级尝试启动 Chromium：
    1. bundled 内核（xhs-exporter/browsers/chromium-XXXX/）
    2. 系统 Chrome（channel='chrome'）
    3. 系统 Edge（channel='msedge'） — 仅 Windows
    都失败 → 丢出「人话错误 + 诊断信息」。
    """
    diag = _diagnose_browser()
    errors: List[str] = []

    # 1. bundled
    if diag["bundled_ok"]:
        try:
            browser = pw.chromium.launch(headless=headless)
            diag["chosen"] = "bundled"
            diag["ok"] = True
            return browser, diag
        except Exception as e:
            errors.append(f"随包 Chromium: {e}")

    # 2. channel 兜底
    channels_to_try = []
    if sys.platform == "darwin":
        channels_to_try = ["chrome"]
    elif sys.platform.startswith("win"):
        channels_to_try = ["msedge", "chrome"]
    # Linux 上 Playwright channel='chrome' 效果有限，这里不做兜底（用户应装 chromium）

    for channel in channels_to_try:
        try:
            browser = pw.chromium.launch(headless=headless, channel=channel)
            diag["chosen"] = f"system-channel-{channel}"
            diag["ok"] = True
            return browser, diag
        except Exception as e:
            errors.append(f"系统 {channel}: {e}")

    # 都失败
    hint_lines = [
        "",
        "💡 解决方案（任选其一）：",
        "",
        "  ① 最简单：装一个浏览器（macOS Chrome.app / Windows Edge），下次启动时本工具会自动用上。",
        "",
        "  ② 或者把 Playwright Chromium 装到默认缓存目录：",
        "     python -m playwright install chromium",
        "     （这条命令需要 Python + pip；如果不想装 Python，也可以直接重装一下本工具，"
        "      新版 v2.1.0+ 应该已经带了 Chromium 内核）",
        "",
        "  ③ 你用的安装包可能是旧版（v2.0.0 不带浏览器）。请到 GitHub Release 下载 v2.1.0+：",
        "     https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter/releases",
        "",
        "诊断信息：",
        f"  • 随包浏览器目录：{diag.get('bundled_dir', '')}",
        f"  • 随包浏览器存在：{diag['bundled_ok']}",
        f"  • 系统可用 channels：{list(diag.get('system_channels_available', {}).items())}",
    ]
    msg = "\n".join(["❌ 没找到可用的浏览器内核。"] + errors + hint_lines)
    raise RuntimeError(msg)


# —— 业务辅助 ——

def _open_xhs_home(page: Page) -> None:
    try:
        page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        raise RuntimeError(f"打开小红书首页失败：{e}") from e


def _looks_logged_in(page: Page) -> bool:
    try:
        js = r"""() => {
            const msgBtn = Array.from(document.querySelectorAll('a,button,div'))
                .some(el => /消息|inbox/i.test(el.textContent || '') && (el.offsetWidth>0));
            const avatar = document.querySelector('img[alt*="用户"], .user-avatar, .avatar img');
            const hasUid = /user\/profile|\/user\//.test(location.href);
            return !!(msgBtn || avatar || hasUid);
        }"""
        return bool(page.evaluate(js))
    except Exception:
        return False


def ensure_browser(headless: bool = False, force_relogin: bool = False
                   ) -> Tuple[sync_playwright, Browser, BrowserContext, Page, bool]:
    """启动浏览器 + 登录。返回 (pw, browser, context, page, is_new_login)。"""
    pw = sync_playwright().start()
    try:
        browser, _diag = _launch_browser(pw, headless=headless)
    except Exception:
        pw.stop()
        raise

    reuse_state = (STATE_FILE.exists() and not force_relogin)

    if reuse_state:
        try:
            context = browser.new_context(storage_state=str(STATE_FILE))
        except Exception as e:
            print(f"⚠️ 登录态文件损坏，将重新登录。({e})")
            STATE_FILE.unlink(missing_ok=True)
            context = browser.new_context()
            reuse_state = False
    else:
        context = browser.new_context()

    context.add_init_script("""() => {
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    }""")
    page = context.new_page()

    if reuse_state:
        _open_xhs_home(page)
        if _looks_logged_in(page):
            return pw, browser, context, page, False
        print("⚠️ 登录态已失效，请重新扫码登录。")

    _open_xhs_home(page)
    print("\n" + "=" * 60)
    print("👉 请在弹出的浏览器里扫码 / 登录小红书账号")
    print("👉 登录成功、看到首页后，回到这里按回车继续…")
    print("=" * 60)

    start = time.time()
    logged = False
    while time.time() - start < 300:
        if _looks_logged_in(page):
            logged = True
            break
        time.sleep(1.0)

    if not logged:
        input("\n如果已经登录成功，请按回车继续；如果登录失败请 Ctrl-C 退出：")

    try:
        context.storage_state(path=str(STATE_FILE))
        print(f"✅ 登录态已保存到 {STATE_FILE}")
    except Exception as e:
        print(f"⚠️ 登录态保存失败（不影响本次使用）：{e}")

    return pw, browser, context, page, True


def close_browser(pw, browser) -> None:
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


# —— _launch_browser 用到的 List ——
from typing import List  # noqa: E402  (放函数末尾也行，但提前引一次)
