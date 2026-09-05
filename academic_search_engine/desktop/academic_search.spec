# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec：学术论文检索 桌面版（onefile + 独立窗口，无控制台）
import os

try:
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _here = os.path.dirname(os.path.abspath(SPEC))
base = _here
# 桌面目录位于主项目(academic_search_engine)之内：engine = base 的上层
engine = os.path.abspath(os.path.join(base, os.pardir))

datas = [
    (os.path.join(engine, "templates"), "templates"),
    (os.path.join(engine, "static"), "static"),
    (os.path.join(engine, "data", "papers.json"), "data"),
    (os.path.join(engine, "data", "stopwords.txt"), "data"),
    (os.path.join(engine, "data", "bilingual.json"), "data"),
]

a = Analysis(
    [os.path.join(base, "desktop_app.py")],
    pathex=[engine, base],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "paths", "logutil", "web", "service", "core", "ingest",
        "crawler", "agent", "agent.settings", "agent.llm",
        "webview.platforms.edgechromium",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AcademicSearchEngine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(base, "app.ico"),
)