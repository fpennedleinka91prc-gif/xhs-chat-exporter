# -*- coding: utf-8 -*-
"""核心流程：登录 → 选会话 → 导出。抽出来给 CLI 和 GUI 共用。

GUI 侧的用法（伪代码）：
    t = threading.Thread(target=run_pipeline, args=(options,),
                         kwargs={"logger": gui_logger, "progress_cb": gui_progress})
    t.start()

所有可能慢的步骤都走 logger / progress_cb 回调，不打印 stdout，方便 GUI 接。
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple


# —— 人话错误映射（给 GUI / CLI 共用）——

HUMAN_HINTS = {
    "nolist": "没找到消息列表。小红书页面可能加载太慢，或网页结构有更新。",
    "nomsglist": "没找到消息列表容器（.xhs-im-msg-list 之类）。可能需要更新脚本。",
    "timeout": "等待超时。网络慢或小红书页面加载异常。可以换网络重开。",
    "登录态已失效": "登录态过期。用 --relogin 重登，或 GUI 里点「重新登录」。",
    "打开会话失败": "打开会话失败。可能是 uid 不对，或被风控。",
    "采集历史失败": "采集历史失败。可能需要把滚动时长（scroll-ms）调大。",
}


def humanize(msg: str) -> str:
    """把原始异常消息翻译成带人话提示的字符串。"""
    hint = ""
    for kw, hint_text in HUMAN_HINTS.items():
        if kw in msg:
            hint = f"\n💡 {hint_text}"
            break
    return msg + hint


# —— 核心数据类 ——

@dataclass
class PipelineOptions:
    """三步走的所有可调参数。CLI argparse 和 GUI 最终都往这里灌。"""
    outdir: Path                          # 导出目录
    relogin: bool = False                 # 强制重登
    headless: bool = False                # 无头（GUI 模式下一般 False）
    scroll_ms: int = 45000                # 每个会话的自动滚动时长
    formats: List[str] = field(            # md / html / json / csv
        default_factory=lambda: ["md", "html", "json", "csv"])
    download_media: bool = True           # 是否下载媒体
    chat_user_ids: Optional[List[str]] = None  # 预指定的会话 uid（GUI 多选后会填）
    export_all: bool = False              # 导出全部会话

    # 回调（GUI 用）
    logger: Optional[Callable[[str], None]] = None   # 接收日志行
    progress_cb: Optional[Callable[[int, int, str], None]] = None  # (current, total, label)

    def log(self, msg: str) -> None:
        if self.logger:
            self.logger(msg)
        else:
            print(msg)


@dataclass
class PipelineResult:
    ok_count: int = 0
    fail_count: int = 0
    total_messages: int = 0
    failures: List[Tuple[str, str]] = field(default_factory=list)  # (uid, reason)
    exported_paths: List[Path] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.ok_count > 0 and self.fail_count == 0


def run_pipeline(opts: PipelineOptions) -> PipelineResult:
    """三步走主流程。可以被 CLI main() 直接调用，也可以被 GUI 放后台线程。

    注意：blocking；调用方自己套线程。
    """
    # 本地 import，避免 GUI 起一个 dummy 线程就把 Playwright 拉起来
    from browser import ensure_browser, close_browser
    from collector import XhsCollector, select_conversations_interactive
    from exporter import export_all

    res = PipelineResult()
    pw = browser = None
    opts.outdir.mkdir(parents=True, exist_ok=True)

    try:
        opts.log("=" * 50)
        opts.log("📱 小红书聊天记录导出 v2")
        opts.log("=" * 50)
        opts.log(f"📂 导出目录：{opts.outdir}")

        # —— 1. 登录 ——
        opts.log("🔐 正在启动浏览器…")
        pw, browser, context, page, is_new = ensure_browser(
            headless=opts.headless, force_relogin=opts.relogin)
        opts.log("✅ 登录成功" if is_new else "✅ 已复用之前的登录态。")

        # —— 2. 选会话 ——
        collector = XhsCollector(page)

        # 没指定 uid 时，走交互选择——但 GUI 下用户应该已经在列表里选好，
        # 所以如果 chat_user_ids 为空、export_all 也 False，就报错。
        if opts.chat_user_ids is None and not opts.export_all:
            opts.log("❌ 必须先选择要导出的会话（或指定 --chat-user / --all）。")
            return res

        if opts.chat_user_ids is None:
            # GUI 没填，CLI 可能要交互
            opts.chat_user_ids = []

        if not opts.chat_user_ids and opts.export_all:
            opts.log("📋 正在加载全部会话…")
            convs = collector.list_conversations()
            opts.chat_user_ids = [c.uid for c in convs if c.uid]
            opts.log(f"   找到 {len(opts.chat_user_ids)} 个有 uid 的会话。")

        if not opts.chat_user_ids:
            opts.log("❌ 没选到任何会话，退出。")
            return res

        total = len(opts.chat_user_ids)
        opts.log(f"\n✅ 待导出 {total} 个会话")

        # —— 3. 逐个导出 ——
        for idx, uid in enumerate(opts.chat_user_ids, start=1):
            if opts.progress_cb:
                opts.progress_cb(idx - 1, total, f"打开会话 {uid[:12]}…")
            opts.log(f"\n{'─' * 40}")
            opts.log(f"▶️ [{idx}/{total}] 会话 {uid}")

            # 打开会话
            try:
                actual_uid = collector.open_conversation(uid)
                opts.log(f"   已进入会话（对方 uid={actual_uid}）")
            except Exception as e:
                res.failures.append((uid, f"打开会话失败：{e}"))
                opts.log(f"   ❌ 打开会话失败：{humanize(str(e))}")
                continue

            # 采集
            try:
                if opts.progress_cb:
                    opts.progress_cb(idx - 1, total, f"滚动加载历史（{opts.scroll_ms//1000}s）…")
                opts.log(f"   正在滚动加载全部历史（最多 {opts.scroll_ms // 1000}s）…")
                msgs = collector.collect_history(scroll_ms=opts.scroll_ms)
                opts.log(f"   抓到 {len(msgs)} 条消息")
                res.total_messages += len(msgs)
            except Exception as e:
                res.failures.append((uid, f"采集历史失败：{e}"))
                opts.log(f"   ❌ 采集历史失败：{humanize(str(e))}")
                continue

            if not msgs:
                opts.log("   ⚠️ 这个会话没抓到消息，跳过。")
                continue

            # 导出
            sub = opts.outdir / actual_uid
            opts.log(f"   导出到 {sub}")
            try:
                exp = export_all(
                    msgs, actual_uid, sub,
                    download_media=opts.download_media,
                    formats=opts.formats,
                )
                res.ok_count += 1
                res.exported_paths.append(sub)
                for fmt, p in exp["formats"].items():
                    opts.log(f"      ✅ {fmt.upper()} → {p}")
            except Exception as e:
                res.failures.append((uid, f"导出失败：{e}"))
                opts.log(f"   ❌ 导出失败：{humanize(str(e))}")
                traceback.print_exc()

            if opts.progress_cb:
                opts.progress_cb(idx, total, f"会话 {uid[:12]} 完成")

        # —— 4. 总结 ——
        opts.log(f"\n{'=' * 50}")
        opts.log("📊 导出总结")
        opts.log(f"{'=' * 50}")
        opts.log(f"  成功会话：{res.ok_count} / {total}")
        opts.log(f"  累计消息：{res.total_messages}")
        if res.failures:
            opts.log(f"\n⚠️ 有 {len(res.failures)} 个会话失败：")
            for uid, reason in res.failures[:10]:
                opts.log(f"  - {uid}: {reason}")
            if len(res.failures) > 10:
                opts.log(f"  …还有 {len(res.failures) - 10} 个")
        opts.log(f"\n📁 导出目录：{opts.outdir}")
        opts.log("   打开 chat.html 可以看气泡视图，chat.md 是纯文本。")

    except Exception as e:
        opts.log(f"\n❌ 出问题了：{humanize(str(e))}")
        traceback.print_exc()
    finally:
        if browser and pw:
            opts.log("\n🔒 关闭浏览器…")
            try:
                close_browser(pw, browser)
            except Exception:
                pass

    return res
