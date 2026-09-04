# -*- coding: utf-8 -*-
"""日志初始化：错误与关键事件写入 logs/app.log（UTF-8，1MB 轮转）。"""

import logging
import logging.handlers
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
_lock = threading.Lock()
_loggers = {}


def get_logger(name="app", path=None):
    """返回文件日志器（同一 name 复用单例；path 仅供测试注入）。"""
    with _lock:
        if name in _loggers:
            return _loggers[name]
        log_file = Path(path) if path else PROJECT_ROOT / "logs" / "app.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(f"ir.{name}")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=1_000_000, backupCount=2,
                encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.propagate = False
        _loggers[name] = logger
        return logger
