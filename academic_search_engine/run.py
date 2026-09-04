# -*- coding: utf-8 -*-
"""学术论文关键词索引与检索系统 —— 项目启动入口。

用法：
    python run.py [--port 5000] [--no-crawl]

说明：
- 启动时若 data/papers.json 缺失或论文数 < 150，自动触发 arXiv 爬虫采集；
- --no-crawl 可跳过该检查（数据已就绪时快速启动）。
"""

import argparse
import sys

from web import create_app


def _safe_stream(stream):
    """控制台/管道输出统一 UTF-8 + 替换错误，杜绝非 GBK 字符导致崩溃。"""
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main():
    _safe_stream(sys.stdout)
    _safe_stream(sys.stderr)

    parser = argparse.ArgumentParser(description="学术论文检索系统")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-crawl", action="store_true",
                        help="跳过启动时论文数不足的自动爬取检查")
    args = parser.parse_args()

    app = create_app(auto_fetch=not args.no_crawl)
    from logutil import get_logger
    get_logger().info("服务启动: http://%s:%s", args.host, args.port)
    print(f"[系统] 服务已就绪：http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
