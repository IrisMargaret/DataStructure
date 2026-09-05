# -*- coding: utf-8 -*-
"""路径统一：可写数据根(DATA_ROOT) 与 只读资源根(RESOURCE_ROOT)。

为什么需要两份：
- 普通源码运行：二者都指向项目根目录；
- 移动端(Chaquopy)：mobile_server 注入 ACADEMIC_DATA_ROOT 指向 App 私有解压目录
  （资源 templates/static/data 与可写数据同目录），两 root 同值；
- 桌面(PyInstaller)：可执行文件被打包后，__file__ 位于只读/临时的 _MEIPASS，
  只读资源(模板/静态/种子)从 _MEIPASS 读取，可写数据(论文库/上传/日志/AI 配置)
  放在 exe 同级目录 —— 由 DATA_ROOT 承载。

约定：任何模块不得再自行推导项目根，统一：
    from paths import DATA_ROOT, RESOURCE_ROOT
资源侧(模板/静态渲染)用 RESOURCE_ROOT；数据侧(读写)一律用 DATA_ROOT。
"""

import os
import sys
from pathlib import Path


def _is_frozen():
    """是否运行在 PyInstaller 打包环境。"""
    return bool(getattr(sys, "frozen", False))


def data_root() -> Path:
    """可写数据根目录（论文库/上传/日志/AI 配置所在）。"""
    env = os.environ.get("ACADEMIC_DATA_ROOT")
    if env:
        return Path(env)
    if _is_frozen():
        # 单文件/目录式打包：exe 同级目录通常可写，便于随带数据
        return Path(sys.executable).resolve().parent
    # 源码运行：本项目根目录
    return Path(__file__).resolve().parent


def resource_root() -> Path:
    """只读资源根目录（模板/静态/内置种子数据）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    env = os.environ.get("ACADEMIC_RESOURCE_ROOT")
    if env:
        return Path(env)
    return data_root()


DATA_ROOT = data_root()
RESOURCE_ROOT = resource_root()
