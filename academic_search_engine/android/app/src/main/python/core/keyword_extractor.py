# -*- coding: utf-8 -*-
"""论文关键词自动提取（TF-IDF 加权法）。

对单篇论文：候选词来自标题与摘要（标题命中权重 ×2），
score(term) = 篇内词频 × log((总文档数+1)/(文档频率+1)+1)，
取 Top K 返回**原始拼写**（便于展示，中文词无需词干）。

该算法同样服务于“把每篇论文的 N 个主题词作为可检索文本入索引”，
从而显著提升检索召回。
"""

import math
from collections import Counter


class KeywordExtractor:
    """基于语料 IDF 的单篇论文关键词提取器。"""

    TITLE_WEIGHT = 2.0  # 标题中出现的词权重更高
    ABSTRACT_WEIGHT = 1.0
    MIN_LEN = 2         # 过滤单字符噪音

    def __init__(self, preprocessor):
        self.preprocessor = preprocessor

    def extract(self, title, abstract, total_docs, df_lookup, top_k=8):
        """提取论文关键词（原始拼写，按分数降序，至多 top_k 个）。

        参数:
            title/abstract: 论文标题与摘要原文。
            total_docs: 语料论文总数（用于 IDF）。
            df_lookup: 函数 stem -> 文档频率（未收录返回 0）。
        """
        # stem -> [加权得分, 原始拼写频次]
        scores = {}

        def add_section(text, weight):
            tokens, originals = self.preprocessor.tokenize(
                text, with_originals=True)
            for stem, orig in zip(tokens, originals):
                if len(stem) < self.MIN_LEN:
                    continue
                entry = scores.setdefault(stem, [0.0, Counter()])
                entry[0] += weight
                entry[1][orig] += 1

        add_section(title, self.TITLE_WEIGHT)
        add_section(abstract, self.ABSTRACT_WEIGHT)
        if not scores:
            return []

        ranked = []
        for stem, (weighted_tf, origs) in scores.items():
            df = df_lookup(stem)
            idf = math.log((total_docs + 1) / (df + 1)) + 1
            best_orig = origs.most_common(1)[0][0]
            ranked.append((weighted_tf * idf, best_orig, stem))
        # 分数降序，同分按词条字典序保证稳定
        ranked.sort(key=lambda item: (-item[0], item[2]))

        picked = []
        for _, orig, _stem in ranked:
            if orig not in picked:
                picked.append(orig)
            if len(picked) >= top_k:
                break
        return picked
