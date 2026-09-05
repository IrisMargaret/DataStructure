# -*- coding: utf-8 -*-
"""AI(LLM) 配置的持久化与运行时注入。

配置来源（优先级从高到低）：
1. 应用内「设置」页 -> data/app_settings.json（权威，UI 保存后立即生效并持久化）；
2. 环境变量 / .env（老方式，仅当设置文件不存在时生效）。

- save_settings() 原子写 JSON（tmp + replace），文件位于 DATA_ROOT/data/ 下
  （安卓=应用私有目录，桌面=exe 同级目录；均已加入 .gitignore）；
- apply_to_env() 把设置同步进 os.environ —— agent/llm.py 每次调用都读环境变量，
  因此保存后无需重启即生效；
- view_settings() 只返回脱敏信息（Key 尾号），接口与日志永不回显明文 Key。
"""

import json
import os
import tempfile
from pathlib import Path

from paths import DATA_ROOT

# 设置字段 <-> 环境变量 的映射
ENV_FIELDS = [
    ("api_base", "LLM_API_BASE"),
    ("api_key", "LLM_API_KEY"),
    ("model", "LLM_MODEL"),
    ("timeout", "LLM_TIMEOUT"),
    ("temperature", "LLM_TEMPERATURE"),
]
SETTINGS_PATH = DATA_ROOT / "data" / "app_settings.json"

_DEFAULTS = {"api_base": "", "api_key": "", "model": "",
             "timeout": 30, "temperature": 0.2}


def settings_path():
    return SETTINGS_PATH


def load_settings(path=None) -> dict:
    """读取设置文件；不存在/损坏时返回空 dict（不要抛异常干扰启动）。"""
    p = Path(path) if path else SETTINGS_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict, path=None):
    """原子写入设置文件（父目录自动创建）。"""
    p = Path(path) if path else SETTINGS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {k: settings.get(k) for k, _ in ENV_FIELDS
               if k in settings}
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cleaned, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def clear_settings(path=None):
    """删除设置文件（彻底清除本地保存的 Key）。"""
    p = Path(path) if path else SETTINGS_PATH
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def apply_to_env(settings=None):
    """把设置文件字段同步到 os.environ（立即生效，无需重启）。

    - 文件不存在（settings=None 且无文件）时不改动任何环境变量；
    - 文件中的空字段（如 Key 被清除）会移除对应环境变量，等价“未配置”；
    - 文件中不存在的字段保持环境现状（启动时 .env 仍可兜底）。
    """
    if settings is None:
        settings = load_settings()
        if not settings:
            return
    for field, env_name in ENV_FIELDS:
        if field not in settings:
            continue
        value = settings.get(field)
        if value is None or str(value) == "":
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = str(value)


def mask_key(key):
    """Key 脱敏：只保留前 4 与后 4 位。"""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 12:
        return key[:3] + "…" + key[-2:]
    return f"{key[:4]}…{key[-4:]}"


def view_settings(settings=None) -> dict:
    """对外脱敏视图（配置状态 + 脱敏 Key），永不含明文 Key。"""
    if settings is None:
        settings = load_settings()
    s = dict(_DEFAULTS)
    s.update({k: settings.get(k) for k, _ in ENV_FIELDS
              if k in settings and settings.get(k) is not None})
    configured = bool(s["api_base"] and s["api_key"] and s["model"])
    return {
        "configured": configured,
        "api_base": s["api_base"],
        "model": s["model"],
        "api_key_masked": mask_key(s["api_key"]),
        "timeout": s["timeout"],
        "temperature": s["temperature"],
    }
