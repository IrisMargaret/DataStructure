# -*- coding: utf-8 -*-
"""文本编码探测与乱码修复。

- best_decode(raw)：按 utf-8(-sig) -> gb18030 -> utf-16 -> big5 择优解码，
  以“替换字符/控制字符最少”为准则，解决中文 TXT 常见编码误判导致的乱码；
- repair_mojibake(text)：检测“UTF-8 字节被误按 Latin-1/GBK 等解码”的
  特征并尝试还原（适用于 PDF 提取出的乱码文本）。
"""

import unicodedata

_ENC_ORDER = ("utf-8-sig", "utf-8", "gb18030", "utf-16", "big5")
_MOJIBAKE_PAIRS = (("latin-1", "utf-8"), ("cp1252", "utf-8"),
                   ("gb18030", "utf-8"))


def _decode_score(text):
    """坏字符越少分越高：替换符计 3 分、控制字符计 1 分。"""
    score = 0
    for ch in text:
        if ch == "\ufffd":
            score += 3
        elif unicodedata.category(ch) == "Cc" and ch not in "\n\r\t":
            score += 1
    return score


def best_decode(raw):
    """按候选编码解码字节，返回 (text, encoding)；均失败则 latin-1 兜底。"""
    best, best_enc, best_score = None, None, None
    for enc in _ENC_ORDER:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
        score = _decode_score(text)
        if best is None or score < best_score:
            best, best_enc, best_score = text, enc, score
        if score == 0:
            break  # 无损解码，直接采用
    if best is None:
        return raw.decode("latin-1", errors="replace"), "latin-1"
    return best, best_enc


def repair_mojibake(text):
    """尝试修复常见乱码（UTF-8 被误按其他编码解码），失败则原样返回。"""
    if not text:
        return text
    best, best_score = text, _decode_score(text)
    for enc_from, enc_to in _MOJIBAKE_PAIRS:
        try:
            repaired = text.encode(enc_from, errors="strict").decode(
                enc_to, errors="strict")
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
        score = _decode_score(repaired)
        if score < best_score or (
                score == best_score and repaired != text and
                _cjk_ratio(repaired) > _cjk_ratio(text)):
            best, best_score = repaired, score
    return best


def _cjk_ratio(text):
    """文本中 CJK 字符占比（用于择优）。"""
    if not text:
        return 0.0
    total = len(text)
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk / total
