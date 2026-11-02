# -*- coding: utf-8 -*-
"""采集器：会话列表 + 单会话完整历史。

关键思路：小红书 IM 接口请求头带动态签名，外部没法直接复刻。
所以让 Playwright 打开 SPA、自己发请求，我们在前端注入拦截器
把响应 JSON 全部抓下来。

相比参考实现（手写 WebSocket CDP）：
- 不再需要调试端口；
- 不再需要手写 CDP 协议；
- 用 Playwright sync API，代码更短、更稳。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable

from playwright.sync_api import Page, Response

from config import XHS_CHAT


# —— 注入到前端的 JS ——

_INJECT_LISTENER = r"""
() => {
  if (window.__xhsCap3) return {already:true};
  window.__xhsCap3 = { messages: [], conversations: [], lastSeq: 0 };
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;

  function tryParse(text){
    try { return JSON.parse(text); } catch(e){ return null; }
  }

  XMLHttpRequest.prototype.open = function(method, url, ...rest){
    this.__xhsUrl = url;
    this.__xhsMethod = method;
    return origOpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function(...args){
    this.addEventListener('load', () => {
      try {
        const url = String(this.__xhsUrl || '');
        const body = tryParse(this.responseText);
        if (!body) return;

        // 聊天历史
        if (/\/messages\/history|group\/messages\/history/.test(url)) {
          const list = (body.data && (body.data.out_message_list || body.data.message_list)) || [];
          for (const m of list) {
            if (m && m.store_id) {
              // 去重
              const existed = window.__xhsCap3.messages.find(x => x.store_id === m.store_id);
              if (!existed) window.__xhsCap3.messages.push(m);
            }
          }
        }

        // 会话列表（常见端点：/api/im/web/conversations 或 /api/im/web/inbox）
        if (/\/api\/im\/web\/(conversations|inbox|conversation)/.test(url)) {
          const items = (body.data && (body.data.conversations || body.data.list || body.data.items)) || [];
          if (Array.isArray(items)) {
            window.__xhsCap3.conversations = items;
          }
        }
      } catch(e) {}
    });
    return origSend.apply(this, args);
  };
  return {injected:true};
}
"""

_SCROLL_TO_LOAD = r"""
async (opts) => {
  const durationMs = (opts && opts.durationMs) || 30000;
  // 优先用小红书 IM 的消息列表容器
  const list = document.querySelector('.xhs-im-msg-list')
    || document.querySelector('[class*="msg-list"]')
    || document.querySelector('[class*="message-list"]')
    || document.querySelector('[class*="chat-list"]');
  if (!list) return {error:'nolist'};
  const t0 = Date.now();
  const prevLen = (window.__xhsCap3 && window.__xhsCap3.messages.length) || 0;
  while (Date.now() - t0 < durationMs) {
    list.scrollTop = 1;
    await new Promise(r=>setTimeout(r, 50));
    list.scrollTop = 0;
    await new Promise(r=>setTimeout(r, 120));
    // 偶尔停下来让前端发请求
    if ((Date.now()-t0) % 8000 < 1500) await new Promise(r=>setTimeout(r, 400));
  }
  const curLen = (window.__xhsCap3 && window.__xhsCap3.messages.length) || 0;
  return {scrollHeight: list.scrollHeight, prev: prevLen, cur: curLen, grew: curLen > prevLen};
}
"""

_DUMP_STATE = r"""
() => {
  const cap = window.__xhsCap3 || {messages:[], conversations:[]};
  const msgs = (cap.messages || []).filter(m => m && m.store_id);
  // 先按 store_id 去重再排序（store_id 是时间有序的 uint）
  const uniq = new Map();
  for (const m of msgs) uniq.set(m.store_id, m);
  const arr = Array.from(uniq.values()).sort((a,b)=>a.store_id-b.store_id);
  return JSON.stringify({
    count: arr.length,
    min: arr.length ? arr[0].store_id : null,
    max: arr.length ? arr[arr.length-1].store_id : null,
    messages: arr,
    conversations: cap.conversations || [],
  });
}
"""

_GET_CHAT_USER_FROM_URL = r"""
() => {
  const m = location.href.match(/\/chat\/([0-9a-fA-F]+)/);
  if (m) return m[1];
  const s = new URLSearchParams(location.search);
  return s.get('openUid') || '';
}
"""


@dataclass
class Conversation:
    """会话的基本信息（用于让用户选）。

    Attributes:
        uid: 对方用户 id；为空时需点击 DOM 再解析
        name: 昵称/备注
        avatar: 头像 URL
        last_msg_preview: 最后一条消息预览
        last_time: 最后活跃时间
        raw: 原始 JSON / DOM 条目，便于调试
    """
    uid: str = ""
    name: str = ""
    avatar: str = ""
    last_msg_preview: str = ""
    last_time: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def display(self) -> str:
        name = self.name or f"(uid:{self.uid[:10]}…)"
        return f"{name}  [{self.last_msg_preview[:30] if self.last_msg_preview else ''}]"


class XhsCollector:
    """单页采集器：一个浏览器 context + 一个 Playwright Page。"""

    def __init__(self, page: Page):
        self.page = page
        self._injected = False

    # —— 工具方法 ——

    def _eval(self, expr: str) -> Any:
        res = self.page.evaluate(expr)
        return res

    def _inject(self) -> None:
        if self._injected:
            return
        self._eval(_INJECT_LISTENER)
        self._injected = True

    def _ensure_on_chat(self) -> None:
        """停留在 /chat 页面，确保 SPA 加载完毕。"""
        try:
            if "xiaohongshu.com/chat" not in self.page.url:
                self.page.goto(XHS_CHAT, wait_until="networkidle", timeout=30000)
        except Exception:
            # networkidle 有时超时，降级到 domcontentloaded
            self.page.goto(XHS_CHAT, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2.5)

    # —— 会话列表 ——

    def list_conversations(self, max_wait_ms: int = 6000) -> List[Conversation]:
        """获取会话列表。优先用拦截到的 XHR JSON；失败则回退到 DOM 解析。"""
        self._ensure_on_chat()
        self._inject()

        # 触发前端刷新会话列表：滚动一下 / 点击一下列表区域
        time.sleep(1.0)
        try:
            self.page.evaluate("""() => {
                const item = document.querySelector('.xhs-im-conv-item, [class*="conv-item"], [class*="conversation-item"]');
                if (item) { item.scrollIntoView({block:'center'}); item.click(); }
            }""")
        except Exception:
            pass
        time.sleep(max_wait_ms / 1000.0)

        # 先看 XHR 拦截里有没有拿到完整 JSON
        raw = self._eval(_DUMP_STATE)
        if isinstance(raw, str):
            raw = json.loads(raw)

        convs: List[Dict[str, Any]] = raw.get("conversations") or []
        if convs:
            return [self._conv_from_json(c) for c in convs]

        # 回退：DOM 解析
        return self._conv_from_dom()

    def _conv_from_json(self, c: Dict[str, Any]) -> Conversation:
        """从 XHR JSON 的一条对话记录里挖字段。小红书字段名不稳定，best-effort。"""
        uid = (c.get("user_id") or c.get("uid") or c.get("target_user_id")
               or c.get("chat_user_id") or c.get("peer_id") or "")
        name = (c.get("nickname") or c.get("remark_name") or c.get("remark")
                or c.get("name") or "")
        avatar = c.get("image") or c.get("avatar") or c.get("head_img") or ""
        last = c.get("last_message") or c.get("last_msg") or {}
        preview = ""
        if isinstance(last, dict):
            preview = str(last.get("content") or last.get("text") or last.get("message") or "")
        elif isinstance(last, str):
            preview = last
        last_time = str(c.get("last_time") or c.get("update_time") or c.get("created_at") or "")
        return Conversation(uid=str(uid), name=str(name), avatar=str(avatar),
                            last_msg_preview=preview, last_time=last_time, raw=c)

    def _conv_from_dom(self) -> List[Conversation]:
        """DOM 回退：从 /chat 左侧列表里抓条目。"""
        try:
            items = self.page.evaluate("""() => {
                const nodes = document.querySelectorAll(
                    '.xhs-im-conv-item, [class*="conv-item"], [class*="conversation-item"], ' +
                    '[class*="chat-item"], [class*="item"]'
                );
                return Array.from(nodes).slice(0, 50).map((it, i) => {
                    const text = (it.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
                    // 猜 uid：点击一下看 URL 变化太侵入，这里只收集文本让用户选；
                    // 真正点击在 select_conversation 时做。
                    return {idx: i, text, uid_hint: ''};
                });
            }""")
        except Exception:
            items = []

        out = []
        for it in items:
            if isinstance(it, dict) and it.get("text"):
                out.append(Conversation(uid="", name=it["text"][:20], last_msg_preview=it["text"][:60],
                                         raw={"_dom_idx": it.get("idx")}))
        return out

    # —— 打开一个会话并采集完整历史 ——

    def open_conversation(self, chat_user_id: str) -> str:
        """打开指定会话，返回实际的 chat_user_id。"""
        # 小红书常见三种 URL 格式
        urls = [
            f"https://www.xiaohongshu.com/chat/{chat_user_id}",
            f"https://www.xiaohongshu.com/chat?openUid={chat_user_id}",
        ]
        for url in urls:
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2.0)
                got = self._eval(_GET_CHAT_USER_FROM_URL)
                if got:
                    self._inject()
                    return got
            except Exception:
                continue
        raise RuntimeError(f"打开会话失败：{chat_user_id}（可能被风控或网络问题）")

    def collect_history(self, scroll_ms: int = 45000) -> List[Dict[str, Any]]:
        """自动滚动 + 等前端把每页发回来，返回原始 messages 列表（按 store_id 升序）。"""
        self._inject()

        # 先等当前页面的第一条历史加载完
        time.sleep(1.5)

        # 分块滚动，避免单次 evaluate 超时
        chunk = 12000
        done = False
        for _ in range(0, scroll_ms, chunk):
            remaining = min(chunk, scroll_ms - 0)  # 简化：每次都滚满 chunk
            try:
                info = self._eval(f"({_SCROLL_TO_LOAD})({{durationMs:{remaining}}})")
                if isinstance(info, dict) and info.get("grew") is False and _ > 12000:
                    # 已经滚到底了
                    done = True
                    break
            except Exception as e:
                print(f"  滚动块出错（忽略）：{e}")
        if not done:
            # 最后再等一轮，确保最后一页响应被 XHR 拦截捕获
            time.sleep(2.0)

        raw = self._eval(_DUMP_STATE)
        if isinstance(raw, str):
            raw = json.loads(raw)
        return raw.get("messages") or []


def select_conversations_interactive(collector: XhsCollector,
                                     chat_user_ids_arg: Optional[List[str]] = None,
                                     chat_user_arg: Optional[str] = None,
                                     all_arg: bool = False) -> List[str]:
    """CLI 交互：列出会话让用户选（支持多选）。

    优先级：--all > --chat-user（可多次） > 交互选择。
    """
    # 如果用户直接给了 user_id，跳过列表
    if chat_user_ids_arg:
        return chat_user_ids_arg
    if chat_user_arg:
        return [chat_user_arg]

    print("\n正在加载会话列表…")
    convs = collector.list_conversations()
    if not convs:
        print("❌ 没抓到会话列表。可能原因：")
        print("  - 登录态失效 → 请用 --relogin 重登")
        print("  - 页面还没加载完 → 等一下再试")
        print("  - 小红书页面结构更新 → 脚本需要跟上（见 README）")
        return []

    print(f"\n📋 检测到 {len(convs)} 个会话：")
    for i, c in enumerate(convs):
        marker = "⭐" if not c.uid else "  "
        print(f"  [{i:>3}] {marker} {c.display()}")

    if all_arg:
        print("\n👉 已选择全部会话（⚠️ 会话多可能耗时很久）")
        # 只返回有 uid 的；没 uid 的 DOM 条目没法打开
        return [c.uid for c in convs if c.uid]

    print("\n选择方式：")
    print("  - 单个：输入序号，如 3")
    print("  - 多个：用逗号分隔，如 1,3,7")
    print("  - 范围：如 1-5")
    print("  - 全部：输入 a")
    while True:
        sel = input("请输入要导出的会话序号（Ctrl-C 退出）：").strip()
        if not sel:
            continue
        try:
            indices: List[int] = []
            for part in sel.split(","):
                part = part.strip()
                if part == "a":
                    indices = list(range(len(convs)))
                    break
                if "-" in part:
                    a, b = part.split("-", 1)
                    indices.extend(range(int(a), int(b) + 1))
                else:
                    indices.append(int(part))
            indices = [i for i in indices if 0 <= i < len(convs)]
            if indices:
                break
        except Exception:
            pass
        print("⚠️ 输入格式不对，重试。")

    chosen = []
    for i in indices:
        c = convs[i]
        if c.uid:
            chosen.append(c.uid)
        else:
            # DOM 回退的会话没有 uid → 得点进去拿到 URL 里的 uid
            print(f"\n点击第 {i} 个会话以解析 uid…")
            # 临时点击一下并抓 URL
            try:
                collector._ensure_on_chat()
                collector.page.evaluate(f"""() => {{
                    const nodes = document.querySelectorAll(
                        '.xhs-im-conv-item, [class*="conv-item"], [class*="conversation-item"], ' +
                        '[class*="chat-item"], [class*="item"]'
                    );
                    const it = nodes[{i}]; if (it) {{ it.scrollIntoView({{block:'center'}}); it.click(); }}
                }}""")
                time.sleep(1.5)
                uid = collector._eval(_GET_CHAT_USER_FROM_URL)
                if uid:
                    chosen.append(uid)
                    print(f"  解析到 uid={uid}")
            except Exception as e:
                print(f"  解析失败：{e}")
    return chosen
