# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：GUI 版入口 gui.py（无控制台）。

用法：
  pyinstaller xhs_exporter_gui.spec
  # 产物：dist/XHS-Exporter/（onedir，跨平台通用）
  # macOS 额外：dist/小红书聊天记录导出.app（BUNDLE）

关键依赖：
- Playwright 的 driver 是独立 Node 运行时 + cli.js，必须一并打包；
- Chromium 浏览器内核**不打包**（~150MB），首次运行缺失时，Playwright 会明确提示
  用户执行 `python -m playwright install chromium`。

注意 PyInstaller 6+ 的 collect_all 返回结构有变，binaries 现在是模块名字符串列表。
这里显式把 driver 目录按 (src, dest_dir) 加入 datas，避免踩坑。
"""
from pathlib import Path
import playwright

block_cipher = None

SPEC_DIR = Path(SPECPATH if 'SPECPATH' in dir() else '.').resolve()
PW_PKG = Path(playwright.__file__).resolve().parent
PW_DRIVER = PW_PKG / 'driver'

# —— datas：Playwright 整个 driver 目录 + 业务源码 ——
datas = [
    # Playwright Python 包本身（不只是 driver，因为 compute_driver_executable 依赖它的 __file__）
    (str(PW_PKG), 'playwright'),
]

# —— binaries：空，让 PyInstaller 自己分析；Playwright driver 的 node 可执行在 datas 里 ——
binaries = []

# —— hiddenimports：Playwright 的同步 API 和内部模块 ——
hiddenimports = [
    'playwright.sync_api',
    'playwright.async_api',
    'playwright._impl._driver',
    'playwright._impl._api_structures',
    'playwright._impl._errors',
    'playwright._impl._helper',
    'playwright._impl._transport',
]

a = Analysis(
    [str(SPEC_DIR / 'gui.py')],
    pathex=[str(SPEC_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XHS-Exporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='XHS-Exporter',
)

# macOS：再封一层 .app（其他平台跳过）
import sys
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='小红书聊天记录导出.app',
        icon=None,
        bundle_identifier='com.xhs.exporter',
        info_plist={
            'CFBundleName': '小红书聊天记录导出',
            'CFBundleDisplayName': '小红书聊天记录导出',
            'CFBundleShortVersionString': '2.0.0',
            'CFBundleVersion': '200',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15.0',
        },
    )
