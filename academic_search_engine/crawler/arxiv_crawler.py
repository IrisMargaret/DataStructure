# -*- coding: utf-8 -*-
"""arXiv 爬虫：使用 arXiv 官方 Python 库采集论文元数据。

采集策略：
1. 按分类抓取最新论文：cs.AI / cs.LG / cs.CV / cs.CL / cs.NE；
2. 按主题关键词补充相关论文（transformer、graph neural network 等）；
3. 按 entry_id 去重，目标 >= min_papers（默认 150）。

所有网络操作均有异常捕获与重试，失败时打印警告而非中断。
"""

import json
import re
from pathlib import Path

import arxiv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPERS_PATH = PROJECT_ROOT / "data" / "papers.json"

# 采集目标分类
CATEGORIES = ["cs.AI", "cs.LG", "cs.CV", "cs.CL", "cs.NE"]

# 主题关键词（按相关度排序抓取）
TOPIC_QUERIES = [
    "transformer", "deep learning", "neural network", "graph neural network",
    "computer vision", "natural language processing", "reinforcement learning",
    "large language model", "recommender system", "data structure",
    "knowledge graph", "attention mechanism", "image classification",
    "object detection", "text generation",
]

# arXiv 编号（用于从 URL 中解析，如 https://arxiv.org/abs/1706.03762v3）
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")


class ArxivCrawler:
    """封装 arxiv 官方库的抓取逻辑。"""

    def __init__(self, min_papers=150, max_papers=300):
        self.min_papers = min_papers
        self.max_papers = max_papers
        # num_retries：网络重试次数；delay_seconds：请求间隔（礼貌抓取）
        self.client = arxiv.Client(num_retries=3, page_size=100,
                                   delay_seconds=3)

    def crawl(self, progress_cb=None):
        """执行采集，返回论文字典列表（已按 entry_id 去重）。"""
        seen = {}  # entry_id -> paper dict

        # 阶段 1：按分类抓取最新论文
        for cat in CATEGORIES:
            if len(seen) >= self.max_papers:
                break
            query = f"cat:{cat}"
            try:
                search = arxiv.Search(
                    query=query,
                    max_results=100,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                )
                for result in self.client.results(search):
                    self._collect(seen, result)
                    if progress_cb:
                        progress_cb(len(seen))
                    if len(seen) >= self.max_papers:
                        break
            except Exception as exc:  # 网络错误等，仅记录并继续
                print(f"[爬虫] 抓取分类 {cat} 失败: {exc}")

        # 阶段 2：按主题关键词补充
        for topic in TOPIC_QUERIES:
            if len(seen) >= self.max_papers:
                break
            try:
                search = arxiv.Search(
                    query=f'all:"{topic}"',
                    max_results=50,
                    sort_by=arxiv.SortCriterion.Relevance,
                )
                for result in self.client.results(search):
                    self._collect(seen, result)
                    if progress_cb:
                        progress_cb(len(seen))
                    if len(seen) >= self.max_papers:
                        break
            except Exception as exc:
                print(f"[爬虫] 抓取主题 {topic} 失败: {exc}")

        return list(seen.values())

    def _collect(self, seen, result):
        """把一条 arXiv 记录规整为论文字典并去重。"""
        entry_id = result.entry_id or ""
        # 取 entry_id 末尾的 arXiv 编号，去掉版本号后缀
        match = ARXIV_ID_RE.search(entry_id)
        paper_id = match.group(1) if match else entry_id.rsplit("/", 1)[-1]
        if paper_id in seen:
            return
        seen[paper_id] = {
            "id": paper_id,
            "source_id": paper_id,
            "title": (result.title or "").replace("\n", " ").strip(),
            "abstract": (result.summary or "").replace("\n", " ").strip(),
            "authors": [a.name for a in (result.authors or [])],
            "year": result.published.year if result.published else None,
            "language": "en",
            "source": "arxiv",
        }

    def save(self, papers, path=PAPERS_PATH):
        """把论文列表写入 JSON 文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(papers, fh, ensure_ascii=False, indent=2)
        print(f"[爬虫] 已保存 {len(papers)} 篇论文 -> {path}")


def load_papers(path=PAPERS_PATH):
    """读取 data/papers.json；文件缺失或损坏时返回空列表。"""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        print(f"[爬虫] 警告：无法读取 {path}，将重新采集")
        return []


def merge_by_id(old, new):
    """按论文 id 合并新旧列表（旧数据优先保留）。"""
    merged = {p.get("id"): p for p in old if p.get("id")}
    for p in new:
        merged.setdefault(p.get("id"), p)
    return list(merged.values())


def ensure_papers(min_papers=150, progress_cb=None, path=PAPERS_PATH):
    """确保数据文件存在且论文数 >= min_papers，否则自动爬取。"""
    papers = load_papers(path)
    if len(papers) >= min_papers:
        return papers
    print(f"[爬虫] 当前论文数 {len(papers)} < {min_papers}，开始自动采集...")
    crawler = ArxivCrawler(min_papers=min_papers)
    fetched = crawler.crawl(progress_cb=progress_cb)
    merged = merge_by_id(papers, fetched)
    crawler.save(merged, path)
    return merged


def fetch_batch(limit=500, progress_cb=None, pages=None):
    """注册表接口：抓取一批 arXiv 论文（分类 + 主题，已按 id 去重）。"""
    crawler = ArxivCrawler(min_papers=1, max_papers=limit)
    return crawler.crawl(progress_cb=progress_cb)


def fetch_by_arxiv_id(url_or_id):
    """根据 arXiv 编号或 URL（如 https://arxiv.org/abs/1706.03762）获取单篇。

    用于“输入 URL 动态添加论文”。找不到时返回 None。
    """
    match = ARXIV_ID_RE.search(url_or_id or "")
    arxiv_id = match.group(1) if match else (url_or_id or "").strip()
    if not arxiv_id:
        return None
    try:
        client = arxiv.Client(num_retries=2)
        search = arxiv.Search(id_list=[arxiv_id])
        for result in client.results(search):
            item = {
                "id": arxiv_id,
                "title": (result.title or "").replace("\n", " ").strip(),
                "abstract": (result.summary or "").replace("\n", " ").strip(),
                "authors": [a.name for a in (result.authors or [])],
                "year": result.published.year if result.published else None,
            }
            return item
    except Exception as exc:
        print(f"[爬虫] 按 arXiv ID 获取失败 {arxiv_id}: {exc}")
    return None


if __name__ == "__main__":
    # 命令行直接运行：python -m crawler.arxiv_crawler
    ensure_papers(min_papers=150)
