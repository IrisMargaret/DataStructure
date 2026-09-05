# -*- coding: utf-8 -*-
"""统一文档拆解流水线（规则拆解 -> 可选 Agent 精修）。

parse_file(path, use_ai=False):
1. 按扩展名分派解析器（PDF / 纯文本）；
2. 规则拆解得到元数据并计算置信度（标题/摘要/作者/年份齐备程度）；
3. 若请求 AI 精修且已配置大模型（.env），交给 agent 精修字段；
4. 返回 {meta, confidence, ai_used}。

任何单点失败只影响该文件，由调用方（service）捕获并汇报。
"""

import re
from pathlib import Path

from . import pdf_extractor, text_parser
from .encodings import best_decode

TEXT_EXTS = {".txt", ".md", ".text", ".log", ".tex"}
PDF_EXTS = {".pdf"}
# 常见“摘要”标记（用于置信度判断）
_ABSTRACT_START = re.compile(r"\babstract\b|摘要", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def parse_file(file_path, use_ai=False):
    """拆解单个文档文件。

    返回:
        dict: {"meta": {...}, "confidence": 0.0~1.0, "ai_used": bool}
    异常:
        PdfExtractError / ValueError / OSError：交由上层处理。
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in PDF_EXTS:
        result = pdf_extractor.extract_pdf(str(path))
    elif ext in TEXT_EXTS:
        raw = _read_text(path)
        result = text_parser.parse_text(raw)
    else:
        raise ValueError(f"不支持的文档类型: {ext or '(无扩展名)'}")

    meta = {
        "title": (result.get("title") or "").strip(),
        "abstract": (result.get("abstract") or "").strip(),
        "authors": result.get("authors") or [],
        "year": result.get("year"),
        "text": result.get("text") or "",
    }
    confidence = _confidence(meta)

    ai_used = False
    # 显式开启 AI 精修，或规则拆解置信度不足（≤0.5）时自动尝试 Agent；
    # 未配置 .env 时 refine_metadata 内部自动回退规则结果。
    if use_ai or confidence <= 0.5:
        try:
            from agent.paper_agent import refine_metadata
            meta, ai_used = refine_metadata(meta["text"], meta)
        except Exception as exc:  # Agent 失败不影响规则结果
            print(f"[拆解] Agent 精修失败，沿用规则结果: {exc}")
            ai_used = False

    # 最终兜底：仍无标题时用摘要首句（去句号）生成临时标题，保证入库不中断
    if not meta["title"] and meta["abstract"]:
        first = re.split(r"(?<=[。.!?])\s+", meta["abstract"].strip(), 1)[0]
        first = first.strip(" .。")
        meta["title"] = (first[0].upper() + first[1:])[:150] if first else ""
    return {"meta": meta, "confidence": confidence, "ai_used": ai_used}


def _read_text(path):
    """读取文本文件：按候选编码择优解码（解决中文 TXT 乱码）。"""
    raw = path.read_bytes()
    text, _encoding = best_decode(raw)
    return text


def _confidence(meta):
    """粗略置信度：标题/摘要/作者/年份四个维度各计一分。"""
    score = 0
    if 4 <= len(meta["title"]) <= 300:
        score += 1
    if len(meta["abstract"]) >= 80:
        score += 1
    if meta["authors"]:
        score += 1
    if isinstance(meta["year"], int):
        score += 1
    return round(score / 4.0, 2)
