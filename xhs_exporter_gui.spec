# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：GUI 版入口 gui.py。

Chromium 内核**不**通过 spec 打进包（PyInstaller 会尝试对 mach-o 二进制签名，
碰到 "Google Chrome for Testing" 这种路径就炸）。
Chromium 由 build.sh / CI workflow 在 PyInstaller 跑完后手动拷贝到：
  dist/XHS-Exporter/_internal/browsers/

运行时 browser.py 通过 _MEIPASS / _internal 定位到这个目录。
"""
from pathlib import Path
import playwright
import sys

block_cipher = None

HERE = Path(SPECPATH if 'SPECPATH' in dir() else '.').resolve()
PW_PKG = Path(playwright.__file__).resolve().parent

# —— datas：只放 Playwright Python 包 + driver（别放 browsers/，放了会炸）——
datas = [
    (str(PW_PKG), 'playwright'),
]

# —— Chromium 打包检查（只打印，spec 不打）——
BROWSERS = HERE / 'browsers'
if BROWSERS.is_dir():
    chromium_size = sum(f.stat().st_size for f in BROWSERS.rglob('*') if f.is_file()) / 1024 / 1024
    print(f'[spec] Chromium found ({chromium_size:.0f}MB), will be copied to dist/_internal/browsers by shell')
else:
    print('[spec] WARNING: no ./browsers/ dir found. Run:'
          ' PLAYWRIGHT_BROWSERS_PATH=./browsers python3 -m playwright install chromium')

hiddenimports = [
    'playwright.sync_api',
    'playwright.async_api',
    'playwright._impl._driver',
    'playwright._impl._api_structures',
    'playwright._impl._errors',
]

a = Analysis(
    [str(HERE / 'gui.py')],
    pathex=[str(HERE)],
    binaries=[],
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

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='小红书聊天记录导出.app',
        icon=None,
        bundle_identifier='com.xhs.exporter',
        info_plist={
            'CFBundleName': '小红书聊天记录导出',
            'CFBundleDisplayName': '小红书聊天记录导出',
            'CFBundleShortVersionString': '2.1.0',
            'CFBundleVersion': '210',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15.0',
        },
    )
