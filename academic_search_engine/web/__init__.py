# -*- coding: utf-8 -*-
"""web 包：Flask 应用层（工厂模式）。

create_app()：
1. 从项目根目录加载 .env（Agent 密钥等仅存于此）；
2. 构造检索服务单例（数据不足会自动爬取）；
3. 注册路由蓝图与统一 JSON 错误处理。
"""

import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from paths import DATA_ROOT, RESOURCE_ROOT
from .routes import register_routes


def _load_env():
    """加载 .env：数据根优先，其次资源根（同一目录时只加载一次）。

    注意：AI 配置的最终权威是应用内「设置」页（agent/settings.py），
    其会在本函数之后把 app_settings.json 覆盖到 os.environ。
    """
    load_dotenv(DATA_ROOT / ".env")
    if RESOURCE_ROOT != DATA_ROOT:
        load_dotenv(RESOURCE_ROOT / ".env")


def create_app(service=None, auto_fetch=True):
    """创建 Flask 应用。

    service 可注入（测试用）；auto_fetch=False 时跳过“数据不足自动爬取”。
    """
    _load_env()

    app = Flask(
        __name__,
        template_folder=str(RESOURCE_ROOT / "templates"),
        static_folder=str(RESOURCE_ROOT / "static"),
    )
    app.json.ensure_ascii = False  # 中文以 UTF-8 输出
    CORS(app)

    if service is None:
        from agent import settings as settings_store
        settings_store.apply_to_env()  # 设置页配置优先于 .env（见 agent/settings.py）
        from service.search_service import SearchService
        service = SearchService(auto_fetch=auto_fetch)
    app.config["SERVICE"] = service

    register_routes(app)
    return app
