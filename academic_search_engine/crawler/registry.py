# -*- coding: utf-8 -*-
"""开放获取数据源注册表 + 跨源严格去重合并。

- 每个源暴露 fetch_batch(limit, progress_cb, pages) -> [归一化论文字典]，
  字段：id/title/abstract/authors/year/language/source/source_id；
- merge_strict：仅“内容完全一致”（规范化标题+作者+年份+摘要全等）的
  论文才合并去重；同名不同文 / 同文不同措辞允许并存。
  返回 {"papers", "added", "skipped"} 供上层透明报告。
"""

from core.paper import paper_content_key

from . import arxiv_crawler, openalex_crawler

# 源名 -> 抓取函数
SOURCES = {
    "arxiv": arxiv_crawler.fetch_batch,
    "openalex": openalex_crawler.fetch_batch,
}


def fetch(source, limit=600, progress_cb=None, pages=2):
    """按源名抓取一批论文（未知源抛 ValueError）。"""
    if source not in SOURCES:
        raise ValueError(f"未知数据源：{source}（可选 {list(SOURCES)}）")
    return SOURCES[source](limit=limit, progress_cb=progress_cb, pages=pages)


def merge_strict(existing, fetched):
    """把 fetched 并入 existing（均为论文字典列表）。

    返回 {"papers": 合并列表, "added": 新增数, "skipped": 重复跳过数}。
    - existing 优先保留；
    - fetched 中内容键与库内任何一篇全等 -> 丢弃（跨源去重）；
    - 同源重抓（相同 source_id）同样只保留先入库者。
    """
    merged = {paper_content_key(p.get("title"), p.get("abstract"),
                                p.get("authors"), p.get("year")): p
              for p in existing}
    source_ids = {p.get("source_id") for p in existing if p.get("source_id")}
    added = 0
    for p in fetched:
        key = paper_content_key(p.get("title"), p.get("abstract"),
                                p.get("authors"), p.get("year"))
        if key in merged:
            continue
        if p.get("source_id") and p["source_id"] in source_ids:
            continue
        merged[key] = p
        if p.get("source_id"):
            source_ids.add(p["source_id"])
        added += 1
    return {"papers": list(merged.values()),
            "added": added,
            "skipped": len(fetched) - added}
