# -*- coding: utf-8 -*-
"""阶段门禁：严格去重 / 原文归档 / 跨语言检索 快速验证（隔离数据）。"""
import json
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import os as _os
for k in ["LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"]:
    _os.environ[k] = ""

from service.search_service import SearchService

tmp = Path(tempfile.mkdtemp(prefix="gate_"))
papers_path = tmp / "papers.json"
papers_path.write_text(json.dumps([
    {"id": 0, "title": "Convolutional Neural Networks for Image Classification",
     "abstract": "We study convolutional neural networks with convolution layers for image classification.",
     "authors": ["Alice"], "year": 2019, "language": "en"},
    {"id": 1, "title": "卷积神经网络图像分类研究",
     "abstract": "本文研究卷积神经网络，使用卷积层进行图像分类。",
     "authors": ["王五"], "year": 2021, "language": "zh"},
], ensure_ascii=False), encoding="utf-8")

svc = SearchService(auto_fetch=False, papers_path=papers_path)
print("初始:", svc.stats()["total_papers"], "篇")

# 1) 严格去重：内容完全一致 -> duplicate；同名不同文 -> 允许并存
r1 = svc.add_manual({"title": "Convolutional Neural Networks for Image Classification",
                     "abstract": "We study convolutional neural networks with convolution layers for image classification.",
                     "authors": ["Alice"], "year": 2019})
print("1a 内容全等:", "duplicate" if not r1["ok"] else "误判为新增", "| existing:", r1.get("existing"))
assert not r1["ok"] and r1["duplicate"]

r2 = svc.add_manual({"title": "Convolutional Neural Networks for Image Classification",
                     "abstract": "A completely different abstract about nothing relevant to the title.",
                     "authors": ["Bob"], "year": 2022})
print("1b 同名不同文:", "duplicate" if not r2["ok"] else "允许并存(正确)")
assert r2["ok"]

# 2) 原文归档 + resolve_file
r3 = svc.add_file(__import__("io").BytesIO(
    b"Deep Hashing for Similarity Search\nAlice\nAbstract: We study deep hashing methods.\n2023"), "hash_paper.txt")
print("2a 文件入库 ok:", r3["ok"], "| file_store:", r3["paper"].get("file_store"))
assert r3["ok"] and r3["paper"].get("file_store")
resolved = svc.resolve_file(r3["paper"]["id"])
print("2b resolve:", resolved[1] if resolved else None)
assert resolved and resolved[0].exists()

# 3) 跨语言检索：中文查询 -> 英文文献；英文查询 cross -> 中文文献
r = svc.search("卷积神经网络", mode="tf")
titles = {x["title"] for x in r["results"]}
print("3a 中文查询命中:", r["count"], "篇 |", "含英文卷积论文:", any("Convolutional" in t for t in titles))
assert any("Convolutional" in t for t in titles)  # 中文词自动跨语言命中英文文献
r = svc.search("convolutional neural network", mode="tf", cross=True)
titles = {x["title"] for x in r["results"]}
print("3b 英文+cross 命中:", r["count"], "篇 | 含中文论文:", any("卷积" in t for t in titles))
assert any("卷积" in t for t in titles)

# 4) 纯英文默认 AND（不开 cross）
r = svc.search("convolutional image", mode="tf")
assert r["query_type"] == "keywords"
print("4 纯英文默认 AND 保留 ✓")

# 5) zip 三分组
import io, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("dup.txt", "Deep Hashing for Similarity Search\nAlice\nAbstract: We study deep hashing methods.\n2023")
    z.writestr("new.txt", "Graph Database Indexing\nLin\nAbstract: Graph databases index nodes and edges for retrieval.\n2024")
buf.seek(0)
rz = svc.add_zip(buf, use_ai=False)
print("5 zip:", "added", len(rz["added"]), "| duplicated", len(rz["duplicated"]),
      "| failed", len(rz["failed"]))
assert len(rz["added"]) == 1 and len(rz["duplicated"]) == 1 and not rz["failed"]

print("\n=== GATE PASSED ===")
shutil_ = __import__("shutil"); shutil_.rmtree(tmp, ignore_errors=True)
