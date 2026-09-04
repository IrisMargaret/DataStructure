# -*- coding: utf-8 -*-
"""倒排索引：构建、检索、TF-IDF 计算（核心手写实现）。

核心数据结构：Map<Key, List<Posting>>（dict: term -> List[Posting]），
Posting 包含 (PaperID, TermFrequency, PositionList)。

特性：
- 词干化一致：索引键为词干（transformer/transformers -> transform），
  并记录 term_display 原词映射供界面展示；
- 关键词入索引：入库文本 = 标题 + 摘要 + 自动提取关键词；
- AND 检索：优先对最短 Posting List 两两归并，复杂度 O(n)；
- 相关性排序：TF 求和 或 TF-IDF 加权（IDF = log((N+1)/(df+1)) + 1）；
- 布尔查询：AND/OR/NOT 与括号（递归下降解析 + 集合运算）；
- 引号短语：基于 PositionList 的相邻位置校验（中英文均适用）；
- 检索剖析 trace：返回各词 df、Posting 长度与归并顺序，供教学演示。
"""

import math
from collections import Counter, defaultdict

from .preprocessor import Preprocessor
from .query_parser import (QueryParser, QuerySyntaxError, collect_terms,
                           evaluate_ast)


class Posting:
    """倒排表项：论文 ID + 词频 + 出现位置列表。"""

    __slots__ = ("paper_id", "tf", "positions")

    def __init__(self, paper_id, tf, positions):
        self.paper_id = paper_id
        self.tf = tf
        self.positions = list(positions)

    def to_dict(self):
        return {
            "paper_id": self.paper_id,
            "tf": self.tf,
            "positions": self.positions,
        }


class InvertedIndex:
    """term -> List[Posting] 的倒排索引，附带论文注册表与检索方法。"""

    def __init__(self, preprocessor=None):
        self.preprocessor = preprocessor or Preprocessor()
        self.index = {}        # term -> List[Posting]
        self.term_display = {}  # term -> Counter(原始拼写)
        self.papers = {}       # paper_id(int) -> Paper
        self._next_id = 0      # 下一个可分配的论文内部 ID

    # ---------------- 构建 ----------------

    def next_id(self):
        """返回下一个可用的论文内部 ID（不消耗）。"""
        return self._next_id

    @staticmethod
    def _index_text(paper):
        """一篇论文参与索引的文本：标题 + 摘要 + 关键词。"""
        parts = [paper.title, paper.abstract]
        if paper.keywords:
            parts.append(" ".join(paper.keywords))
        return "\n".join(parts)

    def add_paper(self, paper):
        """增量添加一篇论文并更新倒排索引（支持动态入库）。"""
        if paper.paper_id in self.papers:
            return paper
        self.papers[paper.paper_id] = paper
        self._next_id = max(self._next_id, paper.paper_id + 1)

        text = self._index_text(paper)
        tokens, positions, originals = self.preprocessor.tokenize(
            text, with_positions=True, with_originals=True)

        # 按词干聚合位置列表
        pos_map = defaultdict(list)
        for token, pos in zip(tokens, positions):
            pos_map[token].append(pos)
        for term, poss in pos_map.items():
            self.index.setdefault(term, []).append(
                Posting(paper.paper_id, len(poss), poss))

        # 登记“词干 -> 原始拼写”频次，用于界面展示
        for token, orig in zip(tokens, originals):
            self.term_display.setdefault(token, Counter())[orig] += 1
        return paper

    def build(self, papers):
        """从论文列表（Paper 对象）重建整个索引。"""
        self.index = {}
        self.term_display = {}
        self.papers = {}
        self._next_id = 0
        for paper in papers:
            self.add_paper(paper)

    # ---------------- 统计与快照 ----------------

    def stats(self):
        """统计信息：总论文数、唯一关键词数、索引总项数。"""
        return {
            "total_papers": len(self.papers),
            "unique_terms": len(self.index),
            "total_postings": sum(len(lst) for lst in self.index.values()),
        }

    def display(self, term):
        """返回词干 term 的最常见原始拼写（供展示），无记录时原样返回。"""
        counter = self.term_display.get(term)
        return counter.most_common(1)[0][0] if counter else term

    def index_snapshot(self, limit=20):
        """倒排索引原始结构：前 limit 个词项（按文档频率降序）。"""
        items = sorted(self.index.items(), key=lambda kv: len(kv[1]),
                       reverse=True)
        return {
            "stats": self.stats(),
            "terms": [
                {
                    "term": term,
                    "display": self.display(term),
                    "df": len(postings),
                    "postings": [p.to_dict() for p in postings],
                }
                for term, postings in items[:limit]
            ],
        }

    # ---------------- 检索 ----------------

    def get_postings(self, term):
        """返回某词的 Posting 列表（不存在时返回空列表）。"""
        return self.index.get(term, [])

    def _term_docs(self, term):
        """词条映射：普通词 -> {pid: (tf, positions)}；
        含空格的引号短语 -> 短语位置匹配结果。"""
        if " " in term:
            return self._phrase_docs(term)
        return {p.paper_id: (p.tf, p.positions)
                for p in self.get_postings(term)}

    def _phrase_docs(self, phrase):
        """短语匹配：返回包含该短语（相邻连续出现）的论文映射。

        短语先经同一分词管线切成词干序列，再校验各词在文档 Token 流
        中的位置严格连续（第 i 个词须含位置 p + i）。
        """
        words = self.preprocessor.tokenize(phrase)
        if not words:
            return {}
        if len(words) == 1:
            return self._term_docs(words[0])
        maps = [self._term_docs(w) for w in words]
        candidates = set.intersection(*[set(m.keys()) for m in maps])
        result = {}
        for pid in candidates:
            starts = [pos for pos in maps[0][pid][1]
                      if all((pos + i) in maps[i][pid][1]
                             for i in range(1, len(words)))]
            if starts:
                result[pid] = (len(starts), starts)
        return result

    def search(self, query, mode="tf", top_k=50):
        """统一检索入口：自动识别布尔表达式，否则按多关键词 AND 检索。"""
        if self._looks_boolean(query):
            return self.search_boolean(query, mode=mode, top_k=top_k)
        return self.search_keywords(query, mode=mode, top_k=top_k)

    @staticmethod
    def _looks_boolean(query):
        """启发式判断是否为布尔表达式。"""
        q = (query or "").strip()
        if not q:
            return False
        upper = f" {q.upper()} "
        return (" AND " in upper or " OR " in upper or " NOT " in upper
                or "(" in q or ")" in q or '"' in q)

    def search_keywords(self, query, mode="tf", top_k=50):
        """多关键词 AND 检索：最短 Posting List 优先两两归并，O(n)。"""
        terms = self.preprocessor.tokenize(query)
        terms = list(dict.fromkeys(terms))  # 去重且保序

        # 词条信息（供评分与 trace 使用）
        infos = []
        for term in terms:
            postings = self.get_postings(term)
            infos.append({
                "term": term,
                "display": self.display(term),
                "df": len(postings),
                "postings": postings,
                "map": {p.paper_id: (p.tf, p.positions) for p in postings},
            })

        if not terms or any(info["df"] == 0 for info in infos):
            # 任一关键词缺失 -> 交集为空
            return self._wrap(query, mode, "keywords", [],
                              self._trace(infos, query_type="keywords"))

        # 核心归并：按列表长度升序，从最短列表开始两两求交
        merged = self._intersect_lists([i["postings"] for i in infos])
        paper_ids = [p.paper_id for p in merged]
        maps = {i["term"]: i["map"] for i in infos}
        results = self._rank(paper_ids, maps, mode)
        return self._wrap(query, mode, "keywords", results,
                          self._trace(infos, query_type="keywords",
                                      lengths=[len(i["postings"])
                                               for i in infos]),
                          top_k=top_k)

    def search_boolean(self, query, mode="tf", top_k=50):
        """复杂布尔查询：解析 AST -> 集合运算求值 -> 相关性排序。"""
        try:
            ast = QueryParser(query).parse()
        except QuerySyntaxError as exc:
            return {
                "query": query, "query_type": "boolean", "mode": mode,
                "error": str(exc), "count": 0, "results": [],
                "trace": {"strategy": f"解析失败：{exc}"},
            }

        universe = set(self.papers.keys())
        paper_ids = evaluate_ast(
            ast, lambda t: set(self._leaf_docs(t).keys()), universe)

        # 叶子词先经分词管线（词干化），保证与索引键一致；
        # maps 以叶子原词为键，评分/展示使用查询原词
        terms = collect_terms(ast)
        maps = {t: self._leaf_docs(t) for t in terms}
        results = self._rank(sorted(paper_ids), maps, mode)

        trace = {
            "strategy": "布尔集合运算：AND->交集 &，OR->并集 |，"
                        "NOT->全集差集 -",
            "ast": self._ast_str(ast),
        }
        return self._wrap(query, mode, "boolean", results, trace,
                          top_k=top_k)

    def _leaf_docs(self, raw):
        """把布尔叶子词（原词）规范化为索引键并返回 {pid: (tf, positions)}。

        - 引号短语：保持相邻位置匹配（_term_docs 内已分词规范化）；
        - 普通词：先分词/词干化（learning -> learn）再查倒排表；
        - 中文等被切成多词的叶子（如 神经网络 -> 神经|网络）：各词干
          文档取交集、词频求和，语义等价于组合词。
        """
        raw = (raw or "").strip()
        if not raw:
            return {}
        if " " in raw:
            return self._term_docs(raw)
        stems = self.preprocessor.tokenize(raw)
        if not stems:
            return {}
        if len(stems) == 1:
            return self._term_docs(stems[0])
        maps = [self._term_docs(s) for s in stems]
        common = set.intersection(*[set(m) for m in maps])
        return {pid: (sum(m[pid][0] for m in maps), maps[0][pid][1])
                for pid in common}

    # ---------------- 评分（TF / TF-IDF） ----------------

    def _rank(self, paper_ids, maps, mode):
        """对候选论文按词条映射评分并降序排列。

        maps: {term: {paper_id: (tf, positions)}}；
        mode: "tf" 词频求和 | "tfidf" TF*IDF 加权求和。
        """
        total_docs = len(self.papers)
        results = []
        for pid in paper_ids:
            matched = []
            score = 0.0
            for term, doc_map in maps.items():
                entry = doc_map.get(pid)
                if entry is None:
                    continue
                tf, poss = entry
                if mode == "tfidf":
                    df = len(doc_map)
                    score += tf * (math.log((total_docs + 1) / (df + 1)) + 1)
                else:
                    score += tf
                matched.append({
                    "term": term,
                    "display": self.display(term) if " " not in term else term,
                    "tf": tf,
                    "positions": poss[:30],
                })
            paper = self.papers[pid]
            results.append({
                "paper_id": paper.paper_id,
                "source_id": paper.source_id,
                "url": paper.external_url(),
                "title": paper.title,
                "abstract": paper.abstract,
                "authors": paper.authors,
                "year": paper.year,
                "keywords": paper.keywords,
                "file_name": paper.file_name,
                "language": paper.language,
                "source": paper.source,
                "score": round(score, 4),
                "matched_terms": matched,
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def search_union(self, query, terms, mode="tf", top_k=50,
                     translations=None):
        """按词条并集检索（跨语言扩展用）：命中任一扩展词即入候选，
        再按 TF / TF-IDF 相关性排序；terms 已是索引键（词干/分词键）。"""
        maps = {}
        for term in terms:
            docs = self._term_docs(term)
            if docs:
                maps[term] = docs
        if not maps:
            return self._wrap(query, mode, "cross", [], {})
        paper_ids = set()
        for doc_map in maps.values():
            paper_ids.update(doc_map)
        results = self._rank(sorted(paper_ids), maps, mode)
        trace = {
            "query_type": "cross",
            "strategy": "跨语言扩展：原词 ∪ 同义词（任一命中即候选，"
                        "按相关性降序）",
            "terms": [{"term": t, "display": self.display(t),
                       "df": len(m)} for t, m in maps.items()],
            "translations": translations or {},
        }
        return self._wrap(query, mode, "cross", results, trace, top_k)

    # ---------------- 归并核心 ----------------

    @staticmethod
    def _intersect_lists(lists):
        """多路交集归并：按长度升序，从最短列表开始两两归并。"""
        if not lists:
            return []
        lists = sorted(lists, key=len)
        result = lists[0]
        for other in lists[1:]:
            result = InvertedIndex._merge_two(result, other)
            if not result:
                break
        return result

    @staticmethod
    def _merge_two(a, b):
        """双指针归并两个已按 paper_id 升序的 Posting 列表，返回交集。"""
        i = j = 0
        out = []
        while i < len(a) and j < len(b):
            pa, pb = a[i], b[j]
            if pa.paper_id < pb.paper_id:
                i += 1
            elif pa.paper_id > pb.paper_id:
                j += 1
            else:
                out.append(pa)
                i += 1
                j += 1
        return out

    # ---------------- 检索剖析 trace ----------------

    @staticmethod
    def _trace(infos, query_type, lengths=None):
        """生成教学演示用的检索剖析数据。"""
        ordered = sorted(lengths) if lengths else \
            sorted(i["df"] for i in infos)
        terms = [
            {"term": i["term"], "display": i["display"], "df": i["df"]}
            for i in infos
        ]
        strategy = ("关键词 AND：各词 Posting 列表长度 " +
                    "，".join(str(i["df"]) for i in infos) +
                    "；按长度升序归并 " + " → ".join(map(str, ordered)))
        return {"query_type": query_type, "terms": terms,
                "merge_order": ordered, "strategy": strategy}

    @staticmethod
    def _ast_str(node, indent=0):
        """把布尔 AST 渲染为缩进文本（教学展示）。"""
        pad = "  " * indent
        kind = node[0]
        if kind == "term":
            return f"{pad}词条: {node[1]}"
        op = {"and": "AND ∩", "or": "OR ∪", "not": "NOT −"}[kind]
        if kind == "not":
            return f"{pad}{op}\n{InvertedIndex._ast_str(node[1], indent + 1)}"
        return (f"{pad}{op}\n{InvertedIndex._ast_str(node[1], indent + 1)}\n"
                f"{InvertedIndex._ast_str(node[2], indent + 1)}")

    @staticmethod
    def _wrap(query, mode, query_type, results, trace, top_k=None):
        """统一结果包装：count 为真实命中数，results 按 top_k 截断。"""
        total = len(results)
        if top_k is not None:
            results = results[:top_k]
        return {
            "query": query,
            "query_type": query_type,
            "mode": mode,
            "count": total,
            "results": results,
            "trace": trace,
        }
