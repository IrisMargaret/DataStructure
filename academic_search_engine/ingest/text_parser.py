# -*- coding: utf-8 -*-
"""纯文本/标记文本论文的结构拆解（中英文通用，PDF 提取文本亦复用）。

对清洗后的行序列做规则识别：
- 标题：显式「标题/Title：」标记，或首个“像标题”的行；中文标题下的
  英文翻译行会被跳过；
- 作者：显式「作者/Author：」行，或紧随标题的合理作者行；
- 摘要：**只取 摘要/Abstract/Summary 标记段**；无显式摘要标记时，宁可
  返回空也不把 引言/Introduction 截进来（宁缺勿错，交由 AI 精修）；
- 年份：正文出现的合理年份（1990–2100）。

本模块只做规则拆解；乱码/低置信度由 document_parser 交给 Agent 精修。
"""

import re

from .clean_text import clean_text

_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,:;\-&'()/]*$")

_TITLE_LABEL = re.compile(r"^(title|题目|标题)\s*[:：]", re.IGNORECASE)
_AUTHOR_LABEL = re.compile(r"^(author|authors|作者|作者简介)\s*[:：]",
                           re.IGNORECASE)
# 摘要起始标记（容忍 摘 要 / 【摘要】 / 标签与正文同行）
_ABSTRACT_START = re.compile(
    r"^[【\[]?\s*(摘\s*要|内容提要|abstract|summary)\b",
    re.IGNORECASE)
# 摘要结束标记：关键词/中图分类号/引言/章节标题/参考文献等
_ABSTRACT_END = re.compile(
    r"^(关键词|key\s*words?|keywords?|中图分类号|引\s*言|"
    r"\d{1,2}\s*[.、]?\s*(引言|介绍|相关工作|introduction|related work)|"
    r"introduction|references|参考文献)", re.IGNORECASE)
# 无摘要标记时的“正文段落”终止符（章节标题等，含中英文编号标题）
_SECTION_HEAD = re.compile(
    r"^(引言|introduction|摘要|abstract|references|参考文献|"
    r"\d{1,2}\s*[.、]?\s*(引言|介绍|相关工作|相关工作|背景|background|"
    r"introduction|related\s*work|方法|method|结论|conclusion|实验|"
    r"experiment|结果|results)\b|^\d{1,2}\s*$)",
    re.IGNORECASE)
_MAX_ABSTRACT = 2400


def parse_text(text):
    """从纯文本拆解论文元数据。

    返回: {"title", "abstract", "authors", "year", "text"}
    """
    text = (text or "").strip()
    lines = [ln for ln in clean_text(text).splitlines() if ln.strip()]

    meta = {"title": "", "abstract": "", "authors": [], "year": None,
            "text": text}
    if not lines:
        return meta

    # ---------- 标题 ----------
    body = 0
    if _TITLE_LABEL.match(lines[0]):
        meta["title"] = _after_label(lines[0])
        body = 1
    else:
        for idx, line in enumerate(lines[:4]):
            if _ABSTRACT_START.match(line) or _is_noise_header(line):
                continue
            if _looks_like_title(line):
                meta["title"] = line[:200]
                body = idx + 1
                break
        # 中文标题下方常紧跟英文翻译标题——跳过该行（避免当作者）
        while body < len(lines) and _CJK.search(meta["title"]) \
                and _LATIN.fullmatch(lines[body]) \
                and len(lines[body]) <= 200 \
                and not _AUTHOR_LABEL.match(lines[body]):
            body += 1

    # ---------- 作者 ----------
    for idx in range(body, min(body + 4, len(lines))):
        line = lines[idx]
        if _AUTHOR_LABEL.match(line):
            meta["authors"] = _split_authors(_after_label(line))
            body = idx + 1
            break
        if idx == body and meta["title"] and _looks_like_author(line,
                                                                meta["title"]):
            meta["authors"] = _split_authors(line)
            body = idx + 1
            break

    # ---------- 摘要（只取显式摘要段；不截引言） ----------
    meta["abstract"] = _extract_abstract(lines, body)

    # ---------- 年份 ----------
    years = [int(y) for y in _YEAR_RE.findall(text) if 1990 <= int(y) <= 2100]
    meta["year"] = max(set(years), key=years.count) if years else None
    return meta


def _extract_abstract(lines, body):
    """定位显式摘要标记段；缺失时尝试取第一个正文段落，仍无则返回空。"""
    start = None
    inline = ""
    for idx in range(body, len(lines)):
        m = _ABSTRACT_START.match(lines[idx])
        if m:
            start = idx
            inline = lines[idx][m.end():].lstrip(":： \t-")
            break
    if start is not None:
        buf = [inline] if inline else []
        for line in lines[start + 1:]:
            if _ABSTRACT_END.match(line):
                break
            if _YEAR_RE.fullmatch(line):
                continue          # 孤立年份行不入摘要
            buf.append(line)
            if sum(len(b) for b in buf) > _MAX_ABSTRACT:
                break
        abstract = " ".join(buf).strip()
        return abstract[:_MAX_ABSTRACT]
    # 无显式摘要标记：取首个“正文自然段”，若以章节标题开头则返回空
    return _first_prose_paragraph(lines, body)


def _first_prose_paragraph(lines, start):
    """收集首个正文自然段；以标题行开头或内容过短则返回空。"""
    buf = []
    for line in lines[start:]:
        if _SECTION_HEAD.match(line):
            break
        buf.append(line)
        if sum(len(b) for b in buf) > 600:
            break
    return " ".join(buf).strip()[: _MAX_ABSTRACT] if buf else ""


# ---------------- 判定辅助 ----------------

def _is_noise_header(line):
    """期刊名/卷期/会议信息等头行（不该当标题）。"""
    return bool(re.search(
        r"(journal|proceedings|conference|vol\.?\s*\d+|"
        r"no\.?\s*\d+|pp?\.?\s*\d+|issn|doi)", line, re.IGNORECASE))


def _looks_like_title(line):
    """中英文标题判据：长度 4~200，非小写句首的整段散文；排除章节标题行
    （如 “1 Introduction”、“2. 相关工作”）。"""
    if not 4 <= len(line) <= 200 or line.isdigit():
        return False
    if re.match(r"^\d{1,2}\s*[.、]?\s+[A-Za-z\u4e00-\u9fff]", line) \
            or _SECTION_HEAD.match(line):
        return False
    if _CJK.search(line):
        return True
    if not _LATIN.fullmatch(line):
        return False
    return line[0].isupper() or line[0].isdigit()


def _looks_like_author(line, title):
    """作者行判据：显式标签/含中文/含分隔符；中文标题下的英文整行
    视为翻译标题而非作者，避免误判。"""
    if not line or len(line) > 120:
        return False
    if _AUTHOR_LABEL.match(line):
        return True
    if _CJK.search(line):
        return True
    if re.search(r"[,，;；、]|\band\b", line, re.IGNORECASE):
        return True
    # 全英文单行：中文标题之后多为英文翻译标题，判为作者需保守
    return not _CJK.search(title)


def _after_label(line):
    """取「标签：内容」中的内容。"""
    return re.split(r"\s*[:：]\s*", line, maxsplit=1)[-1].strip()


def _split_authors(raw):
    """按逗号/分号/ and 拆作者列表，去掉编号与脚注。"""
    raw = re.sub(r"^\s*[\d*†‡#]+\s*", "", raw or "")
    parts = re.split(r"[,，;；、]|\band\b", raw)
    authors = [p.strip().strip("*†‡") for p in parts
               if p.strip() and len(p.strip()) >= 2]
    return authors[:10]
