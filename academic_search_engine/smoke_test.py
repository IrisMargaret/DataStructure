# -*- coding: utf-8 -*-
"""综合冒烟测试：覆盖 core / ingest / service / web 四层。

特点：全部离线运行（无网络、无 .env），数据使用临时目录隔离，
不污染 data/papers.json。直接执行：
    python smoke_test.py
"""

import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = []


def check(name, cond, detail=""):
    """断言并记录。"""
    assert cond, f"[FAIL] {name} {detail}"
    PASS.append(name)
    print(f"  ok  {name}")


def make_pdf_bytes(title, author, abstract):
    """构造最小合法 PDF（含标题/作者/Abstract 文本）。"""
    stream = (f"BT /F1 14 Tf 72 720 Td ({title}) Tj 0 -20 Td "
              f"/F1 10 Tf ({author}) Tj 0 -20 Td /F1 10 Tf (Abstract) Tj "
              f"0 -16 Td /F1 10 Tf ({abstract}) Tj ET").encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (f"<< /Title ({title}) /Author ({author}) "
         f"/CreationDate (D:20240101000000) >>").encode("latin-1"),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\n"
            b"startxref\n%d\n%%%%EOF" % (len(objs) + 1, len(objs), xref))
    return bytes(out)


# ============================================================ A. core 算法层

def test_core():
    print("== A. core（倒排索引 / 词干 / 布尔 / Trie / 关键词）==")
    from core.inverted_index import InvertedIndex
    from core.keyword_extractor import KeywordExtractor
    from core.paper import Paper
    from core.preprocessor import Preprocessor
    from core.stemmer import PorterStemmer
    from core.trie import Trie

    # A1. Porter 词干（抽样官方向量）
    st = PorterStemmer()
    vectors = {"caresses": "caress", "ponies": "poni", "ties": "ti",
               "agreed": "agre", "feed": "feed", "conflated": "conflat",
               "hopping": "hop", "failing": "fail", "happy": "happi",
               "relational": "relat", "probate": "probat", "rate": "rate",
               "cease": "ceas", "controll": "control", "roll": "roll",
               "transformers": "transform", "convolutional": "convolut"}
    bad = [(w, st.stem(w)) for w, exp in vectors.items()
           if st.stem(w) != exp]
    check("A1 Porter 词干", not bad, str(bad[:3]))

    pp = Preprocessor()
    idx = InvertedIndex(pp)
    papers = [
        Paper(0, "Transformers for Sequence Modelling",
              "We study transformer architectures and attention for sequences.",
              ["A"], 2019),
        Paper(1, "Graph Neural Networks Survey",
              "A survey of graph neural networks and attention mechanisms.",
              ["B"], 2020),
        Paper(2, "卷积神经网络综述",
              "本文综述卷积神经网络在图像分类中的应用与训练方法。",
              ["张三"], 2021),
    ]
    for p in papers:
        p.keywords = KeywordExtractor(pp).extract(p.title, p.abstract,
                                                  total_docs=3,
                                                  df_lookup=lambda t: 1)
    idx.build(papers)

    # A2. 词干一致检索 + display
    r = idx.search_keywords("transformer")
    check("A2 词干检索 transformer", r["count"] >= 1
          and r["results"][0]["matched_terms"][0]["term"] == "transform"
          and r["results"][0]["matched_terms"][0]["display"] in
          ("transformer", "transformers"))

    # A3. 布尔查询（AND / OR / 括号）+ AST
    r = idx.search_boolean("graph AND (neural OR network)")
    check("A3 布尔", r["count"] == 1 and "ast" in r["trace"]
          and r["results"][0]["paper_id"] == 1)

    # A3c. NOT 语义（survey -> 词干 survei，正确排除含 survey 的论文 1）
    r = idx.search_boolean("attention NOT survey")
    check("A3c 布尔 NOT", r["count"] == 1
          and r["results"][0]["paper_id"] == 0)

    # A3b. 布尔叶子词词干化（transformers -> transform）
    r = idx.search_boolean("transformers AND attention")
    check("A3b 布尔词干化", r["count"] == 1
          and r["results"][0]["paper_id"] == 0)

    # A4. 短语位置匹配
    r = idx.search_boolean('"graph neural"')
    check("A4 短语匹配", r["count"] == 1)

    # A5. trace 剖析数据
    r = idx.search_keywords("graph neural")
    check("A5 trace", len(r["trace"]["terms"]) == 2
          and r["trace"]["merge_order"] == sorted(r["trace"]["merge_order"]))

    # A6. 中文检索与关键词
    r = idx.search_keywords("卷积神经网络")
    check("A6 中文检索", r["count"] == 1)
    check("A6b 中文关键词", any("卷积" in k for k in papers[2].keywords))

    # A7. TF / TF-IDF 双模
    r1 = idx.search_keywords("network", mode="tf")
    r2 = idx.search_keywords("network", mode="tfidf")
    check("A7 TF-IDF 双模", r1["count"] == r2["count"] >= 1
          and all(x["score"] > 0 for x in r2["results"]))

    # A8. Trie 补全
    trie = Trie()
    trie.build_from_index(idx)
    sug = trie.suggest("trans")
    check("A8 Trie 补全", any(s["term"] == "transform" for s in sug))

    # A9. 索引快照结构
    snap = idx.index_snapshot(limit=3)
    check("A9 快照", len(snap["terms"]) == 3
          and all("postings" in t and "display" in t for t in snap["terms"]))


# ============================================ B. ingest（拆解与安全解包）

def test_ingest():
    print("== B. ingest（纯文本 / PDF / ZIP）==")
    from ingest import document_parser, pdf_extractor, text_parser
    from ingest.zip_importer import extract_entries

    # B1. 纯文本拆解
    txt = ("A Survey of Vector Databases\nLi Si\n"
           "Abstract: We survey vector databases for similarity search "
           "and retrieval.\n2024")
    meta = text_parser.parse_text(txt)
    check("B1 纯文本拆解", meta["title"].startswith("A Survey of Vector")
          and meta["authors"] and meta["year"] == 2024)

    # B2. PDF 提取（内存构造的真实格式 PDF）
    pdf_bytes = make_pdf_bytes("Deep Learning for Graphs", "Alice Chen",
                               "We present deep learning models on graphs.")
    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / "t.pdf"
        pdf_path.write_bytes(pdf_bytes)
        got = pdf_extractor.extract_pdf(str(pdf_path))
        check("B2 PDF 提取", got["title"].startswith("Deep Learning")
              and "graph" in got["abstract"].lower() and got["year"] == 2024)

        # B3. document_parser 分派 + 置信度
        parsed = document_parser.parse_file(str(pdf_path), use_ai=False)
        check("B3 拆解流水线", parsed["meta"]["title"] and
              parsed["confidence"] >= 0.5 and parsed["ai_used"] is False)

        # B4. ZIP：正常成员入库候选 + 穿越成员被拒
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.txt", txt)
            zf.writestr("b.pdf", pdf_bytes)
            zf.writestr("../evil.pdf", pdf_bytes)
        buf.seek(0)
        entries = extract_entries(buf)
        names = [e.name for e in entries]
        check("B4 ZIP 安全解包", sorted(names) == ["a.txt", "b.pdf"]
              and all(Path(e.name).name == e.name for e in entries))


# ============================== C. service + web（隔离数据，端到端）

def test_service_web():
    print("== C. service + web（Flask test_client，隔离数据）==")
    import os as _os
    from service.search_service import SearchService
    from web import create_app

    # 强制离线：先置空 LLM 环境变量（load_dotenv 不会覆盖已存在的键），
    # 保证测试不依赖 .env、不发起真实模型调用；结束恢复。
    env_keys = ["LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"]
    saved_env = {k: _os.environ.get(k) for k in env_keys}
    for k in env_keys:
        _os.environ[k] = ""

    tmp = Path(tempfile.mkdtemp(prefix="ir_smoke_"))
    try:
        papers_path = tmp / "papers.json"
        # 预置小语料（直接构造数据文件）
        seed = [
            {"id": 0, "title": "Attention Is All You Need",
             "abstract": "The dominant sequence transduction models are based "
                         "on complex recurrent neural networks.", "authors":
             ["Vaswani"], "year": 2017},
            {"id": 1, "title": "卷积神经网络在图像识别中的研究",
             "abstract": "本文研究卷积神经网络与图像识别技术。", "authors":
             ["王五"], "year": 2020},
        ]
        papers_path.write_text(json.dumps(seed, ensure_ascii=False),
                               encoding="utf-8")

        svc = SearchService(auto_fetch=False, papers_path=papers_path,
                            files_dir=tmp / "files",
                            uploads_dir=tmp / "uploads")
        app = create_app(service=svc)
        c = app.test_client()

        # C1. 统计与关键词字段
        m = c.get("/api/meta").get_json()
        check("C1 meta", m["total_papers"] == 2 and m["llm_configured"] is False)

        # C2. 中英文检索 + trace
        r = c.get("/api/search?q=attention%20neural").get_json()
        check("C2 检索", r["count"] == 1 and r["results"][0]["keywords"])
        r2 = c.get("/api/search?q=%E5%8D%B7%E7%A7%AF").get_json()
        check("C2b 中文检索", r2["count"] == 1)

        # C3. 补全 / 快照 / 文库
        s = c.get("/api/suggest?prefix=atten").get_json()
        check("C3 补全", any(x["term"].startswith("atten") for x in s["suggestions"]))
        idx = c.get("/api/index?limit=5").get_json()
        check("C3b 索引快照", len(idx["terms"]) >= 3)
        pl = c.get("/api/papers?page=1&size=10").get_json()
        check("C3c 文库", pl["total"] == 2)

        # C4. 手动添加 -> 可检索 -> 详情
        d = c.post("/api/papers/manual",
                   json={"title": "Graph Databases for IR",
                         "abstract": "Graph databases organize data as nodes "
                                     "and edges for efficient retrieval.",
                         "authors": ["Zhao Liu"], "year": 2023}).get_json()
        pid = d["paper"]["id"]
        r = c.get("/api/search?q=graph%20databases").get_json()
        check("C4 手动入库可检索", r["count"] == 1
              and r["results"][0]["paper_id"] == pid)
        detail = c.get(f"/api/papers/{pid}").get_json()
        check("C4b 详情", detail["title"].startswith("Graph Databases"))

        # C5. TXT 上传（含 AI 开关但未配置 -> 规则拆解）
        txt = ("Retrieval-Augmented Generation\nHan Mei\nAbstract: "
               "Retrieval augmented generation combines retrieval and "
               "generation for knowledge tasks.\n2023")
        resp = c.post("/api/papers/file",
                      data={"file": (io.BytesIO(txt.encode()), "rag.txt"),
                            "ai": "1"},
                      content_type="multipart/form-data")
        d = resp.get_json()
        check("C5 TXT 上传", resp.status_code == 200 and d["ok"]
              and d["paper"]["title"].startswith("Retrieval-Augmented")
              and d["ai_used"] is False)
        r = c.get("/api/search?q=retrieval").get_json()
        check("C5b 上传后可检索", r["count"] >= 1)

        # C6. ZIP 批量（txt + pdf；含穿越成员）
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("p1.txt", "Text Classification with BERT\nAnn\n"
                                  "Abstract: BERT models achieve strong text "
                                  "classification results on benchmarks.")
            zf.writestr("p2.pdf", make_pdf_bytes(
                "Image Generation with Diffusion", "Bob",
                "Diffusion models generate high quality images from noise."))
            zf.writestr("../../evil.pdf", "x")
        buf.seek(0)
        resp = c.post("/api/papers/file",
                      data={"file": (buf, "batch.zip")},
                      content_type="multipart/form-data")
        d = resp.get_json()
        check("C6 ZIP 批量", resp.status_code == 200
              and len(d["added"]) == 2 and len(d["failed"]) == 0
              and all(not x["name"].startswith("..") for x in d["added"]))

        # C7. 删除 -> 检索消失
        resp = c.delete(f"/api/papers/{pid}")
        check("C7 删除", resp.status_code == 200)
        r = c.get("/api/search?q=graph%20databases").get_json()
        check("C7b 删除后检索为空", r["count"] == 0)

        # C8. 错误处理
        e1 = c.post("/api/papers/manual", json={}).get_json()
        check("C8 缺标题报错", "error" in e1)
        e2 = c.get("/api/papers/999999").status_code
        check("C8b 详情404", e2 == 404)

        # C9. 持久化校验（keywords 写入文件）
        saved = json.loads(papers_path.read_text(encoding="utf-8"))
        check("C9 持久化", len(saved) >= 4
              and all("keywords" in p for p in saved))
        print("  C 层运行后论文数:", svc.stats()["total_papers"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k in env_keys:
            _os.environ[k] = saved_env.get(k) or ""


# ========================== D. 中英互译检索（双语语料）

def test_cross_language():
    print("== D. 跨语言互译检索 ==")
    import os as _os
    for k in ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"):
        _os.environ[k] = ""
    from service.search_service import SearchService
    from core.translator import Translator, detect_lang

    t = Translator()
    check("D1 双语词典", t.translate("卷积")[:1] == ["convolution"]
          and "图" in t.translate("graph"))
    check("D2 语言探测", detect_lang("神经网络") == "zh"
          and detect_lang("graph neural") == "en"
          and detect_lang("图 graph") == "mixed")

    tmp = Path(tempfile.mkdtemp(prefix="ir_cross_"))
    try:
        pp = tmp / "papers.json"
        pp.write_text(json.dumps([
            {"id": 0, "title": "Convolutional Neural Networks for Image "
                               "Classification",
             "abstract": "We study convolutional neural networks with "
                         "convolution layers for image classification.",
             "authors": ["Alice"], "year": 2019, "language": "en"},
            {"id": 1, "title": "卷积神经网络图像分类研究",
             "abstract": "本文研究卷积神经网络，使用卷积层进行图像分类。",
             "authors": ["王五"], "year": 2021, "language": "zh"},
        ], ensure_ascii=False), encoding="utf-8")
        svc = SearchService(auto_fetch=False, papers_path=pp,
                            files_dir=tmp / "files",
                            uploads_dir=tmp / "uploads")

        r = svc.search("卷积神经网络", mode="tf")
        titles = {x["title"] for x in r["results"]}
        check("D3 中文查英文", any("Convolutional" in x for x in titles))
        r = svc.search("convolutional neural network", mode="tf", cross=True)
        titles = {x["title"] for x in r["results"]}
        check("D4 英文查中文", any("卷积神经网络" in x for x in titles))
        r = svc.search("convolutional image", mode="tf")
        check("D5 纯英文默认 AND", r["query_type"] == "keywords")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==================== E. 中文拆解 / 原文归档 / 严格去重 / 子串补全

def test_zh_ingest_and_dedupe():
    print("== E. 中文拆解 / 原文归档 / 严格去重 / 子串补全 ==")
    import os as _os
    for k in ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"):
        _os.environ[k] = ""
    from ingest import text_parser
    from ingest.encodings import best_decode, repair_mojibake
    from service.search_service import SearchService
    from web import create_app

    # E1. GB18030 中文 TXT 拆解（乱码/噪声/字段）
    zh_bytes = ("卷积神经网络在图像分类中的研究\n张三, 李四\n"
                "收稿日期：2020-01-01\n基金项目：国家自然科学基金\n"
                "摘要：本文研究卷积神经网络在图像分类任务中的应用，"
                "提出改进的卷积网络结构，提升了分类准确率。\n"
                "关键词：卷积神经网络；图像分类；深度学习\n"
                "1 引言\n近年来卷积神经网络发展迅速。").encode("gb18030")
    text, enc = best_decode(zh_bytes)
    meta = text_parser.parse_text(text)
    check("E1 中文编码拆解", enc in ("gb18030", "utf-8") and "\ufffd" not in text
          and meta["title"] == "卷积神经网络在图像分类中的研究"
          and meta["authors"] == ["张三", "李四"] and meta["year"] == 2020
          and "基金项目" not in meta["abstract"]
          and "关键词" not in meta["abstract"])

    # E2. 双语标题行：作者不误判
    m = text_parser.parse_text("图神经网络研究综述\nA Survey of Graph Neural "
                               "Networks\n王小明\n摘要：本文综述图神经网络。\n2023")
    check("E2 双语标题", m["title"] == "图神经网络研究综述"
          and m["authors"] == ["王小明"])

    # E3. mojibake 还原
    check("E3 乱码还原", repair_mojibake("æ±‰å­—ç½‘ç»œ") == "汉字网络")

    # E4. 文件归档 + /file 路由 + 严格去重 + zip 三分组 + 子串补全
    tmp = Path(tempfile.mkdtemp(prefix="ir_zh_"))
    try:
        pp = tmp / "papers.json"
        pp.write_text(json.dumps([
            {"id": 0, "title": "卷积神经网络图像分类研究",
             "abstract": "本文研究卷积神经网络，使用卷积层进行图像分类。",
             "authors": ["王五"], "year": 2021, "language": "zh"},
        ], ensure_ascii=False), encoding="utf-8")
        svc = SearchService(auto_fetch=False, papers_path=pp,
                            files_dir=tmp / "files",
                            uploads_dir=tmp / "uploads")
        app = create_app(service=svc)
        c = app.test_client()

        # 文件上传 -> 归档可下载
        txt = ("图数据索引与查询优化\n赵六\n摘要：本文研究图数据库的索引结构"
               "与查询优化方法。\n2024").encode("utf-8")
        r = c.post("/api/papers/file",
                   data={"file": (io.BytesIO(txt), "zh_paper.txt"),
                         "ai": "0"},
                   content_type="multipart/form-data").get_json()
        check("E4 上传归档", r["ok"] and r["paper"].get("file_store"))
        pid = r["paper"]["id"]
        fr = c.get(f"/api/papers/{pid}/file")
        check("E4b 原文下载", fr.status_code == 200
              and fr.data == txt and "zh_paper.txt" in
              (fr.headers.get("Content-Disposition") or ""))

        # 严格去重：内容完全一致 -> duplicate 且不新增
        r2 = c.post("/api/papers/manual", json={
            "title": "图数据索引与查询优化",
            "abstract": "本文研究图数据库的索引结构与查询优化方法。",
            "authors": ["赵六"], "year": 2024}).get_json()
        check("E4c 严格去重", r2["ok"] is False and r2["duplicate"]
              and r2["existing"]["paper_id"] == pid)
        # 同名不同文 -> 允许并存
        r3 = c.post("/api/papers/manual", json={
            "title": "图数据索引与查询优化",
            "abstract": "另一篇内容完全不同的论文摘要。",
            "authors": ["孙七"], "year": 2023}).get_json()
        check("E4d 同名不同文并存", r3["ok"] is True)

        # zip 三分组：重复 1 + 新增 1
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("dup.txt", "图数据索引与查询优化\n赵六\n摘要：本文研究"
                                  "图数据库的索引结构与查询优化方法。\n2024")
            z.writestr("new.txt", "基于强化学习的推荐系统\n钱八\n摘要：本文把"
                                  "强化学习应用于推荐系统以提升交互体验。\n2023")
        buf.seek(0)
        rz = c.post("/api/papers/file",
                    data={"file": (buf, "batch.zip"), "ai": "0"},
                    content_type="multipart/form-data").get_json()
        check("E4e zip 三分组", len(rz["added"]) == 1
              and len(rz["duplicated"]) == 1 and not rz["failed"])

        # 中文子串补全：网络 ⊂ 神经网络
        s = svc.suggest("网络", top_k=5)
        check("E4f 子串补全", any("神经网络" in x["term"] for x in s))
        s2 = svc.suggest("卷积")
        check("E4g 前缀补全", any(x["term"].startswith("卷积") for x in s2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ==================== F. 摘要截取 / 外链 / 去噪 / 合并报告

def test_quality_fixes():
    print("== F. 摘要精确截取 / 外链 / 去噪 / 合并报告 ==")
    from core.paper import Paper
    from crawler.registry import merge_strict
    from ingest import text_parser
    from ingest.clean_text import clean_text

    # F1. 无摘要标记、以 Introduction 开头 -> 摘要为空（不截引言）
    m = text_parser.parse_text(
        "Attention Is All You Need\nA. Vaswani\n1 Introduction\nThe dominant "
        "sequence models are based on recurrent neural networks.\n2017")
    check("F1 引言不当摘要", m["abstract"] == ""
          and m["title"].startswith("Attention"))

    # F2. 显式中文摘要止于关键词
    m2 = text_parser.parse_text(
        "Transformer研究\n张三\n摘要：本文研究Transformer注意力机制，在机器"
        "翻译与文本分类中取得显著效果。\n关键词：Transformer；注意力机制\n"
        "1 引言\n正文内容")
    check("F2 摘要截断", "引言" not in m2["abstract"]
          and "关键词" not in m2["abstract"])

    # F3. 单位/基金/通讯行噪声清除
    cleaned = clean_text(
        "基于图神经网络的推荐\n张三\n南京大学 计算机学院 南京 210023\n"
        "通讯作者：李四\n基金项目：国家自然科学基金(62000000)\n"
        "摘要：本文研究图神经网络推荐方法。\n2022")
    check("F3 中文噪声清理", "南京大学" not in cleaned
          and "基金" not in cleaned and "通讯" not in cleaned)

    # F4. external_url 分支（arXiv / DOI http / 无）
    check("F4 外链 arXiv",
          Paper(0, "t", "a", source_id="1706.03762").external_url()
          == "https://arxiv.org/abs/1706.03762")
    check("F4b 外链 DOI",
          Paper(0, "t", "a", source_id="https://doi.org/10.1000/x")
          .external_url() == "https://doi.org/10.1000/x")
    check("F4c 无外链", Paper(0, "t", "a").external_url() is None)

    # F5. merge_strict 返回新增/跳过统计
    r = merge_strict(
        [{"title": "A", "abstract": "x", "authors": ["a"], "year": 1}],
        [{"title": "A", "abstract": "x", "authors": ["a"], "year": 1},
         {"title": "B", "abstract": "y", "authors": ["b"], "year": 2}])
    check("F5 合并报告", r["added"] == 1 and r["skipped"] == 1)

    # F6. 解析异常映射为中文提示（不泄露技术细节）
    from ingest.errors import friendly_parse_error
    class FakePdfError(Exception):
        pass
    check("F6 错误映射 PDF",
          "损坏" in friendly_parse_error(FakePdfError(
              "PdfReadError: EOF marker not found")))
    check("F6b 错误映射编码",
          "编码" in friendly_parse_error(UnicodeDecodeError(
              "utf-8", b"\xff", 0, 1, "invalid")))
    check("F6c 未知异常通用提示",
          "日志" in friendly_parse_error(RuntimeError("boom")))

    # F7. 日志器可写入含 traceback 的文件
    import tempfile as _tf
    from logutil import get_logger
    with _tf.TemporaryDirectory() as _td:
        log_path = Path(_td) / "x.log"
        lg = get_logger("testlog", path=str(log_path))
        try:
            raise ValueError("demo-error")
        except ValueError:
            lg.exception("捕获异常示例")
        content = log_path.read_text(encoding="utf-8")
        for handler in list(lg.handlers):  # 释放句柄，便于 Windows 清理
            handler.close()
            lg.removeHandler(handler)
        check("F7 日志写入", "demo-error" in content
              and "Traceback" in content)


# ==================== G. Top-K / 上传卫生 / 参数健壮

def test_topk_and_hygiene():
    print("== G. Top-K 截断 / 上传卫生 / 目录隔离 / 参数健壮 ==")
    import os as _os
    for k in ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"):
        _os.environ[k] = ""
    from service.search_service import SearchService
    from web import create_app

    tmp = Path(tempfile.mkdtemp(prefix="ir_topk_"))
    try:
        pp = tmp / "papers.json"
        seed = []
        for i in range(60):  # 60 篇同含 "commonterm" 的论文
            seed.append({
                "id": i, "title": f"Paper {i} on commonterm research",
                "abstract": f"Abstract {i}: this paper studies commonterm "
                            f"topics with experiments.",
                "authors": [f"Author{i}"], "year": 2020 + i % 5,
                "language": "en"})
        pp.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
        svc = SearchService(auto_fetch=False, papers_path=pp,
                            files_dir=tmp / "files",
                            uploads_dir=tmp / "uploads")
        app = create_app(service=svc)
        c = app.test_client()

        # G1. Top-K 截断：count 为真实命中，results 被截到默认 50
        r = svc.search("commonterm", mode="tf")
        check("G1 关键词 Top-K", r["count"] == 60 and len(r["results"]) == 50)
        rb = svc.search("(commonterm)", mode="tf")
        check("G1b 布尔 Top-K", rb["count"] == 60 and len(rb["results"]) == 50)

        # G2. 上传后 uploads 临时目录无残留（成功与失败路径）
        good = ("Top-K Validation Paper\nAlice\nAbstract: This paper "
                "validates top k truncation behaviour of search results.\n2024")
        c.post("/api/papers/file",
               data={"file": (io.BytesIO(good.encode()), "g.txt"),
                     "ai": "0"},
               content_type="multipart/form-data")
        bad = io.BytesIO(b"")  # 空文件触发解析失败
        c.post("/api/papers/file",
               data={"file": (bad, "bad.pdf"), "ai": "0"},
               content_type="multipart/form-data")
        check("G2 uploads 无残留", not (tmp / "uploads").exists()
              or not list((tmp / "uploads").iterdir()))

        # G3. 原文归档仅落在注入目录，不触碰项目 data/papers_files
        proj_files = Path(__file__).resolve().parent / "data" / "papers_files"
        before = {p.name for p in proj_files.iterdir()} \
            if proj_files.exists() else set()
        r2 = c.post("/api/papers/file",
                    data={"file": (io.BytesIO(
                        b"Archival Isolation Paper\nBob\nAbstract: check "
                        b"files dir isolation.\n2023"), "iso.txt"),
                          "ai": "0"},
                    content_type="multipart/form-data").get_json()
        after = {p.name for p in proj_files.iterdir()} \
            if proj_files.exists() else set()
        stored = r2["paper"].get("file_store") or ""
        check("G3 目录隔离", r2["ok"] and after == before
              and not stored.startswith("data/"))

        # G4. 畸形整型参数回退默认，不再 500
        r4 = c.get("/api/papers?page=abc&size=zz")
        check("G4 畸形分页参数", r4.status_code == 200)
        r5 = c.get("/api/index?limit=notnum")
        check("G4b 畸形 limit", r5.status_code == 200
              and len(r5.get_json().get("terms", [])) > 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 62)
    test_core()
    test_ingest()
    test_service_web()
    test_cross_language()
    test_zh_ingest_and_dedupe()
    test_quality_fixes()
    test_topk_and_hygiene()
    print("=" * 62)
    print(f"全部通过：{len(PASS)} 项检查")
