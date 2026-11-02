# -*- coding: utf-8 -*-
"""媒体下载（语音 / 图片 / 视频 / 表情 / 笔记封面）。

精简自参考实现：
- 不强制 ffmpeg（可选）；
- 只用 requests，降低依赖门槛；
- best-effort，单条失败不影响整体。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import requests


UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Referer": "https://www.xiaohongshu.com/",
}

_SAFE = re.compile(r"[^\w\u4e00-\u9fff.-]")


def _safe(name: str) -> str:
    return _SAFE.sub("_", str(name)).strip("_") or "media"


def _detect_ext(url: str, sample_header: Optional[bytes] = None, default: str = ".bin") -> str:
    """优先看 URL 后缀，兜底看文件头 magic number。"""
    m = re.search(r"\.(mp4|m4a|aac|jpg|jpeg|webp|png|mp3|gif)(?:\?|$)", url.lower())
    if m:
        return "." + m.group(1)
    if url.lower().find("format/jpg") > 0:
        return ".jpg"
    if sample_header:
        head = sample_header[:12]
        if head[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
        if head[:2] == b"\xff\xd8": return ".jpg"
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return ".webp"
        if head[:4] == b"\x00\x00\x00\x18" and head[4:8] == b"ftyp": return ".mp4"
        if head[:4] == b"ftyp": return ".mp4"
        if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3"): return ".mp3"
        if head[:3] == b"GIF": return ".gif"
    return default


def download_one(url: str, dest: Path, timeout: int = 30) -> Optional[Path]:
    """下载单个文件，自动识别扩展名。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, headers=UA, timeout=timeout, stream=True)
        r.raise_for_status()
        # 先用临时名写，识别完后缀再重命名
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            header = None
            for chunk in r.iter_content(chunk_size=1 << 15):
                if chunk:
                    f.write(chunk)
                    if header is None:
                        header = chunk[:12]
        ext = _detect_ext(url, header)
        final = tmp.with_suffix(ext)
        tmp.rename(final)
        return final
    except Exception as e:
        # 清理 part 文件
        try:
            tmp = dest.with_suffix(dest.suffix + ".part")
            if tmp.exists(): tmp.unlink()
        except Exception:
            pass
        raise e


def download_manifest(media_list: List[Dict], outdir: Path, delay: float = 0.1) -> Tuple[int, List[Tuple[str, str]]]:
    """批量下载。media_list 格式：[{store_id, kind, url, sender?, time?, duration_ms?}]。

    Returns: (成功数, 失败列表 [(store_id, reason)])
    """
    kind_subdir = {
        "voice": "voice", "image": "image", "video": "video",
        "emoji": "emoji", "note": "note",
    }
    ok = 0
    failed: List[Tuple[str, str]] = []

    for item in media_list:
        sid = str(item.get("store_id") or "")
        kind = item.get("kind", "media")
        url = item.get("url") or ""
        if not url:
            failed.append((sid, "no url"))
            continue
        sub = kind_subdir.get(kind, "media")
        folder = outdir / sub
        folder.mkdir(parents=True, exist_ok=True)

        who = _safe(item.get("sender") or "user")
        dur = item.get("duration_ms") or 0
        base = f"{sid}_{who}"
        if kind == "voice":
            base += f"_{dur/1000:.1f}s"
        dest = folder / base

        try:
            # 跳过已下载
            if dest.with_suffix(dest.suffix + ".part").exists():
                dest.with_suffix(dest.suffix + ".part").unlink()
            if any(p.name.startswith(base) for p in folder.iterdir()):
                ok += 1
                continue
            download_one(url, dest)
            ok += 1
        except Exception as e:
            failed.append((sid, str(e)[:80]))

        if delay:
            time.sleep(delay)

    return ok, failed
