# -*- coding: utf-8 -*-
"""论文拆解 Agent：在规则拆解基础上用大模型精修元数据。

refine_metadata(raw_text, heuristic) -> (meta, ai_used)：
- 未配置 .env / 调用失败 -> 原样返回规则结果，ai_used=False；
- 成功 -> 逐字段校验并合并（模型结果优先），ai_used=True。

校验只做类型与长度约束，保证进入索引的数据结构稳定。
"""

import re

from . import llm, prompts


def refine_metadata(raw_text, heuristic):
    """精修元数据（标题/摘要/作者/年份/关键词）。

    参数:
        raw_text:   论文原始文本（可能为空）。
        heuristic:  规则拆解得到的 meta 字典。
    返回:
        (meta, ai_used)
    """
    if not llm.is_configured() or not (raw_text or "").strip():
        return heuristic, False

    user = prompts.USER_TEMPLATE.format(
        text=(raw_text or "")[:prompts.MAX_TEXT_CHARS])
    answer = llm.chat_json(prompts.SYSTEM_PROMPT, user)
    if not isinstance(answer, dict):
        return heuristic, False

    meta = dict(heuristic)
    raw = (raw_text or "")[:prompts.MAX_TEXT_CHARS]
    # 原文是否存在显式摘要标记（摘要/Abstract/Summary）
    has_marker = bool(re.search(r"摘要|Abstract|Summary", raw[:4000]))
    # 标题不得是章节标题或纯数字（如 “1 Introduction”/“2019”）
    heading = re.compile(r"^\d{1,2}\s*[.、]?\s+[A-Za-z\u4e00-\u9fff]|"
                         r"^\d{4}$|"
                         r"^(introduction|abstract|references|background)\b",
                         re.IGNORECASE)
    title = str(answer.get("title") or "").strip()
    if 4 <= len(title) <= 150 and not heading.match(title):
        meta["title"] = title

    abstract = str(answer.get("abstract") or "").strip()
    # 仅当原文确有摘要标记且模型摘要足够长、非引言式开头才采信，
    # 防止“无摘要却拿引言/臆造内容”充数
    if has_marker and len(abstract) >= 60 \
            and not _looks_like_intro(abstract):
        meta["abstract"] = abstract[:3000]

    authors = answer.get("authors")
    if isinstance(authors, list):
        cleaned = [str(a).strip() for a in authors
                   if str(a).strip() and len(str(a).strip()) >= 2]
        if cleaned:
            meta["authors"] = cleaned[:10]

    year = answer.get("year")
    if isinstance(year, int) and 1900 <= year <= 2100:
        meta["year"] = year

    keywords = _clean_keywords(answer.get("keywords"))
    # 关键词仅当论文确有摘要/标题内容时才采纳（防纯引言噪声词）
    if keywords and (meta["abstract"] or meta["title"]):
        meta["agent_keywords"] = keywords
    return meta, True


def _looks_like_intro(text):
    """摘要是否以引言式开头（应拒绝）。"""
    head = (text or "").strip()[:60]
    return bool(re.match(r"^(引言|introduction|we present|in this (paper|work)"
                         r"|this (paper|work) (presents|proposes|introduces))",
                         head, re.IGNORECASE))


def _clean_keywords(raw):
    """清洗关键词：字符串/长度/纯数字/标点过滤，剔除泛词，至多 8 个。"""
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw:
        word = str(item or "").strip().strip("。，,;； ")
        if not 2 <= len(word) <= 40 or word.isdigit():
            continue
        if word.lower() in prompts.GENERIC_WORDS:
            continue
        if word not in cleaned:
            cleaned.append(word)
        if len(cleaned) >= 8:
            break
    return cleaned
