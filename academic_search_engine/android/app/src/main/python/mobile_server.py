# -*- coding: utf-8 -*-
"""移动端入口：被 Android（Chaquopy）调用，在 App 私有数据目录上启动 Flask。

约定：
- data_root：App 首次启动把 assets/academic 解压到的私有目录（filesDir/academic）；
  本模块把它注入 ACADEMIC_DATA_ROOT 环境变量，之后 web/service/core 等模块的
  PROJECT_ROOT 全部指向该目录（源码目录只读、禁止写数据）。
- 必须在 import 任何业务模块之前设置环境变量（模块级常量在 import 时求值）。
- 启动异常会写入 data_root/startup-error.log 并原样抛出，便于手机端排查。
"""

import os
import sys
import threading
import traceback


def _write_error(data_root, exc):
    """把启动异常完整写盘，方便无 logcat 时排查。"""
    try:
        log_dir = os.fspath(data_root)
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "startup-error.log"),
                  "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
    except Exception:
        pass


def start(data_root: str, port: int = 8765, host: str = "127.0.0.1") -> int:
    """在后台线程启动 Flask 服务并立即返回端口号（不阻塞调用方）。"""
    os.environ["ACADEMIC_DATA_ROOT"] = os.fspath(data_root)
    os.environ["ACADEMIC_MOBILE"] = "1"

    # stdout/stderr 在 Chaquopy 下默认重定向到 Logcat，便于 adb 查看
    print("[mobile] ACADEMIC_DATA_ROOT =", data_root, flush=True)

    try:
        # 延迟导入：此时 ACADEMIC_DATA_ROOT 已就绪
        from web import create_app
        from werkzeug.serving import make_server

        # 数据由 assets 预置，启动时不联网爬取
        print("[mobile] creating flask app ...", flush=True)
        app = create_app(auto_fetch=False)
        print("[mobile] app ready, starting server ...", flush=True)
        server = make_server(host, port, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print("[mobile] server started on %s:%s" % (host, port), flush=True)
        return port
    except Exception as exc:
        print("[mobile] STARTUP FAILED", flush=True)
        traceback.print_exc()
        _write_error(data_root, exc)
        raise
