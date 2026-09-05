# -*- coding: utf-8 -*-
"""论文实体类。

封装一篇论文的元数据：内部 ID、外部来源 ID、标题、摘要、作者列表、
发表年份、自动提取的关键词，以及原文文件（file_name/file_store）与
语言/来源标记（language/source）。字段与 data/papers.json 一一对应，
全部向后兼容历史数据（缺失字段取默认值）。
"""

import re
import unicodedata

# 内容键归一化：折叠标点/空白为单个空格后小写化
_PUNCT_SPACE_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_text(text):
    """把文本规范化为可比较的紧凑形式（NFKC + 小写 + 折叠空白）。"""
    text = unicodedata.normalize("NFKC", text or "")
    return _PUNCT_SPACE_RE.sub(" ", text).strip().lower()


def paper_content_key(title, abstract, authors=None, year=None):
    """生成“内容完全一致”判定键（严格去重用）。

    规范化后 标题 + 作者（排序）+ 年份 + 摘要 四项全部一致才视为同一篇。
    同名不同文 / 同文不同措辞均不会误判。
    """
    author_list = authors if isinstance(authors, (list, tuple)) else []
    author_key = tuple(sorted(normalize_text(a) for a in author_list
                              if str(a).strip()))
    return (
        normalize_text(title),
        author_key,
        int(year) if isinstance(year, int) else None,
        normalize_text(abstract),
    )


# arXiv 编号形态（如 1706.03762 或带版本）
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


def _arxiv_url(paper_id):
    """arXiv 编号 -> 详情页链接。"""
    return f"https://arxiv.org/abs/{paper_id}"


class Paper:
    """论文实体：ID / Title / Abstract / Authors / Year / Keywords。"""

    def __init__(self, paper_id, title, abstract, authors=None, year=None,
                 source_id=None, keywords=None, file_name=None,
                 file_store=None, language=None, source=None):
        # paper_id 为内部使用的整数 ID（倒排索引 Posting 引用它）
        self.paper_id = paper_id
        # source_id 为外部来源 ID（如 arXiv 编号 / DOI），用于结果页链接
        self.source_id = source_id
        self.title = (title or "").strip()
        self.abstract = (abstract or "").strip()
        # 作者：始终规范化为字符串列表
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        self.authors = list(authors or [])
        self.year = year
        self.keywords = list(keywords or [])
        # 原文文件：展示名 + 相对 data/ 的落盘路径
        self.file_name = file_name
        self.file_store = file_store
        # 语言（zh/en）与来源（arxiv/openalex/upload/manual/url）
        self.language = language
        self.source = source

    @classmethod
    def from_dict(cls, data, paper_id=None):
        """从字典构造 Paper（兼容 data/papers.json 中的记录）。"""
        raw_id = data.get("id", data.get("paper_id"))
        source_id = data.get("source_id")
        # 优先使用整数 id 作为内部 ID；否则退化为外部来源 ID
        if isinstance(raw_id, int):
            pid = raw_id
            if source_id is None:
                source_id = str(raw_id)
        else:
            pid = paper_id
            if source_id is None:
                source_id = raw_id
        authors = data.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        keywords = data.get("keywords") or data.get("tags") or []
        return cls(
            paper_id=pid,
            title=data.get("title", ""),
            abstract=data.get("abstract", ""),
            authors=authors,
            year=data.get("year"),
            source_id=source_id,
            keywords=keywords,
            file_name=data.get("file_name"),
            file_store=data.get("file_store"),
            language=data.get("language"),
            source=data.get("source"),
        )

    def external_url(self):
        """推导可点击的文献外链（arXiv / DOI / 其他 http 来源）。

        优先级：
        1. source_id 本身是完整 http(s) 链接（OpenAlex 的 DOI 或 OpenAlex ID）
           -> 原样返回；
        2. source_id 是 arXiv 编号 -> https://arxiv.org/abs/<id>；
        3. 其余返回 None（本地文件文献可经 file_store 阅读原文）。
        """
        sid = (self.source_id or "").strip()
        if not sid:
            return None
        if sid.lower().startswith(("http://", "https://")):
            return sid
        if _ARXIV_ID_RE.match(sid):
            return _arxiv_url(sid)
        return None

    def to_dict(self):
        """序列化为字典，便于写回 data/papers.json。"""
        return {
            "id": self.paper_id,
            "source_id": self.source_id,
            "url": self.external_url(),
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "keywords": self.keywords,
            "file_name": self.file_name,
            "file_store": self.file_store,
            "language": self.language,
            "source": self.source,
        }

    def content_key(self):
        """本论文的内容键（严格去重用，与 paper_content_key 一致）。"""
        return paper_content_key(self.title, self.abstract, self.authors,
                                 self.year)

    def __repr__(self):
        return f"<Paper id={self.paper_id} title={self.title[:40]!r}>"
