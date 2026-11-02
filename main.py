#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书聊天记录导出（CLI 入口）。

三步走：登录 → 选对话 → 一键导出。GUI 入口见 gui.py。

示例：
  python main.py
  python main.py --relogin
  python main.py --chat-user <uid>
  python main.py --chat-user <a> --chat-user <b>   # 多选
  python main.py --all
  python main.py --out ./exports
  python main.py --formats md,json
  python main.py --no-media
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core import PipelineOptions, run_pipeline  # noqa: E402
from config import DEFAULT_OUT, DEFAULT_SCROLL_MS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="小红书聊天记录导出（CLI）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py                          # 交互式：登录 + 选会话
  python main.py --relogin                # 强制重新登录
  python main.py --chat-user <uid>        # 指定会话（可多次以多选）
  python main.py --all                    # 导出全部会话（慢）
  python main.py --out ./exports          # 导出目录
  python main.py --formats md,html        # 只要这两种格式
  python main.py --no-media               # 不下载媒体
        """,
    )
    ap.add_argument("--relogin", action="store_true", help="强制重新扫码登录")
    ap.add_argument("--chat-user", action="append", default=None, metavar="UID",
                    help="指定一个会话的对方 user_id；可多次使用以多选")
    ap.add_argument("--all", action="store_true", help="导出全部会话（慢）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="导出目录")
    ap.add_argument("--no-media", action="store_true", help="不下载媒体")
    ap.add_argument("--scroll-ms", type=int, default=DEFAULT_SCROLL_MS,
                    help="每个会话的自动滚动加载时长（毫秒），默认 45000")
    ap.add_argument("--formats", default="md,html,json,csv",
                    help="导出格式，逗号分隔：md / html / json / csv")
    ap.add_argument("--headless", action="store_true",
                    help="无头模式（不推荐，登录时看不到扫码二维码）")
    args = ap.parse_args()

    # 解析格式
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    known = {"md", "html", "json", "csv"}
    bad = [f for f in formats if f not in known]
    if bad:
        print(f"⚠️ 未知格式 {bad}，忽略。")
    formats = [f for f in formats if f in known] or ["md", "html", "json", "csv"]

    outdir = Path(args.out).expanduser().resolve()

    opts = PipelineOptions(
        outdir=outdir,
        relogin=args.relogin,
        headless=args.headless,
        scroll_ms=args.scroll_ms,
        formats=formats,
        download_media=not args.no_media,
        chat_user_ids=args.chat_user,
        export_all=args.all,
    )
    res = run_pipeline(opts)
    return 0 if res.ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
