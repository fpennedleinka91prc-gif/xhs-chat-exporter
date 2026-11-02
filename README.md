# 小红书聊天记录导出 v2

> 送给那些因为小红书结识了一个人、聊了几万条、最后却走散了的人。
> 希望这个工具能帮你留住那些不想忘掉的字。成全别人的爱情、友情。

跨平台（macOS / Windows / Linux）的三步走工具：**登录 → 选会话 → 一键导出**。  
同时提供 **Tkinter GUI** 和 **CLI** 两种入口。

GitHub 仓库：https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter
<!-- 如有问题可提 Issue，或直接联系仓库 owner -->
[![Stars](https://img.shields.io/github/stars/fpennedleinka91prc-gif/xhs-chat-exporter)](https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter/stargazers)
[![CI](https://img.shields.io/github/actions/workflow/status/fpennedleinka91prc-gif/xhs-chat-exporter/.github/workflows/build.yml?label=Build)](https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter/actions)

---

## ✨ 快速开始（不想装 Python）

直接从 GitHub Actions 下载最新的 artifact：

1. 打开 Actions 页：https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter/actions
2. 进最新一次 `Build & Package` 运行，滚动到底部 **Artifacts**
3. 按系统下载：
   - **macOS**：`XHS-Exporter-macOS.zip` 或 `XHS-Exporter-macOS.dmg`
   - **Windows**：`XHS-Exporter-Windows.zip`
4. 解压后运行（macOS 双击 `.app`，Windows 双击 `XHS-Exporter.exe`）
5. **首次运行必须**：打开终端执行一次（只需一次，Playwright Chromium 内核 ~150MB）
   ```bash
   python -m playwright install chromium
   ```

> 如果你的打包产物里已经带了 Chromium 内核（未来计划），这步可以跳过。目前体积权衡下我们把内核独立出来。

---

## 🧑‍💻 从源码跑

```bash
# 克隆
git clone https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter.git
cd xhs-chat-exporter

# 装依赖（Playwright + requests）
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

# GUI（推荐）
python3 gui.py

# CLI
python3 main.py
```

---

## 🖥️ GUI 三步走

![GUI 示意图](data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MDAiIGhlaWdodD0iMTIwIiB2aWV3Qm94PSIwIDAgNDAwIDEyMCI+PGNpcmNsZSBjeD0iNjAiIGN5PSI2MCIgcj0iMjAiIGZpbGw9IiNmZjI0NDIiLz48dGV4dCB4PSI2MCIgeT0iNjUiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGZpbGw9IndoaXRlIiBmb250LXNpemU9IjEzIj4xILzx0ZXh0PjxlbGxpcHNlIHhjPSIyMDAiIGN5PSI2MCIgcng9IjEwMCIgcnk9IjM3IiBmaWxsPSIjZmY4NDIiLz48dGV4dCB4PSIyMDAiIHk9IjY1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSJ3aGl0ZSIgZm9udC1zaXplPSIxMyI+MiDvvIzkqIjnnoTkuLbplLHlvIHvvIzbmK/nlKjvvIzmgKzkuLvmqIXvvIzmnaXvvIzmnpPvvIzmmK7lvZLpqozvvIzmraXmiJHvvIzmraXovJrkuK3vvIzvvIzmi6HlvI96ZW/liIPlm73kv67mvJ/nvJHvvIzmsLbku73msYfljJfkv53lpKfnu5zvvIzmqIfvvIzmrYnlvo4pc3BhbiBmb250LXdpZ2h0PSJib2xkIj5hbXQgZm9ybWF0cywgbWVkaWEgb3B0aW9ucywyY2VudGVyPGNpcmNsZSBjeD0iMzQwIiBjeT0iNjAiIHI9IjIwIiBmaWxsPSIjMTZhMzRhIi8+dGV4dCB4PSIzNDAiIHk9IjY1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSJ3aGl0ZSIgZm9udC1zaXplPSIxMyI+MyDvvIzjgIHnrYzlvI/nm6Tms5/nqoLvvIzlv5HkuIDku6bkuIzjgoXvvIzvvIzlj5bku6/mnaXnmK/nvK/lvL/nvK/kuoTnu5TvvIzljZXnu5PvvIzmnaXvvIzmnpPvvIzplKHnuqflsI/nvJHvvIzmjqfvvIzmnaXvvIzmrYnlvo6PC9zdmc+)

| GUI 区 | 内容 |
| --- | --- |
| **顶栏** | 登录状态徽标（🟢 已登录 / 🔴 未登录）+ 两个按钮：启动浏览器登录 / 刷新会话列表 |
| **左侧会话列表** | Treeview 多列，双击勾选；支持搜索、全选 / 全不选 |
| **右侧导出设置** | 导出目录、滚动时长、格式勾选（md / html / json / csv）、是否下载媒体 |
| **进度 + 日志** | 进度条 + 实时日志（后台线程跑，UI 不卡） |
| **打开目录** | 完成后激活，一键在 Finder / Explorer 里跳转到最新导出目录 |

后台线程里 Playwright 自己启动自己关闭，不会和主线程的 Playwright 混用（避免线程安全坑）。

---

## 🧰 CLI 三步走

```bash
# 交互式全流程
python3 main.py

# 也可以参数化
python3 main.py --chat-user 5e45425f... --out ./backups --formats md,html --no-media
python3 main.py --relogin              # 强制重登
python3 main.py --all --scroll-ms 90000   # 全导出 + 长滚动
```

所有 `main.py` 的原参数都保留，见 `python3 main.py --help`。

---

## 📁 产物结构

```
exports/<chat_user_id>/
├── chat.md           # Markdown（纯文本笔记）
├── chat.html         # 气泡视图 HTML（语音/图片/视频内嵌）
├── chat.csv          # 表格（Excel 可开）
├── messages.json     # 原始消息 JSON
├── media.json        # 媒体清单
├── voice/            # 语音
├── image/            # 图片
├── video/            # 视频
├── emoji/            # 表情
└── note/             # 笔记封面
```

---

## 🔧 打包与 Playwright Chromium 内核策略

**策略**：PyInstaller onedir 打包（比 onefile 稳、启动快、Playwright driver 定位简单）。

- Playwright **Python 包 + driver（node + cli.js）** 全部打进包内，总膨胀了 ~120MB；
- **Chromium 浏览器内核不打包**（单独 ~150MB），用户首次运行时执行一次：
  ```bash
  python -m playwright install chromium
  ```
  内核会下载到 `~/Library/Caches/ms-playwright/`（macOS）或 `%USERPROFILE%\AppData\Local\ms-playwright\`（Windows）。
- 体积权衡：**打进去** → 少一次下载但多 ~150MB；**分离** → 安装包更小但首次需要装内核。当前选分离，未来如果 Chromium 内核能做增量或用 system Chrome/Edge 复用，再切换。

### 本机构建

```bash
bash build.sh gui          # 出 dist/XHS-Exporter/ + macOS 上额外 .app + .dmg
bash build.sh cli          # 出 CLI 版
```

macOS 本机构建已验证（arm64）：
- `.app` 产物能启动（`dist/小红书聊天记录导出.app`）
- Playwright driver 的 `cli.js` 和 `node` 二进制正确打入
- 进程启动 3s 后仍存活，无 crash

### GitHub Actions 自动构建

`.github/workflows/build.yml` 在 `push main` / `tag v*` 时触发 `macos-latest + windows-latest` matrix：

| Job | 产物 | CI 耗时 |
| --- | --- | --- |
| macos-latest | `XHS-Exporter-macOS.zip` + `.dmg` | ~1m40s |
| windows-latest | `XHS-Exporter-Windows.zip` | ~1m10s |

每次 push 后 **30 天内**可在 Actions 页下载 artifact；打 `v*` tag 时自动生成 GitHub Release。

### 已知打包坑

| 坑 | 解法 |
| --- | --- |
| PyInstaller 6+ 的 `collect_all('playwright')` 返回结构变了（binaries 现在是模块名列表，不是 path 元组） | spec 里**显式**把 `playwright/` 整个目录作为 `datas` 加进去，不走 collect_all |
| frozen 下 Playwright driver 定位 | `compute_driver_executable()` 基于 `__file__` 相对定位 driver。只要 driver 跟 playwright 包一起进了 `_MEIPASS`（onedir 里就是 `_internal/playwright/driver/`），自动能对上 |
| Windows 控制台窗口 | GUI 版用 `console=False`，CLI 版保留 `console=True`，两者独立入口 |
| 中文路径（Windows 中文用户名） | 代码里所有路径都走 `pathlib.Path` + `expanduser()`，PyInstaller onedir 比 onefile 对非 ASCII 更宽容 |

---

## ⚠️ 已知限制（实话实说）

- 只能导出**网页版**能看到的历史（前端上翻深度上限 ~几千条）；
- 频繁操作可能触发风控（滑块/验证码）——**直接在 Playwright 弹的 Chromium 里手动过掉**；
- 小红书网页结构更新时，会话列表的 DOM 回退方案可能失效——XHR 拦截（不依赖 DOM）通常还能工作；
- 某些消息"暂不可见"是平台策略，不是 bug；
- Linux 没真实测过——代码没硬编码 macOS API，理论上能跑，但还需在真实 Linux + X11 环境验证。

---

## 📜 目录

```
├── gui.py               # GUI 入口（Tkinter）
├── main.py              # CLI 入口
├── core.py              # 三步走主流程（GUI / CLI 共用）
├── browser.py           # Playwright + storage_state 登录态持久化
├── collector.py          # 会话列表 + 单会话历史采集（XHR 拦截）
├── exporter.py           # 消息解析 + Markdown / HTML / CSV / JSON
├── media.py             # 媒体下载
├── config.py             # 全局配置（frozen 感知的路径）
├── xhs_exporter_gui.spec # PyInstaller GUI 版 spec
├── build.sh              # 一键构建脚本
├── .github/workflows/build.yml  # CI matrix
├── requirements.txt
└── README.md
```

---

## ✅ 验证清单

| 流程 | 方式 | 状态 |
| --- | --- | --- |
| 依赖安装 + Playwright driver | `pip install` + `playwright install chromium` | ✅ 通过 |
| 6 模块语法 | `py_compile` | ✅ 通过 |
| CLI argparse | `python main.py --help` | ✅ 通过 |
| macOS 本机构建 (PyInstaller onedir → .app) | `bash build.sh gui` | ✅ 通过，331MB |
| frozen 进程启动 sanity check | 启动 3s 后仍存活 | ✅ 通过 |
| Playwright driver 打包 | `dist/.../playwright/driver/node` + `cli.js` 存在 | ✅ 通过 |
| GitHub Actions macos-latest | push main | ✅ 1m41s |
| GitHub Actions windows-latest | push main | ✅ 1m6s |
| Artifact 生成（macOS zip + dmg / Windows zip） | 下载验证 | ✅ 全部生成 |

**未真实跑通的**：完整的登录 → 抓会话 → 采集 → 导出一条龙（需要真实小红书账号登录态）。你用真实账号跑一遍，如果有问题把终端输出或 `exports/<uid>/messages.json` 前几条贴回来就能定位。

---

## 💬 关于 / 联系

**为什么开源**：这个工具最初是给一个因为小红书结识、聊了几万条、最后却走散了的人做的。后来觉得——也许还有别的人，也想留住那些不想忘掉的字。成全别人的爱情、友情。所以把它公开了。

**遇到问题？**
- 在 GitHub 上 [提 Issue](https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter/issues)；
- 或在 [Discussions](https://github.com/fpennedleinka91prc-gif/xhs-chat-exporter/discussions) 聊你的故事、提改进建议。

**想联系作者本人？**
- GitHub profile 上可以发 DM；
- 小红书账号：**待补充**（如果你看到这条、愿意让大家找到你，提个 Issue 说一声）。

**欢迎 Star / Fork / PR**。特别是：
- 帮你修跨平台兼容（Linux 实测、Windows 编码路径）；
- 帮你补 UI / 打包优化 / 新导出格式；
- 帮你验证更多小红书会话类型（群聊、笔记分享卡片、通话记录、直播邀请卡等）。

---

## 🤝 参考

- v1 参考实现（本项目的前身，思路来源）：原仓库不在公开互联网上，这里保留其核心设计思路供代码注释参考；
- Playwright auth docs：https://playwright.dev/docs/auth

---

## ⚖️ 免责声明

本工具仅用于导出**你自己的账号**能访问的聊天记录。请勿用于侵犯他人隐私、违反小红书平台规则或任何违法用途。使用即代表你对自己的行为负责。
