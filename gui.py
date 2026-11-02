#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书聊天记录导出 —— Tkinter GUI 入口。

三步走图形界面：
  1. 点 "启动浏览器 / 登录" → 弹出 Chromium 让用户扫码 → 状态变成"已登录"
  2. 点 "刷新会话列表" → 左侧出现会话 → 多选 / 搜索 → 点 "开始导出"
  3. 进度条走 → 日志区滚 → 完成后点 "打开导出目录"

所有慢操作都在后台线程，UI 不会被卡。
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

# GUI 启动瞬间就要保证根级包可 import（PyInstaller 冻结后也对）
sys.path.insert(0, str(Path(__file__).parent))

from config import (  # noqa: E402
    APP_NAME, APP_VERSION, DEFAULT_OUT, STATE_FILE, DEFAULT_SCROLL_MS,
)
from core import PipelineOptions, run_pipeline  # noqa: E402


# —— Playwright 状态文件所在目录（显示给用户 + 状态判断）——

def _state_exists() -> bool:
    return STATE_FILE.exists() and STATE_FILE.stat().st_size > 0


# —— 后台 worker：GUI 的"会话列表刷新"也走 Playwright，必须自己开 browser ——

class GuiWorker(threading.Thread):
    """在后台线程跑一个 Playwright + collector 动作，结果通过 queue 回传。

    这样 Playwright 的 browser / page 永远在启动它的那个线程里用，规避线程安全问题。
    """

    def __init__(self, action: str, **kwargs):
        super().__init__(daemon=True)
        self.action = action
        self.kwargs = kwargs
        self.result_q: queue.Queue = queue.Queue()
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            if self.action == "list":
                self._do_list()
            elif self.action == "refresh_login":
                self._do_refresh_login()
            elif self.action == "export":
                self._do_export()
            else:
                self.result_q.put(("error", f"未知 action：{self.action}"))
        except Exception as e:
            self.result_q.put(("error", f"{type(e).__name__}: {e}"))
            traceback.print_exc()

    # —— 子动作 ——

    def _emit(self, t: str, **kw) -> None:
        if not self._stop:
            self.result_q.put((t, kw))

    def _do_refresh_login(self) -> None:
        """打开浏览器让用户扫码；完成后返回 ("login_done", is_new=bool)。"""
        from browser import ensure_browser, close_browser

        self._emit("log", msg="🔐 正在启动浏览器，请在弹出的 Chromium 里扫码登录…")
        pw = browser = None
        try:
            pw, browser, context, page, is_new = ensure_browser(
                headless=False, force_relogin=self.kwargs.get("relogin", False))
            self._emit("log", msg="✅ 登录态已保存")
            self._emit("login_done", is_new=is_new)
        finally:
            if browser and pw:
                try:
                    close_browser(pw, browser)
                except Exception:
                    pass

    def _do_list(self) -> None:
        """启动浏览器 → 打开 /chat → 拉会话列表。"""
        from browser import ensure_browser, close_browser
        from collector import XhsCollector

        self._emit("log", msg="📋 正在加载会话列表…")
        pw = browser = None
        try:
            pw, browser, context, page, is_new = ensure_browser(
                headless=False, force_relogin=False)
            collector = XhsCollector(page)
            convs = collector.list_conversations()
            self._emit("log", msg=f"   抓到 {len(convs)} 个会话")
            # 把 convs 转成纯 dict 方便主线程渲染
            items = [
                {
                    "uid": c.uid,
                    "name": c.name or "(未命名)",
                    "preview": c.last_msg_preview,
                    "last_time": c.last_time,
                }
                for c in convs
            ]
            self._emit("list_done", items=items)
        finally:
            if browser and pw:
                try:
                    close_browser(pw, browser)
                except Exception:
                    pass

    def _do_export(self) -> None:
        """完整 pipeline。kwargs 里塞好了 PipelineOptions 所有参数。"""
        opts = self.kwargs["opts"]  # PipelineOptions 实例
        opts.logger = lambda m: self._emit("log", msg=m)
        def _prog(cur, total, label):
            self._emit("progress", current=cur, total=total, label=label)
        opts.progress_cb = _prog
        res = run_pipeline(opts)
        self._emit("export_done", result=res)


# —— GUI 主窗口 ——

class XhsExporterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("980x700")
        self.minsize(880, 620)

        self._worker: Optional[GuiWorker] = None
        self._poll_id: Optional[str] = None  # after() 返回的 id
        self._list_items: List[dict] = []    # 原始会话列表（搜索用）
        self._selected_uids: List[str] = []  # 多选后导出用
        self._outdir_var = tk.StringVar(value=str(DEFAULT_OUT))
        self._scroll_var = tk.IntVar(value=DEFAULT_SCROLL_MS)
        self._formats_vars = {fmt: tk.BooleanVar(value=(fmt != "csv"))
                              for fmt in ("md", "html", "json", "csv")}
        self._no_media_var = tk.BooleanVar(value=False)
        self._login_status_var = tk.StringVar()

        self._build()
        self._refresh_login_badge()

    # —— UI 构建 ——

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 6}

        # 顶栏：状态 + 操作
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Label(top, text=f"{APP_NAME} v{APP_VERSION}",
                  font=("-size", 14, "-weight", "bold")).pack(side="left")

        self._login_badge = ttk.Label(top, textvariable=self._login_status_var,
                                      foreground="#ff2442")
        self._login_badge.pack(side="left", padx=10)

        ttk.Button(top, text="启动浏览器 / 登录",
                   command=self._on_login).pack(side="right", padx=3)
        ttk.Button(top, text="刷新会话列表",
                   command=self._on_refresh_list).pack(side="right", padx=3)

        # 主体：左侧会话列表 + 右侧设置
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # —— 左：会话列表 ——
        left = ttk.Frame(body)
        body.add(left, weight=3)

        ttk.Label(left, text="📋 会话列表（Ctrl/Shift 多选）").pack(anchor="w")

        search_row = ttk.Frame(left)
        search_row.pack(fill="x", pady=(2, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_list())
        ttk.Entry(search_row, textvariable=self._search_var).pack(side="left", fill="x", expand=True)
        ttk.Button(search_row, text="搜索", width=6,
                   command=self._filter_list).pack(side="left", padx=2)
        ttk.Button(search_row, text="全选", width=6,
                   command=lambda: self._set_all(True)).pack(side="left", padx=2)
        ttk.Button(search_row, text="全不选", width=6,
                   command=lambda: self._set_all(False)).pack(side="left", padx=2)

        # Treeview 多列：勾选 + 昵称 + 最后一条消息 + uid
        cols = ("_sel", "name", "preview", "last_time", "uid")
        self._tv = ttk.Treeview(left, columns=cols, show="headings",
                                selectmode="extended", height=14)
        self._tv.heading("_sel", text="")
        self._tv.heading("name", text="昵称")
        self._tv.heading("preview", text="最后消息")
        self._tv.heading("last_time", text="最后活跃")
        self._tv.heading("uid", text="UID")
        self._tv.column("_sel", width=30, anchor="center", stretch=False)
        self._tv.column("name", width=130)
        self._tv.column("preview", width=280)
        self._tv.column("last_time", width=110, anchor="center")
        self._tv.column("uid", width=130)
        self._tv.bind("<Double-1>", self._on_tv_toggle)
        self._tv.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self._tv.yview)
        scrollbar.place(relx=1.0, rely=0, relheight=1, anchor="ne")
        self._tv.configure(yscrollcommand=scrollbar.set)

        self._count_var = tk.StringVar(value="已选 0 / 0")
        ttk.Label(left, textvariable=self._count_var, foreground="#666").pack(anchor="w", pady=2)

        # —— 右：设置 + 执行 ——
        right = ttk.Frame(body)
        body.add(right, weight=2)

        ttk.Label(right, text="⚙️ 导出设置").pack(anchor="w")

        # 导出目录
        out_row = ttk.Frame(right)
        out_row.pack(fill="x", pady=(2, 4))
        ttk.Label(out_row, text="导出目录").pack(side="left")
        ttk.Entry(out_row, textvariable=self._outdir_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(out_row, text="浏览…", command=self._pick_outdir).pack(side="left")

        # 滚动时长
        srow = ttk.Frame(right)
        srow.pack(fill="x", pady=4)
        ttk.Label(srow, text="滚动加载时长").pack(side="left")
        ttk.Spinbox(srow, from_=10000, to=180000, increment=5000, width=8,
                    textvariable=self._scroll_var).pack(side="left", padx=4)
        ttk.Label(srow, text="毫秒").pack(side="left")

        # 格式勾选
        fmt_box = ttk.LabelFrame(right, text="导出格式")
        fmt_box.pack(fill="x", pady=6)
        for fmt, label in [("md", "Markdown"), ("html", "HTML 气泡"),
                           ("json", "原始 JSON"), ("csv", "CSV 表格")]:
            ttk.Checkbutton(fmt_box, text=label, variable=self._formats_vars[fmt]).pack(anchor="w", padx=6)

        # 媒体
        ttk.Checkbutton(right, text="不下载媒体（语音/图片/视频）",
                        variable=self._no_media_var).pack(anchor="w", pady=2)

        # 开始导出
        self._export_btn = ttk.Button(right, text="🚀 开始导出", command=self._on_export)
        self._export_btn.pack(fill="x", pady=(10, 4))

        self._progress = ttk.Progressbar(right, mode="determinate")
        self._progress.pack(fill="x", pady=2)
        self._progress_label = ttk.Label(right, text="", foreground="#666")
        self._progress_label.pack(anchor="w")

        # 打开导出目录按钮（完成后激活）
        self._open_btn = ttk.Button(right, text="📂 打开导出目录",
                                    command=self._open_outdir, state="disabled")
        self._open_btn.pack(fill="x", pady=(6, 4))

        # —— 底部：日志 ——
        bottom = ttk.LabelFrame(self, text="📝 日志")
        bottom.pack(fill="both", expand=False, padx=8, pady=4)
        self._log = tk.Text(bottom, height=10, wrap="word", state="disabled",
                            font=("-family", "Menlo", "-size", 11))
        self._log.pack(fill="both", expand=True, side="left")
        lsb = ttk.Scrollbar(bottom, orient="vertical", command=self._log.yview)
        lsb.pack(side="right", fill="y")
        self._log.configure(yscrollcommand=lsb.set)

    # —— 事件处理 ——

    def _pick_outdir(self) -> None:
        d = filedialog.askdirectory(initialdir=self._outdir_var.get() or str(Path.home()),
                                    title="选择导出目录")
        if d:
            self._outdir_var.set(d)

    def _refresh_login_badge(self) -> None:
        if _state_exists():
            self._login_status_var.set("🟢 已登录（点「刷新会话列表」）")
            self._login_badge.configure(foreground="#16a34a")
        else:
            self._login_status_var.set("🔴 未登录（点「启动浏览器 / 登录」）")
            self._login_badge.configure(foreground="#ff2442")

    def _set_all(self, v: bool) -> None:
        for item_id in self._tv.get_children():
            self._tv.set(item_id, "_sel", "✓" if v else "")

    def _filter_list(self) -> None:
        q = self._search_var.get().strip().lower()
        self._render_list(
            [it for it in self._list_items
             if not q or q in (it.get("name", "") + it.get("preview", "") + it.get("uid", "")).lower()]
        )

    def _render_list(self, items: List[dict]) -> None:
        self._tv.delete(*self._tv.get_children())
        for idx, it in enumerate(items):
            self._tv.insert("", "end", iid=str(idx),
                            values=("", it.get("name", ""), it.get("preview", ""),
                                    it.get("last_time", ""), it.get("uid", "")))
        self._count_var.set(f"已选 0 / {len(items)}")

    def _on_tv_toggle(self, event) -> None:
        """双击行：勾选/取消勾选（不影响 Treeview 的 extended 选择）。"""
        sel = self._tv.selection()
        for iid in sel:
            cur = self._tv.set(iid, "_sel")
            self._tv.set(iid, "_sel", "" if cur == "✓" else "✓")
        self._update_selected_count()

    def _on_login(self) -> None:
        self._start_worker("refresh_login", relogin=False)

    def _on_refresh_list(self) -> None:
        self._start_worker("list")

    def _on_export(self) -> None:
        # 收勾选里的 uid
        uids: List[str] = []
        for iid in self._tv.get_children():
            if self._tv.set(iid, "_sel") == "✓":
                uid = self._tv.item(iid)["values"][4]
                if uid:
                    uids.append(uid)

        if not uids:
            messagebox.showwarning("提示", "请先勾选至少一个会话（也可以先点「刷新会话列表」）。")
            return

        formats = [f for f, v in self._formats_vars.items() if v.get()]
        if not formats:
            messagebox.showwarning("提示", "至少勾选一种导出格式。")
            return

        outdir = Path(self._outdir_var.get()).expanduser()
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("导出目录不可用", str(e))
            return

        opts = PipelineOptions(
            outdir=outdir,
            chat_user_ids=uids,
            formats=formats,
            download_media=not self._no_media_var.get(),
            scroll_ms=int(self._scroll_var.get() or DEFAULT_SCROLL_MS),
            headless=False,
        )
        self._start_worker("export", opts=opts)

    # —— worker 通信 ——

    def _start_worker(self, action: str, **kwargs) -> None:
        # 禁用按钮 + 重置进度
        self._export_btn.configure(state="disabled")
        self._open_btn.configure(state="disabled")
        self._progress.configure(value=0, maximum=1)
        self._progress_label.configure(text="")
        self._worker = GuiWorker(action, **kwargs)
        self._worker.start()
        self._log_msg(f"▶️ 开始：{action}")
        self._poll_queue()

    def _poll_queue(self) -> None:
        """每 100ms 轮询一次 worker 的结果队列，把事件转到 UI 线程。"""
        if not self._worker or not self._worker.is_alive():
            return
        try:
            while True:
                kind, payload = self._worker.result_q.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self._poll_id = self.after(100, self._poll_queue)

    def _handle_event(self, kind: str, payload: dict) -> None:
        if kind == "log":
            self._log_msg(payload["msg"])
        elif kind == "progress":
            cur = payload["current"]
            total = max(1, payload["total"])
            self._progress.configure(maximum=total, value=cur)
            self._progress_label.configure(text=payload["label"])
        elif kind == "login_done":
            self._refresh_login_badge()
            self._log_msg("✅ 浏览器已关闭。现在可以点「刷新会话列表」或「开始导出」。")
        elif kind == "list_done":
            self._list_items = payload["items"]
            self._render_list(self._list_items)
            self._refresh_login_badge()
            self._log_msg(f"✅ 会话列表已刷新：{len(self._list_items)} 个。"
                          f"（双击行 = 勾选/取消；Ctrl/Cmd + 点击 = Treeview 多选）")
        elif kind == "export_done":
            res = payload["result"]
            self._log_msg(f"\n{'='*40}\n📊 完成！成功 {res.ok_count} / "
                          f"{res.ok_count + len(res.failures)} 个会话。")
            self._export_btn.configure(state="normal")
            if res.exported_paths:
                self._open_btn.configure(state="normal")
                self._last_export_dir = res.exported_paths[0]  # 第一个会话的目录
                self._log_msg(f"📂 最新目录：{self._last_export_dir}")
            if res.failures:
                self._log_msg("⚠️ 有失败：" +
                              "; ".join(f"{u}: {r[:40]}" for u, r in res.failures[:5]))
        elif kind == "error":
            self._log_msg(f"\n❌ 出错了：{payload}")
            messagebox.showerror("出错了", str(payload)[:300])
            self._export_btn.configure(state="normal")

    def _log_msg(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
        # 顺便更选中计数
        try:
            sel = [iid for iid in self._tv.get_children()
                   if self._tv.set(iid, "_sel") == "✓"]
            self._count_var.set(f"已选 {len(sel)} / {len(self._tv.get_children())}")
        except Exception:
            pass

    def _open_outdir(self) -> None:
        d = self._outdir_var.get()
        if not d or not Path(d).exists():
            messagebox.showinfo("提示", "导出目录不存在。")
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", d])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showerror("打不开目录", str(e))


def main() -> int:
    app = XhsExporterApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
