# -*- coding: utf-8 -*-
"""中英文关键词互译模块（跨语言检索）。

数据：data/bilingual.json 中的双语词对表（离线、确定性）；
功能：
- detect_lang(text)：按 CJK 字符判定查询语言；
- expand(terms)：把查询词翻译为另一语言候选（中文词 -> 英文候选，
  英文词 -> 中文候选），供检索做“原文 ∪ 同义词”的跨语言扩展。

词典加载失败自动降级为空表（系统仍可单语言检索），不抛异常。
"""

import json
import os
import re
from pathlib import Path

# 项目根目录 = core 包的上层目录（移动端可经 ACADEMIC_DATA_ROOT 重定向）
PROJECT_ROOT = Path(os.environ.get("ACADEMIC_DATA_ROOT")
                    or Path(__file__).resolve().parent.parent)
BILINGUAL_PATH = PROJECT_ROOT / "data" / "bilingual.json"

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_lang(text):
    """返回查询文本语言：zh（含中文）/ en / mixed（中英混合）。"""
    has_zh = bool(_CJK_RE.search(text or ""))
    has_en = bool(re.search(r"[A-Za-z]", text or ""))
    if has_zh and has_en:
        return "mixed"
    return "zh" if has_zh else "en"


class Translator:
    """双语词典查询器：zh <-> en 双向映射。"""

    def __init__(self, path=BILINGUAL_PATH):
        self.en2zh = {}
        self.zh2en = {}
        self._load(path)

    def _load(self, path):
        """读取 {"pairs": [["convolution","卷积"], …]}，构建双向索引。"""
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            print(f"[互译] 词典缺失或损坏：{path}，跨语言检索不可用")
            return
        for en, zh in data.get("pairs", []):
            en_key = str(en).strip().lower()
            zh_key = str(zh).strip()
            if en_key and zh_key:
                self.en2zh.setdefault(en_key, []).append(zh_key)
                self.zh2en.setdefault(zh_key, []).append(en_key)

    def translate(self, term):
        """翻译单个查询词：返回另一语言候选列表（可能为空）。"""
        term = (term or "").strip()
        if not term:
            return []
        if _CJK_RE.search(term):
            return self.zh2en.get(term, [])
        return self.en2zh.get(term.lower(), [])

    def expand(self, terms):
        """批量扩展。

        参数:
            terms: 原始查询词列表（去重后）。
        返回:
            {term: {"lang": "zh"|"en", "syn": [同义词候选, …]}}
        """
        result = {}
        for term in terms:
            syn = self.translate(term)
            if syn:
                result[term] = {
                    "lang": "zh" if _CJK_RE.search(term) else "en",
                    "syn": syn,
                }
        return result
