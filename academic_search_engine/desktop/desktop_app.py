# -*- coding: utf-8 -*-
"""桌面独立软件入口（PyInstaller onefile + pywebview/WebView2 内置窗口）。

行为：
- frozen 打包：只读资源(模板/静态/种子)在 _MEIPASS，可写数据(论文库/日志/AI 配置)在 exe 同级目录；
  首次启动自动把种子数据 data/papers.json 等复制到数据目录；
- 启动本地 Flask 服务 -> 打开独立窗口（标题/图标/可缩放），窗口关闭即退出，无残留进程；
- 系统缺少 WebView2 运行时或窗口启动失败时，自动回退到默认浏览器打开；
- 参数 --browser 强制使用系统浏览器模式（不弹窗口）。
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path


def _app_root():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent.parent


def _data_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _app_root()


def _seed_if_needed(data: Path, resource: Path):
    """把内置种子数据复制到可写数据目录（仅缺失时）。"""
    dst = data / "data"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("papers.json", "stopwords.txt", "bilingual.json"):
        src = resource / "data" / name
        if src.exists() and not (dst / name).exists():
            try:
                (dst / name).write_bytes(src.read_bytes())
            except OSError as exc:
                print("[desktop] seed %s failed: %s" % (name, exc))


def _write_error_log(data: Path, text: str):
    try:
        log = data / "startup-error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
    except Exception:
        pass


def _find_port(base=5000):
    import socket
    for port in range(base, base + 40):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return base


def _hold_and_serve(server, url):
    """浏览器回退模式：服务常驻直到 Ctrl+C / 进程结束。"""
    print("[desktop] 本地服务已启动: " + url)
    print("[desktop] 关闭此控制台(Ctrl+C)即退出服务。")
    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.shutdown()
        except Exception:
            pass


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    app_root = _app_root()
    data_root = _data_root()
    os.environ.setdefault("ACADEMIC_DATA_ROOT", str(data_root))
    if app_root != data_root:
        os.environ.setdefault("ACADEMIC_RESOURCE_ROOT", str(app_root))
    _seed_if_needed(data_root, app_root)
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    force_browser = "--browser" in sys.argv
    port = _find_port()
    url = "http://127.0.0.1:%d" % port

    # 延迟导入：环境变量已就绪（web 工厂内部会加载 AI 设置文件并应用）
    from web import create_app
    from werkzeug.serving import make_server
    try:
        app = create_app()
    except Exception:
        import traceback
        traceback.print_exc()
        _write_error_log(data_root, traceback.format_exc())
        return 1

    try:
        server = make_server("127.0.0.1", port, app, threaded=True)
    except OSError as exc:
        _write_error_log(data_root, str(exc))
        print("[desktop] 端口占用或绑定失败: %s" % exc)
        return 1
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if force_browser:
        webbrowser.open(url)
        return _hold_and_serve(server, url)

    try:
        import webview  # noqa: F401
    except Exception as exc:
        print("[desktop] pywebview 不可用，回退系统浏览器: %s" % exc)
        webbrowser.open(url)
        return _hold_and_serve(server, url)

    class FileBridge:
        """前端桥：原生文件对话框 + 服务端直传（pywebview 窗口内 file input 不可靠）。"""

        def __init__(self, base_url):
            self._base = base_url
            self._win = None

        def attach(self, win):
            self._win = win

        def pick_upload(self, ai):
            if self._win is None:
                return {"error": "窗口尚未就绪，请稍候重试"}
            try:
                files = self._win.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=False,
                    file_types=("Documents (*.pdf;*.txt;*.md;*.zip)",),
                )
            except Exception as exc:
                return {"error": "打开文件对话框失败：%s" % exc}
            if not files:
                return {"cancelled": True}
            return self._post(files[0], 1 if ai else 0)

        def pickUpload(self, ai):
            """与 JS 端命名对齐的入口（pywebview 按方法名原样暴露）。"""
            return self.pick_upload(ai)

        def _post(self, path, ai):
            import os
            import requests
            try:
                with open(path, "rb") as fh:
                    resp = requests.post(
                        self._base + "/api/papers/file",
                        files={"file": (os.path.basename(path), fh)},
                        data={"ai": str(ai)},
                        timeout=300,
                    )
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                if resp.status_code >= 400:
                    data["error"] = data.get("error") or (
                        "服务器返回异常（HTTP %d）" % resp.status_code)
                return data
            except Exception as exc:
                return {"error": "上传失败：%s" % exc}

    bridge = FileBridge(url)
    try:
        win = webview.create_window(
            "学术论文检索",
            url,
            width=1180,
            height=780,
            min_size=(980, 620),
            resizable=True,
            background_color="#f6f4ee",
            js_api=bridge,
        )
        bridge.attach(win)
        webview.start()
        print("[desktop] 窗口已关闭，退出。")
    except Exception as exc:
        print("[desktop] 内置窗口启动失败，回退系统浏览器: %s" % exc)
        webbrowser.open(url)
        return _hold_and_serve(server, url)
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())