# -*- coding: utf-8 -*-
"""文本预处理：中英文混合分词、停用词过滤、词干提取。

处理策略：
1. 英文按正则切分为单词、统一转小写，再做 Porter 词干化
   （transformers/transformer -> transform，保证变体可互相检索）；
2. 中文使用 jieba 分词（细粒度模式），不参与词干化；
3. 过滤停用词（data/stopwords.txt）与纯数字串；
4. 可选返回词在过滤后 Token 流中的位置（Posting 的 PositionList）
   及每个词干对应的原始拼写（用于界面展示原词）。

重要约定：索引构建、查询解析、短语匹配必须全部经由本模块分词，
以保证“词干化前后一致”，映射不会错位。
"""

import os
import re
from pathlib import Path

import jieba

from .stemmer import PorterStemmer

# 项目根目录 = core 包的上层目录（移动端可经 ACADEMIC_DATA_ROOT 重定向）
PROJECT_ROOT = Path(os.environ.get("ACADEMIC_DATA_ROOT")
                    or Path(__file__).resolve().parent.parent)
STOPWORDS_PATH = PROJECT_ROOT / "data" / "stopwords.txt"

# 匹配一段连续中文，或一个拉丁单词（含连字符/下划线）
_TOKEN_SPLIT_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9\-_]*")
_ZH_SEG_RE = re.compile(r"[\u4e00-\u9fff]+")
# 纯数字 / 数字与符号串
_PURE_NUMBER_RE = re.compile(r"^[\d\-_\.]+$")


class Preprocessor:
    """中英文混合文本 -> 词干化关键词序列。"""

    def __init__(self, stopwords_file=STOPWORDS_PATH, stemmer=None):
        self.stopwords = self._load_stopwords(stopwords_file)
        self.stemmer = stemmer or PorterStemmer()
        # 首次使用 jieba 需要加载词典
        jieba.initialize()

    @staticmethod
    def _load_stopwords(path):
        """读取停用词表：每行一个词，支持 # 注释。"""
        words = set()
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    word = line.strip()
                    if word and not word.startswith("#"):
                        words.add(word.lower())
        except OSError:
            print(f"[预处理] 警告：停用词文件不存在 {path}，跳过停用词过滤")
        return words

    @staticmethod
    def _split_mixed(text):
        """把中英文混合文本切成 (中文片段 | 英文单词) 的有序序列。"""
        return [m.group(0) for m in _TOKEN_SPLIT_RE.finditer(text or "")]

    def _keep(self, word):
        """原始词是否保留（非停用词、非纯数字、非空）。"""
        return bool(word) and word not in self.stopwords \
            and not _PURE_NUMBER_RE.fullmatch(word)

    def tokenize(self, text, with_positions=False, with_originals=False):
        """中英文混合分词主入口。

        参数:
            text: 原始文本。
            with_positions: 同时返回词在 Token 流中的下标。
            with_originals: 同时返回每个 Token 的原始拼写（小写）。

        返回:
            tokens；加 with_positions -> (tokens, positions)；
            再加 with_originals -> (tokens, positions, originals)。
        """
        tokens = []
        positions = []
        originals = []
        for seg in self._split_mixed(text):
            if _ZH_SEG_RE.fullmatch(seg):
                # 中文：jieba 切分，原样保留（不做词干）
                for word in jieba.cut(seg):
                    word = word.strip().lower()
                    if self._keep(word):
                        positions.append(len(tokens))
                        tokens.append(word)
                        originals.append(word)
            else:
                # 英文：小写 -> 词干
                orig = seg.lower()
                if self._keep(orig):
                    positions.append(len(tokens))
                    tokens.append(self.stemmer.stem(orig))
                    originals.append(orig)
        if with_positions and with_originals:
            return tokens, positions, originals
        if with_positions:
            return tokens, positions
        if with_originals:
            return tokens, originals
        return tokens
