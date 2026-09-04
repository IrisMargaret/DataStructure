# -*- coding: utf-8 -*-
"""解析异常 -> 用户可读中文提示（技术细节只进日志）。"""

import re

_PATTERNS = [
    (re.compile(r"pdf.*(encrypt|password|not allowed)", re.I),
     "PDF 已加密或受保护，无法读取"),
    (re.compile(r"(pdfreaderror|startxref|eof marker|cross-reference|"
                r"pdf header)", re.I),
     "PDF 文件损坏或格式异常，无法解析"),
    (re.compile(r"codec can't (?:decode|encode)|"
                r"unicode(?:decode|encode)error", re.I),
     "文本编码无法识别或含非常用字符，已跳过该文件"),
    (re.compile(r"zipfile|badzipfile|not a zip", re.I),
     "压缩包不是有效的 ZIP 或已损坏"),
    (re.compile(r"filenotfound|permission", re.I),
     "文件读取失败（不存在或无权限）"),
]


def friendly_parse_error(exc):
    """把异常映射为中文提示；未知类型给出通用指引。"""
    message = str(exc) or type(exc).__name__
    for pattern, hint in _PATTERNS:
        if pattern.search(message):
            return hint
    return "解析失败，详情已记录到日志，可改用 AI 精修或手动填写"
