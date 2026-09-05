# -*- coding: utf-8 -*-
"""程序化生成应用图标（品牌资源）。

用法：python scripts/gen_icons.py [--variant sunset|paper|midnight]

输出（全部位图按目标尺寸超采样绘制，抗锯齿）：
- android: mipmap-*dpi 的 ic_launcher / ic_launcher_round（legacy 48-192）
          与 ic_launcher_foreground（adaptive 108dp 各密度）+ anydpi-v26 xml
- web:     static/img/favicon.svg 已有；另输出 favicon.png(64) 与 icon-192.png
- desktop: desktop/app.ico（16-256 多尺寸，PyInstaller/窗口图标）
- 预览:    .build-tmp/icon_preview/<variant>.png（512，候选对比用）
"""

import sys
import xml.sax.saxutils as sax
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent

# ---------------- 调色板 ----------------

PALETTES = {
    # 暖纸 x 陶土橙（默认方向）：陶土底 + 奶油书页
    "sunset": {
        "bg": (185, 79, 34),       # #B94F22
        "bg2": (143, 59, 22),      # #8F3B16 深角（微妙的双色底）
        "fg": (255, 244, 228),     # 奶油
        "line": (92, 34, 10),      # 深线（行文字）
        "ring": (255, 228, 199),   # 放大镜圈
    },
    # 纸白底 + 陶土几何（柔和学术）
    "paper": {
        "bg": (246, 244, 238),
        "bg2": (240, 236, 226),
        "fg": (185, 79, 34),
        "line": (143, 59, 22),
        "ring": (143, 59, 22),
    },
    # 深炭底（科研极简）
    "midnight": {
        "bg": (46, 43, 38),
        "bg2": (34, 31, 27),
        "fg": (255, 244, 228),
        "line": (203, 178, 146),
        "ring": (224, 146, 98),
    },
}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vertical_gradient(size, c_top, c_bottom):
    """返回纵向渐变图片（用于整块底）。"""
    img = Image.new("RGB", size, c_top)
    px = img.load()
    w, h = size
    for y in range(h):
        col = lerp(c_top, c_bottom, y / max(1, h - 1))
        for x in range(w):
            px[x, y] = col
    return img


def draw_master(pal):
    """在 1024 画布绘制最终主图（含底与内容），返回 RGBA。"""
    S = 1024
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = vertical_gradient((S, S), pal["bg"], pal["bg2"])
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, S - 1, S - 1], radius=230, fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)

    cx = 512
    # ---- 打开的书（两页 + 中缝） ----
    top_in = 330
    bot_in = 806
    lip = 24   # 页边斜口
    left_page = [(cx, top_in + 26), (266, 402), (266, 826), (cx, 778)]
    right_page = [(cx, top_in + 26), (758, 402), (758, 826), (cx, 778)]
    d.polygon(left_page, fill=pal["fg"])
    d.polygon(right_page, fill=pal["fg"])
    # 封面下缘（两页之间露出一点深色）
    d.line([(cx, top_in + 26), (cx, 778)], fill=pal["bg2"], width=30)
    # 页内行（正文行/关键词行）
    row_col = pal["line"]
    for i in range(3):
        y = 512 + i * 78
        w_row = 296 if i == 0 else (210 if i == 1 else 152)
        x_l = 330
        x_r = 694 - w_row
        d.line([(x_l, y), (x_l + w_row, y)], fill=row_col, width=24)
        d.line([(x_r, y), (x_r + w_row, y)], fill=row_col, width=24)
    # 标题行
    d.line([(cx - 190, 452), (cx + 190, 452)], fill=row_col, width=26)

    # ---- 放大镜（检索），压在右下页上 ----
    ring = pal["ring"]
    rc = (688, 622)
    rr = 176
    lens = lerp(pal["fg"], pal["bg"], 0.06)
    d.ellipse([rc[0] - rr, rc[1] - rr, rc[0] + rr, rc[1] + rr],
              outline=ring, width=58)
    # 把镜内行覆盖成透镜浅色
    lens_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lens_img)
    ld.ellipse([rc[0] - rr + 34, rc[1] - rr + 34,
                rc[0] + rr - 34, rc[1] + rr - 34], fill=lens + (255,))
    img.alpha_composite(lens_img)
    # 重画镜圈（避免被透镜盖住）
    d.ellipse([rc[0] - rr, rc[1] - rr, rc[0] + rr, rc[1] + rr],
              outline=ring, width=58)
    # 手柄
    import math as _m
    hx = rc[0] + rr - 40
    hy = rc[1] + rr - 40
    ex = hx + 170
    ey = hy + 170
    d.line([(hx, hy), (ex, ey)], fill=ring, width=64)
    cap = 46
    d.ellipse([ex - cap, ey - cap, ex + cap, ey + cap], fill=ring)
    return img


def rounded_icon(master, size, radius_ratio=0.23):
    """缩放到 size 并切成圆角方形（legacy 图标可用；角外透明）。"""
    img = master.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out

def render_fg(master, size):
    """自适应前景：内容安全区绘制（无底色）。
    前景画布=108dp；内容须落在中心约 66dp 圆内 => 画布留白 (108-66)/108/2。
    直接在主图上把外圈(切角之外的内容)去掉：此处简单取主图中心 62% 缩小。
    """
    crop = 0.70
    m = master
    w, h = m.size
    box = (int(w * (1 - crop) / 2), int(h * (1 - crop) / 2),
           int(w * (1 + crop) / 2), int(h * (1 + crop) / 2))
    img = m.crop(box).resize((size, size), Image.LANCZOS)
    return img

def ico_frames(master):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [rounded_icon(master, s).convert("RGBA") for s in sizes]
    # Pillow 需 256 承载；直接逐帧保存
    out = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    frames = [rounded_icon(master, s).convert("RGBA") for s in sizes]
    return sizes, frames

def write_ico(path, frames):
    first = frames[-1]
    first.save(path, format="ICO", sizes=[(s, s) for s in sizes_global])

def main():
    variant = "sunset"
    if "--variant" in sys.argv:
        i = sys.argv.index("--variant")
        variant = sys.argv[i + 1]
    pal = PALETTES[variant]
    master = draw_master(pal)

    # 预览
    prev_dir = REPO.parent / ".build-tmp" / "icon_preview"
    prev_dir.mkdir(parents=True, exist_ok=True)
    rounded_icon(master, 512).save(prev_dir / ("%s_512.png" % variant))
    print("preview ->", prev_dir / ("%s_512.png" % variant))

    # web
    (REPO / "static/img").mkdir(parents=True, exist_ok=True)
    rounded_icon(master, 64).save(REPO / "static/img/favicon.png")
    rounded_icon(master, 192).save(REPO / "static/img/icon-192.png")

    # desktop ico
    sizes_local = [16, 24, 32, 48, 64, 128, 256]
    frames = [rounded_icon(master, s).convert("RGBA") for s in sizes_local]
    (REPO.parent / "desktop" if False else REPO / "desktop").mkdir(parents=True, exist_ok=True)
    ico_path = REPO / "desktop" / "app.ico"
    frames[-1].save(ico_path, format="ICO",
                    sizes=[(s, s) for s in sizes_local])
    print("ico ->", ico_path)

    # android res
    densities = [("mdpi", 48, 108), ("hdpi", 72, 162), ("xhdpi", 96, 216),
                 ("xxhdpi", 144, 324), ("xxxhdpi", 192, 432)]
    res = REPO / "android" / "app" / "src" / "main" / "res"
    for dpi, legacy, fgpx in densities:
        d = res / ("mipmap-" + dpi)
        d.mkdir(parents=True, exist_ok=True)
        rounded_icon(master, legacy).save(d / "ic_launcher.png")
        rounded_icon(master, legacy).save(d / "ic_launcher_round.png")
        render_fg(master, fgpx).save(d / "ic_launcher_foreground.png")
    (res / "mipmap-anydpi-v26").mkdir(parents=True, exist_ok=True)
    def adaptive_xml(round_icon):
        n = "ic_launcher_round" if round_icon else "ic_launcher"
        return (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
            "<adaptive-icon xmlns:android=\"http://schemas.android.com/apk/res/android\">\n"
            "    <background android:drawable=\"@color/ic_launcher_background\"/>\n"
            "    <foreground android:drawable=\"@mipmap/ic_launcher_foreground\"/>\n"
            "</adaptive-icon>\n")
    for name, content in (
            ("ic_launcher.xml", adaptive_xml(False)),
            ("ic_launcher_round.xml", adaptive_xml(True))):
        (res / "mipmap-anydpi-v26" / name).write_text(content, encoding="utf-8")
    print("android mipmaps + adaptive xml written")
    print("ALL DONE variant=", variant)

if __name__ == "__main__":
    main()