# xhs-exporter — 小红书聊天记录导出（傻瓜版 v2）

三步走：**打开扫码登录 → 选会话 → 一键导出**。  
登录态会被持久化（`state.json`），第二次运行开始就直接用，不用再登。

---

## 🎯 和参考实现（v1）的差异

| 维度 | v1 参考版 | v2 傻瓜版（本项目） |
| --- | --- | --- |
| 浏览器控制 | 手写 WebSocket CDP 客户端，需要用户先用命令行开 Chrome 调试端口 | Playwright，一键启动 Chromium，不用手动开浏览器 |
| 依赖 | `websocket-client` + `requests` | `playwright` + `requests`（Playwright 自带 Chromium） |
| 登录态 | 无持久化（每次重开 Chrome 都要重新登录） | `storage_state` 持久化到 `state.json`，自动复用 |
| 会话选择 | 交互列表 + 单选 | 交互列表 + **多选**（序号逗号分隔、范围、`a` 全选） |
| 导出格式 | HTML + CSV + JSON | Markdown + HTML + CSV + JSON（可选） |
| 媒体下载 | 强依赖 ffmpeg 做格式转换 | best-effort，**不依赖 ffmpeg** |
| 异常处理 | 抛原始异常、或打印 Python 栈 | 人话错误提示 + 常见坑提示 |
| 滚动加载 | 单次 `Runtime.evaluate` 60s 超时会失败 | 分块 12s 滚 + 兜底，更稳 |
| 已知 bug | `resolve_tab` 定义了两次 | 修掉了 |

---

## 📦 目录结构

```
xhs-exporter/
├── main.py             # 主入口（三步走）
├── browser.py          # Playwright 浏览器 + 登录态持久化
├── collector.py        # 会话列表 + 单会话完整历史采集
├── exporter.py         # 消息解析 + Markdown / HTML / CSV / JSON 生成
├── media.py            # 媒体文件下载（语音/图片/视频/表情/笔记封面）
├── config.py           # 全局配置（路径、常量、消息类型标签）
├── requirements.txt    # Python 依赖
├── README.md           # 本文件
├── state.json          # 登录态（首次登录后自动生成，**别删**）
└── exports/            # 默认导出目录（按对方 uid 分子目录）
    └── <chat_user_id>/
        ├── chat.md         # Markdown 版
        ├── chat.html       # 气泡视图 HTML
        ├── chat.csv        # 表格（Excel 可开）
        ├── messages.json   # 原始消息 JSON
        ├── media.json      # 媒体清单
        ├── voice/          # 语音 .m4a
        ├── image/          # 图片
        ├── video/          # 视频
        ├── emoji/          # 表情
        └── note/           # 笔记封面
```

---

## 🚀 使用三步走

### 第 1 步：装依赖（只需一次）

```bash
cd xhs-exporter
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

### 第 2 步：第一次运行，扫码登录

```bash
python3 main.py
```

- 会弹出一个 Chromium 窗口自动打开 `https://www.xiaohongshu.com`；
- 在浏览器里扫码 / 账号密码登录；
- 登录成功、看到首页后，**回到终端按一下回车**；
- 登录态会自动保存到 `state.json`，下次直接用。

### 第 3 步：选会话、一键导出

```
正在加载会话列表…
📋 检测到 12 个会话：
  [  0] 💬 张三  [好啊今晚吃啥？]
  [  1] 🛒 购物群  [已发货请注意查收]
  ...

选择方式：
  - 单个：输入序号，如 3
  - 多个：用逗号分隔，如 1,3,7
  - 范围：如 1-5
  - 全部：输入 a

请输入要导出的会话序号（Ctrl-C 退出）：0,2,5
```

回车 → 自动打开每个会话 → 自动滚动加载历史 → 抓 XHR 响应 → 下载媒体 → 生成产物。

导出完成后，终端会打印成功数 / 失败数，然后你去 `exports/<uid>/` 里打开 `chat.html` 或 `chat.md` 就能看。

---

## 🛠️ 常用命令

```bash
# 强制重新扫码（state.json 过期 / 账号变了时用）
python3 main.py --relogin

# 直接指定某个会话的 user_id（跳过交互选择）
python3 main.py --chat-user 5e45425f0000000001008a6c

# 指定多个会话（多选）
python3 main.py --chat-user 5e45425f0000000001008a6c --chat-user 6e45...

# 导出全部会话（⚠️ 慢，可能被风控）
python3 main.py --all

# 自定义导出目录
python3 main.py --out ./my_backup

# 只要 Markdown + JSON，不生成 HTML / CSV
python3 main.py --formats md,json

# 不下载语音/图片/视频，只要文本
python3 main.py --no-media

# 长会话：把滚动时长调大（默认 45000ms ≈ 45s）
python3 main.py --scroll-ms 90000
```

### 怎么拿到会话的 `user_id`？

- 第一次用这个工具**交互选会话** → 它会自动打开会话并从 URL 里解析 `chat_user_id`；
- 或者在小红书网页版里点进会话，看地址栏里 `/chat/<一串 hex>` 那串 hex；
- 也可以看 `exports/<uid>/messages.json` 里每条消息的 `sender_id` / `receiver_id`。

---

## ⚠️ 已知限制（**实话实说**）

这些不是 bug，是小红书平台的设计。

### 1. 只能导出"网页版"能看到的历史

小红书 IM 前端对"上翻"历史有深度限制（大致几千到上万条，取决于会话活跃度）。工具会**尽可能拉满这个上限**，但老到一定程度的消息网页版本身就不加载。

**替代方案**：如果你要的历史超出网页版，只能在手机 App 里手动截图，或考虑小红书开放平台的商家能力（需要注册应用 + 申请权限）。

### 2. 可能被风控

频繁请求、异常 UA、短时间内多次操作可能触发小红书的风控（弹出滑块 / 验证码）。Playwright 已经做了 `navigator.webdriver` 伪装，但如果小红书升级检测，**重登 + 用自己正常使用的账号操作**是最稳的。

建议：
- 不要一次跑 `--all` 几百个会话；
- 不要把 `--scroll-ms` 调到特别大；
- 如果看到验证码，**直接在弹出的 Chromium 里手动过掉**——Playwright 用的是你自己的账号，过一次就好。

### 3. 网页结构更新了怎么办？

`collector.py` 里会查 `.xhs-im-conv-item`、`.xhs-im-msg-list` 等 class，如果小红书改版，可能抓不到。碰到这种情况：

1. 加 `print` 或断在 `collector.py` 的 `_conv_from_dom` / `collect_history` 里，看 `page.content()`；
2. 把选择器更新一下；
3. 或者退一步，**手工在 Chromium 里点开会话**，再运行 `collect_history`（XHR 拦截不依赖 DOM 选择器，只要 SPA 发了请求就能抓到）。

### 4. 某些消息内容"暂不可见"

小红书 IM 有几种消息会被策略拦截（敏感词、转发自已封禁笔记、撤回超过时限等），这些网页版本来就显示不出来，工具同样拿不到内容，只会保留一个占位。

---

## ✅ 我实际验证了哪些流程

| 流程 | 验证方式 | 状态 |
| --- | --- | --- |
| 依赖能装起来 | `pip install -r requirements.txt` + `playwright install chromium` | ✅ 通过 |
| 语法正确 | `py_compile` 全部模块 | ✅ 通过 |
| CLI argparse | `python main.py --help` | ✅ 通过 |
| 登录态持久化逻辑 | 代码走查（Playwright `storage_state` 是官方稳定 API） | ✅ 可信 |
| 会话列表 XHR 拦截 | 代码走查（`XMLHttpRequest.prototype.open/send` 拦截 `\/api\/im\/web\/(conversations|inbox)`） | ✅ 逻辑对 |
| 消息历史 XHR 拦截 | 代码走查（拦截 `\/messages\/history` 提取 `out_message_list`） | ✅ 逻辑对 |
| 自动滚动触发前端加载 | 代码走查（`scrollTop = 1` 再 `= 0` 的轻抖动策略，参考 v1 已验证过） | ⚠️ 依赖页面结构 |
| 消息解析（content_type 0/1/2/3/4/9/10/11/13/16/17） | 代码走查 + 复用 v1 已验证的 `parse_message` | ✅ 可信 |
| Markdown 生成 | 代码走查 | ✅ 可信 |
| HTML 气泡视图 | 代码走查 + 复用 v1 已验证的模板 | ✅ 可信 |
| 媒体下载 | 代码走查（纯 `requests` + UA 伪装） | ✅ 可信 |

**我没真跑**：完整的登录 → 抓会话 → 采集 → 导出一条龙。原因：我的测试账号是本地虚拟账号，不一定能成功登上小红书生产环境；而且需要真实账号的登录态，这是**你自己跑最准**的。如果你跑了有问题，把终端输出贴给我（或贴 `exports/<uid>/` 里的 `messages.json` 前几条），我就能定位。

---

## 🤝 参考

| 项目 | 说明 |
| --- | --- |
| v1 参考实现 | `/Users/andy/Documents/deepseek-harness/default-workspace/xhs_chat_exporter/`（未被修改） |
| Playwright auth docs | https://playwright.dev/docs/auth |

---

## ⚖️ 免责声明

本工具仅用于导出**你自己的账号**能访问的聊天记录。请勿用于侵犯他人隐私、违反小红书平台规则或任何违法用途。使用即代表你对自己的行为负责。
