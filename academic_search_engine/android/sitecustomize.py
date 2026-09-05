# -*- coding: utf-8 -*-
"""sitecustomize —— 构建期环境修补（仅影响 Chaquopy 的 pip 阶段）。

背景：本机构建沙箱对以 mode=0o700 创建（os.mkdir/tempfile.mkdtemp）的目录
拒绝其后的文件写入（ACL 受限），而 pip 解包恰用 mkdtemp(0o700) 建临时目录，
导致 pip install 报 Permission denied。

对策：把 os.mkdir 的 mode 参数一律规约为沙箱接受的默认值（不传 mode），
使 pip 能正常解包。仅在 Windows 下生效，不影响 Linux/macOS 正常构建。
"""

import os
import sys

if sys.platform == "win32":
    _orig_mkdir = os.mkdir

    def _mkdir_safe(path, mode=0o777, *, dir_fd=None):
        # Windows 上 mode 本就无 POSIX 语义；不传 mode 以规避沙箱 ACL 限制
        if dir_fd is not None:
            return _orig_mkdir(path, dir_fd=dir_fd)
        return _orig_mkdir(path)

    os.mkdir = _mkdir_safe
