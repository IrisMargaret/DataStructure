# -*- coding: utf-8 -*-
"""Trie 树：输入前缀的模糊提示（自动补全）。

每个节点保存：
- children：字符 -> 子节点 的字典；
- freq    ：若该节点恰好是一个完整词，则累加该词在语料库中的总词频，
            否则为 0。

查询前缀时深度优先收集所有以该前缀开头的完整词，按词频降序返回 Top K。
"""


class TrieNode:
    """Trie 节点：子节点字典 + 词频计数器。"""

    __slots__ = ("children", "freq")

    def __init__(self):
        self.children = {}  # str -> TrieNode
        self.freq = 0       # 完整词的累计词频；中间节点恒为 0


class Trie:
    """前缀树，支持插入词条与按前缀查询 Top K。"""

    def __init__(self):
        self.root = TrieNode()

    def insert(self, word, freq=1):
        """插入一个词条，词频累加 freq。"""
        node = self.root
        for ch in word:
            node = node.children.setdefault(ch, TrieNode())
        node.freq += freq

    def build_from_index(self, index):
        """根据倒排索引重建 Trie。

        词条 = 索引中的全部关键词；
        词频 = 该词在所有论文中出现的总次数（各 Posting 的 TF 之和）。
        """
        self.root = TrieNode()
        for term, postings in index.index.items():
            total_tf = sum(p.tf for p in postings)
            self.insert(term, total_tf)

    def _find_prefix_node(self, prefix):
        """沿前缀逐字符下钻，返回前缀末端节点（不存在则返回 None）。"""
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def _collect(self, node, prefix, acc):
        """深度优先遍历，收集以 prefix 为前缀的所有完整词。"""
        if node.freq > 0:
            acc.append((prefix, node.freq))
        for ch, child in node.children.items():
            self._collect(child, prefix + ch, acc)

    def suggest(self, prefix, top_k=10):
        """返回前 top_k 个以 prefix 为前缀的词，按词频降序。"""
        prefix = (prefix or "").strip().lower()
        if not prefix:
            return []
        node = self._find_prefix_node(prefix)
        if node is None:
            return []
        acc = []
        self._collect(node, prefix, acc)
        acc.sort(key=lambda item: item[1], reverse=True)  # 按词频降序
        return [{"term": word, "freq": freq} for word, freq in acc[:top_k]]
