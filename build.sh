#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# 构建 PyInstaller 产物（macOS / Linux / Windows 都能跑，靠 CI 分发）。
# 用法：
#   ./build.sh              # 构建 GUI 版（默认）
#   ./build.sh cli          # 构建 CLI 版（main.py 入口）
set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-gui}"
VERSION="2.0.0"

echo "==> 清理旧产物"
rm -rf dist build *.spec.bak
rm -rf __pycache__ */__pycache__

echo "==> 安装 / 校验依赖"
python3 -m pip install -q -r requirements.txt
python3 -m pip install -q pyinstaller

echo "==> 安装 Playwright Chromium（~150MB，只下载一次）"
python3 -m playwright install chromium

if [ "$MODE" = "gui" ]; then
    echo "==> 构建 GUI 版"
    pyinstaller --noconfirm --clean xhs_exporter_gui.spec
    OUTNAME="XHS-Exporter"
else
    echo "==> 构建 CLI 版"
    pyinstaller \
        --name "XHS-Exporter-CLI" \
        --windowed=false \
        --console \
        --collect-all playwright \
        --add-data "config.py:." \
        --add-data "core.py:." \
        --add-data "browser.py:." \
        --add-data "collector.py:." \
        --add-data "exporter.py:." \
        --add-data "media.py:." \
        --add-data "gui.py:." \
        main.py
    OUTNAME="XHS-Exporter-CLI"
fi

echo "==> 构建完成"
echo "   产物在 dist/"
ls -la dist/

# macOS 再封一个 .dmg（有 create-dmg 才做，CI 会装；没有就跳过）
if [[ "$(uname -s)" == "Darwin" && -d "dist/${OUTNAME}.app" ]]; then
    if command -v create-dmg >/dev/null 2>&1; then
        echo "==> 生成 DMG"
        rm -f "dist/${OUTNAME}-mac.dmg"
        create-dmg \
            --volname "小红书聊天记录导出 ${VERSION}" \
            --window-size 500 320 \
            --window-pos 200 120 \
            --icon-size 100 \
            --app-drop-link 400 150 \
            "dist/${OUTNAME}-mac.dmg" \
            "dist/${OUTNAME}.app" || echo "⚠️ create-dmg 失败（可能是权限），跳过 DMG"
    else
        echo "==> 未检测到 create-dmg，跳过 DMG（brew install create-dmg）"
    fi
fi
