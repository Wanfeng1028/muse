"""Parse trang Facebook da luu bang Ctrl+S (.html hoac .mhtml) -> bai dang + binh luan.

Dung: python parse_saved.py "D:\\Downloads\\ten-file.html"
Khong truyen tham so thi tu tim file moi nhat trong D:\\Downloads.
"""
import glob
import html as html_mod
import json
import os
import quopri
import re
import sys

VI = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
VI_SET = set(VI + VI.upper())

# rac giao dien Facebook
NOISE = (
    "Bạn hiện không xem được", "Lỗi này thường do chủ sở hữu", "Đăng nhập", "Tạo tài khoản",
    "Quyền riêng tư", "Điều khoản", "Xem thêm bình luận", "Hiển thị bình luận",
    "Bất kỳ ai cũng có thể", "Trang chủ", "Thông báo", "Bạn bè", "Nhóm này",
    "Viết bình luận", "Thích Phản hồi", "Chia sẻ", "Meta", "Cookie", "Quảng cáo",
    "Người tham gia ẩn danh", "Ảnh của", "Xem bản dịch", "Tất cả bình luận",
    "Phù hợp nhất", "Mới nhất", "Cũ nhất", "Bình luận đã bị tắt",
)


def vi_ratio(s):
    return sum(1 for c in s if c in VI_SET) / len(s) if s else 0


def load(path):
    raw = open(path, "rb").read()
    if path.lower().endswith((".mhtml", ".mht")):
        try:
            raw = quopri.decodestring(raw)
        except Exception:
            pass
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def strip_tags(h):
    h = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(div|p|li|span)>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return html_mod.unescape(h)


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        cands = []
        for pat in ("D:/Downloads/*.html", "D:/Downloads/*.mhtml", "D:/Downloads/*.htm",
                    os.path.expanduser("~/Downloads/*.html")):
            cands += glob.glob(pat)
        if not cands:
            print("Khong tim thay file da luu trong D:\\Downloads")
            sys.exit(1)
        path = max(cands, key=os.path.getmtime)
    print(f"File: {path}\n")

    text = strip_tags(load(path))

    blocks, seen = [], set()
    for line in text.split("\n"):
        s = " ".join(line.split())
        if len(s) < 45 or s in seen:
            continue
        if vi_ratio(s) < 0.035 or any(k in s for k in NOISE):
            continue
        seen.add(s)
        blocks.append(s)

    print(f"TIM THAY {len(blocks)} doan noi dung:\n")
    for i, b in enumerate(blocks, 1):
        print(f"--- [{i}] {len(b)} ky tu ---")
        print(b)
        print()

    json.dump(blocks, open("v2/parsed.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("Da luu -> v2/parsed.json")


if __name__ == "__main__":
    main()
