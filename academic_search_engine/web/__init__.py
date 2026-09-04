# -*- coding: utf-8 -*-
"""web 包：Flask 应用层（工厂模式）。

create_app()：
1. 从项目根目录加载 .env（Agent 密钥等仅存于此）；
2. 构造检索服务单例（数据不足会自动爬取）；
3. 注册路由蓝图与统一 JSON 错误处理。
"""

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from .routes import register_routes

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(service=None, auto_fetch=True):
    """创建 Flask 应用。

    service 可注入（测试用）；auto_fetch=False 时跳过“数据不足自动爬取”。
    """
    load_dotenv(PROJECT_ROOT / ".env")

    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.json.ensure_ascii = False  # 中文以 UTF-8 输出
    CORS(app)

    if service is None:
        from service.search_service import SearchService
        service = SearchService(auto_fetch=auto_fetch)
    app.config["SERVICE"] = service

    register_routes(app)
    return app
