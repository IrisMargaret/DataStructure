# -*- coding: utf-8 -*-
"""检索服务门面（单例）：Web 层与算法层之间的唯一入口。

职责：
- 组合 InvertedIndex / Trie / KeywordExtractor / Translator / 拆解 / 采集；
- 所有公开方法持 RLock，保证“检索 / 动态入库 / 爬虫重建”并发安全；
- 论文持久化采用原子写；上传原文文件归档于 data/papers_files/；
- 严格去重：仅“内容完全一致”（规范化标题+作者+年份+摘要全等）判重。

对外接口：
    stats / meta / search(cross) / suggest / index_snapshot
    list_papers / get_paper / resolve_file / add_manual / add_by_url
    add_file / add_zip / remove_paper / crawl_start(source) / crawl_status
"""

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from core.inverted_index import InvertedIndex
from core.keyword_extractor import KeywordExtractor
from core.paper import Paper, paper_content_key
from core.preprocessor import Preprocessor
from core.translator import Translator, detect_lang
from core.trie import Trie

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPERS_PATH = PROJECT_ROOT / "data" / "papers.json"
UPLOAD_DIR = PROJECT_ROOT / "uploads"
FILES_DIR = PROJECT_ROOT / "data" / "papers_files"

MIN_PAPERS = 150  # 论文少于该数量时启动自动采集


class SearchService:
    """学术论文检索服务的组合根对象。"""

    def __init__(self, min_papers=MIN_PAPERS, auto_fetch=True,
                 papers_path=None, files_dir=None, uploads_dir=None):
        self.min_papers = min_papers
        self.auto_fetch = auto_fetch
        self.papers_path = Path(papers_path) if papers_path else PAPERS_PATH
        # 原文归档目录与上传临时目录：默认项目内；测试可注入隔离目录
        self.files_dir = Path(files_dir) if files_dir else FILES_DIR
        self.uploads_dir = Path(uploads_dir) if uploads_dir else UPLOAD_DIR
        self._lock = threading.RLock()
        self._preprocessor = Preprocessor()
        self._extractor = KeywordExtractor(self._preprocessor)
        self._translator = Translator()
        self._index = InvertedIndex(self._preprocessor)
        self._trie = Trie()
        self._content_idx = {}   # 内容键 -> paper_id（严格去重）
        self._crawl = {"running": False, "total": 0, "message": ""}
        self._load_or_fetch()    # 数据不足时自动采集

    # ---------------- 装载与重建 ----------------

    def _load_or_fetch(self):
        """读取论文数据；不足 min_papers 时自动触发 arXiv 采集。"""
        from crawler.arxiv_crawler import ensure_papers, load_papers
        data = (ensure_papers(min_papers=self.min_papers,
                              path=self.papers_path)
                if self.auto_fetch else load_papers(self.papers_path))
        self._index.build(self._map_papers(data))
        self._finalize_keywords()
        self._rebuild_trie()
        self._rebuild_content_index()
        self._persist()
        print(f"[系统] 索引就绪：{self._index.stats()}")

    @staticmethod
    def _map_papers(data):
        """把 JSON 记录映射为 Paper，保证内部整数 ID 唯一。"""
        used = set()
        papers = []

        def next_free():
            pid = 0
            while pid in used:
                pid += 1
            return pid

        for raw in data:
            paper = Paper.from_dict(raw)
            if paper.paper_id is None or paper.paper_id in used:
                paper.paper_id = next_free()
            used.add(paper.paper_id)
            papers.append(paper)
        return papers

    def _finalize_keywords(self):
        """为每篇论文计算关键词并重建索引（关键词参与检索）。"""
        index = self._index
        for paper in list(index.papers.values()):
            paper.keywords = self._extractor.extract(
                paper.title, paper.abstract,
                total_docs=len(index.papers),
                df_lookup=lambda t: len(index.get_postings(t)))
        index.build(list(index.papers.values()))

    def _rebuild_trie(self):
        """基于索引词条的原词映射重建 Trie（补全输入的是原词）。"""
        self._trie = Trie()
        for counter in self._index.term_display.values():
            for orig, freq in counter.items():
                self._trie.insert(orig, freq)

    def _rebuild_content_index(self):
        """重建内容键表（严格去重判定）。"""
        self._content_idx = {}
        for pid, paper in self._index.papers.items():
            self._content_idx.setdefault(paper.content_key(), pid)

    def _persist(self):
        """把论文原子写回数据文件（排序后写入，避免半截文件）。"""
        data = [p.to_dict() for p in
                sorted(self._index.papers.values(), key=lambda p: p.paper_id)]
        self.papers_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.papers_path.parent),
                                   suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.papers_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ---------------- 查询接口 ----------------

    def stats(self):
        """统计：论文数 / 关键词数 / 索引项数 / 停用词数。"""
        with self._lock:
            stats = self._index.stats()
        stats["stopwords_count"] = len(self._preprocessor.stopwords)
        return stats

    def meta(self):
        """系统元信息（前端开关使用）。"""
        with self._lock:
            stats = self._index.stats()
        try:
            from agent.llm import is_configured
            llm_ok = is_configured()
        except Exception:
            llm_ok = False
        langs = {}
        for paper in self._index.papers.values():
            lang = paper.language or "en"
            langs[lang] = langs.get(lang, 0) + 1
        return {
            "total_papers": stats["total_papers"],
            "unique_terms": stats["unique_terms"],
            "total_postings": stats["total_postings"],
            "llm_configured": llm_ok,
            "languages": langs,
        }

    def search(self, query, mode="tf", top_k=50, cross=False):
        """统一检索。

        cross=True 或查询含中文时启用跨语言扩展：
        原词 ∪ 双语词典同义词做并集检索（命中任一即候选，按相关性排序）。
        纯英文且未开启 cross 时保持经典 AND 语义。
        """
        query = (query or "").strip()
        if not query:
            return {"query": "", "count": 0, "results": [], "error": "查询内容为空"}
        with self._lock:
            index = self._index
            lang = detect_lang(query)
            want_cross = cross or lang in ("zh", "mixed")
            if want_cross and not index._looks_boolean(query):
                tokens, originals = self._preprocessor.tokenize(
                    query, with_originals=True)
                originals = list(dict.fromkeys(originals))
                translations = self._translator.expand(originals)
                # 短语级互译：连续 2~3 个原词拼成短语后再查词典，
                # 覆盖 neural network -> 神经网络 等整词映射
                if detect_lang(query) != "zh":
                    for n in (2, 3):
                        for i in range(len(originals) - n + 1):
                            phrase = " ".join(originals[i:i + n])
                            syn = self._translator.translate(phrase)
                            if syn:
                                translations.setdefault(
                                    phrase, {"lang": "en", "syn": syn})
                if translations:
                    # 同义词（可能是英文短语/中文词）也经同一分词管线变索引键
                    union = list(dict.fromkeys(tokens))
                    for info in translations.values():
                        for phrase in info["syn"]:
                            union.extend(
                                self._preprocessor.tokenize(phrase))
                    union = list(dict.fromkeys(union))
                    return index.search_union(query, union, mode=mode,
                                              top_k=top_k,
                                              translations=translations)
            return index.search(query, mode=mode, top_k=top_k)

    def suggest(self, prefix, top_k=10):
        """Trie 前缀补全；前缀未命中时回退“子串包含”扫描（中英文通用）。"""
        prefix = (prefix or "").strip()
        with self._lock:
            hits = self._trie.suggest(prefix, top_k=top_k)
            if hits or len(prefix) < 2:
                return hits
            # 子串兜底：输入位于词条中间（如 网络 ⊂ 神经网络）
            lowered = prefix.lower()
            candidates = []
            for term, counter in self._index.term_display.items():
                if lowered in term:
                    candidates.append((sum(counter.values()), term))
            candidates.sort(reverse=True)
            return [{"term": term, "freq": freq}
                    for freq, term in candidates[:top_k]]

    def index_snapshot(self, limit=20):
        """倒排索引原始结构快照。"""
        with self._lock:
            return self._index.index_snapshot(limit=limit)

    # ---------------- 文库管理 ----------------

    def list_papers(self, page=1, size=20, query=""):
        """论文文库分页（可按标题/作者/摘要包含过滤）。"""
        with self._lock:
            papers = sorted(self._index.papers.values(),
                            key=lambda p: p.paper_id)
            if query:
                q = query.lower()
                papers = [p for p in papers
                          if q in p.title.lower()
                          or q in p.abstract.lower()
                          or any(q in (a or "").lower() for a in p.authors)]
            total = len(papers)
            start = (page - 1) * size
            items = [p.to_dict() for p in papers[start:start + size]]
        return {"total": total, "page": page, "size": size, "papers": items}

    def get_paper(self, paper_id):
        """单篇论文详情。"""
        with self._lock:
            paper = self._index.papers.get(paper_id)
            return paper.to_dict() if paper else None

    def _stored_path(self, file_store):
        """把 file_store 解析为受控的归档绝对路径（越界/不存在返回 None）。

        兼容三种形态：相对项目根（默认）、纯文件名（files_dir 内）、绝对路径。
        """
        if not file_store:
            return None
        files_root = self.files_dir.resolve()
        candidates = [PROJECT_ROOT / file_store, self.files_dir / file_store,
                      Path(file_store)]
        for cand in candidates:
            try:
                path = cand.resolve()
            except OSError:
                continue
            if path.is_relative_to(files_root) and path.exists():
                return path
        return None

    def resolve_file(self, paper_id):
        """返回论文原文文件的 (绝对路径, 展示名)；无文件或越界返回 None。"""
        with self._lock:
            paper = self._index.papers.get(paper_id)
            if paper is None:
                return None
            path = self._stored_path(paper.file_store)
            if path is None:
                return None
            return path, paper.file_name or path.name

    def remove_paper(self, paper_id):
        """删除论文并重建索引；同步清理内容键表与原文文件。"""
        with self._lock:
            papers = self._index.papers
            paper = papers.get(paper_id)
            if paper is None:
                return False
            path = self._stored_path(paper.file_store)
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            del papers[paper_id]
            self._index.build(list(papers.values()))
            self._rebuild_trie()
            self._rebuild_content_index()
            self._persist()
            return True

    # ---------------- 动态入库 ----------------

    def add_manual(self, data):
        """手动添加论文（title 必填；严格去重）。"""
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("缺少论文标题")
        result = self._add_from_meta({
            "title": title,
            "abstract": (data.get("abstract") or "").strip(),
            "authors": data.get("authors") or [],
            "year": data.get("year"),
            "source_id": data.get("source_id") or data.get("id"),
            "keywords": data.get("keywords"),
            "language": data.get("language"),
            "source": "manual",
        })
        return self._pack_result(result)

    def add_by_url(self, url):
        """按 arXiv URL/编号 添加论文（严格去重）。"""
        from crawler.arxiv_crawler import fetch_by_arxiv_id
        info = fetch_by_arxiv_id(url)
        if not info:
            raise ValueError(f"未找到 arXiv 论文：{url}")
        result = self._add_from_meta({
            "title": info.get("title", ""),
            "abstract": info.get("abstract", ""),
            "authors": info.get("authors") or [],
            "year": info.get("year"),
            "source_id": info.get("id"),
            "language": "en",
            "source": "url",
        })
        return self._pack_result(result)

    @staticmethod
    def _pack_result(result):
        """把入库结果统一为 {ok, paper} 或 {ok:False, duplicate, existing}。"""
        if "duplicate" in result:
            return {**result, "ok": False}
        return {"ok": True, "paper": result}

    def add_file(self, file_stream, filename, use_ai=False):
        """上传单个文档（PDF / 纯文本）并入库（原文归档 + 严格去重）。

        上传临时副本解析后立即清理；原文在 _add_from_meta 归档到 files_dir。
        """
        from ingest.document_parser import parse_file

        data_bytes = file_stream.read()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        safe = f"{int(time.time())}_{Path(filename).name}"
        save_path = self.uploads_dir / safe
        save_path.write_bytes(data_bytes)
        try:
            parsed = parse_file(str(save_path), use_ai=use_ai)
            meta = parsed["meta"]
            if not meta["title"]:
                raise ValueError("未能识别论文标题，请改用 AI 精修或手动填写")
            meta.setdefault("source", "upload")
            result = self._add_from_meta(
                meta, file_bytes=data_bytes, file_name=Path(filename).name,
                file_ext=Path(filename).suffix.lower())
            if "duplicate" in result:
                return {**result, "ok": False}
            return {
                "ok": True,
                "paper": result,
                "confidence": parsed["confidence"],
                "ai_used": parsed["ai_used"],
            }
        finally:
            # 临时解析副本用后即删（原文已在 files_dir 归档）
            try:
                save_path.unlink(missing_ok=True)
            except OSError:
                pass

    def add_zip(self, file_stream, use_ai=False):
        """批量导入 ZIP；逐文件结果分 added / duplicated / failed 三组。"""
        from io import BytesIO

        from ingest.document_parser import parse_file
        from ingest.errors import friendly_parse_error
        from ingest.zip_importer import extract_entries

        # werkzeug 上传流为 SpooledTemporaryFile，Python 3.10 的 zipfile
        # 访问 .seekable 属性会失败，先读入内存再解包
        entries = extract_entries(BytesIO(file_stream.read()))
        added, duplicated, failed = [], [], []
        for entry in entries:
            try:
                data_bytes = Path(entry.path).read_bytes()
                parsed = parse_file(entry.path, use_ai=use_ai)
                meta = parsed["meta"]
                if not meta["title"]:
                    raise ValueError("未能识别论文标题")
                meta.setdefault("source", "upload")
                result = self._add_from_meta(
                    meta, file_bytes=data_bytes, file_name=entry.name,
                    file_ext=Path(entry.name).suffix.lower())
                if "duplicate" in result:
                    duplicated.append({
                        "name": entry.name,
                        **result["existing"],
                    })
                else:
                    added.append({
                        "name": entry.name,
                        "paper_id": result["id"],
                        "title": result["title"],
                        "ai_used": parsed["ai_used"],
                    })
            except Exception as exc:
                failed.append({"name": entry.name,
                               "error": friendly_parse_error(exc)})
        if entries:
            shutil.rmtree(Path(entries[0].path).parent, ignore_errors=True)
        return {"added": added, "duplicated": duplicated, "failed": failed}

    def _add_from_meta(self, meta, file_bytes=None, file_name=None,
                       file_ext=""):
        """公共入库流水线：严格去重 -> 原文归档 -> 索引 -> 持久化。

        返回论文 to_dict；若内容与库内完全一致则返回
        {"duplicate": True, "existing": {paper_id, title}}。
        """
        with self._lock:
            index = self._index
            title = (meta.get("title") or "").strip()
            content_key = paper_content_key(
                title, meta.get("abstract", ""), meta.get("authors") or [],
                meta.get("year"))
            dup_id = self._content_idx.get(content_key)
            if dup_id is not None:
                dup = index.papers[dup_id]
                return {"duplicate": True,
                        "existing": {"paper_id": dup.paper_id,
                                     "title": dup.title}}

            paper_id = index.next_id()
            # 关键词来源：显式提供（手动）> AI 精修词 > 规则提取（清洗后文本）
            explicit_kw = meta.get("keywords") or meta.get("agent_keywords")
            keywords = (list(explicit_kw) if explicit_kw else
                        self._extractor.extract(
                            title, meta.get("abstract", ""),
                            total_docs=len(index.papers),
                            df_lookup=lambda t: len(index.get_postings(t))))

            file_store = None
            if file_bytes:
                file_store = self._store_file(paper_id, file_bytes, file_ext)
            paper = Paper(
                paper_id=paper_id,
                title=title,
                abstract=meta.get("abstract", ""),
                authors=meta.get("authors") or [],
                year=meta.get("year"),
                source_id=meta.get("source_id") or meta.get("id"),
                keywords=keywords,
                file_name=file_name,
                file_store=file_store,
                language=meta.get("language"),
                source=meta.get("source") or "manual",
            )
            index.add_paper(paper)
            self._content_idx[content_key] = paper_id
            self._rebuild_trie()
            self._persist()
            return paper.to_dict()

    def _store_file(self, paper_id, data_bytes, ext):
        """把上传原文归档到 files_dir，返回可持久化的 file_store 值。

        默认目录在项目 data/papers_files 下 -> 存相对项目根路径（可移植）；
        注入的自定义目录 -> 存绝对路径（测试隔离用）。
        """
        digest = hashlib.sha256(data_bytes).hexdigest()[:8]
        self.files_dir.mkdir(parents=True, exist_ok=True)
        name = f"{paper_id}_{digest}{ext or '.bin'}"
        dest = self.files_dir / name
        if not dest.exists():
            dest.write_bytes(data_bytes)
        try:
            return str(dest.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return str(dest)

    # ---------------- 数据采集 ----------------

    def crawl_start(self, source="arxiv", pages=2):
        """后台抓取（arxiv / openalex / all），严格合并并重建索引。

        状态字段：running / total / message / added / skipped / source。
        """
        from crawler.arxiv_crawler import load_papers
        from crawler.registry import SOURCES, merge_strict

        sources = ["arxiv", "openalex"] if source == "all" else [source]
        if source not in SOURCES and source != "all":
            raise ValueError(f"未知数据源：{source}")
        with self._lock:
            if self._crawl["running"]:
                return False
            self._crawl.update(running=True, total=0, added=0, skipped=0,
                               source="+".join(sources),
                               message="启动中（" + "+".join(sources) + "）")

        def worker():
            try:
                existing = load_papers(self.papers_path)
                merged = existing
                for name in sources:
                    fetched = SOURCES[name](
                        limit=600, pages=pages,
                        progress_cb=lambda n: self._crawl.update(total=n))
                    report = merge_strict(merged, fetched)
                    merged = report["papers"]
                    self._crawl["added"] += report["added"]
                    self._crawl["skipped"] += report["skipped"]
                self._crawl["message"] = "数据已更新，正在重建索引..."
                with self._lock:
                    papers = self._map_papers(merged)
                    self._index.build(papers)
                    self._finalize_keywords()
                    self._rebuild_trie()
                    self._rebuild_content_index()
                    self._persist()
                added = self._crawl["added"]
                skipped = self._crawl["skipped"]
                self._crawl["message"] = (
                    f"采集完成：新增 {added} 篇"
                    + (f"（内容重复跳过 {skipped} 篇）" if skipped else ""))
            except Exception:
                from logutil import get_logger
                get_logger().exception("采集失败 source=%s", source)
                self._crawl["message"] = "采集失败，详情见 logs/app.log"
            finally:
                self._crawl["running"] = False

        threading.Thread(target=worker, daemon=True).start()
        return True

    def crawl_status(self):
        """后台采集状态。"""
        with self._lock:
            return dict(self._crawl)
