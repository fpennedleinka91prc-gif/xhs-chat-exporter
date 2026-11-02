#!/usr/bin/env bash
# 构建 macOS GUI 版（含 Chromium 内核，下载即用）。
# 三步法：
#   1. PyInstaller 打应用代码（不通过 spec 打 Chromium，PyInstaller 会对 mach-o 签名炸）
#   2. shell 把 Chromium 拷进 dist/XHS-Exporter/_internal/browsers/ + .app/Contents/Resources/browsers/
#   3. zip / dmg
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "==> 1) 安装 Chromium 到 ./browsers/"
mkdir -p browsers
export PLAYWRIGHT_BROWSERS_PATH="$HERE/browsers"
python3 -m playwright install chromium 2>&1 | tail -3
echo "   $(du -sh browsers/ | cut -f1)"

echo
echo "==> 2) PyInstaller 打应用代码"
pip show pyinstaller >/dev/null 2>&1 || pip install pyinstaller
pyinstaller --clean --noconfirm xhs_exporter_gui.spec 2>&1 | tail -5

echo
echo "==> 3) 把 Chromium 拷进构建产物"
# onedir (Windows/Linux 打包会用到这个)
mkdir -p "dist/XHS-Exporter/_internal/browsers"
cp -R browsers/* "dist/XHS-Exporter/_internal/browsers/"
# macOS .app
if [ -d "dist/小红书聊天记录导出.app" ]; then
    mkdir -p "dist/小红书聊天记录导出.app/Contents/Resources/browsers"
    cp -R browsers/* "dist/小红书聊天记录导出.app/Contents/Resources/browsers/"
fi

echo
echo "==> 4) 最终产物"
du -sh dist/XHS-Exporter/
ls -lh dist/*.app 2>/dev/null
echo "   browsers 子目录大小："
du -sh dist/XHS-Exporter/_internal/browsers/ 2>/dev/null || \
    du -sh "dist/小红书聊天记录导出.app/Contents/Resources/browsers"

echo
echo "✅ 构建完成。dist/ 下的 .app / XHS-Exporter/ 都是下载即用的。"
