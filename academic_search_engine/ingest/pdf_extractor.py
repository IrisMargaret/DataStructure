# -*- coding: utf-8 -*-
"""PDF 文本与元数据提取（鲁棒版）。

- **双库回退**：pypdf 优先，提取质量差或失败时自动用 PyPDF2 重试，
  取文本质量更优者；
- 提取结果做乱码还原 + 噪声清理；若清洗后为空但原始文本非空，保留
  原始文本交由结构解析与 AI 精修兜底，不直接抛错；
- 仅当两个库均取不到任何文本时才报“无文本层（可能扫描版/加密）”。

字段结构识别委托 text_parser（中英文版式统一逻辑）。
"""

import importlib
import re

from . import text_parser

# (库名, 读取器类型) 按优先级尝试
_LIB_ORDER = (("pypdf", "PdfReader"), ("PyPDF2", "PdfReader"))
_MAX_PAGES = 5


class PdfExtractError(Exception):
    """PDF 解析失败异常。"""


def extract_pdf(file_path):
    """提取 PDF 的标题/摘要/作者/年份与全文文本。

    返回: {"title", "abstract", "authors", "year", "text"}
    异常: PdfExtractError（两库均无文本 / 均加密）
    """
    raw_text, meta = _extract_best(file_path)
    if raw_text is None:
        raise PdfExtractError(
            "未能提取到文本（PDF 可能为扫描版、加密或特殊编码）")

    from .clean_text import clean_text
    from .encodings import repair_mojibake

    repaired = repair_mojibake(raw_text)
    text = clean_text(repaired) or repaired  # 清洗为空则保留原始文本

    parsed = text_parser.parse_text(text)
    meta = meta or {}

    # 元数据兜底：标题与年份
    title = parsed["title"]
    meta_title = repair_mojibake(str(meta.get("/Title") or "")).strip()
    if not title and 4 <= len(meta_title) <= 300:
        title = meta_title
    year = parsed["year"] or _metadata_year(meta)
    return {
        "title": title,
        "abstract": parsed["abstract"],
        "authors": parsed["authors"],
        "year": year,
        "text": text,
    }


def _extract_best(file_path):
    """依次尝试各 PDF 库，返回 (最佳文本, 元数据)；全部失败返回 (None, None)。"""
    best, best_meta, best_score = None, None, -1
    for lib_name, reader_type in _LIB_ORDER:
        try:
            module = importlib.import_module(lib_name)
        except ImportError:
            continue
        try:
            reader = getattr(module, reader_type)(file_path)
        except Exception:
            continue
        if getattr(reader, "is_encrypted", False):
            continue
        pages = []
        for page in reader.pages[:_MAX_PAGES]:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        raw = "\n".join(pages)
        score = _quality(raw)
        if score > best_score:
            best, best_score = raw, score
            best_meta = getattr(reader, "metadata", None) or {}
    return best, best_meta


def _quality(text):
    """文本质量分：有效字符数越多越好，替换符/控制字符扣分。"""
    if not text:
        return -1
    bad = text.count("\ufffd") * 20
    bad += sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    return len(text) - bad


def _metadata_year(meta):
    """从 PDF 创建/修改日期元数据提取年份。"""
    for key in ("/CreationDate", "/ModDate"):
        raw = meta.get(key)
        if raw:
            match = re.search(r"(?:19|20)\d{2}", str(raw))
            if match:
                return int(match.group(0))
    return None
