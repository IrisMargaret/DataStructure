# -*- coding: utf-8 -*-
"""OpenAlex 开放获取文献源（免 key）。

- 按主题搜索 works（中英主题混合，中文主题走 language:zh 过滤）；
- 每个主题**翻多页**抓取以发现更多不同论文（同 query 反复抓同一批
  是“二次爬取新增为 0”的根源，翻页可显著缓解）；
- 摘要由 abstract_inverted_index 重建（部分中文期刊无摘要，属数据源现状）；
- 网络失败只记录并继续，不影响其他源与其他主题。
"""

import requests

API = "https://api.openalex.org/works"
PAGE_SIZE = 50

# (主题, 语言过滤)
TOPICS = [
    ("图神经网络", "zh"), ("卷积神经网络", "zh"), ("大语言模型", "zh"),
    ("图像分类", "zh"), ("目标检测", "zh"), ("推荐系统", "zh"),
    ("注意力机制", "zh"), ("知识图谱", "zh"), ("强化学习", "zh"),
    ("transformer", "en"), ("graph neural network", "en"),
    ("large language model", "en"), ("retrieval augmented generation", "en"),
    ("contrastive learning", "en"), ("diffusion model", "en"),
]


def _rebuild_abstract(inverted):
    """由 abstract_inverted_index 重建摘要文本。"""
    if not inverted:
        return ""
    words = [(pos, w) for w, positions in inverted.items()
             for pos in positions]
    words.sort()
    return " ".join(w for _, w in words)


def _to_paper(item):
    """OpenAlex work -> 归一化论文字典。"""
    title = (item.get("title") or "").strip()
    authors = [a.get("author", {}).get("display_name", "")
               for a in (item.get("authorships") or [])]
    authors = [a for a in authors if a][:10]
    doi = item.get("doi") or ""
    oid = item.get("id") or ""
    return {
        "id": doi.rsplit("/", 1)[-1] if doi else oid.rsplit("/", 1)[-1],
        "source_id": doi or oid,
        "title": title,
        "abstract": _rebuild_abstract(item.get("abstract_inverted_index")),
        "authors": authors,
        "year": item.get("publication_year"),
        "language": item.get("language"),
        "source": "openalex",
    }


def fetch_batch(limit=600, progress_cb=None, pages=2):
    """按主题翻页采集（中英主题混合），已去重；失败主题跳过。"""
    seen = {}
    per_topic = max(limit // len(TOPICS), 10)

    for topic, lang in TOPICS:
        if len(seen) >= limit:
            break
        for page in range(1, pages + 1):
            if len(seen) >= limit:
                break
            params = {
                "search": topic,
                "per-page": min(per_topic, PAGE_SIZE),
                "page": page,
                "select": ("id,doi,title,authorships,publication_year,"
                           "abstract_inverted_index,language"),
            }
            if lang == "zh":
                params["filter"] = "language:zh"
            try:
                resp = requests.get(API, params=params, timeout=20)
                if resp.status_code != 200:
                    print(f"[OpenAlex] {topic} 第{page}页返回 "
                          f"{resp.status_code}，跳过")
                    break
                results = resp.json().get("results", [])
                for item in results:
                    paper = _to_paper(item)
                    if paper["title"] and paper["id"] not in seen:
                        seen[paper["id"]] = paper
                if progress_cb:
                    progress_cb(len(seen))
                if len(results) < PAGE_SIZE:
                    break  # 已到末页
            except requests.RequestException as exc:
                print(f"[OpenAlex] 抓取主题 {topic} 第{page}页失败：{exc}")
                break

    return list(seen.values())
