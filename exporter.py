# -*- coding: utf-8 -*-
"""导出器：解析 + 生成 JSON / Markdown / HTML。

消息解析逻辑基于参考实现，覆盖 content_type 0/1/2/3/4/9/10/11/13/16/17；
HTML 模板做了精简（去掉日期跳转等花哨交互，优先稳定可读）；
新增 Markdown 纯文本导出，方便放到任何笔记软件里。
"""
from __future__ import annotations

import csv
import datetime
import html as html_mod
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import TYPE_LABELS


# —— 消息解析 ——

def _unwrap(v: Any) -> Any:
    """反复把 JSON-string 类型的值 parse 成对象。"""
    out = v
    for _ in range(3):
        if isinstance(out, str) and out.strip().startswith(("{", "[", '"')):
            try:
                out = json.loads(out)
            except Exception:
                break
        else:
            break
    return out


def _clean_text(t: Any) -> str:
    if not isinstance(t, str):
        return ""
    t = t.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        t = t[1:-1]
    return t


def _note_web_url(link: str, note_id: str) -> str:
    import urllib.parse as _up
    if not link:
        return ""
    nid = note_id
    token = ""
    if not nid:
        m = re.search(r"item[/:]([0-9a-fA-F]+)", link)
        nid = m.group(1) if m else ""
    q = _up.parse_qs(_up.urlparse(link).query)
    token = q.get("xsec_token", [""])[0]
    if not nid:
        return ""
    base = f"https://www.xiaohongshu.com/explore/{nid}"
    params = {"xsec_source": "pc"}
    if token:
        params["xsec_token"] = token
    return base + "?" + _up.urlencode(params)


def parse_message(m: Dict[str, Any]) -> Dict[str, Any]:
    """返回结构化的消息字段，对 content_type 做 best-effort 覆盖。"""
    c = _unwrap(m.get("content") or "{}")
    c = c if isinstance(c, dict) else {}
    ct = c.get("content_type") or m.get("content_type") or 0
    content = c.get("content", "")
    d = _unwrap(content)
    d = d if isinstance(d, dict) else {}
    link = ""
    text = content if isinstance(content, str) else str(content)
    emoji_img = ""
    note_title = note_cover = note_type = note_nickname = note_avatar = note_id = note_web_url = ""

    if ct == 1:
        obj = _unwrap(content)
        if isinstance(obj, dict):
            text = obj.get("content", "") or obj.get("front_chain", "") or ""
        else:
            text = str(content)
    elif ct == 2:
        text = "[图片]"
        link = (d.get("imageDataMap", {}).get("IM_ORG", {}) or {}).get("url") or d.get("link", "")
    elif ct == 3:
        text = "[笔记] " + _clean_text(d.get("title", ""))
        link = d.get("link", "")
        note_title = _clean_text(d.get("title", ""))
        note_cover = d.get("image") or d.get("cover", "")
        note_type = d.get("noteType", "")
        author = d.get("user", {}) or {}
        note_nickname = author.get("nickname", "")
        note_avatar = author.get("image", "")
        note_id = d.get("id", "")
        note_web_url = _note_web_url(link, note_id)
    elif ct == 9:
        text = "[语音]"
        link = d.get("link", "")
    elif ct == 11:
        text = "[视频]"
        link = d.get("videoLink", "") or ((d.get("imageDataMap", {}).get("IM_ORG", {}) or {}).get("url", ""))
    elif ct in (13, 16):
        text = "[表情]"
        emoji_img = d.get("url", "") or d.get("image", "")
    elif ct == 0:
        inner = d.get("content", "")
        text = _clean_text(inner) or "[空消息]"
    elif ct == 4:
        inner = d.get("content", "")
        text = _clean_text(inner) or "[系统消息]"
        text = re.sub(r'"(.*?)"撤回', r"\1 撤回", text)
    elif ct == 10:
        text = _clean_text(d.get("content", "")) or "[提示]"
    elif ct == 17:
        call_type = d.get("streamType")
        prefix = {0: "语音通话", 1: "视频通话"}.get(call_type, "通话")
        text = _clean_text(d.get("senderContent", "")) or ""
        text = f"[{prefix}] {text}".strip()
    else:
        text = str(content) if isinstance(content, str) else f"[未知类型 {ct}]"

    # 引用消息
    ref = m.get("ref_message") or {}
    ref_store_id = ref.get("store_id")
    ref_nickname = ref.get("nickname", "")
    ref_text = ""
    if ref:
        rc = _unwrap(ref.get("content") or "{}")
        rc = rc if isinstance(rc, dict) else {}
        cand = rc.get("content")
        if isinstance(cand, str):
            co = _unwrap(cand)
            if isinstance(co, dict):
                cand = co.get("title") or co.get("frontChain") or co.get("content") or cand
        else:
            cand = rc.get("front_chain")
        ref_text = _clean_text(cand) if isinstance(cand, str) else ""

    return {
        "store_id": m.get("store_id"),
        "sender_id": m.get("sender_id"),
        "receiver_id": m.get("receiver_id"),
        "time": m.get("created_at"),
        "type": ct,
        "type_label": TYPE_LABELS.get(ct, f"类型{ct}"),
        "text": text,
        "link": link,
        "emoji_img": emoji_img,
        "duration_ms": d.get("duration"),
        "revoked": bool(m.get("revoked")),
        "note_title": note_title,
        "note_cover": note_cover,
        "note_type": note_type,
        "note_nickname": note_nickname,
        "note_avatar": note_avatar,
        "note_id": note_id,
        "note_web_url": note_web_url,
        "ref_store_id": ref_store_id,
        "ref_nickname": ref_nickname,
        "ref_text": ref_text,
    }


def fmt_time(ts: Any) -> str:
    if not ts:
        return ""
    try:
        return datetime.datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


# —— 识别"我"与"对方" ——

def identify_me_and_he(messages: List[Dict[str, Any]], chat_user_id: str
                       ) -> Tuple[str, str]:
    """chat_user_id 是对方，剩下那个高频 receiver 是自己。"""
    sid = set()
    for m in messages:
        sid.add(m.get("sender_id"))
        sid.add(m.get("receiver_id"))
    others = sid - {chat_user_id, None}
    if len(others) == 1:
        return next(iter(others)), chat_user_id
    # 兜底：receiver 出现次数最多的那个通常是"我"
    from collections import Counter
    recv = Counter(m.get("receiver_id") for m in messages if m.get("receiver_id"))
    me_id = recv.most_common(1)[0][0] if recv else ""
    return me_id, chat_user_id


def who(sid: Any, me_id: str, he_id: str, me_name: str, he_name: str) -> str:
    if sid == me_id: return me_name
    if sid == he_id: return he_name
    return str(sid or "?")[:12]


# —— 扫描已下载的媒体文件 ——

def scan_media_files(outdir: Path) -> Dict[str, Dict[str, str]]:
    """返回 {store_id: {kind: 相对路径}}。kind ∈ {audio,image,video,emoji,note}"""
    mapping: Dict[str, Dict[str, str]] = {}
    sub_kinds = {"voice": "audio", "image": "image", "video": "video", "emoji": "emoji", "note": "note"}
    for sub, kind in sub_kinds.items():
        d = outdir / sub
        if not d.is_dir():
            continue
        for fn in os.listdir(d):
            m = re.match(r"(\d+)_", fn)
            if not m:
                continue
            sid = m.group(1)
            mapping.setdefault(sid, {})[kind] = f"{sub}/{fn}"
    return mapping


# —— Markdown ——

def build_markdown(messages: List[Dict[str, Any]], parsed: List[Dict[str, Any]],
                   me_id: str, he_id: str, me_name: str, he_name: str,
                   outdir: Path) -> Path:
    """生成可读的 Markdown 文件，段落按日期分隔。"""
    media_map = scan_media_files(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    md_path = outdir / "chat.md"

    lines = []
    lines.append(f"# 小红书聊天记录（{me_name} ↔ {he_name}）")
    lines.append("")
    oldest = next((fmt_time(p["time"]) for p in parsed if p["time"]), "")
    newest = next((fmt_time(p["time"]) for p in reversed(parsed) if p["time"]), "")
    lines.append(f"- 消息总数：{len(parsed)}")
    lines.append(f"- 时间范围：{oldest} ~ {newest}")
    lines.append(f"- 导出时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    prev_date = None
    for p in parsed:
        dk = fmt_time(p["time"])[:10] if p["time"] else ""
        if dk and dk != prev_date:
            prev_date = dk
            lines.append(f"## {dk}")
            lines.append("")

        sender = who(p["sender_id"], me_id, he_id, me_name, he_name)
        ts = fmt_time(p["time"])
        lines.append(f"**{sender}** · `{ts}`  *({p['type_label']})*")

        # 引用
        if p["ref_text"]:
            rnick = p["ref_nickname"] or ""
            lines.append(f"> 引用 {rnick}：{p['ref_text']}")

        mf = media_map.get(str(p["store_id"]), {})
        text_body = p["text"]

        # 各类媒体
        if "audio" in mf:
            dur = (p.get("duration_ms") or 0) / 1000.0
            lines.append(f"- 🔊 语音 {dur:.1f}s: [{mf['audio']}]({mf['audio']})")
        elif p["type"] == 9 and p["link"]:
            text_body = f"{text_body} （音频未下载）"

        if "image" in mf:
            lines.append(f"- 🖼️ 图片: ![]({mf['image']})")
        elif p["type"] == 2 and p["link"]:
            lines.append(f"- 🖼️ 图片源: {p['link']}")

        if "video" in mf:
            lines.append(f"- 🎬 视频: [{mf['video']}]({mf['video']})")

        if "emoji" in mf:
            lines.append(f"- 😀 表情: ![]({mf['emoji']})")
        elif p.get("emoji_img"):
            lines.append(f"- 😀 表情源: {p['emoji_img']}")

        if p["type"] == 3 and (p["note_title"] or p["note_web_url"] or p["link"]):
            title = p["note_title"] or "分享的笔记"
            url = p["note_web_url"] or p["link"] or ""
            cover = mf.get("note", "") or p["note_cover"]
            link_md = f"[打开笔记]({url})" if url else ""
            cover_md = f"![]({cover}) " if cover and not url.startswith("xhsdiscover") else ""
            lines.append(f"- 📄 笔记分享: {cover_md}**{title}** {link_md}")

        # 正文
        if text_body and text_body not in ("[空消息]", "[消息]", "[消息] 点击查看"):
            lines.append("")
            for t in str(text_body).split("\n"):
                lines.append(f"> {t}")

        if p["revoked"]:
            lines.append("")
            lines.append("> ↩️ 该消息已被撤回")

        lines.append("")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


# —— HTML ——

_HTML_TEMPLATE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>小红书聊天记录导出</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC',Roboto,sans-serif;max-width:820px;margin:0 auto;padding:20px 24px 60px;background:#f5f5f7;color:#1f1f1f}
h1{font-size:22px;margin:10px 0 4px} .summary{color:#666;font-size:13px;margin:0 0 18px;line-height:1.6}
.date-divider{display:flex;align-items:center;gap:12px;margin:22px 0 12px;color:#999;font-size:12px}
.date-divider::before,.date-divider::after{content:"";flex:1;height:1px;background:rgba(0,0,0,.06)}
.date-divider span{background:#e8e8ee;padding:3px 12px;border-radius:20px;font-weight:600;color:#555}
.row{display:flex;flex-direction:column;margin-bottom:14px}
.row .meta{font-size:11px;color:#999;margin-bottom:4px}
.row .bubble{padding:10px 14px;border-radius:15px;line-height:1.7;font-size:14px;max-width:82%;word-break:break-word}
.row.me{align-items:flex-end} .row.me .bubble{background:#6c5ce7;color:#fff;border-top-right-radius:4px}
.row.them{align-items:flex-start} .row.them .bubble{background:#fff;border-top-left-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.bubble .tag{font-size:10px;opacity:.55;margin-top:6px}
.media{margin-top:8px}
.media img{max-width:260px;max-height:340px;border-radius:10px;display:block}
.media video{max-width:300px;max-height:400px;border-radius:10px;display:block;background:#000}
.media audio{max-width:290px;height:34px;vertical-align:middle}
.ref-card{display:flex;flex-direction:column;gap:1px;margin-bottom:8px;padding:6px 10px;background:rgba(0,0,0,.05);border-left:3px solid #ff2442;border-radius:6px;text-decoration:none;color:inherit;font-size:13px;max-width:100%}
.row.me .ref-card{background:rgba(0,0,0,.18);border-left-color:rgba(255,255,255,.7)}
.ref-nick{font-size:11px;color:#ff2442;font-weight:600}
.row.me .ref-nick{color:#ffd6a0}
.ref-text{color:#555;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.row.me .ref-text{color:#eee}
.note-card{display:flex;gap:12px;margin-top:8px;background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:12px;overflow:hidden;max-width:340px;padding:10px;text-decoration:none;color:inherit}
.row.me .note-card{background:#8f85ef;border-color:rgba(255,255,255,.25)}
.note-cover{flex:0 0 92px;width:92px;height:92px;border-radius:8px;overflow:hidden;background:#eee}
.note-cover img{width:100%;height:100%;object-fit:cover;display:block}
.note-body{flex:1;display:flex;flex-direction:column;gap:3px;min-width:0;text-align:left}
.note-title{font-size:13px;font-weight:600;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;color:#222}
.row.me .note-title{color:#fff}
.note-link{font-size:12px;color:#ff2442;font-weight:600;margin-top:2px;text-decoration:none}
.row.me .note-link{color:#fff}
.empty-msg{margin-top:4px;padding:8px 10px;background:rgba(0,0,0,.04);border-radius:8px;color:#999;font-size:12px;text-align:center}
.revoked{font-size:12px;color:#aaa;font-style:italic;margin-top:2px}
.undl{font-size:12px;opacity:.6}
</style></head><body>
<h1>小红书聊天记录导出</h1>
<div class="summary">共 __COUNT__ 条 · __OLDEST__ ~ __NEWEST__ · 生成于 __GEN__</div>
__ROWS__
</body></html>"""


def build_html(messages: List[Dict[str, Any]], parsed: List[Dict[str, Any]],
               me_id: str, he_id: str, me_name: str, he_name: str,
               outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    media_map = scan_media_files(outdir)
    by_store = {p["store_id"]: p for p in parsed}

    prev_date = None
    rows = []

    for p in parsed:
        dk = fmt_time(p["time"])[:10] if p["time"] else ""
        if dk and dk != prev_date:
            prev_date = dk
            label = datetime.datetime.strptime(dk, "%Y-%m-%d").strftime("%Y年%m月%d日")
            rows.append(f'<div class="date-divider"><span>{label}</span></div>')

        sender = who(p["sender_id"], me_id, he_id, me_name, he_name)
        cls = "me" if p["sender_id"] == me_id else "them"

        content_html_parts = []

        # 引用卡片
        if p["ref_store_id"] is not None and p["ref_store_id"] in by_store:
            rp = by_store[p["ref_store_id"]]
            rtext = html_mod.escape((rp.get("text") or rp.get("note_title") or "")[:60]).replace("\n", " ")
            rnick = html_mod.escape(p.get("ref_nickname") or who(rp["sender_id"], me_id, he_id, me_name, he_name))
            content_html_parts.append(
                f'<div class="ref-card"><span class="ref-nick">{rnick}</span>'
                f'<span class="ref-text">{rtext}</span></div>'
            )

        # 媒体
        sid = str(p["store_id"])
        mf = media_map.get(sid, {})
        if "audio" in mf:
            dur = (p.get("duration_ms") or 0) / 1000.0
            content_html_parts.append(
                f'<div class="media"><audio controls preload="none" src="{html_mod.escape(mf["audio"])}"></audio>'
                f'<span class="undl">🔊 {dur:.1f}s</span></div>'
            )
        if "image" in mf:
            content_html_parts.append(
                f'<div class="media"><img src="{html_mod.escape(mf["image"])}" alt="图片"></div>'
            )
        if "video" in mf:
            content_html_parts.append(
                f'<div class="media"><video controls preload="none" src="{html_mod.escape(mf["video"])}"></video></div>'
            )
        if "emoji" in mf:
            content_html_parts.append(
                f'<div class="media"><img src="{html_mod.escape(mf["emoji"])}" alt="表情" style="width:72px;height:72px"></div>'
            )
        elif p.get("emoji_img"):
            content_html_parts.append(
                f'<div class="media"><img src="{html_mod.escape(p["emoji_img"])}" alt="表情" style="width:72px;height:72px"></div>'
            )
        # 笔记
        if p["type"] == 3 and (p["note_title"] or p["note_web_url"] or p["link"]):
            ntitle = html_mod.escape(p["note_title"] or "分享的笔记")
            ncover = html_mod.escape(mf.get("note", "") or p["note_cover"])
            nlink = html_mod.escape(p["note_web_url"] or p["link"] or "")
            cover_html = f'<div class="note-cover"><img src="{ncover}" alt="封面" onerror="this.style.display=\'none\'"></div>' if ncover else '<div class="note-cover"></div>'
            link_tag = f'<a class="note-link" href="{nlink}" target="_blank">↗ 打开笔记</a>' if nlink else ""
            card_inner = f'{cover_html}<div class="note-body"><div class="note-title">{ntitle}</div>{link_tag}</div>'
            card_tag = "a" if nlink else "div"
            card_class = "note-card" + ("" if nlink else "")
            content_html_parts.append(f'<{card_tag} class="{card_class}" href="{nlink}" target="_blank">{card_inner}</{card_tag}>' if nlink else f'<div class="note-card">{card_inner}</div>')

        # 正文
        raw_text = str(p["text"] or "").strip()
        is_empty = raw_text in ("", "[空消息]", "[消息]", "[消息] 点击查看")
        if not is_empty:
            text_html = html_mod.escape(raw_text).replace("\n", "<br>")
            content_html_parts.insert(0, f'<div class="msg-text" style="white-space:pre-wrap">{text_html}</div>')
        elif not content_html_parts:
            content_html_parts.append('<div class="empty-msg">💬 这条消息暂不可见</div>')

        if p["revoked"]:
            content_html_parts.append('<div class="revoked">↩️ 该消息已被撤回</div>')

        bubble = f'<div class="bubble">{"".join(content_html_parts)}<div class="tag">{p["type_label"]}</div></div>'
        rows.append(
            f'<div class="row {cls}"><div class="meta">[{p["store_id"]}] {sender} · {fmt_time(p["time"])}</div>{bubble}</div>'
        )

    oldest = next((fmt_time(p["time"])[:10] for p in parsed if p["time"]), "")
    newest = next((fmt_time(p["time"])[:10] for p in reversed(parsed) if p["time"]), "")
    html_out = (_HTML_TEMPLATE
                .replace("__COUNT__", str(len(parsed)))
                .replace("__OLDEST__", oldest)
                .replace("__NEWEST__", newest)
                .replace("__GEN__", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
                .replace("__ROWS__", "\n".join(rows)))
    html_path = outdir / "chat.html"
    html_path.write_text(html_out, encoding="utf-8")
    return html_path


# —— 媒体 manifest（给下载器用） ——

def build_media_manifest(parsed: List[Dict[str, Any]], me_id: str, he_id: str,
                         me_name: str, he_name: str) -> List[Dict[str, Any]]:
    media = []
    for p in parsed:
        if p["type"] == 9 and p["link"]:
            media.append({"store_id": p["store_id"], "kind": "voice", "url": p["link"],
                          "duration_ms": p.get("duration_ms") or 0,
                          "sender": who(p["sender_id"], me_id, he_id, me_name, he_name),
                          "time": fmt_time(p["time"])})
        if p["type"] == 2 and p["link"]:
            media.append({"store_id": p["store_id"], "kind": "image", "url": p["link"],
                          "sender": who(p["sender_id"], me_id, he_id, me_name, he_name),
                          "time": fmt_time(p["time"])})
        if p["type"] == 11 and p["link"]:
            media.append({"store_id": p["store_id"], "kind": "video", "url": p["link"],
                          "sender": who(p["sender_id"], me_id, he_id, me_name, he_name),
                          "time": fmt_time(p["time"])})
        if p["type"] in (13, 16) and p.get("emoji_img"):
            media.append({"store_id": p["store_id"], "kind": "emoji", "url": p["emoji_img"],
                          "sender": who(p["sender_id"], me_id, he_id, me_name, he_name),
                          "time": fmt_time(p["time"])})
        if p["type"] == 3 and p.get("note_cover"):
            media.append({"store_id": p["store_id"], "kind": "note", "url": p["note_cover"],
                          "sender": who(p["sender_id"], me_id, he_id, me_name, he_name),
                          "time": fmt_time(p["time"]), "title": p["note_title"]})
    return media


# —— CSV ——

def build_csv(parsed: List[Dict[str, Any]], me_id: str, he_id: str,
              me_name: str, he_name: str, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "chat.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["store_id", "发送者", "时间", "类型", "内容"])
        for p in parsed:
            w.writerow([p["store_id"], who(p["sender_id"], me_id, he_id, me_name, he_name),
                        fmt_time(p["time"]), p["type_label"], str(p["text"])])
    return path


# —— 统一入口 ——

def export_all(raw_messages: List[Dict[str, Any]], chat_user_id: str,
               outdir: Path, me_name: str = "我", he_name: str = "对方",
               download_media: bool = True, formats: Optional[List[str]] = None
               ) -> Dict[str, Any]:
    """生成所有产物。formats 默认 ['json', 'md', 'html', 'csv']。"""
    if formats is None:
        formats = ["json", "md", "html", "csv"]
    outdir.mkdir(parents=True, exist_ok=True)

    # 解析
    parsed = [parse_message(m) for m in raw_messages]
    parsed.sort(key=lambda x: x.get("store_id") or 0)

    # 识别"我"/"对方"
    me_id, he_id = identify_me_and_he(raw_messages, chat_user_id)

    # 原始 JSON
    if "json" in formats:
        (outdir / "messages.json").write_text(
            json.dumps(raw_messages, ensure_ascii=False, indent=2), encoding="utf-8")

    # 媒体清单（先写，下载器看这个）
    manifest = build_media_manifest(parsed, me_id, he_id, me_name, he_name)
    if manifest:
        (outdir / "media.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 媒体下载（先下载再生成 HTML/MD，否则它们引用不到本地文件）
    if download_media and manifest:
        import media as _media
        ok, failed = _media.download_manifest(manifest, outdir)
        if failed:
            print(f"  ⚠️ 媒体下载：成功 {ok}，失败 {len(failed)}（失败项会留空或用外链替代）")
        else:
            print(f"  📦 媒体下载完成：{ok} 个")

    results: Dict[str, Any] = {"message_count": len(parsed), "me_id": me_id, "he_id": he_id,
                                "formats": {}}
    if "md" in formats:
        results["formats"]["md"] = str(build_markdown(raw_messages, parsed, me_id, he_id, me_name, he_name, outdir))
    if "html" in formats:
        results["formats"]["html"] = str(build_html(raw_messages, parsed, me_id, he_id, me_name, he_name, outdir))
    if "csv" in formats:
        results["formats"]["csv"] = str(build_csv(parsed, me_id, he_id, me_name, he_name, outdir))

    return results
