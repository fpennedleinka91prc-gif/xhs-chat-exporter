# -*- coding: utf-8 -*-
"""浏览器生命周期 + 登录态持久化。

设计原则：
- 只启动一个可见的 Chromium（headless=False），让用户扫码；
- 首次启动保存 storage_state 到 state.json，后续复用；
- state.json 过期或登录失效时，自动提示用户重新登录。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Tuple

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from config import STATE_FILE, XHS_HOME


def _open_xhs_home(page: Page) -> None:
    try:
        page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        raise RuntimeError(f"打开小红书首页失败：{e}") from e


def _looks_logged_in(page: Page) -> bool:
    """粗判：页面里出现头像/消息按钮/用户相关 DOM 就算登录了。"""
    try:
        # 小红书登录态常见标记：导航栏有"消息"入口、或存在 img.avatar
        js = r"""() => {
            const msgBtn = Array.from(document.querySelectorAll('a,button,div'))
                .some(el => /消息|inbox/i.test(el.textContent || '') && (el.offsetWidth>0));
            const avatar = document.querySelector('img[alt*="用户"], .user-avatar, .avatar img');
            const hasUid = /user\/profile|\/user\//.test(location.href);
            return !!(msgBtn || avatar || hasUid);
        }"""
        logged = page.evaluate(js)
        return bool(logged)
    except Exception:
        return False


def ensure_browser(headless: bool = False, force_relogin: bool = False
                   ) -> Tuple[sync_playwright, Browser, BrowserContext, Page, bool]:
    """启动浏览器，确保在小红书已登录。

    Returns: (pw, browser, context, page, is_new_login)
    """
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)

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

    # 伪装 UA，避免被风控一眼识别
    context.add_init_script("""() => {
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    }""")

    page = context.new_page()

    if reuse_state:
        _open_xhs_home(page)
        if _looks_logged_in(page):
            return pw, browser, context, page, False
        print("⚠️ 登录态已失效，请重新扫码登录。")

    # 需要新登录：打开首页让用户扫码
    _open_xhs_home(page)
    print("\n" + "=" * 60)
    print("👉 请在弹出的浏览器里扫码 / 登录小红书账号")
    print("👉 登录成功、看到首页后，回到这里按回车继续…")
    print("=" * 60)

    # 后台监听登录变化
    start = time.time()
    logged = False
    while time.time() - start < 300:  # 最多等 5 分钟
        if _looks_logged_in(page):
            logged = True
            break
        time.sleep(1.0)

    if not logged:
        # 给个兜底：让用户自己确认
        input("\n如果已经登录成功，请按回车继续；如果登录失败请 Ctrl-C 退出：")

    # 保存状态
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
