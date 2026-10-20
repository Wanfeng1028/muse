# -*- coding: utf-8 -*-
"""Đường dẫn dùng chung cho pipeline video Tabcom.

Mọi script trong skill import module này thay vì viết đường dẫn tuyệt đối:

    from tabcom_paths import FIX, LOGO, FONTS, STICKERS, F_BLACK, F_XBOLD, F_BOLD
    from tabcom_paths import src, out_file, assets, work, extra

Asset cố định (font, nền, logo, sticker, OUTRO) nằm ngay trong skill nên chạy được
trên mọi máy, không cần cấu hình gì.

Thư mục làm việc của từng video lấy theo thứ tự:
  1. biến môi trường TABCOM_VIDEO_ROOT
  2. "video_root" trong config.json cạnh SKILL.md
  3. thư mục hiện tại (cwd)

Từng video thì set thêm (env hoặc gán trực tiếp trong script):
  TABCOM_SRC    - file source người nói
  TABCOM_OUT    - file video xuất ra
  TABCOM_ASSETS - thư mục ảnh minh họa riêng của video đó
"""
import json
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# assets nằm trong skill tabcom-video-edit; skill thumbnail dùng ké qua đường dẫn anh em
_a = os.path.join(SKILL_DIR, "assets")
if not os.path.isdir(_a):
    _a = os.path.join(os.path.dirname(SKILL_DIR), "tabcom-video-edit", "assets")
ASSETS = _a

FONTS = os.path.join(ASSETS, "fonts", "ps-display")
FIX = os.path.join(ASSETS, "co-dinh")          # nền, card gradient, OUTRO
LOGO = os.path.join(ASSETS, "logo")            # logo thương hiệu đã tách nền
STICKERS = os.path.join(ASSETS, "stickers")    # sticker, badge, flash

F_BLACK = os.path.join(FONTS, "PS Anton - Regular V1.0.otf")
F_XBOLD = os.path.join(FONTS, "Big Shoulders ExtraBold Viet Hoa.otf")
F_BOLD = os.path.join(FONTS, "PS Big Shoulders Bold Viet Hoa.otf")

BG = os.path.join(FIX, "Nền.png")
BG_SPLIT = os.path.join(FIX, "Nền nhỏ đặt sau người khi đã remove bg.png")
OUTRO = os.path.join(FIX, "OUTRO TABCOM", "OUTRO TABCOM-1.mp4")


def _cfg(key):
    p = os.path.join(SKILL_DIR, "config.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get(key)
    except (OSError, ValueError):
        return None


VIDEO_ROOT = os.environ.get("TABCOM_VIDEO_ROOT") or _cfg("video_root") or os.getcwd()


def _need(env, mota, vd):
    v = os.environ.get(env)
    if not v:
        raise SystemExit(
            f"\nThiếu {mota}. Set biến môi trường {env} rồi chạy lại.\n"
            f"  PowerShell:  $env:{env} = \"{vd}\"\n"
            f"  Bash:        export {env}=\"{vd}\"\n"
            f"Hoặc gán thẳng giá trị vào biến ở đầu script.\n")
    return v


def src():
    """File source người nói (bắt buộc)."""
    return _need("TABCOM_SRC", "file source video", r"D:\Video\26.08.20 - Ten video\source.mp4")


def out_file():
    """File video xuất ra (bắt buộc)."""
    return _need("TABCOM_OUT", "file video xuất ra",
                 r"D:\Video\26.08.20 - Ten video\26.08.20 - Ten video (draft v1).mp4")


def assets(sub=""):
    """Ảnh minh họa riêng của video đang dựng."""
    base = os.environ.get("TABCOM_ASSETS") or os.path.join(VIDEO_ROOT, "video-assets")
    return os.path.join(base, sub) if sub else base


def work(sub=""):
    """Thư mục render tạm (frame, clip, mask). Mặc định: ./build cạnh nơi chạy."""
    base = os.environ.get("TABCOM_WORK") or os.path.join(os.getcwd(), "build")
    p = os.path.join(base, sub) if sub else base
    os.makedirs(p, exist_ok=True)
    return p


def extra(sub=""):
    """Tài nguyên chung tùy chọn (illustration, ảnh generated, screenshot).

    Đặt ở <VIDEO_ROOT>/tai-nguyen/<sub>. Không có cũng dựng được video.
    """
    base = os.path.join(VIDEO_ROOT, "tai-nguyen")
    return os.path.join(base, sub) if sub else base


def check():
    """Kiểm tra asset cố định có đủ không — chạy: python tabcom_paths.py"""
    can = [("Font Anton", F_BLACK), ("Font Big Shoulders XBold", F_XBOLD),
           ("Font Big Shoulders Bold", F_BOLD), ("Nền", BG),
           ("Nền cảnh split", BG_SPLIT), ("OUTRO", OUTRO),
           ("Thư mục logo", LOGO), ("Thư mục sticker", STICKERS)]
    thieu = 0
    for ten, p in can:
        ok = os.path.exists(p)
        thieu += 0 if ok else 1
        print(f"[{'OK ' if ok else 'THIEU'}] {ten}: {p}")
    print(f"\nVIDEO_ROOT = {VIDEO_ROOT}")
    print("Thieu {} muc.".format(thieu) if thieu else "\nDu asset, chay duoc.")
    return thieu


if __name__ == "__main__":
    raise SystemExit(1 if check() else 0)
