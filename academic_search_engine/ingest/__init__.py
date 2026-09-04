# -*- coding: utf-8 -*-
"""ingest 包：本地论文文档的解析与拆解入库。

子模块：
- pdf_extractor：PDF 文本与元数据提取（PyPDF2/pypdf，外部库仅用于解析）；
- text_parser   ：纯文本/标记文本的启发式拆解；
- document_parser：统一拆解流水线（规则拆解 -> 低置信度时可选 Agent 精修）；
- zip_importer  ：ZIP 压缩包批量解包（防路径穿越与超限）。
"""

__all__ = ["pdf_extractor", "text_parser", "document_parser", "zip_importer"]
