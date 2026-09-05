# -*- coding: utf-8 -*-
"""文本噪声行清理（PDF/纯文本拆解前处理）。

逐行过滤与归整：
- 页码行（含中文/英文页脚）、arXiv 编号、DOI/URL/邮箱；
- 纯符号/纯数字行、连续重复行（页眉页脚）；
- 出版信息行：收稿/基金/作者简介/中图分类号/文献标志码/文章编号/
  网络首发/引文格式 等；
- 作者单位/通讯作者/邮编行（如“xxx大学 北京 100000”）。
"""

import re

_PAGE_LINE = re.compile(
    r"^\s*(第\s*\d+\s*页(\s*共\s*\d+\s*页)?|page\s*\d+\s*of\s*\d+|"
    r"\d{1,4}\s*[/-]\s*\d{1,4})\s*$", re.IGNORECASE)
_ARXIV_LINE = re.compile(r"^arxiv\s*:\s*\d{4}\.\d{4,5}", re.IGNORECASE)
_URL_MAIL_LINE = re.compile(
    r"^(https?://|www\.|doi\s*:|\S+@\S+\.\S+)", re.IGNORECASE)
_PURE_SYMBOL = re.compile(r"^[\W_—–·•\s]*$")
# 题录/出版信息行
_META_PREFIX = re.compile(
    r"^(收稿日期|修回日期|录用日期|网络首发|基金项目|基金资助|资助项目|"
    r"作者简介|作者单位|通讯作者|通信作者|电子邮箱|e-?mail|邮编|"
    r"中图分类号|文献标志码|文献标识码|文章编号|引文格式|引用本文|DOI|"
    r"received|revised|accepted|funding|corresponding author)\b",
    re.IGNORECASE)
# 作者单位行：含“大学/学院/研究院/研究所/中心”等机构词
_UNIT_KEYWORD = re.compile(
    r"(大学|学院|研究院|研究所|学校|中心|实验室|"
    r"University|College|Institute|Department|School)", re.IGNORECASE)
# 一行内出现 5~6 位邮编（如“北京 100000”）
_POSTCODE = re.compile(r"\b\d{5,6}\b")
# 可接受的普通行（含句读），避免误删正文
_HAS_SENTENCE = re.compile(r"[。．.!?？]|[，,:：]")


def clean_text(text):
    """返回清洗后的多行文本（按行过滤 + 规整空白）。"""
    cleaned = []
    prev = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or _PURE_SYMBOL.fullmatch(line):
            continue
        if _PAGE_LINE.fullmatch(line) or _ARXIV_LINE.match(line) \
                or _URL_MAIL_LINE.match(line) or _META_PREFIX.match(line):
            continue
        if line == prev:      # 重复页眉/页脚
            continue
        # 机构行：短行 + 机构词 + (邮编 或 无句读) -> 视为单位/归属行
        if len(line) <= 90 and _UNIT_KEYWORD.search(line) \
                and (_POSTCODE.search(line) or not _HAS_SENTENCE.search(line)):
            continue
        # 规整内部空白（PDF 提取常见的多余空格）
        line = re.sub(r"[ \t\u3000]+", " ", line).strip()
        cleaned.append(line)
        prev = line
    return "\n".join(cleaned)
