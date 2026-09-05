# -*- coding: utf-8 -*-
"""ZIP 压缩包批量解包（防路径穿越、限制大小与数量）。

extract_entries(stream_or_path) -> [Entry(name, temp_path)]
仅放行 .pdf/.txt/.md/.tex 等可解析成员；解包到独立临时目录，
返回的安全名已去除目录成分，供上层逐文件走拆解流水线。
"""

import re
import tempfile
import zipfile
from pathlib import Path

ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".text", ".log", ".tex"}
MAX_FILES = 200      # 单包最大成员数
MAX_TOTAL_SIZE = 512 * 1024 * 1024   # 解压总量上限
MAX_FILE_SIZE = 64 * 1024 * 1024     # 单文件上限


class ZipEntry:
    """解包出的单个文档：原始名称 + 临时文件路径。"""

    __slots__ = ("name", "path")

    def __init__(self, name, path):
        self.name = name      # 原始文件名（仅 basename，防穿越）
        self.path = path      # 解压后的临时文件路径


class ZipImportError(ValueError):
    """ZIP 导入异常（结构非法/超限/无可用文档）。"""


def extract_entries(source):
    """解包 ZIP，返回可用文档条目列表。

    参数:
        source: zip 文件路径 或 二进制流（BytesIO/上传对象）。
    """
    try:
        with zipfile.ZipFile(source) as zf:
            infos = zf.infolist()
            if not infos:
                raise ZipImportError("压缩包为空")
            if len(infos) > MAX_FILES:
                raise ZipImportError(f"压缩包成员数超过上限 {MAX_FILES}")

            total_size = sum(i.file_size for i in infos)
            if total_size > MAX_TOTAL_SIZE:
                raise ZipImportError("压缩包解压总量超过上限 512MB")

            tmp_dir = tempfile.mkdtemp(prefix="paper_zip_")
            entries = []
            for info in infos:
                raw_name = info.filename.replace("\\", "/")
                # 安全校验：拒绝路径穿越（../、绝对路径、盘符）
                if ".." in raw_name.split("/") or raw_name.startswith("/") \
                        or re.match(r"^[A-Za-z]:", raw_name):
                    continue
                name = Path(raw_name).name  # 仅取 basename（二次防护）
                suffix = Path(name).suffix.lower()
                if info.is_dir() or suffix not in ALLOWED_SUFFIXES:
                    continue
                if info.file_size > MAX_FILE_SIZE:
                    continue  # 超限单文件跳过，不中断
                dest = Path(tmp_dir) / f"{len(entries)}_{name}"
                with zf.open(info) as src, open(dest, "wb") as out:
                    out.write(src.read())
                entries.append(ZipEntry(name, str(dest)))
            if not entries:
                raise ZipImportError("压缩包内没有可解析的 PDF/纯文本文档")
            return entries
    except zipfile.BadZipFile as exc:
        raise ZipImportError(f"不是有效的 ZIP 文件: {exc}") from exc
