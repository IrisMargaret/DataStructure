# -*- coding: utf-8 -*-
"""Web 路由（薄层）：只做参数解析与 JSON 化，全部业务委托 SearchService。

按功能分三节：
- 检索：/api/search /api/suggest /api/index /api/stats /api/meta
- 文库：/api/papers（列表/详情/新增/删除）
- 系统：/api/crawl /api/crawl/status

错误约定：统一返回 {"error": msg}，配合 400/404/409/502 状态码。
"""

import time

from flask import jsonify, render_template, request

from ingest.errors import friendly_parse_error
from logutil import get_logger


def _safe_int(raw, default, lo=1, hi=10 ** 6):
    """宽容解析整型参数：非法/越界回退默认，避免 500。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return min(max(value, lo), hi)


def register_routes(app):
    """把全部路由注册到 app（业务实例取 app.config['SERVICE']）。"""
    svc = app.config["SERVICE"]
    logger = get_logger()

    # ---------------- 页面 ----------------

    @app.get("/")
    def home():
        return render_template("index.html")

    # ---------------- 检索 ----------------

    @app.get("/api/search")
    def api_search():
        query = request.args.get("q", "").strip()
        mode = request.args.get("mode", "tf")
        cross = request.args.get("cross") == "1"
        if mode not in ("tf", "tfidf"):
            mode = "tf"
        if not query:
            return jsonify({"error": "查询内容为空", "count": 0,
                            "results": []})
        started = time.time()
        result = svc.search(query, mode=mode, cross=cross)
        result["time_ms"] = round((time.time() - started) * 1000, 2)
        return jsonify(result)

    @app.get("/api/suggest")
    def api_suggest():
        prefix = request.args.get("prefix", "").strip()
        return jsonify({"prefix": prefix,
                        "suggestions": svc.suggest(prefix, top_k=10)})

    @app.get("/api/index")
    def api_index():
        limit = _safe_int(request.args.get("limit"), 20, 1, 200)
        return jsonify(svc.index_snapshot(limit=limit))

    @app.get("/api/stats")
    def api_stats():
        return jsonify(svc.stats())

    @app.get("/api/meta")
    def api_meta():
        return jsonify(svc.meta())

    # ---------------- 文库 ----------------

    @app.get("/api/papers")
    def api_papers():
        page = _safe_int(request.args.get("page"), 1)
        size = _safe_int(request.args.get("size"), 20, 1, 100)
        query = request.args.get("q", "").strip()
        return jsonify(svc.list_papers(page=page, size=size, query=query))

    @app.get("/api/papers/<int:paper_id>")
    def api_paper_detail(paper_id):
        paper = svc.get_paper(paper_id)
        if paper is None:
            return jsonify({"error": "论文不存在"}), 404
        return jsonify(paper)

    @app.get("/api/papers/<int:paper_id>/file")
    def api_paper_file_download(paper_id):
        """下载/内联查看论文原文文件（仅库内归档路径）。"""
        import mimetypes
        from flask import send_file

        resolved = svc.resolve_file(paper_id)
        if resolved is None:
            return jsonify({"error": "该论文没有可下载的原文文件"}), 404
        path, display_name = resolved
        mime, _ = mimetypes.guess_type(str(path))
        return send_file(path, as_attachment=False,
                         download_name=display_name,
                         mimetype=mime or "application/octet-stream")

    @app.delete("/api/papers/<int:paper_id>")
    def api_paper_delete(paper_id):
        if not svc.remove_paper(paper_id):
            return jsonify({"error": "论文不存在"}), 404
        return jsonify({"ok": True})

    @app.post("/api/papers/manual")
    def api_paper_manual():
        data = request.get_json(silent=True) or {}
        try:
            return jsonify(svc.add_manual(data))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/papers/url")
    def api_paper_url():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "URL 为空"}), 400
        try:
            return jsonify(svc.add_by_url(url))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.post("/api/papers/file")
    def api_paper_file():
        """上传 PDF / 纯文本 / ZIP（按扩展名自动识别）。

        multipart 字段：file 必填；ai 缺省开启（配置 .env 后自动 AI 精修，
        前端取消勾选时显式传 ai=0）。重复导入返回 {duplicate:true,…}。
        """
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return jsonify({"error": "未选择文件"}), 400
        use_ai = request.form.get("ai", "1") == "1"
        name = uploaded.filename.lower()
        try:
            if name.endswith(".zip"):
                return jsonify(svc.add_zip(uploaded.stream, use_ai=use_ai))
            return jsonify(svc.add_file(uploaded.stream, uploaded.filename,
                                        use_ai=use_ai))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            # 完整异常写入日志；对用户只给中文可读提示
            logger.exception("解析失败 filename=%s", uploaded.filename)
            return jsonify({"error": friendly_parse_error(exc)}), 400

    # ---------------- 系统（爬虫） ----------------

    @app.post("/api/crawl")
    def api_crawl():
        data = request.get_json(silent=True) or {}
        source = data.get("source", "arxiv")
        pages = _safe_int(data.get("pages"), 2, 1, 5)
        try:
            if not svc.crawl_start(source, pages=pages):
                return jsonify({"ok": False, "message": "爬虫已在运行中"}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "message": f"爬虫已启动（{source}，"
                                              f"翻页深度 {pages}），可在后台查看进度"})

    @app.get("/api/crawl/status")
    def api_crawl_status():
        return jsonify(svc.crawl_status())

    # ---------------- 统一错误处理 ----------------

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "接口不存在"}), 404

    @app.errorhandler(500)
    def server_error(_error):
        return jsonify({"error": "服务器内部错误"}), 500
